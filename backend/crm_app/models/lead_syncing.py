"""Facebook lead sync — the doctypes, behind `ENABLE_FACEBOOK_LEAD_SYNC`.

Ports `crm/lead_syncing/doctype/`. Transcribed from the DocType JSON, not inferred:
`facebook_page.json`, `facebook_lead_form.json`, `facebook_lead_form_question.json`,
`failed_lead_sync_log.json` and `lead_sync_source.json`.

## Two access tokens, and upstream only protects one

`Lead Sync Source.access_token` is a `Password` fieldtype, so upstream keeps it in the
encrypted `__Auth` table. **`Facebook Page.access_token` is a plain `Small Text`** — a
long-lived page access token, sitting in the document table with no `permlevel`, readable
by anyone the doctype's role permissions admit.

That is not a small difference. A page access token can read every lead the page has ever
collected and post as the page. `PHASE_7_INTEGRATIONS.md` §3 says never to commit
credentials and to keep them encrypted at rest, and `AS_BUILT.md`'s checklist says a name
that looks like a credential must be declared. Both tokens are therefore
`SENSITIVE_FIELDS` **and** `ENCRYPTED_FIELDS` here. `UPSTREAM_BUGS` #28.

`tests/test_credential_fields.py` would have failed on both of these anyway, which is the
point of it existing before this phase rather than after.
"""

from __future__ import annotations

from django.db import models

from frappe_core.models import BaseDocument
from frappe_core.naming import FieldValue, Hash
from frappe_core.registry import register_doctype
from frappe_core.secrets import EncryptedFieldsMixin

#: `lead_sync_source.json` — the six frequencies map onto phase 5's six registered tasks.
SYNC_FREQUENCY_CHOICES = [
    (c, c)
    for c in (
        "Every 5 Minutes",
        "Every 10 Minutes",
        "Every 15 Minutes",
        "Hourly",
        "Daily",
        "Monthly",
    )
]

#: `failed_lead_sync_log.json`. `Synced` is in the Select and is never written by the sync
#: path — kept because it is in the source options list.
SYNC_LOG_TYPE_CHOICES = [(c, c) for c in ("Duplicate", "Failure", "Synced")]

SOURCE_TYPE_CHOICES = [("Facebook", "Facebook")]


@register_doctype("Facebook Page")
class FacebookPage(EncryptedFieldsMixin, BaseDocument):
    """``autoname=field:id`` — the PK is Facebook's own page id."""

    id = models.CharField(max_length=140, blank=True, default="")
    page_name = models.CharField(max_length=280, blank=True, default="")
    category = models.CharField(max_length=140, blank=True, default="")
    account_id = models.CharField(max_length=140, blank=True, default="")
    access_token = models.TextField(blank=True, default="")

    #: **Stricter than upstream**, which stores this as plain `Small Text`. See the module
    #: docstring: a page access token reads every lead the page has collected.
    SENSITIVE_FIELDS = ("access_token",)
    ENCRYPTED_FIELDS = ("access_token",)

    class Meta:
        ordering = ["name"]
        name_strategy = FieldValue("id")


@register_doctype("Facebook Lead Form")
class FacebookLeadForm(BaseDocument):
    """``autoname=field:id`` — the PK is Facebook's own form id."""

    id = models.CharField(max_length=140, blank=True, default="")
    form_name = models.CharField(max_length=280, blank=True, default="")
    page = models.ForeignKey(
        FacebookPage, on_delete=models.CASCADE, null=True, blank=True, related_name="forms"
    )

    class Meta:
        ordering = ["name"]
        name_strategy = FieldValue("id")


