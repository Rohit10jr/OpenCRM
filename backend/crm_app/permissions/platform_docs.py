"""Row-level rules for platform doctypes the generic route left open.

Phase 1 registered `User` as a routable doctype, which published
``/api/resource/User`` to every authenticated caller with no rule behind it. Observed
before this module existed, driving the real route as a plain Sales User:

* ``PUT /api/resource/User/<someone-else>`` renamed another user, and set
  ``enabled: false`` on them - locking a colleague out of the product;
* ``GET /api/resource/User`` listed every account.

The self-escalation half of that finding (``groups``, ``is_superuser``) is closed by
``User.SENSITIVE_FIELDS``, not here - **a self-only rule cannot close it**, because
setting your own roles on your own document is precisely what "self-only" allows. The two
fixes are complementary and neither is sufficient alone.

Upstream comparison (`frappe/core/doctype/user/user.json`): only **System Manager** holds
read/write on `User`; the `Desk User` role gets `select` alone, which is the permission to
appear in a link dropdown rather than to read. Its row rule
(`user.py:1164`) does one thing - hide the standard users from everyone but Administrator
- which is ported verbatim below.

We are more permissive than upstream on **reads** and stricter than the status quo on
**writes**, both deliberately - see :func:`user_query_conditions` for why narrowing reads
broke kanban and was reverted.

Writes are the half that mattered. The Vue profile screens edit the session user's own
document through this route (`ProfileSettings.vue`, `PreferencesSettings.vue`,
`UserEmailSettings.vue` - all three call
``createDocumentResource({doctype: 'User', name: sessionUser})``, never another user's
name), so self-write is required and write to anyone else is not.
"""

from __future__ import annotations

from django.db.models import Q

from frappe_core.session import get_current_user

#: Frappe's built-ins. Non-Administrators may not see or touch them
#: (`frappe/core/doctype/user/user.py:1173`), which keeps `Administrator` out of every
#: list a normal user can produce.
STANDARD_USERS = ("Administrator", "Guest")

#: Who may administer *users*. System Manager alone, matching upstream - `update_user_role`
#: lets a Sales Manager promote someone to Sales User, but the User doctype itself is
#: System Manager's (`user.json` permissions).
ADMIN_ROLES = {"System Manager"}

#: Who may administer *email accounts*. Wider than :data:`ADMIN_ROLES`, and deliberately:
#: it matches `crm_app.api.settings.create_email_account`, gated to this pair by phase 3's
#: decision D5. Narrowing it to System Manager would leave a Sales Manager able to create
#: an account but not correct a typo in it.
MAIL_ADMIN_ROLES = {"System Manager", "Sales Manager"}


def _roles(user: str) -> set[str]:
    """Memoised per request, the way `metadata_docs._roles` is - a role test per row is
    an N+1 on any batch path, and these rules are row-independent."""
    from frappe_core.session import get_request_cache

    cache = get_request_cache()
    key = ("platform_docs.roles", user)
    if key not in cache:
        from frappe_platform.models import User

        found = User._default_manager.filter(pk=user).first()
        cache[key] = found.get_roles() if found is not None else set()
    return cache[key]


def _is_admin(user: str) -> bool:
    return user == "Administrator" or bool(_roles(user) & ADMIN_ROLES)


def user_query_conditions(doctype: str, user: str | None = None):
    """Everyone but the built-ins. **Reads are deliberately not narrowed to self.**

    A first attempt restricted reads to your own row, which is closer to upstream's
    doctype permission - and it broke kanban. A board grouped by a Link-to-User builds one
    column per user, and upstream builds that list with ``frappe.get_all`` (
    `crm_view_settings.py:187`), which **ignores permissions by design**. Narrowing reads
    left a Sales User looking at a board with exactly one column: their own.

    Colleague rows are directory data in a single-tenant CRM, and
    ``crm.api.session.get_users`` already serves the same people to any authenticated
    caller. What actually needed protecting is off the wire entirely
    (``User.SENSITIVE_FIELDS``) or unwritable (``User.READONLY_FIELDS``); what needed
    narrowing is *writes*, below.

    One honest divergence: this exposes more per user than upstream does. `get_users`
    returns name, email, full name, image and user type; this route also carries
    ``mobile_no``, ``phone``, ``language``, ``time_zone`` and ``email_signature``.
    Tightening that later means auditing every path that enumerates users through the
    permission layer - link dropdowns and kanban columns among them - which is the audit
    that produced this comment.
    """
    user = user or get_current_user()
    if user == "Administrator":
        return None
    return ~Q(pk__in=STANDARD_USERS)


def user_has_permission(doc, ptype: str = "read", user: str | None = None):
    """Read anyone but the built-ins; write only yourself.

    ``create`` is admin-only: accounts are made by invitation
    (``crm_app.api.misc.invite_by_email``, restricted to managers and refusing to invite a
    role above the inviter's own). Nothing legitimate posts to ``/api/resource/User``.

    ``delete`` is admin-only too, and deliberately not self-service: deleting your own
    account would cascade to every document that references you as owner.
    """
    user = user or get_current_user()
    if user == "Administrator":
        return True

    if ptype == "create":
        return _is_admin(user)

    # An unsaved document has no identity to compare against; `create` is handled above.
    name = getattr(doc, "pk", None)
    if name is None:
        return _is_admin(user)

    if str(name) in STANDARD_USERS:
        return False

    if _is_admin(user):
        return True

    if ptype == "read":
        return True

    # write / delete / anything else: your own row, and `delete` is excluded because
    # removing your own account orphans everything that references you.
    return ptype == "write" and str(name) == str(user)


# ---------------------------------------------------------------------------
# Email Account
# ---------------------------------------------------------------------------
#
# Upstream gives `Email Account` to **System Manager** alone
# (`email_account.json` permissions). `Inbox User` also holds read there, but Frappe CRM
# never grants that role - zero references in the repo - so in practice nobody below
# System Manager sees an email account at all.
#
# This port had no rule, so any authenticated caller could rewrite or delete one. The
# damage is not credential theft (the password is not served): it is **redirecting the
# mail**. Point `smtp_server` at a host you control and every message the system sends
# passes through it, invitation links included. Observed at 200, as was DELETE.
#
# One rule covers every door. `/api/resource/` and the `frappe.client.*` endpoints -
# `set_value`, `delete`, `rename_doc` - all resolve through `_get_checked`, so un-routing
# would have fixed neither.


def email_account_query_conditions(doctype: str, user: str | None = None):
    """No row restriction. **Reads are open by decision, not by omission.**

    Upstream shows a non-manager nothing here - which means its own
    `UserEmailSettings.vue` account picker ("which address do I send from?") comes back
    **empty for every non-manager**, since that screen sits under Profile and Profile
    carries no role condition. The feature is quietly broken upstream.

    We keep the frontend contract working instead. The cost is that ordinary users can
    read `smtp_server`, `login_id`, `domain` and `api_key`, which upstream would not show
    them - information disclosure rather than takeover, and narrowed by
    ``EmailAccount.RESTRICTED_FIELDS``.
    """
    return None


def email_account_has_permission(doc, ptype: str = "read", user: str | None = None):
    """Read for anyone; create, write and delete for managers.

    The role pair matches ``crm_app.api.settings.create_email_account``, gated that way by
    phase 3's decision D5. Without this rule the two disagreed: you could not *create* an
    account without being a manager, but you could edit or delete one as anybody.
    """
    user = user or get_current_user()
    if user == "Administrator":
        return True
    if ptype == "read":
        return True
    return bool(_roles(user) & MAIL_ADMIN_ROLES)
