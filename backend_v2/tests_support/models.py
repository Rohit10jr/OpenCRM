"""Small document models installed only by the test settings."""

from django.conf import settings
from django.db import models

from core.models import AutoIncrementDocument, BaseDocument
from core.naming import (
    DataImportTimestamp,
    FieldValue,
    Format,
    Hash,
    NamingSeries,
    Prompt,
)


class SeriesDocument(BaseDocument):
    DOCTYPE = "Foundation Series"
    NAME_STRATEGY = NamingSeries("FOUNDATION-.YYYY.-")
    label = models.CharField(max_length=140, blank=True, default="")


class FieldDocument(BaseDocument):
    DOCTYPE = "Foundation Field"
    NAME_STRATEGY = FieldValue("title")
    title = models.CharField(max_length=140)


class HashDocument(BaseDocument):
    DOCTYPE = "Foundation Hash"
    NAME_STRATEGY = Hash()
    label = models.CharField(max_length=140, blank=True, default="")


class FormatDocument(BaseDocument):
    DOCTYPE = "Foundation Format"
    NAME_STRATEGY = Format("{document_type}-{layout_type}")
    document_type = models.CharField(max_length=140)
    layout_type = models.CharField(max_length=140)


class PromptDocument(BaseDocument):
    DOCTYPE = "Foundation Prompt"
    NAME_STRATEGY = Prompt()
    label = models.CharField(max_length=140, blank=True, default="")


class AutoIncrementDocumentFixture(AutoIncrementDocument):
    DOCTYPE = "Foundation Auto Increment"
    label = models.CharField(max_length=140, blank=True, default="")


class DataImportDocument(BaseDocument):
    DOCTYPE = "Foundation Data Import"
    NAME_STRATEGY = DataImportTimestamp()
    reference_doctype = models.CharField(max_length=140)


class Widget(BaseDocument):
    DOCTYPE = "Foundation Widget"
    NAME_STRATEGY = NamingSeries("WIDGET-.YYYY.-")
    widget_name = models.CharField(max_length=140, blank=True, default="")
    status = models.CharField(max_length=50, blank=True, default="Open")
    amount = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    quantity = models.IntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    widget_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )


class WidgetRow(BaseDocument):
    DOCTYPE = "Foundation Widget Row"
    NAME_STRATEGY = Hash()
    IS_CHILD_TABLE = True
    parent = models.ForeignKey(Widget, on_delete=models.CASCADE, related_name="rows")
    parentfield = models.CharField(max_length=140, default="rows")
    parenttype = models.CharField(max_length=140, default="Foundation Widget")


class SingletonDocument(BaseDocument):
    DOCTYPE = "Foundation Singleton"
    NAME_STRATEGY = Prompt()
    IS_SINGLE = True
    value = models.CharField(max_length=140, blank=True, default="")


class SecuredDocument(BaseDocument):
    DOCTYPE = "Foundation Secured"
    NAME_STRATEGY = Hash()
    SENSITIVE_FIELDS = ("secret",)
    RESTRICTED_FIELDS = ("manager_note",)
    secret = models.CharField(max_length=140, blank=True, default="")
    manager_note = models.CharField(max_length=140, blank=True, default="")


class PointingDocument(BaseDocument):
    DOCTYPE = "Foundation Pointing"
    NAME_STRATEGY = Hash()
    FETCH_FROM = {"widget_status": ("widget", "status")}
    widget = models.ForeignKey(Widget, on_delete=models.PROTECT, related_name="pointers")
    widget_status = models.CharField(max_length=50, blank=True, default="")


class EmailDocument(BaseDocument):
    DOCTYPE = "Foundation Email"
    NAME_STRATEGY = Hash()
    EMAIL_FIELDS = ("recipients",)
    recipients = models.TextField(blank=True, default="")


class TextLinkDocument(BaseDocument):
    DOCTYPE = "Foundation Text Link"
    NAME_STRATEGY = Hash()
    TEXT_LINK_FIELDS = {
        "widget_name": ("tests_support.Widget", "Widget"),
        "audit_widget_name": ("tests_support.Widget", "Audit Widget"),
    }
    ALLOW_DANGLING_LINK_FIELDS = ("audit_widget_name",)
    widget_name = models.CharField(max_length=140, blank=True, default="")
    audit_widget_name = models.CharField(max_length=140, blank=True, default="")
