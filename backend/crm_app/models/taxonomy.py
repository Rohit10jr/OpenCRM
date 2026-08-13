"""Cluster 3 - taxonomy and lookups.

PHASE_1_MODELS.md section 5. Near-trivial value tables, except ``CRM Territory``, which
is a tree.

Every field below is transcribed from ``crm/fcrm/doctype/<name>/<name>.json``; layout
fieldtypes (Section/Column/Tab Break) are excluded, as PHASE_1_MODELS.md section 2
requires - they are form layout, and belong to phase 4.
"""

from django.db import models

from frappe_core.models import BaseDocument
from frappe_core.naming import FieldValue, Hash
from frappe_core.registry import register_doctype

#: ``Select`` options are newline-separated in the JSON; these are the parsed lists.
#: All 13, transcribed from the full ``options`` string - an earlier revision stopped at
#: ``yellow`` because the tool I was inspecting the JSON with truncated long values.
COLOR_CHOICES = [
    (c, c)
    for c in (
        "black",
        "gray",
        "blue",
        "green",
        "red",
        "pink",
        "orange",
        "amber",
        "yellow",
        "cyan",
        "teal",
        "violet",
        "purple",
    )
]

STATUS_TYPE_CHOICES = [
    (t, t) for t in ("Open", "Ongoing", "On Hold", "Won", "Lost")
]


@register_doctype("CRM Lead Status")
class CRMLeadStatus(BaseDocument):
    lead_status = models.CharField(max_length=140)
    color = models.CharField(max_length=20, choices=COLOR_CHOICES, default="gray", blank=True)
    position = models.IntegerField(default=1)
    type = models.CharField(
        max_length=20, choices=STATUS_TYPE_CHOICES, default="Open", blank=True
    )

    class Meta:
        ordering = ["position"]
        name_strategy = FieldValue("lead_status")


@register_doctype("CRM Deal Status")
class CRMDealStatus(BaseDocument):
    deal_status = models.CharField(max_length=140)
    color = models.CharField(max_length=20, choices=COLOR_CHOICES, default="gray", blank=True)
    position = models.IntegerField(null=True, blank=True)
    probability = models.FloatField(null=True, blank=True)
    type = models.CharField(
        max_length=20, choices=STATUS_TYPE_CHOICES, default="Open", blank=True
    )

    class Meta:
        ordering = ["position"]
        name_strategy = FieldValue("deal_status")


@register_doctype("CRM Lead Source")
class CRMLeadSource(BaseDocument):
    source_name = models.CharField(max_length=140)
    details = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]
        name_strategy = FieldValue("source_name")


@register_doctype("CRM Industry")
class CRMIndustry(BaseDocument):
    # reqd=0 in the JSON, but it is the naming field, so an empty value cannot produce a
    # name; FieldValue raises for that case.
    industry = models.CharField(max_length=140, blank=True, default="")

    class Meta:
        ordering = ["name"]
        name_strategy = FieldValue("industry")


@register_doctype("CRM Lost Reason")
class CRMLostReason(BaseDocument):
    lost_reason = models.CharField(max_length=140)
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]
        name_strategy = FieldValue("lost_reason")


@register_doctype("CRM Communication Status")
class CRMCommunicationStatus(BaseDocument):
    status = models.CharField(max_length=140)

    class Meta:
        ordering = ["name"]
        name_strategy = FieldValue("status")


