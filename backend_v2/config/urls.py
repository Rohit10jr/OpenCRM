from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.defaults import page_not_found

from core.exceptions import build_error_body

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
]


def handler404(request, exception):
    if request.path.startswith("/admin/"):
        return page_not_found(request, exception)
    return JsonResponse(
        build_error_body(
            "DoesNotExistError",
            ["Not found."],
            "Not Found",
        ),
        status=404,
    )
