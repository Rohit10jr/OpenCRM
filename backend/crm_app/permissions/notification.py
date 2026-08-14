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

    if not doc.to_user_id:
        return True

    return doc.to_user_id == user
