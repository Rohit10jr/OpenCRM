from django.contrib import admin
from django.urls import include, path, re_path
from django.views.defaults import page_not_found

from core.views import frappe_not_found

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("core.urls")),
    path("api/v1/", include("accounts.urls")),
    path("api/v1/", include("configuration.urls")),
    path("api/v1/", include("contacts.urls")),
    path("api/v1/", include("sla.urls")),
    path("api/v1/", include("sales.urls")),
    path("api/v1/", include("activities.urls")),
    path("api/v1/", include("notifications.urls")),
    path("api/v1/", include("dashboard.urls")),
    path("api/v1/", include("integrations.urls")),
    re_path(r"^.*$", frappe_not_found),
]


def handler404(request, exception):
    if request.path.startswith("/admin/"):
        return page_not_found(request, exception)
    return frappe_not_found(request)
