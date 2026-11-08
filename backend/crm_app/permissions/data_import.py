"""System Manager-only access to Data Import and Data Import Log.

Version-15 grants every operation on both doctypes to System Manager. This port uses
the same hooks for the routed parent and for ``frappe.client.*``, which can resolve an
unrouted doctype too.

Port only: access is decided by the System Manager role, not the target doctype's
upstream ``import`` right, which this port does not model (``UPSTREAM_BUGS.md`` 68).
"""

from django.db.models import Q

from frappe_core.session import get_current_user

from crm_app.permissions.platform_docs import _is_admin


def data_import_query_conditions(doctype: str, user: str | None = None):
    user = user or get_current_user()
    if _is_admin(user):
        return None
    return Q(pk__in=[])


def data_import_has_permission(doc, ptype: str = "read", user: str | None = None):
    return _is_admin(user or get_current_user())
