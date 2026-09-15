"""``crm.fcrm.doctype.crm_deal.crm_deal.*`` and ``crm.fcrm.doctype.crm_deal.api.*``.

The five deal endpoints the frontend calls by their doctype-module path: the "Create
Deal" modal (``create_deal``), the contacts panel on the deal page
(``get_deal_contacts``) and its three buttons (``add_contact``, ``remove_contact``,
``set_primary_contact``). Ported from ``crm/fcrm/doctype/crm_deal/crm_deal.py:358-475``
and ``crm/fcrm/doctype/crm_deal/api.py`` (main). They were the first of the twenty
paths ``docs/http/14_unserved_paths.http`` recorded as unserved.

Upstream inserts the deal, the contact and the organization with
``ignore_permissions=True``; here the caller needs create permission on CRM Deal, as
every other create path in the port requires, and the same on the rows it creates on
the way. Everything else follows the source: which fields go where, the "first name or
last name or email or mobile" test for whether a contact is wanted, and the
match-by-email-then-phone rule for reusing one.
"""

from __future__ import annotations

from django.db import transaction

from frappe_core import children, permissions, registry
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.query import parse_json_param
from frappe_core.session import get_current_user
from frappe_core.views import _candidate_instance
from frappe_core.whitelist import whitelist


def _deal_for_write(name: str, denial: str):
    """``frappe.has_permission("CRM Deal", "write", deal)`` with upstream's sentence."""
    from crm_app.models import CRMDeal

    deal = CRMDeal._default_manager.filter(pk=name).first()
    if deal is None or not permissions.check_object_permission(deal, "write", get_current_user()):
        raise FrappePermissionError(denial)
    return deal


def _contact_rows(deal) -> list[dict]:
    return [
        {"contact": row.contact_id, "is_primary": row.is_primary}
        for row in deal.contacts.all().order_by("idx", "pk")
    ]


def _write_contact_rows(deal, rows: list[dict]) -> None:
    """``deal.contacts = [...]; deal.save()``: the rows are replaced and the deal saved,
    so its validate - primary contact, derived email and phone - runs over them."""
    spec = children.discover_child_tables(type(deal))["contacts"]
    with transaction.atomic():
        children.replace_children(deal, "contacts", spec, rows)
        deal.refresh_from_db()
        deal.save()


@whitelist("crm.fcrm.doctype.crm_deal.crm_deal.add_contact", methods=("POST",))
def add_contact(deal: str, contact: str):
    """``crm_deal.py:358-366``."""
    instance = _deal_for_write(deal, "Not allowed to add contact to Deal")
    _write_contact_rows(instance, _contact_rows(instance) + [{"contact": contact}])
    return True


@whitelist("crm.fcrm.doctype.crm_deal.crm_deal.remove_contact", methods=("POST",))
def remove_contact(deal: str, contact: str):
    """``crm_deal.py:369-377``."""
    instance = _deal_for_write(deal, "Not allowed to remove contact from Deal")
    rows = [row for row in _contact_rows(instance) if row["contact"] != contact]
    _write_contact_rows(instance, rows)
    return True


@whitelist("crm.fcrm.doctype.crm_deal.crm_deal.set_primary_contact", methods=("POST",))
def set_primary_contact(deal: str, contact: str):
    """``crm_deal.py:380-388``: the named contact becomes primary, the rest are demoted."""
    instance = _deal_for_write(deal, "Not allowed to set primary contact for Deal")
    with transaction.atomic():
        instance.set_primary_contact(contact)
        instance.save()
    return True


@whitelist("crm.fcrm.doctype.crm_deal.api.get_deal_contacts")
def get_deal_contacts(name: str):
    """``crm/fcrm/doctype/crm_deal/api.py``: the contacts panel's rows, each contact's
    own record flattened to the six keys the panel reads. Rows whose contact is gone
    are skipped, as upstream skips them. Read permission on the deal is required here
    where upstream asks nothing; the panel only opens on a deal the user can see."""
    from crm_app.api.doc import _require_readable
    from crm_app.models import CRMContacts
    from frappe_platform.models import Contact

    _require_readable("CRM Deal", name)
    rows = (
        CRMContacts._default_manager.filter(parent_deal_id=name)
        .exclude(contact__isnull=True)
        .order_by("idx", "pk")
        .values_list("contact_id", "is_primary")
    )
    seen: set[str] = set()
    deal_contacts = []
    for contact_name, is_primary in rows:
        if contact_name in seen:
            continue
        seen.add(contact_name)
        contact = Contact._default_manager.filter(pk=contact_name).first()
        if contact is None:
            continue
        deal_contacts.append(
            {
                "name": contact.pk,
                "image": contact.image,
                "full_name": contact.full_name,
                "email": contact.email_id,
                "mobile_no": contact.mobile_no,
                "is_primary": is_primary,
            }
        )
    return deal_contacts


