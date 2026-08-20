"""C1d - converting a lead into a deal.

Port of ``crm/fcrm/doctype/crm_lead/crm_lead.py``: ``convert_to_deal`` (:489-510) and
the four methods it drives - ``create_contact`` (:203-238), ``create_organization``
(:240-262), ``contact_exists`` (:278-301) and ``create_deal`` (:303-378).

The conversion is the only place a single user action writes four doctypes, so it runs
in one transaction: a half-converted lead - marked converted with no deal - is worse
than a failed conversion.

**Upstream uses ``db_set`` throughout**, which writes the column and skips ``validate``.
The Django equivalent is a queryset ``update()``, used below for the same reason: it
keeps the conversion from re-running lead validation, and - a consequence worth naming -
means the status move to "Qualified" writes **no status-change-log row**. That is
upstream behaviour, not an omission here.
"""

from __future__ import annotations

from django.db import transaction

from frappe_core import assignment
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.exceptions import ValidationError
from frappe_core.session import get_current_user

#: ``crm_lead.py:18``. The only renamed field in the whole mapping.
LEAD_DEAL_FIELD_MAP = {"lead_owner": "deal_owner"}

#: ``crm_lead.py:307-329``. Identity, audit, status and SLA columns never copy across;
#: the SLA block is re-added conditionally in :func:`create_deal`.
RESTRICTED_MAP_FIELDS = frozenset(
    {
        "name",
        "naming_series",
        "creation",
        "owner",
        "modified",
        "modified_by",
        "idx",
        "docstatus",
        "status",
        "email",
        "mobile_no",
        "phone",
        "sla",
        "sla_status",
        "response_by",
        "first_response_time",
        "first_responded_on",
        "communication_status",
        "sla_creation",
        "status_change_log",
    }
)

#: Not upstream. Our ``_assign``/``_liked_by``/``_comments``/``_user_tags`` are real
#: columns shared by both models, where Frappe keeps them off the fields list entirely -
#: so an unfiltered copy would clone the lead's assignee cache onto the deal.
_UNDERSCORE_FIELDS = frozenset({"_assign", "_liked_by", "_comments", "_user_tags"})


def contact_exists(lead, throw: bool = True):
    """``crm_lead.py:278-301`` - find a Contact already holding this lead's email/phone.

    Returns the contact name, or ``False``. With ``throw=True`` it raises instead, which
    is what the "create contact" button does; conversion passes ``False`` and reuses the
    match.
    """
    from frappe_platform.models import ContactEmail, ContactPhone

    email_row = (
        ContactEmail.objects.filter(email_id=lead.email).first() if lead.email else None
    )
    phone_row = ContactPhone.objects.filter(phone=lead.phone).first() if lead.phone else None
    mobile_row = (
        ContactPhone.objects.filter(phone=lead.mobile_no).first() if lead.mobile_no else None
    )

    row = email_row or phone_row or mobile_row
    if not row:
        return False

    if email_row:
        label, value = "Email", lead.email
    elif phone_row:
        label, value = "Phone", lead.phone
    else:
        label, value = "Mobile No", lead.mobile_no

    if throw:
        raise ValidationError(f"Contact already exists with {label}: {value}")

    return row.parent_contact_id


def update_lead_contact(lead, contact_name) -> None:
    """``crm_lead.py:264-276`` - copy the matched contact's details back onto the lead.

    ``db.set_value`` upstream, so no validation and no ``modified`` bump.
    """
    from crm_app.models import CRMLead
    from frappe_platform.models import Contact

    contact = Contact.objects.get(pk=contact_name)
    CRMLead._default_manager.filter(pk=lead.pk).update(
        salutation=contact.salutation,
        first_name=contact.first_name,
        last_name=contact.last_name,
        email=contact.email_id,
        mobile_no=contact.mobile_no,
    )


def create_contact(lead, existing_contact=None, throw: bool = True):
    """``crm_lead.py:203-238``."""
    from frappe_platform.models import Contact, ContactEmail, ContactPhone

    existing = existing_contact or contact_exists(lead, throw)
    if existing:
        update_lead_contact(lead, existing)
        return existing

    contact = Contact.objects.create(
        first_name=lead.first_name or lead.lead_name,
        last_name=lead.last_name,
        salutation=lead.salutation,
        gender=lead.gender,
        designation=lead.job_title,
        company_name=lead.organization,
        image=lead.image or "",
    )

    if lead.email:
        ContactEmail.objects.create(
            parent_contact=contact, email_id=lead.email, is_primary=True
        )
    if lead.phone:
        ContactPhone.objects.create(
            parent_contact=contact, phone=lead.phone, is_primary_phone=True
        )
    if lead.mobile_no:
        ContactPhone.objects.create(
            parent_contact=contact, phone=lead.mobile_no, is_primary_mobile_no=True
        )

    contact.sync_primary_values()
    contact.save(update_fields=["email_id", "mobile_no", "phone"])
    return contact.pk


