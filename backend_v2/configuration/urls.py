from django.urls import re_path

from configuration.views import (
    AppsView,
    ClearDemoDataView,
    OnboardingStatusView,
    SiteInfoView,
    TelemetryConfigView,
    TranslationsView,
)

urlpatterns = [
    re_path(r"^desk/apps/?$", AppsView.as_view(), name="desk-apps"),
    re_path(r"^desk/site-info/?$", SiteInfoView.as_view(), name="desk-site-info"),
    re_path(
        r"^desk/telemetry-config/?$",
        TelemetryConfigView.as_view(),
        name="desk-telemetry-config",
    ),
    re_path(r"^demo/clear/?$", ClearDemoDataView.as_view(), name="demo-clear"),
    re_path(r"^translations/?$", TranslationsView.as_view(), name="translations"),
    re_path(
        r"^onboarding/status/?$",
        OnboardingStatusView.as_view(),
        name="onboarding-status",
    ),
]
