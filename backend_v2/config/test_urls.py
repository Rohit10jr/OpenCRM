from django.urls import include, path


urlpatterns = [
    path("api/v1/", include("tests_support.urls")),
    path("", include("config.urls")),
]
