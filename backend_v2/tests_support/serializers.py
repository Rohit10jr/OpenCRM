"""Explicit serializers used only by the foundation tests."""

from core.serializers import DocumentSerializer
from tests_support.models import (
    AutoIncrementDocumentFixture,
    FieldDocument,
    PromptDocument,
    SecuredDocument,
    Widget,
    WidgetNote,
    WidgetRow,
)


STANDARD_FIELDS = (
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


class WidgetRowSerializer(DocumentSerializer):
    class Meta:
        model = WidgetRow
        fields = (*STANDARD_FIELDS, "parent", "parentfield", "parenttype", "value")


class WidgetNoteSerializer(DocumentSerializer):
    class Meta:
        model = WidgetNote
        fields = (*STANDARD_FIELDS, "parent", "parentfield", "parenttype", "value")


class WidgetSerializer(DocumentSerializer):
    CHILD_TABLES = {"rows": "tests_support.WidgetRow"}

    class Meta:
        model = Widget
        fields = (
            *STANDARD_FIELDS,
            "widget_name",
            "status",
            "amount",
            "quantity",
            "active",
            "due_date",
            "notes",
            "widget_owner",
            "rows",
            "poly_rows",
        )


class SecuredDocumentSerializer(DocumentSerializer):
    class Meta:
        model = SecuredDocument
        fields = (
            *STANDARD_FIELDS,
            "secret",
            "encrypted_secret",
            "manager_note",
            "audit_value",
            "manager_value",
        )


class FieldDocumentSerializer(DocumentSerializer):
    class Meta:
        model = FieldDocument
        fields = (*STANDARD_FIELDS, "title")


class PromptDocumentSerializer(DocumentSerializer):
    class Meta:
        model = PromptDocument
        fields = (*STANDARD_FIELDS, "label")


class AutoIncrementDocumentSerializer(DocumentSerializer):
    class Meta:
        model = AutoIncrementDocumentFixture
        fields = (*STANDARD_FIELDS, "label")
