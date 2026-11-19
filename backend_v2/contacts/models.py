"""CONTACTS' documents (specs/CONTACTS.md section 3).

Milestone 1: the reference data. Salutation and Gender
(`backend/frappe_platform/models.py:1842-1870`) and CRM Industry
(`backend/crm_app/models/taxonomy.py:83-91`), each named by its one field.
"""

from django.db import models

from core.exceptions import ValidationError
from core.models import BaseDocument
from core.naming import FieldValue, Hash, NameStrategy, append_number_if_name_exists


class Salutation(BaseDocument):
    """The Link target of `salutation` on a contact, a lead and a deal (FINDINGS 66)."""

    DOCTYPE = "Salutation"
    NAME_STRATEGY = FieldValue("salutation", label="Salutation")

    salutation = models.CharField("Salutation", max_length=140, unique=True)

    class Meta(BaseDocument.Meta):
        ordering = ["name"]


class Gender(BaseDocument):
    """The Link target of `gender` on a contact, a lead and a deal (FINDINGS 66)."""

    DOCTYPE = "Gender"
    NAME_STRATEGY = FieldValue("gender", label="Gender")

    gender = models.CharField("Gender", max_length=140, unique=True)

    class Meta(BaseDocument.Meta):
        ordering = ["name"]


class CRMIndustry(BaseDocument):
    """An organization's industry, a vocabulary (reviewed-open)."""

    DOCTYPE = "CRM Industry"
    NAME_STRATEGY = FieldValue("industry", label="Industry")

    industry = models.CharField(max_length=140, blank=True, default="")

    class Meta(BaseDocument.Meta):
        ordering = ["name"]


class DynamicLink(BaseDocument):
    """Frappe's "this document points at that one" child table (old
    `frappe_platform/models.py:1560-1598`): polymorphic on both ends, so it carries
    `parent`/`parenttype` rather than a foreign key. `link_name` is a dynamic link on
    `link_doctype`, which the delete check and the linked-documents scan read."""

    DOCTYPE = "Dynamic Link"
    NAME_STRATEGY = Hash(10)
    IS_CHILD_TABLE = True
    DYNAMIC_LINK_FIELDS = (("link_doctype", "link_name"),)
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
        "parenttype",
        "parentfield",
        "parent",
        "link_doctype",
        "link_name",
        "link_title",
    )

    parenttype = models.CharField(max_length=140, blank=True, default="", db_index=True)
    parentfield = models.CharField(max_length=140, blank=True, default="")
    parent = models.CharField(max_length=140, blank=True, default="", db_index=True)
    link_doctype = models.CharField(max_length=140, db_index=True)
    link_name = models.CharField(max_length=140, db_index=True)
    link_title = models.CharField(max_length=280, blank=True, default="")

    class Meta(BaseDocument.Meta):
        ordering = ["idx"]
        indexes = [
            models.Index(fields=["parenttype", "parent"], name="dynamic_link_parent_idx"),
            models.Index(fields=["link_doctype", "link_name"], name="dynamic_link_target_idx"),
        ]


#: `address.json` `address_type` options, in order.
ADDRESS_TYPES = (
    "Billing",
    "Shipping",
    "Office",
    "Personal",
    "Plant",
    "Postal",
    "Shop",
    "Subsidiary",
    "Warehouse",
    "Current",
    "Permanent",
    "Other",
)


class AddressName(NameStrategy):
    """`Address.autoname` (old `models.py:1944-1955`): `<title>-<type>`, and on a
    collision the numbered form, `-1`, `-2` …"""

    def generate(self, instance) -> str:
        title = (instance.address_title or "").strip()
        if not title:
            raise ValidationError("Address Title is mandatory.")
        base = f"{title}-{str(instance.address_type or '').strip()}"
        return append_number_if_name_exists(type(instance), base)


def document_title(doctype: str, name: str) -> str:
    """`Document.get_title`: the doctype's title field's value, else the name (old
    `_document_title`); what a Dynamic Link row's `link_title` shows (DECISIONS 60)."""
    from configuration.field_meta import get_title_field
    from core.doctypes import model_for_doctype

    model = model_for_doctype(doctype)
    title_field = get_title_field(doctype) if model is not None else None
    if not title_field:
        return name
    value = model._default_manager.filter(pk=name).values_list(title_field, flat=True).first()
    return value or name


