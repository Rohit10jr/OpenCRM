"""Cluster 5 - telephony.

PHASE_1_MODELS.md section 5: "Models now, provider logic in phase 7."

The two settings singletons carry ``Password`` fieldtypes. Those are registered in
``SENSITIVE_FIELDS`` so they are never serialised or selectable - see
``frappe_core.field_security``. Without that they would be readable through the generic
``/api/resource/`` endpoint the moment they are registered.
"""

from django.db import models

from frappe_core.models import BaseDocument
from frappe_core.naming import FieldValue, Hash
from frappe_core.registry import register_doctype

CALL_STATUS_CHOICES = [
    (c, c)
    for c in (
        "Initiated",
        "Ringing",
        "In Progress",
        "Completed",
        "Failed",
        "Busy",
        "No Answer",
        "Queued",
        "Canceled",
    )
]
CALL_TYPE_CHOICES = [("Incoming", "Incoming"), ("Outgoing", "Outgoing")]
TELEPHONY_MEDIUM_CHOICES = [("", ""), ("Manual", "Manual"), ("Twilio", "Twilio"), ("Exotel", "Exotel")]
DEFAULT_MEDIUM_CHOICES = [("", ""), ("Twilio", "Twilio"), ("Exotel", "Exotel")]
RECEIVING_DEVICE_CHOICES = [("Computer", "Computer"), ("Phone", "Phone")]


class SingletonMixin(models.Model):
    """``"issingle": 1`` - exactly one row.

    PHASE_1_MODELS.md section 6 allows ``django-solo`` or a ``pk=1`` constraint. Our PKs
    are strings, so the row is pinned to a fixed name instead, which keeps the singleton
    reachable through the same generic endpoint as everything else.
    """

    SINGLETON_NAME = "Settings"

    class Meta:
        abstract = True

    @classmethod
    def load(cls):
        obj, _created = cls._default_manager.get_or_create(pk=cls.SINGLETON_NAME)
        return obj

    def _assign_name(self) -> bool:
        if self.pk:
            return False
        self.pk = self.SINGLETON_NAME
        return True


