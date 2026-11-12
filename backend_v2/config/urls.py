from django.contrib import admin
from django.urls import include, path

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
