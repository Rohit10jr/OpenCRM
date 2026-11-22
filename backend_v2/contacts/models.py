"""CONTACTS' documents (specs/CONTACTS.md section 3).

Milestone 1: the reference data. Salutation and Gender
(`backend/frappe_platform/models.py:1842-1870`) and CRM Industry
(`backend/crm_app/models/taxonomy.py:83-91`), each named by its one field.
"""

import contextvars

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete, post_save, pre_delete

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
    """What a Dynamic Link row's `link_title` shows: the linked document's name, as
    `backend/` stores it. The old `_document_title` reads a title field no model there
    declares (`frappe_platform/models.py:1609`), so it always answers the name
    (DECISIONS 65)."""
    del doctype
    return name


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
        saves the address again once its rows are written."""
        creating = self._state.adding
        super().save(*args, user=user, **kwargs)
        if creating:
            self.link_address()
        self.deduplicate_links()
        self.set_link_title()
        self.validate_preferred_address()

    def link_address(self) -> bool:
        """`address.py:79-89` (old `models.py:1971-1990`): an address created without
        links takes the links of the Contact whose email is the owner's."""
        if self.link_rows().exists():
            return False
        contact = Contact._default_manager.filter(email_id=self.owner_id).first()
        if contact is None:
            return False
        rows = DynamicLink._default_manager.filter(
            parenttype="Contact", parent=str(contact.pk)
        ).order_by("idx", "pk")
        for idx, row in enumerate(rows, start=1):
            DynamicLink(
                parenttype="Address",
                parent=str(self.pk),
                parentfield="links",
                idx=idx,
                link_doctype=row.link_doctype,
                link_name=row.link_name,
            ).save(user=self.owner_id)
        return rows.exists()

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
        """Each row's `link_title` is the linked document's name, as `backend/`."""
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


# --- Contact (CONTACTS milestone 3) ----------------------------------------------------------


class ContactName(NameStrategy):
    """`Contact.autoname` (old `frappe_platform/models.py:434-478`, upstream
    `contact.py:54-63`): first, middle and last name stripped and space-joined,
    `company_name` only when all three are empty, plus the links suffix (always "" here:
    Contact has no `links` table), then the collision number. An empty name reaches
    `validate_name`, which answers "No Name Specified for Contact"."""

    def generate(self, instance) -> str:
        base = instance.build_full_name() + instance.name_links_suffix()
        return append_number_if_name_exists(type(instance), base)


def _contact_email_match(email_id: str):
    """§11.2: the User whose `email` is the contact's, ignoring case (v2 stores
    `User.email` lowercased, as upstream); of two, the most recently modified, as
    upstream's `get_value` orders by `modified` (v15 `database.py:623`), and a bare
    field sorts descending (v15 `frappe/database/query.py:329-338`)."""
    from accounts.models import User

    address = str(email_id or "").strip().lower()
    if not address:
        return None
    return (
        User._default_manager.filter(email=address)
        .order_by("-modified", "pk")
        .values_list("pk", flat=True)
        .first()
    )