@register_doctype("CRM Call Log")
class CRMCallLog(BaseDocument):
    """``autoname=field:id`` - the PK is the provider's call id.

    ``id`` is ``reqd=0`` in the JSON but is the naming field, so a blank value cannot
    produce a name; ``FieldValue`` raises for that, which is the faithful outcome.
    """

    id = models.CharField(max_length=140, blank=True, default="")
    status = models.CharField(max_length=20, choices=CALL_STATUS_CHOICES)
    type = models.CharField(max_length=20, choices=CALL_TYPE_CHOICES)
    medium = models.CharField(max_length=140, blank=True, default="")
    telephony_medium = models.CharField(
        max_length=20, choices=TELEPHONY_MEDIUM_CHOICES, blank=True, default=""
    )
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    #: Duration -> seconds.
    duration = models.IntegerField(null=True, blank=True)
    recording_url = models.TextField(blank=True, default="")
    note = models.ForeignKey(
        "crm_app.FCRMNote", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    receiver = models.ForeignKey(
        "frappe_platform.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_calls",
    )
    caller = models.ForeignKey(
        "frappe_platform.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="placed_calls",
    )
    reference_doctype = models.CharField(
        max_length=140, blank=True, default="CRM Lead", db_index=True
    )
    reference_docname = models.CharField(max_length=140, blank=True, default="", db_index=True)

    class Meta:
        ordering = ["-creation"]
        name_strategy = FieldValue("id")
        indexes = [
            models.Index(
                fields=["reference_doctype", "reference_docname"], name="call_log_reference_idx"
            ),
        ]

    def before_insert(self):
        """``crm_call_log.py:50-54``.

        Without this a manually-created call log has no ``id``, and ``field:id`` naming
        then fails - which is exactly what the "Log a call" flow does.
        """
        import secrets

        if not self.id:
            self.id = secrets.token_hex(6)  # generate_hash(length=12)
        if not self.telephony_medium:
            self.telephony_medium = "Manual"

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.before_insert()
        return super().save(*args, **kwargs)


# `from` / `to` are Python keywords - same treatment as CRM Status Change Log.
CRMCallLog.add_to_class("from", models.CharField(max_length=140))
CRMCallLog.add_to_class("to", models.CharField(max_length=140))


@register_doctype("CRM Telephony Agent")
class CRMTelephonyAgent(BaseDocument):
    """``autoname=field:user`` - one agent record per user."""
    #: ``fetch_from`` in ``crm_telephony_agent.json``.
    FETCH_FROM = {"user_name": ("user", "full_name")}


    user = models.OneToOneField(
        "frappe_platform.User", on_delete=models.CASCADE, related_name="telephony_agent"
    )
    user_name = models.CharField(max_length=280, blank=True, default="")
    mobile_no = models.CharField(max_length=140, blank=True, default="")
    exotel_number = models.CharField(max_length=140, blank=True, default="")
    twilio_number = models.CharField(max_length=140, blank=True, default="")
    default_medium = models.CharField(
        max_length=20, choices=DEFAULT_MEDIUM_CHOICES, blank=True, default=""
    )
    call_receiving_device = models.CharField(
        max_length=20, choices=RECEIVING_DEVICE_CHOICES, default="Computer"
    )

    class Meta:
        ordering = ["name"]
        name_strategy = FieldValue("user")


@register_doctype("CRM Telephony Phone", is_child_table=True)
class CRMTelephonyPhone(BaseDocument):
    """Child of CRM Telephony Agent only."""

    parent_agent = models.ForeignKey(
        CRMTelephonyAgent, on_delete=models.CASCADE, related_name="phone_nos"
    )
    parenttype = models.CharField(max_length=140, default="CRM Telephony Agent")
    parentfield = models.CharField(max_length=140, default="phone_nos")

    number = models.CharField(max_length=140)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["idx"]
        name_strategy = Hash()


@register_doctype("CRM Twilio Settings", is_single=True)
class CRMTwilioSettings(SingletonMixin, BaseDocument):
    enabled = models.BooleanField(default=False)
    account_sid = models.CharField(max_length=280, blank=True, default="")
    api_key = models.CharField(max_length=280, blank=True, default="")
    api_secret = models.CharField(max_length=280, blank=True, default="")
    auth_token = models.CharField(max_length=280, blank=True, default="")
    twiml_sid = models.CharField(max_length=280, blank=True, default="")
    app_name = models.CharField(max_length=140, blank=True, default="")
    twilio_apps = models.CharField(max_length=280, blank=True, default="")
    record_calls = models.BooleanField(default=False)

    #: `Password` fieldtype in the JSON - never serialised, never selectable.
    SENSITIVE_FIELDS = ("api_secret", "auth_token")

    class Meta:
        verbose_name = "CRM Twilio Settings"


@register_doctype("CRM Exotel Settings", is_single=True)
class CRMExotelSettings(SingletonMixin, BaseDocument):
    enabled = models.BooleanField(default=False)
    account_sid = models.CharField(max_length=280, blank=True, default="")
    api_key = models.CharField(max_length=280, blank=True, default="")
    api_token = models.CharField(max_length=280, blank=True, default="")
    subdomain = models.CharField(max_length=140, blank=True, default="")
    webhook_verify_token = models.CharField(max_length=280, blank=True, default="")
    record_call = models.BooleanField(default=False)

    #: `Password` fieldtype in the JSON.
    SENSITIVE_FIELDS = ("api_token",)

    class Meta:
        verbose_name = "CRM Exotel Settings"


__all__ = [
    "CRMCallLog",
    "CRMTelephonyAgent",
    "CRMTelephonyPhone",
    "CRMTwilioSettings",
    "CRMExotelSettings",
    "SingletonMixin",
]
