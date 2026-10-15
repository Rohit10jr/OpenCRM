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


# ---------------------------------------------------------------------------
# Email Template
# ---------------------------------------------------------------------------
#
# Upstream's `email_template.json` (FINDINGS.md 87, the role passes): `Desk User` reads,
# and `Desk User` is the role every System User holds (`frappe/permissions.py:36`), so
# every CRM user; `System Manager` alone creates, writes and deletes. CRM adds nothing to
# that table, and its Templates page is shown to every role, so a Sales User or Sales
# Manager sees the list, picks a template in the mail editor, and is refused on New, on
# an edit and on delete. The port had no rule, so any CRM user rewrote the wording of
# mail sent in the company's name.


def email_template_query_conditions(doctype: str, user: str | None = None):
    """Everyone reads every template: the list feeds the mail editor's picker."""
    return None


def email_template_has_permission(doc, ptype: str = "read", user: str | None = None):
    """Read for everyone; create, write and delete for System Manager."""
    user = user or get_current_user()
    if ptype in ("read", "select"):
        return True
    return _is_admin(user)


# ---------------------------------------------------------------------------
# Integration settings singles - A4
# ---------------------------------------------------------------------------
#
# `CRM Twilio Settings` and `CRM Exotel Settings` hold the credentials for the telephony
# integrations. Upstream grants both to **System Manager and Sales Manager only**, at
# every permlevel; no Sales User sees them at all. This port had no rule, so any
# authenticated caller could read *and rewrite* them - including pointing the integration
# at an account they control.
#
# Reads are closed here, unlike `Email Account`, and the difference is the nature of the
# screen rather than an inconsistency:
#
# * the Email Account *list* feeds a user-facing feature - "which address do I send
#   from?" - on a Profile page meant for everyone, so it has to be readable;
# * Telephony is an **administration screen**. Its entire purpose is manager-only.
#
# Opening credentials so that an admin screen renders for non-admins would be backwards.
# Upstream's own Settings.vue omits the `isManager()` condition on the Telephony entry
# that eleven of its siblings carry, so a Sales User can reach a screen whose data they
# cannot read - it errors. That is upstream bug #19, a cosmetic UI defect, and we
# reproduce the behaviour rather than weakening the permission to paper over it.


def telephony_settings_query_conditions(doctype: str, user: str | None = None):
    """Managers only. Deny-all for everyone else.

    ``None`` here would mean "no restriction", so the *list* route would hand back the
    row even though :func:`telephony_settings_has_permission` refuses the document. Both
    hooks have to agree; a rule that guards one route and not the other is the shape of
    every finding in this phase.
    """
    user = user or get_current_user()
    if user == "Administrator" or _roles(user) & MAIL_ADMIN_ROLES:
        return None
    return Q(pk__in=[])


def telephony_settings_has_permission(doc, ptype: str = "read", user: str | None = None):
    user = user or get_current_user()
    if user == "Administrator":
        return True
    return bool(_roles(user) & MAIL_ADMIN_ROLES)


# ---------------------------------------------------------------------------
# Lead sync (phase 7)
# ---------------------------------------------------------------------------
#
# Three doctypes, one rule: managers only, reads closed.
#
# `Lead Sync Source` and `Facebook Page` hold **access tokens** — a Facebook page token
# reads every lead the page has ever collected and can post as the page. `Failed Lead Sync
# Log` holds `lead_data`, which is the raw Graph payload: a real person's name, email and
# phone number, for a lead that never made it into the CRM and therefore has no row rule of
# its own protecting it.
#
# That last one is the reason this is not "just settings". Everything else in this group is
# configuration; the failure log is personal data about members of the public, sitting in a
# table nobody would think to look at.
#
# Same shape as the telephony settings above, and for the same reason: these back an
# administration screen, so closing reads costs nothing a user needs.


def lead_sync_query_conditions(doctype: str, user: str | None = None):
    user = user or get_current_user()
    if user == "Administrator" or _roles(user) & MAIL_ADMIN_ROLES:
        return None
    return Q(pk__in=[])


def lead_sync_has_permission(doc, ptype: str = "read", user: str | None = None):
    user = user or get_current_user()
    if user == "Administrator":
        return True
    return bool(_roles(user) & MAIL_ADMIN_ROLES)


# `FCRM Settings` is different, and upstream says so: **Sales User holds read** on it.
# It has to - `stores/settings.js` loads it as a document resource and the activity
# timeline reads `crm_timeline_timestamp_format` from it on every screen in the product.
#
# Which is exactly why `access_key` has no business being on it in the clear. See
# `FCRMSettings.RESTRICTED_FIELDS`.


