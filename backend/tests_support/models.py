"""Throwaway doctypes that exercise the phase-0 framework.

Registered only under ``config.settings.test`` so no test model ever reaches a real
database. They exist because PHASE_0_FOUNDATION.md section 9 forbids phase 0 from
building any CRM model - so the framework has to be proved against models of its own.

``Widget`` doubles as the acceptance test for section 10's "a throwaway model registers
and becomes fully routable in <=3 lines": the decorator, the class line, and the
``name_strategy`` are the whole registration.
"""

from django.db import models

from frappe_core.assignment import register_todo_model
from frappe_core.models import AutoIncrementDocument, BaseDocument
from frappe_core.naming import FieldValue, Format, Hash, NamingSeries, Prompt
from frappe_core.registry import register_doctype


@register_doctype("Phase Zero Widget")
class Widget(BaseDocument):
    """The general-purpose fixture: one field per filter-grammar branch."""

    widget_name = models.CharField(max_length=140, blank=True, default="")
    status = models.CharField(max_length=50, blank=True, default="Open")
    amount = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    quantity = models.IntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    widget_owner = models.ForeignKey(
        "frappe_platform.User",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )

    class Meta:
        name_strategy = NamingSeries("PZW-.YYYY.-")

    @staticmethod
    def default_list_data():
        return {
            "columns": [
                {"label": "Widget", "type": "Data", "key": "widget_name", "width": "12rem"},
                {"label": "Status", "type": "Data", "key": "status", "width": "8rem"},
                {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
            ],
            "rows": ["name", "widget_name", "status", "modified"],
        }

    @staticmethod
    def get_non_filterable_fields():
        return ["notes"]


@register_doctype("Phase Zero Series")
class SeriesDoc(BaseDocument):
    label = models.CharField(max_length=140, blank=True, default="")

    class Meta:
        name_strategy = NamingSeries("PZS-.YYYY.-")


@register_doctype("Phase Zero Field")
class FieldDoc(BaseDocument):
    organization_name = models.CharField(max_length=140)

    class Meta:
        name_strategy = FieldValue("organization_name")


@register_doctype("Phase Zero Counter")
class CounterDoc(AutoIncrementDocument):
    """Genuinely integer PKs - crm_task / crm_view_settings / crm_product_sync_issue."""

    label = models.CharField(max_length=140, blank=True, default="")


@register_doctype("Phase Zero Hash")
class HashDoc(BaseDocument):
    label = models.CharField(max_length=140, blank=True, default="")

    class Meta:
        name_strategy = Hash()


@register_doctype("Phase Zero Format")
class FormatDoc(BaseDocument):
    """Mirrors ``crm_fields_layout``'s ``format:{dt}-{type}``."""

    dt = models.CharField(max_length=140)
    type = models.CharField(max_length=140)

    class Meta:
        name_strategy = Format("{dt}-{type}")


@register_doctype("Phase Zero Prompt")
class PromptDoc(BaseDocument):
    """Mirrors ``crm_form_script``'s ``prompt``."""

    label = models.CharField(max_length=140, blank=True, default="")

    class Meta:
        name_strategy = Prompt()


@register_doctype("Phase Zero ToDo")
class TodoDoc(BaseDocument):
    """Stands in for the platform ``ToDo`` that phase 1 cluster 1 will build.

    Phase 0 owns the ``_assign`` sync mechanism but not the model
    (PHASE_0_FOUNDATION.md section 9), so the mechanism is proved against this.
    Field names match Frappe's ToDo exactly.
    """

    reference_type = models.CharField(max_length=140, blank=True, default="")
    reference_name = models.CharField(max_length=140, blank=True, default="")
    allocated_to = models.CharField(max_length=140, blank=True, default="")
    status = models.CharField(max_length=50, default="Open")

    class Meta:
        name_strategy = Hash()


register_todo_model(TodoDoc)


@register_doctype("Phase Zero Child", is_child_table=True)
class ChildDoc(BaseDocument):
    """Child tables must not be routable (PHASE_1_MODELS.md section 3)."""

    parent_widget = models.ForeignKey(
        Widget, on_delete=models.CASCADE, related_name="children", null=True, blank=True
    )
    parenttype = models.CharField(max_length=140, blank=True, default="")
    parentfield = models.CharField(max_length=140, blank=True, default="")

    class Meta:
        name_strategy = Hash()