class Contact(BaseDocument):
    """Frappe `Contact` (old `frappe_platform/models.py:330-527`). `email_id`, `mobile_no`
    and `phone` mirror the primary child rows; the labels are upstream's, since the
    metadata comes from the model."""

    DOCTYPE = "Contact"
    NAME_STRATEGY = ContactName()
    EMAIL_FIELDS = ("email_id",)
    ATTACH_FIELDS = ("image",)
    #: §7a: the two Table rows the old field metadata derives for Contact.
    TABLE_FIELD_LABELS = {"email_ids": "Email IDs", "phone_nos": "Contact Numbers"}
    TEXT_LINK_FIELDS = {
        "salutation": ("contacts.Salutation", "Salutation"),
        "gender": ("contacts.Gender", "Gender"),
    }

    first_name = models.CharField("First Name", max_length=140, blank=True, default="")
    middle_name = models.CharField("Middle Name", max_length=140, blank=True, default="")
    last_name = models.CharField("Last Name", max_length=140, blank=True, default="")
    full_name = models.CharField("Full Name", max_length=420, blank=True, default="")
    salutation = models.CharField("Salutation", max_length=140, blank=True, default="")
    company_name = models.CharField("Company Name", max_length=140, blank=True, default="")
    designation = models.CharField("Designation", max_length=140, blank=True, default="")
    gender = models.CharField("Gender", max_length=140, blank=True, default="")
    image = models.CharField("Image", max_length=500, blank=True, default="")
    status = models.CharField(
        "Status",
        max_length=20,
        choices=[(s, s) for s in ("Passive", "Open", "Replied")],
        blank=True,
        default="Passive",
    )
    #: A-74 (owner): deleting an Address a Contact names is refused, as upstream.
    address = models.ForeignKey(
        Address,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Address",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="User Id",
    )
    email_id = models.CharField("Email Address", max_length=140, blank=True, default="")
    mobile_no = models.CharField("Mobile No", max_length=140, blank=True, default="")
    phone = models.CharField("Phone", max_length=140, blank=True, default="")

    class Meta(BaseDocument.Meta):
        ordering = ["-modified"]

    def build_full_name(self) -> str:
        """`get_full_name` (upstream `contact.py:463`): `company_name` is a fallback,
        never a suffix."""
        parts = [self.first_name, self.middle_name, self.last_name]
        full_name = " ".join(p.strip() for p in parts if p and p.strip())
        if not full_name and self.company_name:
            full_name = self.company_name
        return full_name

    def name_links_suffix(self) -> str:
        """Upstream appends `-<first Dynamic Link's name>` (`contact.py:57-60`); Contact
        has no `links` table here, as in `backend/`, and no CRM path fills one on
        create, so the suffix is always empty."""
        return ""

    def set_primary_email(self) -> None:
        """`contact.py:175-194`: no rows clears the column; two primaries are refused; a
        lone row is made primary and that is persisted; the column mirrors the primary
        row, stripped, or is empty when none is flagged."""
        rows = list(self.email_ids.all().order_by("idx", "pk"))
        if not rows:
            self.email_id = ""
            return
        if len([row for row in rows if row.is_primary]) > 1:
            raise ValidationError("Only one <strong>Email ID</strong> can be set as primary.")
        if len(rows) == 1 and not rows[0].is_primary:
            rows[0].is_primary = True
            type(rows[0])._default_manager.filter(pk=rows[0].pk).update(is_primary=True)
        primary = next((row for row in rows if row.is_primary), None)
        self.email_id = primary.email_id.strip() if primary else ""

    def set_primary(self, fieldname: str) -> None:
        """`contact.py:196-219`, for `phone` and `mobile_no`: a lone row is **not**
        promoted."""
        rows = list(self.phone_nos.all().order_by("idx", "pk"))
        if not rows:
            setattr(self, fieldname, "")
            return
        flag = "is_primary_" + fieldname
        if len([row for row in rows if getattr(row, flag)]) > 1:
            label = fieldname.replace("_", " ").title()  # frappe.unscrub
            raise ValidationError(f"Only one <strong>{label}</strong> can be set as primary.")
        primary = next((row for row in rows if getattr(row, flag)), None)
        setattr(self, fieldname, primary.phone if primary else "")

    def sync_primary_values(self) -> None:
        """The three primary rules `Contact.validate` runs (`contact.py:65-68`), email
        first, then phone, then mobile; then §11.2's `set_user` (`contact.py:71`)."""
        self.set_primary_email()
        self.set_primary("phone")
        self.set_primary("mobile_no")
        self.set_user()

    def set_user(self) -> None:
        """§11.2 (upstream `contact.py:131-133`): an empty `user` is filled from the User
        with the contact's email; an explicit one is kept."""
        if self.user_id or not self.email_id:
            return
        match = _contact_email_match(self.email_id)
        if match is not None:
            self.user_id = match

    def save(self, *args, user, **kwargs):
        self.full_name = self.build_full_name()
        # The mirror columns follow the rows on every save. A row cannot exist before
        # the contact does, so a create clears them; the resource saves again once its
        # rows are written (FINDINGS 8), and a row edit re-syncs through the row signal.
        if self._state.adding:
            self.email_id = self.mobile_no = self.phone = ""
        else:
            self.sync_primary_values()
        return super().save(*args, user=user, **kwargs)


