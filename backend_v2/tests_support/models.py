"""Small document models installed only by the test settings."""

from django.conf import settings
from django.db import models

from core.fields import EncryptedCharField
from core.models import (
    AutoIncrementDocument,
    BaseDocument,
    SingletonDocument as BaseSingletonDocument,
    TreeDocument,
)
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


class TrackedDocument(BaseDocument):
    DOCTYPE = "Foundation Tracked"
    NAME_STRATEGY = Hash()
    TRACKED_FIELDS = ("label", "amount", "effective_date", "assigned_to")
    label = models.CharField(max_length=140, blank=True, default="")
    amount = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    effective_date = models.DateField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True, default="")


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
    POLYMORPHIC_CHILD_TABLES = {"poly_rows": "tests_support.WidgetNote"}
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
    CHILD_FIELDS = (
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
        "parent",
        "parentfield",
        "parenttype",
        "value",
        "related_widget",
    )
    parent = models.ForeignKey(Widget, on_delete=models.CASCADE, related_name="rows")
    parentfield = models.CharField(max_length=140, default="rows")
    parenttype = models.CharField(max_length=140, default="Foundation Widget")
    value = models.CharField(max_length=140)
    related_widget = models.ForeignKey(
        Widget,
        on_delete=models.PROTECT,
        related_name="linked_rows",
        null=True,
        blank=True,
    )


class WidgetNote(BaseDocument):
    DOCTYPE = "Foundation Widget Note"
    NAME_STRATEGY = Hash()
    IS_CHILD_TABLE = True
    CHILD_FIELDS = (
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
        "parent",
        "parenttype",
        "parentfield",
        "value",
    )
    parent = models.CharField(max_length=140)
    parenttype = models.CharField(max_length=140)
    parentfield = models.CharField(max_length=140)
    value = models.CharField(max_length=140)


class SingletonDocument(BaseSingletonDocument):
    DOCTYPE = "Foundation Singleton"
    value = models.CharField(max_length=140, blank=True, default="")
    manager_note = models.CharField(max_length=140, blank=True, default="")
    RESTRICTED_FIELDS = ("manager_note",)


class SecuredDocument(BaseDocument):
    DOCTYPE = "Foundation Secured"
    NAME_STRATEGY = Hash()
    SENSITIVE_FIELDS = ("secret", "encrypted_secret")
    READONLY_FIELDS = ("audit_value",)
    RESTRICTED_FIELDS = ("manager_note",)
    PRIVILEGED_WRITE_FIELDS = ("manager_value",)
    secret = models.CharField(max_length=140, blank=True, default="")
    encrypted_secret = EncryptedCharField(max_length=255, blank=True, default="")
    manager_note = models.CharField(max_length=140, blank=True, default="")
    audit_value = models.CharField(max_length=140, blank=True, default="")
    manager_value = models.CharField(max_length=140, blank=True, default="")


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


class TestTree(TreeDocument):
    DOCTYPE = "Foundation Test Tree"
    NAME_STRATEGY = Prompt()
    PARENT_FIELD = "parent_node"
    parent_node = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="children",
        null=True,
        blank=True,
    )


class TreeItem(BaseDocument):
    DOCTYPE = "Foundation Tree Item"
    NAME_STRATEGY = Prompt()
    tree = models.ForeignKey(TestTree, on_delete=models.PROTECT, related_name="items")
    widget = models.ForeignKey(
        Widget,
        on_delete=models.PROTECT,
        related_name="tree_items",
        null=True,
        blank=True,
    )
    label = models.CharField(max_length=140, blank=True, default="")


class DynamicReference(BaseDocument):
    DOCTYPE = "Foundation Dynamic Reference"
    NAME_STRATEGY = Hash()
    DYNAMIC_LINK_FIELDS = (("reference_doctype", "reference_name"),)
    reference_doctype = models.CharField(max_length=140)
    reference_name = models.CharField(max_length=140)