class Address(BaseDocument):
    """Frappe `Address`, the target of the `address` Link on CRM Organization and
    Contact (old `models.py:1890-2030`; FINDINGS 45). The labels are upstream's: its
    metadata comes from the model. `get_address_display` is not ported."""

    DOCTYPE = "Address"
    NAME_STRATEGY = AddressName()
    POLYMORPHIC_CHILD_TABLES = {"links": "contacts.DynamicLink"}
    EMAIL_FIELDS = ("email_id",)
    #: `address.py:92`: the two flags only one address per linked document may carry.
    PREFERRED_FLAGS = ("is_primary_address", "is_shipping_address")

    address_title = models.CharField("Address Title", max_length=140, blank=True, default="")
    address_type = models.CharField(
        "Address Type", max_length=20, choices=[(t, t) for t in ADDRESS_TYPES]
    )
    address_line1 = models.CharField("Address Line 1", max_length=240)
    address_line2 = models.CharField("Address Line 2", max_length=240, blank=True, default="")
    city = models.CharField("City/Town", max_length=140)
    county = models.CharField("County", max_length=140, blank=True, default="")
    state = models.CharField("State/Province", max_length=140, blank=True, default="")
    country = models.ForeignKey(
        "configuration.Country",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Country",
    )
    pincode = models.CharField("Postal Code", max_length=140, blank=True, default="")
    email_id = models.CharField("Email Address", max_length=140, blank=True, default="")
    phone = models.CharField("Phone", max_length=140, blank=True, default="")
    fax = models.CharField("Fax", max_length=140, blank=True, default="")
    is_primary_address = models.BooleanField("Preferred Billing Address", default=False)
    is_shipping_address = models.BooleanField("Preferred Shipping Address", default=False)
    disabled = models.BooleanField("Disabled", default=False)

    class Meta(BaseDocument.Meta):
        ordering = ["name"]

    def link_rows(self):
        return DynamicLink._default_manager.filter(parenttype="Address", parent=str(self.pk)).order_by(
            "idx", "pk"
        )

    @classmethod
    def linked_to(cls, link_doctype=None, link_name=None) -> list[str]:
        """The names of the addresses whose Dynamic Link rows name that document (old
        `address_query`, `crm_app/api/client.py:64-81`)."""
        rows = DynamicLink._default_manager.filter(parenttype="Address")
        if link_doctype:
            rows = rows.filter(link_doctype=link_doctype)
        if link_name:
            rows = rows.filter(link_name=link_name)
        return list(rows.values_list("parent", flat=True).distinct())

    def save(self, *args, user, **kwargs):
        """`address.py:73-77`, `validate`, over the rows now in the table: the resource
        saves the address again once its rows are written. Taking the links of the
        Contact whose email is the owner's comes with Contact (milestone 3)."""
        super().save(*args, user=user, **kwargs)
        self.deduplicate_links()
        self.set_link_title()
        self.validate_preferred_address()

    def deduplicate_links(self) -> None:
        """`deduplicate_dynamic_links`: one row per (doctype, name), the first kept."""
        seen: set[tuple[str, str]] = set()
        for row in self.link_rows():
            key = (row.link_doctype, row.link_name)
            if key in seen:
                row.delete()
            else:
                seen.add(key)

    def set_link_title(self) -> None:
        """Each row's `link_title` is the linked document's title, or its name."""
        for row in self.link_rows():
            title = document_title(row.link_doctype, row.link_name)
            if row.link_title != title:
                DynamicLink._default_manager.filter(pk=row.pk).update(link_title=title)

    def validate_preferred_address(self) -> None:
        """`address.py:91-100`: a preferred flag set here is cleared on every other
        enabled address linked to the same document."""
        for flag in self.PREFERRED_FLAGS:
            if not getattr(self, flag):
                continue
            for row in self.link_rows():
                others = (
                    DynamicLink._default_manager.filter(
                        parenttype="Address", link_doctype=row.link_doctype, link_name=row.link_name
                    )
                    .exclude(parent=str(self.pk))
                    .values_list("parent", flat=True)
                )
                type(self)._default_manager.filter(
                    pk__in=list(others), disabled=False, **{flag: True}
                ).update(**{flag: False})
