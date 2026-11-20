"""Serializers for the configuration resources."""

from core.serializers import DocumentSerializer

from .models import (
    SYSDEFAULT_FIELDS,
    Country,
    Currency,
    EmailAccount,
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


class EmailAccountSerializer(DocumentSerializer):
    class Meta:
        model = EmailAccount
        fields = (
            *DOCUMENT_FIELDS,
            "email_account_name",
            "email_id",
            "service",
            "enable_incoming",
            "enable_outgoing",
            "default_incoming",
            "default_outgoing",
            "email_sync_option",
            "initial_sync_count",
            "create_contact",
            "track_email_status",
            "use_tls",
            "use_imap",
            "smtp_server",
            "smtp_port",
            "email_server",
            "password",
            "no_smtp_authentication",
            "add_signature",
            "signature",
            "api_key",
            "api_secret",
            "frappe_mail_site",
            "append_to",
            "domain",
            "login_id",
            "login_id_is_different",
            "awaiting_password",
            "ascii_encode_password",
            "use_ssl",
            "use_ssl_for_outgoing",
            "use_starttls",
            "validate_ssl_certificate",
            "incoming_port",
            "always_use_account_email_id_as_sender",
        )
