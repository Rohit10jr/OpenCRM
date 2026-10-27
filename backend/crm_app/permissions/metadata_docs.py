"""Row-level rules for metadata and other manager-maintained CRM doctypes.

The first rules were added in phase 4, after a review found the metadata doctypes
reachable through the generic ``/api/resource/`` route. They were "protected" only by
their own endpoints — which is no protection at all, because the generic route does not
go through those endpoints. The final route-surface review later added SLA and Tag here
because they use the same shared CRM-manager role helper.

`AS_BUILT.md` §3 says it plainly: *"An endpoint reading through `frappe_core.query`
cannot bypass row-level security."* The converse is what bit here — a doctype with **no
hook** is world-readable and world-writable to any authenticated user, and these were
registered as ordinary routable doctypes.

* **CRM View Settings** holds *per-user* saved views. Without a rule, one user could
  list, read and edit everybody else's — failing `PHASE_4_METADATA.md` §4's last
  criterion through a route its own endpoint never sees.
* **CRM Form Script** holds user-authored **JavaScript that every client executes**.
  Without a rule, a Sales User could write a script that runs in every colleague's
  browser. `PHASE_4_METADATA.md` §2 calls this out as an XSS surface and says to gate
  write access to admins; `save_fields_layout`'s sibling endpoint was gated, but the
  generic route was not.
"""

from __future__ import annotations

from django.db.models import Q

from frappe_core.session import get_current_user

ADMIN_ROLES = {"System Manager", "Sales Manager"}


def _roles(user: str) -> set[str]:
    """Memoised per request, the way ``org_hierarchy._get_roles`` is.

    Every rule below is a role test, so an unmemoised lookup meant one query *per row* on
    any batch path — the N+1 C9 is about. The rules themselves are row-independent, so
    with the roles cached a whole batch costs one query.
    """
    from frappe_core.session import get_request_cache

    cache = get_request_cache()
    key = ("metadata_docs.roles", user)
    if key not in cache:
        from frappe_platform.models import User

        obj = User._default_manager.filter(pk=user).first()
        cache[key] = obj.get_roles() if obj else set()
    return cache[key]


def _is_admin(user: str) -> bool:
    return user == "Administrator" or "System Manager" in _roles(user)


# ---------------------------------------------------------------------------
# CRM View Settings
# ---------------------------------------------------------------------------


def view_settings_query_conditions(doctype: str, user: str | None = None):
    """Own views plus public ones. Mirrors ``crm/api/views.py:get_views``."""
    user = user or get_current_user()
    if _is_admin(user):
        return None
    return Q(user=user) | Q(user__isnull=True) | Q(public=True)


def view_settings_has_permission(doc, ptype: str = "read", user: str | None = None):
    """Read follows the list rule; write follows ``check_permission``.

    The two are deliberately different: a Sales Manager may **edit** a public view
    (``crm_view_settings.py:150-160``) but that is a stronger right than reading one.
    """
    user = user or get_current_user()
    if _is_admin(user):
        return True

    is_own = doc.user_id == user
    is_public = bool(doc.public) or doc.user_id is None

    if ptype in ("read", "select"):
        return is_own or is_public
    if ptype == "create":
        return True
    # write / delete
    if is_own:
        return True
    if doc.public and "Sales Manager" in _roles(user):
        return True
    return False


# ---------------------------------------------------------------------------
# CRM Form Script
# ---------------------------------------------------------------------------


def form_script_query_conditions(doctype: str, user: str | None = None):
    """Readable by everyone — ``get_data`` serves the script to every client."""
    return None


def form_script_has_permission(doc, ptype: str = "read", user: str | None = None):
    """Read for all, **write for admins only**.

    This is the XSS boundary. Anyone may receive a form script (they have to — the
    frontend runs it); almost nobody may author one.
    """
    user = user or get_current_user()
    if ptype in ("read", "select"):
        return True
    return user == "Administrator" or bool(_roles(user) & ADMIN_ROLES)


# ---------------------------------------------------------------------------
# CRM Fields Layout — same reasoning as the form script, minus the XSS
# ---------------------------------------------------------------------------


def fields_layout_query_conditions(doctype: str, user: str | None = None):
    """Site-wide configuration; everyone reads it."""
    return None


def fields_layout_has_permission(doc, ptype: str = "read", user: str | None = None):
    """Read for all, write for admins — matching ``save_fields_layout``'s own guard,
    so the generic route cannot be used to sidestep it."""
    user = user or get_current_user()
    if ptype in ("read", "select"):
        return True
    return user == "Administrator" or bool(_roles(user) & ADMIN_ROLES)


# ---------------------------------------------------------------------------
# CRM Service Level Agreement — managers only, including reads
# ---------------------------------------------------------------------------


def service_level_agreement_query_conditions(doctype: str, user: str | None = None):
    """Managers see every policy; everyone else gets an empty list.

    Upstream's role table grants every operation to System Manager and Sales Manager,
    and has no Sales User row (``crm_service_level_agreement.json:143-167``). The SLA
    engine reads policies through the model manager, so this route rule does not stop a
    Sales User's lead or deal save from selecting and applying a policy.
    """
    user = user or get_current_user()
    if user == "Administrator" or _roles(user) & ADMIN_ROLES:
        return None
    return Q(pk__in=[])


def service_level_agreement_has_permission(
    doc, ptype: str = "read", user: str | None = None
):
    user = user or get_current_user()
    return user == "Administrator" or bool(_roles(user) & ADMIN_ROLES)


# ---------------------------------------------------------------------------
# Tag — everyone reads/writes/creates; System Manager alone deletes
# ---------------------------------------------------------------------------


def tag_query_conditions(doctype: str, user: str | None = None):
    """Tag names are shared reference data, so every authenticated user sees them."""
    return None


def tag_has_permission(doc, ptype: str = "read", user: str | None = None):
    """Reproduce version-15's ``Tag`` role table.

    The ``All`` row grants read, write and create. Only the System Manager row grants
    delete. Adding or removing a tag from a document updates that document's
    ``_user_tags`` cache; removing it does not delete the shared ``Tag`` row.
    """
    if ptype != "delete":
        return True
    return _is_admin(user or get_current_user())