def create_organization(lead, existing_organization=None):
    """``crm_lead.py:240-262``.

    Returns ``None`` when the lead names no organization - the deal simply has none.
    """
    from crm_app.models import CRMLead, CRMOrganization

    if not lead.organization and not existing_organization:
        return None

    existing = existing_organization or (
        CRMOrganization.objects.filter(organization_name=lead.organization)
        .values_list("pk", flat=True)
        .first()
    )
    if existing:
        # db_set upstream: record the resolved name on the lead without revalidating.
        CRMLead._default_manager.filter(pk=lead.pk).update(organization=existing)
        return existing

    organization = CRMOrganization.objects.create(
        organization_name=lead.organization,
        website=lead.website,
        territory_id=lead.territory_id,
        industry_id=lead.industry_id,
        annual_revenue=lead.annual_revenue,
    )
    return organization.pk


def _copyable_fields(lead_model, deal_model) -> dict[str, str]:
    """Lead field name -> deal field name, for everything that should carry over.

    Upstream walks ``self.meta.fields`` and skips layout fieldtypes; our models have no
    layout fields at all (phase 1 dropped them), so the equivalent is the concrete field
    set minus the restricted names.

    Custom fields are not handled: ``get_matching_custom_deal_field``
    (``crm_lead.py:524-528``) resolves user-defined columns by label and type, and this
    port has no custom-field system for them to live in.
    """
    deal_names = {f.name for f in deal_model._meta.get_fields() if getattr(f, "concrete", False)}
    mapping: dict[str, str] = {}

    for field in lead_model._meta.get_fields():
        if not getattr(field, "concrete", False):
            continue
        name = field.name
        if name in RESTRICTED_MAP_FIELDS or name in _UNDERSCORE_FIELDS:
            continue

        target = LEAD_DEAL_FIELD_MAP.get(name)
        if target:
            if target in deal_names:
                mapping[name] = target
            continue
        if name in deal_names:
            mapping[name] = name

    return mapping


def create_deal(lead, contact, organization, overrides: dict | None = None):
    """``crm_lead.py:303-378``."""
    from crm_app.models import CRMContacts, CRMDeal

    payload: dict = {}
    for source, target in _copyable_fields(type(lead), CRMDeal).items():
        if target == "organization":
            # Free text on the lead, a Link on the deal - so the resolved organization
            # replaces the typed value (crm_lead.py:349-350).
            continue
        field = type(lead)._meta.get_field(source)
        if field.is_relation:
            payload[f"{target}_id"] = getattr(lead, f"{source}_id")
        else:
            payload[target] = getattr(lead, source)

    payload["organization_id"] = organization
    payload["lead_id"] = lead.pk

    if lead.first_responded_on:
        payload.update(
            sla_id=lead.sla_id,
            sla_creation=lead.sla_creation,
            response_by=lead.response_by,
            sla_status=lead.sla_status,
            communication_status_id=lead.communication_status_id,
            first_response_time=lead.first_response_time,
            first_responded_on=lead.first_responded_on,
        )

    if overrides:
        payload.update(overrides)

    deal = CRMDeal.objects.create(**payload)

    if contact:
        CRMContacts.objects.create(parent_deal=deal, contact_id=contact, is_primary=True)
        deal.sync_contact_fields()

    # Carry the lead's assignees over, skipping the owner - already assigned by
    # CRMDeal.save (crm_lead.py:374-376).
    for user in assignment.get_assigned_users("CRM Lead", lead.pk):
        if user and user != deal.deal_owner_id:
            deal.assign_agent(user)

    return deal


@transaction.atomic
def convert_to_deal(
    lead,
    *,
    deal: dict | None = None,
    existing_contact=None,
    existing_organization=None,
    ignore_permissions: bool = False,
):
    """``crm_lead.py:489-510``. Returns the created :class:`CRMDeal`.

    Upstream returns the deal *name*; we return the object, which the caller can still
    read ``.name`` from. Phase 3's endpoint is where the string is needed.
    """
    from crm_app.models import CRMCommunicationStatus, CRMLead, CRMLeadStatus
    from frappe_core import permissions

    if not ignore_permissions:
        if not permissions.check_object_permission(lead, "write", get_current_user()):
            raise FrappePermissionError("Not allowed to convert Lead to Deal")

    updates: dict = {"converted": True}
    if CRMLeadStatus.objects.filter(pk="Qualified").exists():
        updates["status_id"] = "Qualified"
    if lead.sla_id and CRMCommunicationStatus.objects.filter(pk="Replied").exists():
        updates["communication_status_id"] = "Replied"

    # update() rather than save(): upstream uses db_set, so no validation runs and - a
    # direct consequence - the move to "Qualified" writes no status-change-log row.
    CRMLead._default_manager.filter(pk=lead.pk).update(**updates)
    lead.refresh_from_db()

    contact = create_contact(lead, existing_contact, throw=False)
    organization = create_organization(lead, existing_organization)
    lead.refresh_from_db()

    return create_deal(lead, contact, organization, deal)
