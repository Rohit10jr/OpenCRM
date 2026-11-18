from django.urls import re_path

from configuration.views import (
    AppsView,
    BootView,
    ClearDemoDataView,
    CountryViewSet,
    CurrencyViewSet,
    ExchangeRateView,
    FCRMSettingsViewSet,
    LanguageViewSet,
    OnboardingStatusView,
    SiteInfoView,
    SystemSettingsViewSet,
    TelemetryConfigView,
    TranslationsView,
)
from core.routers import DocumentRouter, SingletonRouter

urlpatterns = [
    re_path(r"^boot/?$", BootView.as_view(), name="boot"),
    re_path(r"^desk/apps/?$", AppsView.as_view(), name="desk-apps"),
    re_path(r"^desk/site-info/?$", SiteInfoView.as_view(), name="desk-site-info"),
    re_path(
        r"^desk/telemetry-config/?$",
        TelemetryConfigView.as_view(),
        name="desk-telemetry-config",
    ),
    re_path(r"^demo/clear/?$", ClearDemoDataView.as_view(), name="demo-clear"),
    re_path(r"^translations/?$", TranslationsView.as_view(), name="translations"),
    re_path(r"^exchange-rate/?$", ExchangeRateView.as_view(), name="exchange-rate"),
    re_path(
        r"^onboarding/status/?$",
        OnboardingStatusView.as_view(),
        name="onboarding-status",
    ),
]

singleton_router = SingletonRouter()
singleton_router.register(
    "system-settings", SystemSettingsViewSet, basename="system-settings"
)
singleton_router.register("crm-settings", FCRMSettingsViewSet, basename="crm-settings")
urlpatterns += singleton_router.urls

router = DocumentRouter()
router.register("countries", CountryViewSet, basename="country")
router.register("currencies", CurrencyViewSet, basename="currency")
router.register("languages", LanguageViewSet, basename="language")
urlpatterns += router.urls
