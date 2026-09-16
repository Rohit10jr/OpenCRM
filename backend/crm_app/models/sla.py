"""Cluster 4 - the SLA engine.

PHASE_1_MODELS.md section 5: "Business-hours arithmetic. Timezone-sensitive." Phase 1
ports the **schema**; the arithmetic is phase 5, which PHASE_5_ASYNC.md section 4 now
records as happening on write, not on a schedule.

``Duration`` fields are seconds (PHASE_1_MODELS.md section 2).
"""

from django.db import models

from frappe_core.models import BaseDocument
from frappe_core.naming import FieldValue, Hash
from frappe_core.registry import register_doctype

WEEKDAY_CHOICES = [
    (d, d)
    for d in (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    )
]

ROLLING_STATUS_CHOICES = [("Fulfilled", "Fulfilled"), ("Failed", "Failed")]


@register_doctype("CRM Holiday List")
class CRMHolidayList(BaseDocument):
    holiday_list_name = models.CharField(max_length=140)
    from_date = models.DateField()
    to_date = models.DateField()
    total_holidays = models.IntegerField(null=True, blank=True)
    weekly_off = models.CharField(
        max_length=20, choices=WEEKDAY_CHOICES, blank=True, default=""
    )

    class Meta:
        ordering = ["name"]
        name_strategy = FieldValue("holiday_list_name")


@register_doctype("CRM Holiday", is_child_table=True)
class CRMHoliday(BaseDocument):
    """Child of CRM Holiday List only - single parent, so a real FK."""

    parent_holiday_list = models.ForeignKey(
        CRMHolidayList, on_delete=models.CASCADE, related_name="holidays"
    )
    parenttype = models.CharField(max_length=140, default="CRM Holiday List")
    parentfield = models.CharField(max_length=140, default="holidays")

    date = models.DateField()
    weekly_off = models.BooleanField(default=False)
    description = models.TextField()

    class Meta:
        ordering = ["idx"]
        name_strategy = Hash()


@register_doctype("CRM Service Level Agreement")
class CRMServiceLevelAgreement(BaseDocument):
    sla_name = models.CharField(max_length=140)
    enabled = models.BooleanField(default=False)
    default = models.BooleanField(default=False)
    # `Code` fieldtype -> TextField. This is a Python expression evaluated by upstream
    # (`validate_condition` builds a temp doc and evals it); phase 5 owns whether we
    # evaluate it at all. Storing it is not executing it.
    condition = models.TextField(blank=True, default="")
    condition_json = models.TextField(blank=True, default="")
    apply_on = models.CharField(max_length=140)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    holiday_list = models.ForeignKey(
        CRMHolidayList, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    rolling_responses = models.BooleanField(default=False)

    class Meta:
        ordering = ["-modified"]
        name_strategy = FieldValue("sla_name", label="SLA Name")


@register_doctype("CRM Service Day", is_child_table=True)
class CRMServiceDay(BaseDocument):
    """Working hours. Child of CRM Service Level Agreement only."""

    parent_sla = models.ForeignKey(
        CRMServiceLevelAgreement, on_delete=models.CASCADE, related_name="working_hours"
    )
    parenttype = models.CharField(max_length=140, default="CRM Service Level Agreement")
    parentfield = models.CharField(max_length=140, default="working_hours")

    workday = models.CharField(max_length=20, choices=WEEKDAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["idx"]
        name_strategy = Hash()


@register_doctype("CRM Service Level Priority", is_child_table=True)
class CRMServiceLevelPriority(BaseDocument):
    """Child of CRM Service Level Agreement only."""

    parent_sla = models.ForeignKey(
        CRMServiceLevelAgreement, on_delete=models.CASCADE, related_name="priorities"
    )
    parenttype = models.CharField(max_length=140, default="CRM Service Level Agreement")
    parentfield = models.CharField(max_length=140, default="priorities")

    default_priority = models.BooleanField(default=False)
    priority = models.ForeignKey(
        "crm_app.CRMCommunicationStatus", on_delete=models.PROTECT, related_name="+"
    )
    #: Duration -> seconds.
    first_response_time = models.IntegerField()

    class Meta:
        ordering = ["idx"]
        name_strategy = Hash()


@register_doctype("CRM Rolling Response Time", is_child_table=True)
class CRMRollingResponseTime(BaseDocument):
    """**Two parents** - ``crm_lead.rolling_responses`` and ``crm_deal.rolling_responses``
    - so this is polymorphic, like CRM Products. See the note in ``taxonomy.py``.
    """

    parenttype = models.CharField(max_length=140, blank=True, default="", db_index=True)
    parentfield = models.CharField(max_length=140, blank=True, default="")
    parent = models.CharField(max_length=140, blank=True, default="", db_index=True)

    response_time = models.IntegerField(null=True, blank=True)
    responded_on = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=ROLLING_STATUS_CHOICES, blank=True, default=""
    )

    class Meta:
        ordering = ["idx"]
        name_strategy = Hash()
        indexes = [
            models.Index(fields=["parenttype", "parent"], name="rolling_resp_parent_idx"),
        ]


@register_doctype("CRM Status Change Log", is_child_table=True)
class CRMStatusChangeLog(BaseDocument):
    """**Two parents** (lead and deal), so polymorphic.

    ``from`` and ``to`` are Python keywords, so they cannot be written as class
    attributes. ``Model.add_to_class`` below installs them under their real names, which
    keeps the wire format exact - the frontend and any ported query use ``from``/``to``.
    Access them with ``getattr(obj, "from")`` or ``filter(**{"from": x})``.
    """

    parenttype = models.CharField(max_length=140, blank=True, default="", db_index=True)
    parentfield = models.CharField(max_length=140, blank=True, default="")
    parent = models.CharField(max_length=140, blank=True, default="", db_index=True)

    from_date = models.DateTimeField(null=True, blank=True)
    to_date = models.DateTimeField(null=True, blank=True)
    #: Duration -> seconds.
    duration = models.IntegerField(null=True, blank=True)
    from_type = models.CharField(max_length=140, blank=True, default="")
    to_type = models.CharField(max_length=140, blank=True, default="")
    last_status_change_log = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    log_owner = models.ForeignKey(
        "frappe_platform.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["idx"]
        name_strategy = Hash()
        indexes = [
            models.Index(fields=["parenttype", "parent"], name="status_log_parent_idx"),
        ]


# `from` / `to` are keywords; add_to_class is the supported way to give a model a field
# whose name is not a legal identifier.
CRMStatusChangeLog.add_to_class(
    "from", models.CharField(max_length=140, blank=True, default="")
)
CRMStatusChangeLog.add_to_class(
    "to", models.CharField(max_length=140, blank=True, default="")
)


__all__ = [
    "CRMHolidayList",
    "CRMHoliday",
    "CRMServiceLevelAgreement",
    "CRMServiceDay",
    "CRMServiceLevelPriority",
    "CRMRollingResponseTime",
    "CRMStatusChangeLog",
]
