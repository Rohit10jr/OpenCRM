"""Serializers for the configuration resources."""

import json

from rest_framework import serializers

from core.exceptions import ValidationError
from core.serializers import DocumentSerializer

from .layouts import validated_layout_text
from .models import (
    SYSDEFAULT_FIELDS,
    VIEW_JSON_FIELDS,
    Country,
    CRMFieldsLayout,
    CRMFormScript,
    CRMGlobalSettings,
    CRMViewSettings,
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
    """PE-30: a non-empty `password` or `api_secret` sent on create or PATCH is stored
    (encrypted by the model); null or "" leaves the stored value. Both stay sensitive:
    write-only here, never in a response, a filter or `fields`."""

    #: The credentials the resource takes in but never shows, with upstream's labels.
    WRITE_ONLY_SECRETS = {"password": "Password", "api_secret": "API Secret"}
    #: Upstream's Password fieldtype is varchar 140.
    SECRET_MAX_LENGTH = 140

    def get_fields(self):
        fields = super().get_fields()
        for name in self.WRITE_ONLY_SECRETS:
            # Stored as sent: upstream does not trim a Password.
            fields[name] = serializers.CharField(
                write_only=True,
                required=False,
                allow_blank=True,
                allow_null=True,
                trim_whitespace=False,
            )
        return fields

    def _secrets_checked(self, validated_data, name):
        for fieldname, label in self.WRITE_ONLY_SECRETS.items():
            if fieldname not in validated_data:
                continue
            value = validated_data[fieldname]
            if not value:
                validated_data.pop(fieldname)
            elif len(value) > self.SECRET_MAX_LENGTH:
                # Upstream's "Value too big", without the value it echoes.
                raise ValidationError(
                    f"Email Account {name}: '<strong>{label}</strong>' will get "
                    f"truncated, as max characters allowed is {self.SECRET_MAX_LENGTH}",
                    title="Value too big",
                )
        return validated_data

    def create(self, validated_data):
        name = validated_data.get("email_account_name") or ""
        return super().create(self._secrets_checked(validated_data, name))

    def update(self, instance, validated_data):
        return super().update(instance, self._secrets_checked(validated_data, instance.pk))

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


class CRMFieldsLayoutSerializer(DocumentSerializer):
    class Meta:
        model = CRMFieldsLayout
        fields = (*DOCUMENT_FIELDS, "dt", "type", "layout")

    def validate_layout(self, value):
        """Valid JSON whose field lists hold fieldnames only (PE-12c, PE-18)."""
        return validated_layout_text(value)


class CRMFormScriptSerializer(DocumentSerializer):
    class Meta:
        model = CRMFormScript
        fields = (*DOCUMENT_FIELDS, "dt", "view", "script", "enabled", "is_standard")


class CRMGlobalSettingsSerializer(DocumentSerializer):
    class Meta:
        model = CRMGlobalSettings
        fields = (*DOCUMENT_FIELDS, "dt", "type", "json")


VIEW_SETTINGS_FIELDS = (
    "dt",
    "user",
    "label",
    "type",
    "columns",
    "rows",
    "filters",
    "order_by",
    "group_by_field",
    "column_field",
    "kanban_columns",
    "kanban_fields",
    "title_field",
    "route_name",
    "icon",
    "pinned",
    "public",
    "load_default_columns",
    "is_standard",
    "is_default",
)


def json_text(value, label: str) -> str:
    """A JSON column's text as written; 417 "<Label> must be valid JSON" when it does
    not parse (PE-12d). Blank stays blank."""
    if value in (None, ""):
        return ""
    try:
        json.loads(value)
    except (TypeError, ValueError, RecursionError):
        raise ValidationError(f"{label} must be valid JSON") from None
    return value


class CRMViewSettingsSerializer(DocumentSerializer):
    class Meta:
        model = CRMViewSettings
        fields = (*DOCUMENT_FIELDS, *VIEW_SETTINGS_FIELDS)

    def validate(self, attrs):
        for fieldname, label in VIEW_JSON_FIELDS.items():
            if fieldname in attrs:
                attrs[fieldname] = json_text(attrs[fieldname], label)
        return super().validate(attrs)

    def create(self, validated_data):
        """A view created on the resource belongs to the caller (PE-19); `user` is
        read-only, and `save(user=...)` names the actor, not this field."""
        validated_data["user"] = self.user
        return super().create(validated_data)