@register_doctype("Facebook Lead Form Question", is_child_table=True)
class FacebookLeadFormQuestion(BaseDocument):
    """Child of Facebook Lead Form.

    `mapped_to_crm_field` is the whole point of the table: it says which CRM Lead field a
    given form question fills. A question with no mapping is dropped
    (`facebook.py:94-96`).
    """

    parent_form = models.ForeignKey(
        FacebookLeadForm, on_delete=models.CASCADE, related_name="questions"
    )
    parenttype = models.CharField(max_length=140, default="Facebook Lead Form")
    parentfield = models.CharField(max_length=140, default="questions")

    label = models.CharField(max_length=280, blank=True, default="")
    key = models.CharField(max_length=140, blank=True, default="")
    type = models.CharField(max_length=140, blank=True, default="")
    id = models.CharField(max_length=140, blank=True, default="")
    mapped_to_crm_field = models.CharField(max_length=140, blank=True, default="")

    class Meta:
        ordering = ["idx"]
        name_strategy = Hash()


@register_doctype("Lead Sync Source")
class LeadSyncSource(EncryptedFieldsMixin, BaseDocument):
    """``autoname=prompt`` — the operator names the source.

    ``last_synced_at`` is the idempotency mechanism: `fetch_leads` filters Facebook-side on
    ``time_created > last_synced_at``, so a re-run does not re-fetch what it already has.
    It is a *narrowing*, not a guarantee — the duplicate check is what actually guarantees
    it, because Facebook's clock and ours are not the same clock.
    """

    type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES, default="Facebook")
    enabled = models.BooleanField(default=False)
    access_token = models.TextField(blank=True, default="")
    last_synced_at = models.DateTimeField(null=True, blank=True)
    background_sync_frequency = models.CharField(
        max_length=20, choices=SYNC_FREQUENCY_CHOICES, blank=True, default=""
    )
    facebook_page = models.ForeignKey(
        FacebookPage, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    facebook_lead_form = models.ForeignKey(
        FacebookLeadForm, on_delete=models.SET_NULL, null=True, blank=True, related_name="sources"
    )

    #: `Password` fieldtype upstream, so encrypted there too. Sensitive as well, which
    #: upstream gets for free by keeping Password fields out of the document table.
    SENSITIVE_FIELDS = ("access_token",)
    ENCRYPTED_FIELDS = ("access_token",)

    class Meta:
        ordering = ["name"]

    def validate_same_fb_form_active(self):
        """`lead_sync_source.py:34-47`, message preserved verbatim.

        Two enabled sources on one form would each fetch the same leads and race to insert
        them — the duplicate check would catch it, but as a stream of failure logs rather
        than as a configuration error.
        """
        from frappe_core.exceptions import throw

        if not self.enabled or not self.facebook_lead_form_id:
            return

        clash = (
            type(self)
            ._default_manager.filter(
                enabled=True, facebook_lead_form_id=self.facebook_lead_form_id
            )
            .exclude(pk=self.pk)
            .exists()
        )
        if clash:
            throw("A lead sync source is already enabled for this Facebook Lead Form!")

    def validate(self):
        self.validate_same_fb_form_active()
        return super().validate() if hasattr(super(), "validate") else None


@register_doctype("Failed Lead Sync Log")
class FailedLeadSyncLog(BaseDocument):
    """Why a lead did not arrive.

    **Holds `lead_data`, which is the raw Facebook payload** — a person's name, email and
    phone number. That makes it a doctype worth being careful with, and it is why it gets a
    row rule rather than being left open: it is the one place in this phase where a failure
    log carries personal data.
    """

    type = models.CharField(max_length=20, choices=SYNC_LOG_TYPE_CHOICES, blank=True, default="")
    lead_data = models.TextField(blank=True, default="")
    traceback = models.TextField(blank=True, default="")
    source = models.ForeignKey(
        LeadSyncSource, on_delete=models.CASCADE, null=True, blank=True, related_name="failures"
    )

    class Meta:
        ordering = ["-creation"]
        name_strategy = Hash()


__all__ = [
    "FacebookPage",
    "FacebookLeadForm",
    "FacebookLeadFormQuestion",
    "LeadSyncSource",
    "FailedLeadSyncLog",
]