@register_doctype("CRM Territory")
class CRMTerritory(BaseDocument):
    """A nested-set tree in Frappe (``lft`` / ``rgt`` are real columns in the JSON).

    PHASE_2_PERMISSIONS.md section 3 calls for ``django-treebeard`` here. Phase 1 ports
    the **schema** faithfully - including ``lft``/``rgt``, which the frontend and any
    imported data carry - and exposes ``parent_crm_territory`` as the self-FK the JSON
    declares.

    **Phase 2 owns the tree behaviour**: maintaining ``lft``/``rgt`` on write and
    answering subtree queries. It should register a resolver through
    ``frappe_core.filters.register_tree_resolver("CRM Territory", ...)`` so the
    ``descendants of`` operator works, and decide there whether to adopt treebeard
    outright or keep the nested-set columns. Deferring that decision keeps phase 1
    mechanical, which is what its spec asks for.
    """

    territory_name = models.CharField(max_length=140)
    territory_manager = models.ForeignKey(
        "frappe_platform.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_territories",
    )
    lft = models.IntegerField(null=True, blank=True, db_index=True)
    rgt = models.IntegerField(null=True, blank=True, db_index=True)
    is_group = models.BooleanField(default=False)
    old_parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="former_children",
        db_column="old_parent",
    )
    parent_crm_territory = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        db_column="parent_crm_territory",
    )

    class Meta:
        ordering = ["name"]
        name_strategy = FieldValue("territory_name")


@register_doctype("CRM Product")
class CRMProduct(BaseDocument):
    """``autoname=field:product_code``.

    The JSON also carries a ``naming_series`` Select (``CRM-PROD-.YYYY.-``), but
    ``autoname`` wins - the series field is vestigial here. Ported as a plain column so
    round-tripping a document does not lose it.
    """

    naming_series = models.CharField(max_length=140, blank=True, default="")
    product_code = models.CharField(max_length=140)
    product_name = models.CharField(max_length=140, blank=True, default="")
    disabled = models.BooleanField(default=False)
    # `Attach Image` is a URL string, not a FileField (PHASE_1_MODELS.md section 2).
    image = models.CharField(max_length=500, blank=True, default="")
    description = models.TextField(blank=True, default="")
    standard_rate = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )

    class Meta:
        ordering = ["name"]
        name_strategy = FieldValue("product_code")

    def set_product_name(self):
        """``crm_product.py:51-52``, called from ``validate``."""
        self.product_name = (self.product_name or self.product_code or "").strip()

    def clean(self):
        self.set_product_name()

    def save(self, *args, **kwargs):
        self.set_product_name()
        return super().save(*args, **kwargs)


@register_doctype("CRM Products", is_child_table=True)
class CRMProducts(BaseDocument):
    """Child table. Reached through its parent; no standalone route.

    **This one cannot take a foreign key.** PHASE_1_MODELS.md section 3 says child
    tables get "FK to parent + parenttype, parentfield, idx", but ``CRM Products`` is
    embedded by *two* doctypes - ``crm_deal.products`` and ``crm_lead.products`` - so
    there is no single target. Same for ``CRM Status Change Log`` and ``CRM Rolling
    Response Time``. Frappe models this polymorphically with a ``parent`` string plus
    ``parenttype``, and that is ported verbatim here.

    Single-parent child tables in this port *do* get a real FK; only these three do not.
    Logged in PROGRESS.md as a deviation from the spec's blanket rule.
    """

    parenttype = models.CharField(max_length=140, blank=True, default="", db_index=True)
    parentfield = models.CharField(max_length=140, blank=True, default="")
    parent = models.CharField(max_length=140, blank=True, default="", db_index=True)

    product_code = models.ForeignKey(
        CRMProduct, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    product_name = models.CharField(max_length=140)
    qty = models.FloatField(default=1)
    rate = models.DecimalField(max_digits=18, decimal_places=6)
    amount = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    discount_percentage = models.FloatField(null=True, blank=True)
    discount_amount = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    net_amount = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)

    class Meta:
        ordering = ["idx"]
        name_strategy = Hash()
        indexes = [
            models.Index(fields=["parenttype", "parent"], name="crm_products_parent_idx"),
        ]


__all__ = [
    "CRMLeadStatus",
    "CRMDealStatus",
    "CRMLeadSource",
    "CRMIndustry",
    "CRMLostReason",
    "CRMCommunicationStatus",
    "CRMTerritory",
    "CRMProduct",
    "CRMProducts",
]
