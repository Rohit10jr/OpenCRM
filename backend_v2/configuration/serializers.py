"""Serializers for the configuration resources."""

from core.serializers import DocumentSerializer

from .models import (
    SYSDEFAULT_FIELDS,
    Country,
    Currency,
    FCRMSettings,
    Language,
    SystemSettings,
)

DOCUMENT_FIELDS = (
    "name",
    "owner",
    "modified_by",
    "creation",
    "modified",
    "idx",
    "docstatus",
    "_assign",
    "_liked_by",
    "_comments",
    "_user_tags",
)


class SystemSettingsSerializer(DocumentSerializer):
    class Meta:
        model = SystemSettings
        fields = (*DOCUMENT_FIELDS, *SYSDEFAULT_FIELDS)


class CountrySerializer(DocumentSerializer):
    class Meta:
        model = Country
        fields = (
            *DOCUMENT_FIELDS,
            "country_name",
            "date_format",
            "time_format",
            "time_zones",
            "code",
        )


class LanguageSerializer(DocumentSerializer):
    class Meta:
        model = Language
        fields = (
            *DOCUMENT_FIELDS,
            "language_code",
            "language_name",
            "flag",
            "based_on",
            "enabled",
        )


class CurrencySerializer(DocumentSerializer):
    class Meta:
        model = Currency
        fields = (
            *DOCUMENT_FIELDS,
            "currency_name",
            "enabled",
            "fraction",
            "fraction_units",
            "smallest_currency_fraction_value",
            "symbol",
            "number_format",
            "symbol_on_right",
        )


FCRM_SETTINGS_FIELDS = (
    "brand_name",
    "brand_logo",
    "favicon",
    "enable_forecasting",
    "enable_sales_hierarchy",
    "currency",
    "service_provider",
    "access_key",
    "auto_update_expected_deal_value",
    "update_timestamp_on_new_communication",
    "auto_mark_replied_on_response",
    "auto_reopen_on_new_communication",
    "crm_timeline_timestamp_format",
    "crm_timeline_sort_order",
    "persona_captured",
)


class FCRMSettingsSerializer(DocumentSerializer):
    CHILD_TABLES = {"dropdown_items": ("configuration.CRMDropdownItem", "parent_settings")}

    class Meta:
        model = FCRMSettings
        fields = (*DOCUMENT_FIELDS, *FCRM_SETTINGS_FIELDS, "dropdown_items")