class ContactEmail(BaseDocument):
    """A row of Contact's `email_ids` (old `models.py:529-548`)."""

    DOCTYPE = "Contact Email"
    NAME_STRATEGY = Hash(10)
    IS_CHILD_TABLE = True
    EMAIL_FIELDS = ("email_id",)
    CHILD_FIELDS = (
        "name", "owner", "modified_by", "creation", "modified", "idx", "docstatus",
        "_assign", "_liked_by", "_comments", "_user_tags",
        "parent_contact", "parenttype", "parentfield", "email_id", "is_primary",
    )

    parent_contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="email_ids")
    parenttype = models.CharField(max_length=140, default="Contact")
    parentfield = models.CharField(max_length=140, default="email_ids")
    email_id = models.CharField("Email ID", max_length=140)
    is_primary = models.BooleanField("Is Primary", default=False)

    class Meta(BaseDocument.Meta):
        ordering = ["idx", "name"]


class ContactPhone(BaseDocument):
    """A row of Contact's `phone_nos` (old `models.py:551-572`)."""

    DOCTYPE = "Contact Phone"
    NAME_STRATEGY = Hash(10)
    IS_CHILD_TABLE = True
    CHILD_FIELDS = (
        "name", "owner", "modified_by", "creation", "modified", "idx", "docstatus",
        "_assign", "_liked_by", "_comments", "_user_tags",
        "parent_contact", "parenttype", "parentfield", "phone",
        "is_primary_phone", "is_primary_mobile_no",
    )

    parent_contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="phone_nos")
    parenttype = models.CharField(max_length=140, default="Contact")
    parentfield = models.CharField(max_length=140, default="phone_nos")
    phone = models.CharField("Number", max_length=140)
    is_primary_phone = models.BooleanField("Is Primary Phone", default=False)
    is_primary_mobile_no = models.BooleanField("Is Primary Mobile", default=False)

    class Meta(BaseDocument.Meta):
        ordering = ["idx", "name"]


# Contact's mirror columns follow its child rows (old `models.py:2104-2150`). Rows are
# written after the parent, so a save-time hook would not see them; signals on the child
# tables are the equivalent. They stand down while a document write replaces the rows
# (the contact's own save applies the rules over all of them) and while the contact itself
# is being deleted (FINDINGS 23).
_DELETING = contextvars.ContextVar("contacts.contact.deleting", default=0)


def _contact_deleting(sender, instance, **kwargs):
    _DELETING.set(_DELETING.get() + 1)


def _contact_deleted(sender, instance, **kwargs):
    _DELETING.set(max(_DELETING.get() - 1, 0))


def _resync_contact(sender, instance, **kwargs):
    from core import children

    if children.replacing_children() or _DELETING.get():
        return
    contact = Contact._default_manager.filter(pk=instance.parent_contact_id).first()
    if contact is None:
        return
    contact.sync_primary_values()
    # update(): `modified` is not bumped (§4 (f)); `user` follows the email (§11.2).
    Contact._default_manager.filter(pk=contact.pk).update(
        email_id=contact.email_id,
        mobile_no=contact.mobile_no,
        phone=contact.phone,
        user_id=contact.user_id,
    )


for _child in (ContactEmail, ContactPhone):
    post_save.connect(_resync_contact, sender=_child, dispatch_uid=f"contact.sync.{_child.__name__}")
    post_delete.connect(_resync_contact, sender=_child, dispatch_uid=f"contact.unsync.{_child.__name__}")
pre_delete.connect(_contact_deleting, sender=Contact, dispatch_uid="contact.deleting")
post_delete.connect(_contact_deleted, sender=Contact, dispatch_uid="contact.deleted")