def app_settings_query_conditions(doctype: str, user: str | None = None):
    """Everyone reads it; the timeline needs it on every screen."""
    return None


def app_settings_has_permission(doc, ptype: str = "read", user: str | None = None):
    """Read for all, write for managers - upstream's own split
    (``fcrm_settings.json``: Sales User ``read: 1``, ``write: 0``)."""
    user = user or get_current_user()
    if user == "Administrator":
        return True
    if ptype == "read":
        return True
    return bool(_roles(user) & MAIL_ADMIN_ROLES)


# ---------------------------------------------------------------------------
# CRM Sales Hierarchy
# ---------------------------------------------------------------------------
#
# **The org tree is an input to the permission engine, so writing to it is writing your
# own permissions.** `org_hierarchy` resolves "records owned by anyone in my subtree"
# against this table on every Lead and Deal read.
#
# With no rule, a Sales User could add themselves as a node and reparent a colleague
# underneath - observed end to end:
#
#     GET  /api/resource/CRM Deal/<bob's deal>      -> 403
#     POST /api/resource/CRM Sales Hierarchy        -> 201   (alice adds herself)
#     PUT  .../CRM Sales Hierarchy/<bob's node>     -> 200   (reports_to = alice)
#     GET  /api/resource/CRM Deal/<bob's deal>      -> 200
#
# One call takes a whole subtree, not one record, and the nested-set maintenance rebuilds
# `lft`/`rgt` for the attacker on the way through. It reads as an ordinary org-chart edit.
#
# Only `FCRM Settings.enable_sales_hierarchy` being off by default kept it from being
# live; any organisation using the feature was exposed. That flag became manager-writable
# in A4, so it could not itself be flipped by the caller.
#
# Upstream: System Manager creates, writes and deletes; **Sales Manager and Sales User
# read only** (`crm_sales_hierarchy.json`). Reproduced exactly - and note the tighter role
# set than `MAIL_ADMIN_ROLES`: a Sales Manager may not restructure the org chart, which is
# right, since the chart is what decides what a Sales Manager can see.

HIERARCHY_ADMIN_ROLES = {"System Manager"}


def sales_hierarchy_query_conditions(doctype: str, user: str | None = None):
    """Everyone reads the chart - upstream grants Sales User ``read: 1``, and the
    Hierarchy settings screen renders it."""
    return None


def sales_hierarchy_has_permission(doc, ptype: str = "read", user: str | None = None):
    user = user or get_current_user()
    if user == "Administrator":
        return True
    if ptype == "read":
        return True
    return bool(_roles(user) & HIERARCHY_ADMIN_ROLES)


# ---------------------------------------------------------------------------
# CRM Invitation
# ---------------------------------------------------------------------------
#
# An invitation row holds the **role being granted** and a **`key` that redeems it**.
# Upstream's `accept_invitation` (`crm/api/__init__.py:83`) looks the invitation up by key
# alone, with no authentication and no binding to the caller, then logs in as -- or sends
# a password-reset link for -- `invitation.email`.
#
# Upstream also grants **Sales User `read: 1`** on this doctype, and `key` is a plain
# `Data` field with no permlevel. Whoever can read the row can redeem it. A Sales User who
# reads a pending System Manager invitation becomes that System Manager. Recorded as
# upstream bug #21.
#
# Two layers here, because either alone leaves something standing:
#
# * reads are **managers only** -- stricter than upstream, and it is exactly upstream's
#   Sales User read that makes the escalation reachable;
# * `key` is in `SENSITIVE_FIELDS`, so it never reaches the wire even for a manager. It is
#   a bearer token; the only thing that ever needs it is the invitation email.
#
# The frontend is unaffected: `InviteUserPage.vue` is the sole consumer, it is
# `isManager()`-gated, and it reads `name`, `email` and `role` -- never `key`.
#
# **This matters more than it looks today.** `crm.api.accept_invitation` is not
# implemented in this port, so a forged or stolen invitation cannot currently be redeemed.
# The day that endpoint lands, this rule is the only thing standing between any user and
# an admin account. See specs/SECURITY_MODEL.md.


def invitation_query_conditions(doctype: str, user: str | None = None):
    """Managers only. Deny-all otherwise - `None` would leak the row through the list
    route while the document route refused it."""
    user = user or get_current_user()
    if user == "Administrator" or _roles(user) & MAIL_ADMIN_ROLES:
        return None
    return Q(pk__in=[])


