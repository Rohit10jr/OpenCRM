"""URL map for the Frappe wire protocol.

``re_path`` rather than ``path`` because DocType names contain spaces ("CRM Lead")
and method paths contain dots and slashes ("crm.api.doc.get_data", "token/refresh").
"""

from django.urls import re_path

from frappe_core.method_views import MethodView
from frappe_core.views import ResourceDetailView, ResourceListView

# A doctype is anything up to the next slash; a document name likewise. Both arrive
# percent-encoded and Django has already decoded them by this point.
_DOCTYPE = r"(?P<doctype>[^/]+)"
_NAME = r"(?P<name>[^/]+)"
_METHOD = r"(?P<method_path>[\w./-]+)"

urlpatterns = [
    re_path(rf"^resource/{_DOCTYPE}/{_NAME}/?$", ResourceDetailView.as_view(), name="resource-detail"),
    re_path(rf"^resource/{_DOCTYPE}/?$", ResourceListView.as_view(), name="resource-list"),
    re_path(rf"^method/{_METHOD}/?$", MethodView.as_view(), name="method-call"),
]
