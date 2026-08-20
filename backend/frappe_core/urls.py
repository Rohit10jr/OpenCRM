"""URL map for the Frappe wire protocol.

``re_path`` rather than ``path`` because DocType names contain spaces ("CRM Lead")
and method paths contain dots and slashes ("crm.api.doc.get_data", "token/refresh").
"""

from django.urls import re_path

from frappe_core.method_views import MethodView
from frappe_core.views import ResourceDetailView, ResourceListView

# A doctype is anything up to the next slash. A document name is a *path* - it may
# itself contain slashes, because Frappe permits them: ``validate_name`` rejects only
# ``<`` and ``>`` (version-15 naming.py:498-501), so an organization literally called
# "R/GA" is a legal record. Upstream routes these with a path converter,
# ``Rule("/resource/<doctype>/<path:name>/")`` (frappe/api/v1.py:148-151); ``[^/]+``
# here would make such records unreachable. Percent-encoding does not save us either:
# WSGI decodes ``%2F`` to ``/`` in PATH_INFO before Django resolves the URL.
_DOCTYPE = r"(?P<doctype>[^/]+)"
_NAME = r"(?P<name>.+?)"
_METHOD = r"(?P<method_path>[\w./-]+)"

urlpatterns = [
    re_path(rf"^resource/{_DOCTYPE}/{_NAME}/?$", ResourceDetailView.as_view(), name="resource-detail"),
    re_path(rf"^resource/{_DOCTYPE}/?$", ResourceListView.as_view(), name="resource-list"),
    re_path(rf"^method/{_METHOD}/?$", MethodView.as_view(), name="method-call"),
]
