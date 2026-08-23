"""ERPNext integration doctypes, behind `ENABLE_ERPNEXT`.

Ports `erpnext_crm_settings.json` and `crm_product_sync_issue.json`, plus the two link
columns upstream adds as **runtime custom fields**.

## The custom fields are real columns here

`create_custom_fields_in_frappe_crm` (`erpnext_crm_settings.py:92-125`) adds
`CRM Deal.erpnext_customer` and `CRM Product.erpnext_item_code` at runtime, through
Frappe's `Custom Field` doctype. This port has no `Custom Field` — schema is Django
migrations — so they are ordinary columns declared here and migrated in.

The behaviour is the same and the mechanism is not, which matters in one direction: a
deployment that has never enabled ERPNext still has the columns, empty. That costs two
`varchar` columns and removes a whole runtime-schema-mutation machinery from the port.
"""

from __future__ import annotations

from django.db import models

from frappe_core.models import AutoIncrementDocument, BaseDocument
from frappe_core.registry import register_doctype
from frappe_core.secrets import EncryptedFieldsMixin
from crm_app.models.telephony import SingletonMixin

#: `crm_product_sync_issue.json` — the reconciliation's findings.
SYNC_ISSUE_KIND_CHOICES = [
    (c, c) for c in ("unlinked_orphan", "missing_item", "duplicate_code", "create_failed")
]


@register_doctype("CRM Product Sync Issue", is_child_table=True)
class CRMProductSyncIssue(AutoIncrementDocument):
    """Child of `ERPNext CRM Settings`. ``autoname=autoincrement``.

    Registered as a child table, so it has no route of its own — it is reached through its
    parent, which is manager-only.
    """

    parenttype = models.CharField(max_length=140, default="ERPNext CRM Settings")
    parentfield = models.CharField(max_length=140, default="sync_issues")
    parent = models.CharField(max_length=140, blank=True, default="", db_index=True)

    product = models.CharField(max_length=140, blank=True, default="")
    kind = models.CharField(
        max_length=40, choices=SYNC_ISSUE_KIND_CHOICES, blank=True, default=""
    )
    detail = models.TextField(blank=True, default="")
    detected_on = models.DateTimeField(null=True, blank=True)
    dismissed = models.BooleanField(default=False)

    class Meta:
        ordering = ["idx"]


@register_doctype("ERPNext CRM Settings", is_single=True)
class ERPNextCRMSettings(EncryptedFieldsMixin, SingletonMixin, BaseDocument):
    """``issingle=1``.

    The credential pair is an ERPNext **API key and secret**, which together authenticate
    as a user on the remote site — `Authorization: token <key>:<secret>`. The secret is a
    `Password` fieldtype upstream and is treated as one here; the key is `Data` upstream and
    is restricted here for the same reason `Twilio.api_key` is.
    """

    enabled = models.BooleanField(default=False)

    api_key = models.CharField(max_length=280, blank=True, default="")
    api_secret = models.CharField(max_length=280, blank=True, default="")

    erpnext_site_url = models.CharField(max_length=280, blank=True, default="")
    erpnext_company = models.CharField(max_length=280, blank=True, default="")

    #: Upstream supports ERPNext installed on the *same* Frappe site, which is not a mode
    #: this port can have — see `crm_app/integrations/erpnext/__init__.py`. The field is
    #: kept because it is in the schema and the frontend renders it; the code treats
    #: "different site" as the only supported value and says so when it is not.
    is_erpnext_in_different_site = models.BooleanField(default=True)

    sync_products = models.BooleanField(default=False)
    create_customer_on_status_change = models.BooleanField(default=False)
    deal_status = models.ForeignKey(
        "crm_app.CRMDealStatus",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    #: `Password` fieldtype upstream, so it lives in the encrypted `__Auth` table there.
    SENSITIVE_FIELDS = ("api_secret",)
    ENCRYPTED_FIELDS = ("api_secret",)

    #: Half of a credential pair. Same treatment as `CRM Twilio Settings.api_key`, and the
    #: same reasoning: inert while reads are manager-only, and the thing that stops being
    #: inert the moment somebody widens reads for a settings screen.
    RESTRICTED_FIELDS = ("api_key", "erpnext_site_url")

    class Meta:
        verbose_name = "ERPNext CRM Settings"


__all__ = ["ERPNextCRMSettings", "CRMProductSyncIssue"]