# --- create_deal: crm_deal.py:391-475 -----------------------------------------------------


def contact_exists(doc: dict):
    """``crm_deal.py:415-425``: a contact that already holds the email, else the mobile
    number, is reused rather than duplicated. Returns its name, or False."""
    from frappe_platform.models import ContactEmail, ContactPhone

    email_row = (
        ContactEmail._default_manager.filter(email_id=doc.get("email")).first()
        if doc.get("email")
        else None
    )
    if email_row is not None:
        return email_row.parent_contact_id
    phone_row = (
        ContactPhone._default_manager.filter(phone=doc.get("mobile_no")).first()
        if doc.get("mobile_no")
        else None
    )
    if phone_row is not None:
        return phone_row.parent_contact_id
    return False


def create_contact(doc: dict) -> str:
    """``crm_deal.py:428-453``."""
    from frappe_platform.models import Contact, ContactEmail, ContactPhone

    existing = contact_exists(doc)
    if existing:
        return existing
    contact = Contact._default_manager.create(
        first_name=doc.get("first_name") or "",
        last_name=doc.get("last_name") or "",
        salutation=doc.get("salutation") or "",
        company_name=doc.get("organization") or doc.get("organization_name") or "",
        gender=doc.get("gender") or "",
    )
    if doc.get("email"):
        ContactEmail._default_manager.create(
            parent_contact=contact, email_id=doc["email"], is_primary=True
        )
    if doc.get("mobile_no"):
        ContactPhone._default_manager.create(
            parent_contact=contact, phone=doc["mobile_no"], is_primary_mobile_no=True
        )
    # ``contact.reload()`` upstream: the rows' hooks have set the mirror columns.
    contact.refresh_from_db()
    contact.save()
    return contact.pk


def create_organization(doc: dict):
    """``crm_deal.py:391-412``: nothing without an ``organization_name``; an existing
    organization of that name is reused."""
    from crm_app.models import CRMOrganization

    if not doc.get("organization_name"):
        return None
    existing = (
        CRMOrganization._default_manager.filter(organization_name=doc["organization_name"])
        .values_list("pk", flat=True)
        .first()
    )
    if existing:
        return existing
    organization = CRMOrganization._default_manager.create(
        organization_name=doc["organization_name"],
        website=doc.get("website") or "",
        territory_id=doc.get("territory") or None,
        industry_id=doc.get("industry") or None,
        annual_revenue=doc.get("annual_revenue") or None,
    )
    return organization.pk


@whitelist("crm.fcrm.doctype.crm_deal.crm_deal.create_deal", methods=("POST",))
def create_deal(doc=None, **extra):
    """``crm_deal.py:456-475``: the "Create Deal" modal's one call. A contact is made
    (or reused) when the form gave a person's name, email or mobile and no existing
    contact; an organization when it gave an ``organization_name`` and no existing
    organization; then the deal, with that contact as its primary. Returns the name."""
    payload = parse_json_param(doc, doc)
    if not isinstance(payload, dict):
        payload = {}
    payload = dict(payload)

    entry = registry.get_entry("CRM Deal")
    deal_fields = {f.name for f in entry.model._meta.get_fields() if getattr(f, "concrete", False)}
    if not permissions.check_object_permission(
        _candidate_instance(entry, {k: v for k, v in payload.items() if k in deal_fields}),
        "create",
        get_current_user(),
    ):
        raise FrappePermissionError("Not permitted to create CRM Deal", title="Not Permitted")

    with transaction.atomic():
        contact = payload.get("contact")
        if not contact and (
            payload.get("first_name")
            or payload.get("last_name")
            or payload.get("email")
            or payload.get("mobile_no")
        ):
            contact = create_contact(payload)
        organization = payload.get("organization") or create_organization(payload)

        # ``doc.pop("organization")`` then ``deal.update(doc)``: everything else the modal
        # sent that is a deal field stays, including ``contact`` when it chose an existing
        # one - CRM Deal has that Link (crm_deal.json), and upstream stores it as sent.
        data = {k: v for k, v in payload.items() if k in deal_fields and k != "organization"}
        data["organization"] = organization
        data["contacts"] = [{"contact": contact, "is_primary": 1}] if contact else []

        serializer = entry.get_serializer_class()(data=data)
        serializer.is_valid(raise_exception=True)
        deal = serializer.save()
    return deal.pk