def invitation_has_permission(doc, ptype: str = "read", user: str | None = None):
    user = user or get_current_user()
    if user == "Administrator":
        return True
    return bool(_roles(user) & MAIL_ADMIN_ROLES)


# ---------------------------------------------------------------------------
# Address and Country (FINDINGS.md 45)
# ---------------------------------------------------------------------------
#
# Two framework doctypes the organization and contact screens reach through the
# `address` Link. Upstream's role tables, reproduced:
#
# * `address.json`: Sales User, and `All`, read, write and create; only System Manager
#   deletes. An address is shared data with no secret on it, and the dialog that
#   creates one is open to every role.
# * `country.json`: `All` reads; System Manager writes. Reference data seeded once
#   from the framework's list.


def address_query_conditions(doctype: str, user: str | None = None):
    """No row restriction, as upstream: every role reads every address."""
    return None


def address_has_permission(doc, ptype: str = "read", user: str | None = None):
    """Read, write and create for everyone; delete for System Manager only."""
    user = user or get_current_user()
    if ptype != "delete":
        return True
    return _is_admin(user)


def contact_query_conditions(doctype: str, user: str | None = None):
    """Everyone reads every contact: the Sales User and Sales Manager rows of
    ``contact.json`` carry ``read`` with no owner condition."""
    return None


def contact_has_permission(doc, ptype: str = "read", user: str | None = None):
    """``contact.json``'s role table (FINDINGS.md 86). Sales User and Sales Manager hold
    read, write and create on every contact and **no delete**; the ``All`` row holds
    delete with ``if_owner``, so a contact is deleted by the user who created it or by a
    System Manager, and by nobody else. The hosted demo refuses a manager the same way.
    """
    user = user or get_current_user()
    if ptype != "delete":
        return True
    if _is_admin(user):
        return True
    owner = getattr(doc, "owner_id", None) or getattr(doc, "owner", None)
    return bool(owner) and str(owner) == str(user)


def country_query_conditions(doctype: str, user: str | None = None):
    """Everyone reads the list; it is what the Country picker shows."""
    return None


def country_has_permission(doc, ptype: str = "read", user: str | None = None):
    """Read for everyone; write, create and delete for System Manager, as
    ``country.json`` grants."""
    user = user or get_current_user()
    if ptype == "read":
        return True
    return _is_admin(user)


def reference_data_query_conditions(doctype: str, user: str | None = None):
    """Everyone reads the list. For the small lookup doctypes a picker shows -
    ``Salutation`` and ``Gender`` (FINDINGS.md 66)."""
    return None


def reference_data_has_permission(doc, ptype: str = "read", user: str | None = None):
    """Read for everyone; write, create and delete for System Manager, as
    ``salutation.json`` and ``gender.json`` grant."""
    user = user or get_current_user()
    if ptype == "read":
        return True
    return _is_admin(user)


def language_query_conditions(doctype: str, user: str | None = None):
    """Everyone reads the list; it is what the Language picker shows."""
    return None


def language_has_permission(doc, ptype: str = "read", user: str | None = None):
    """Read for everyone; write, create and delete for System Manager, as
    ``language.json`` grants (FINDINGS.md 58)."""
    user = user or get_current_user()
    if ptype == "read":
        return True
    return _is_admin(user)


def currency_query_conditions(doctype: str, user: str | None = None):
    """Everyone reads the list; it is what the currency pickers show."""
    return None


def currency_has_permission(doc, ptype: str = "read", user: str | None = None):
    """Read for everyone; write, create and delete for System Manager (FINDINGS.md 63).

    ``currency.json`` gives System Manager everything, read to Sales User and three
    ERPNext roles, and ``select`` to Desk User, the role every System User holds
    (``frappe/permissions.py:36``). ``select`` is what a Link search needs, and a deal's
    Currency field shows its value to whoever opens the deal, so reading is everyone's,
    a Sales Manager included. Writing is System Manager's alone.
    """
    user = user or get_current_user()
    if ptype == "read":
        return True
    return _is_admin(user)


def system_settings_query_conditions(doctype: str, user: str | None = None):
    """Nothing to list for anyone but a System Manager."""
    user = user or get_current_user()
    return None if _is_admin(user) else Q(pk__in=[])


def system_settings_has_permission(doc, ptype: str = "read", user: str | None = None):
    """System Manager for everything, reading included, as ``system_settings.json``
    grants (FINDINGS.md 64).

    Nobody else needs the row: the boot call reads it server-side for every user. A
    Sales Manager is offered the Defaults page all the same and gets a blank panel, as
    on upstream (``UPSTREAM_BUGS.md`` 50).
    """
    return _is_admin(user or get_current_user())
