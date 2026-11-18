from django.urls import re_path

from configuration.views import (
    AppsView,
    BootView,
    ClearDemoDataView,
    CountryViewSet,
    CRMFieldsLayoutViewSet,
    CRMFormScriptViewSet,
    CRMGlobalSettingsViewSet,
    CRMViewSettingsViewSet,
    CurrencyViewSet,
    DocTypeMetaView,
    EmailAccountViewSet,
    FieldsView,
    FilterableFieldsView,
    GroupByFieldsView,
    ExchangeRateView,
    FCRMSettingsViewSet,
    LanguageViewSet,
    OnboardingStatusView,
    QuickFiltersView,
    SiteInfoView,
    SortOptionsView,
    SystemSettingsViewSet,
    TelemetryConfigView,
    TranslationsView,
    UpdateQuickFiltersView,
    UserSettingsView,
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
    re_path(r"^user-settings/?$", UserSettingsView.as_view(), name="user-settings"),
    re_path(r"^meta/doctype/?$", DocTypeMetaView.as_view(), name="meta-doctype"),
    re_path(r"^meta/fields/?$", FieldsView.as_view(), name="meta-fields"),
    re_path(r"^meta/sort-options/?$", SortOptionsView.as_view(), name="meta-sort-options"),
    re_path(
        r"^meta/filterable-fields/?$",
        FilterableFieldsView.as_view(),
        name="meta-filterable-fields",
    ),
    re_path(
        r"^meta/group-by-fields/?$",
        GroupByFieldsView.as_view(),
        name="meta-group-by-fields",
    ),
    re_path(r"^meta/quick-filters/?$", QuickFiltersView.as_view(), name="meta-quick-filters"),
    re_path(
        r"^meta/quick-filters/update/?$",
        UpdateQuickFiltersView.as_view(),
        name="meta-quick-filters-update",
    ),
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
router.register("email-accounts", EmailAccountViewSet, basename="email-account")
router.register("languages", LanguageViewSet, basename="language")
router.register("fields-layouts", CRMFieldsLayoutViewSet, basename="fields-layout")
router.register("form-scripts", CRMFormScriptViewSet, basename="form-script")
router.register("global-settings", CRMGlobalSettingsViewSet, basename="global-setting")
router.register("view-settings", CRMViewSettingsViewSet, basename="view-setting")
urlpatterns += router.urls
