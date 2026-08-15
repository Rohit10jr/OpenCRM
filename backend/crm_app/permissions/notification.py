"""Row-level access for CRM Notification.

Ported from ``crm/fcrm/doctype/crm_notification/crm_notification.py:35-58``.

PHASE_2_PERMISSIONS.md section 6: this doctype uses its **own** doctype-local rule, not
the org-hierarchy one. It is far simpler - a notification is visible to its recipient -
but it differs from `org_hierarchy` on one point that is easy to miss:

    ``has_permission`` returns **False** for ``ptype == "create"``.

That is the opposite of the org-hierarchy rule, where an unsaved document always passes.
Copying the lead/deal short-circuit here would let any user mint notifications for
anyone else.
"""

from __future__ import annotations

from django.db.models import Q

from crm_app.permissions.org_hierarchy import (
    ADMINISTRATOR,
    ROLE_SYSTEM_MANAGER,
    _get_roles,
)


def get_permission_query_conditions(doctype: str = "CRM Notification", user: str | None = None):
    """``crm_notification.py:35-42``. ``None`` == unrestricted."""
    from frappe_core.session import get_current_user

    if not user:
        user = get_current_user()

    if user == ADMINISTRATOR or ROLE_SYSTEM_MANAGER in _get_roles(user):
        return None

    return Q(to_user=user)


def has_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
    """``crm_notification.py:45-58``."""
    from frappe_core.session import get_current_user

    if not user:
        user = get_current_user()

    if user == ADMINISTRATOR or ROLE_SYSTEM_MANAGER in _get_roles(user):
        return True

    # Deliberately False, unlike org_hierarchy - see the module docstring.
    if ptype == "create":
        return False

    # DELIBERATE DIVERGENCE, in unreachable code, in the safe direction.
    #
    # Upstream returns True here (crm_notification.py:55-56), which contradicts its own
    # list rule: get_permission_query_conditions emits `to_user = <user>`, and a blank
    # to_user never matches that - so upstream hides such a row from every list while
    # letting anyone read it directly.
    #
    # Upstream's `reqd: 1` is document-level validation, not a column constraint, so its
    # branch is not quite dead. Ours is a plain ForeignKey with no null=True - NOT NULL
    # at the database level - so no *saved* row can reach here. It is reachable on an
    # unsaved instance, where returning True would grant a read.
    #
    # Denying makes the object rule agree with the list rule. Nothing observable changes
    # against upstream (no saved row can take this path), the asymmetry stops being
    # something later readers have to re-derive as safe, and the failure direction is
    # deny rather than grant.
    if not doc.to_user_id:
        return False

    return doc.to_user_id == user
