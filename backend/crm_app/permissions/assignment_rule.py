"""System Manager-only access to Assignment Rule.

Version-15 ``assignment_rule.json`` grants every operation, reading included, only to
System Manager.  The CRM settings menu is also shown to Sales Manager; upstream refuses
that user when the screen reaches the doctype (``UPSTREAM_BUGS.md`` 53), and so do we.
"""

from django.db.models import Q

from frappe_core.session import get_current_user

from crm_app.permissions.platform_docs import _is_admin


def assignment_rule_query_conditions(doctype: str, user: str | None = None):
    user = user or get_current_user()
    if _is_admin(user):
        return None
    return Q(pk__in=[])


def assignment_rule_has_permission(doc, ptype: str = "read", user: str | None = None):
    return _is_admin(user or get_current_user())
