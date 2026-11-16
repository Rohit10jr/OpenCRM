"""Explicit serializers used only by the foundation tests."""

from core.serializers import DocumentSerializer
from tests_support.models import (
    AutoIncrementDocumentFixture,
    DynamicReference,
    FieldDocument,
    PointingDocument,
    PromptDocument,
    SearchableDocument,
    SecuredDocument,
    SingletonDocument,
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
        fields = (
            *STANDARD_FIELDS,
            "parent",
            "parentfield",
            "parenttype",
            "value",
            "related_widget",
        )


class WidgetNoteSerializer(DocumentSerializer):
    class Meta:
        model = WidgetNote
        fields = (*STANDARD_FIELDS, "parent", "parentfield", "parenttype", "value")


class WidgetSerializer(DocumentSerializer):
    CHILD_TABLES = {"rows": ("tests_support.WidgetRow", "parent")}

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


class SearchableDocumentSerializer(DocumentSerializer):
    class Meta:
        model = SearchableDocument
        fields = (*STANDARD_FIELDS, "title", "disabled")


class PointingDocumentSerializer(DocumentSerializer):
    class Meta:
        model = PointingDocument
        fields = (*STANDARD_FIELDS, "widget", "widget_status")


class DynamicReferenceSerializer(DocumentSerializer):
    class Meta:
        model = DynamicReference
        fields = (*STANDARD_FIELDS, "reference_doctype", "reference_name")


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


class SingletonDocumentSerializer(DocumentSerializer):
    class Meta:
        model = SingletonDocument
        fields = (*STANDARD_FIELDS, "value", "manager_note")
