"""C1d - lead to deal conversion.

Ports ``crm_lead.py:489-510`` and the four methods it drives. The conversion is the only
user action that writes four doctypes at once, so it runs in one transaction.
"""

import pytest

from crm_app.conversion import contact_exists, convert_to_deal
from crm_app.models import (
    CRMCommunicationStatus,
    CRMContacts,
    CRMDeal,
    CRMDealStatus,
    CRMLead,
    CRMLeadStatus,
    CRMOrganization,
    CRMStatusChangeLog,
)
from frappe_core.exceptions import ValidationError
from frappe_core.session import session_user
from frappe_platform.models import Contact, ContactEmail, ContactPhone

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def statuses(administrator):
    with session_user(administrator.name):
        return {
            "new": CRMLeadStatus.objects.create(lead_status="New", type="Open"),
            "qualified": CRMLeadStatus.objects.create(lead_status="Qualified", type="Open"),
            "deal": CRMDealStatus.objects.create(deal_status="Qualification", type="Open"),
        }


@pytest.fixture
def lead(alice, statuses):
    with session_user(alice.name):
        return CRMLead.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            mobile_no="555-0100",
            organization="Acme Corp",
            website="acme.example",
            job_title="CTO",
            lead_owner=alice,
            status=statuses["new"],
        )


# --- the happy path ---------------------------------------------------------------


def test_conversion_creates_a_deal(alice, lead):
    with session_user(alice.name):
        deal = convert_to_deal(lead)

    assert isinstance(deal, CRMDeal)
    assert deal.lead_id == lead.pk


def test_the_lead_is_marked_converted_and_qualified(alice, lead):
    with session_user(alice.name):
        convert_to_deal(lead)

    lead.refresh_from_db()
    assert lead.converted is True
    assert lead.status_id == "Qualified"


def test_a_contact_is_created_from_the_lead(alice, lead):
    with session_user(alice.name):
        convert_to_deal(lead)

    contact = Contact.objects.get(first_name="Ada", last_name="Lovelace")
    assert contact.email_id == "ada@example.com"
    assert ContactPhone.objects.filter(parent_contact=contact, phone="555-0100").exists()


def test_an_organization_is_created_from_the_lead(alice, lead):
    with session_user(alice.name):
        deal = convert_to_deal(lead)

    org = CRMOrganization.objects.get(pk="Acme Corp")
    assert org.website == "acme.example"
    assert deal.organization_id == "Acme Corp"


def test_the_contact_is_linked_to_the_deal_as_primary(alice, lead):
    with session_user(alice.name):
        deal = convert_to_deal(lead)

    row = CRMContacts.objects.get(parent_deal=deal)
    assert row.is_primary is True
    deal.refresh_from_db()
    assert deal.email == "ada@example.com"


# --- field mapping -----------------------------------------------------------------


def test_lead_owner_becomes_deal_owner(alice, lead):
    """The one renamed field - ``LEAD_DEAL_FIELD_MAP`` (``crm_lead.py:18``)."""
    with session_user(alice.name):
        deal = convert_to_deal(lead)

    assert deal.deal_owner_id == alice.name


def test_ordinary_fields_carry_over(alice, lead):
    with session_user(alice.name):
        deal = convert_to_deal(lead)

    assert deal.first_name == "Ada"
    assert deal.last_name == "Lovelace"
    assert deal.job_title == "CTO"
    assert deal.website == "acme.example"


def test_restricted_fields_do_not_carry_over(alice, lead):
    """``crm_lead.py:307-329`` - identity, status and SLA columns are excluded.

    The deal gets its own status from ``validate_status``, not the lead's.
    """
    with session_user(alice.name):
        deal = convert_to_deal(lead)

    assert deal.status_id == "Qualification"
    assert deal.pk != lead.pk
    assert deal.sla_id is None


def test_the_assign_cache_is_not_cloned(alice, lead):
    """Not upstream's concern - Frappe keeps ``_assign`` off the fields list entirely.

    Ours is a real column shared by both models, so an unfiltered copy would hand the
    deal the lead's assignee cache before its own assignment ran.
    """
    with session_user(alice.name):
        deal = convert_to_deal(lead)

    deal.refresh_from_db()
    assert deal._assign == [alice.name]


# --- reuse of existing records ------------------------------------------------------


def test_an_existing_contact_is_reused(alice, lead):
    with session_user(alice.name):
        existing = Contact.objects.create(first_name="Ada", last_name="Lovelace")
        ContactEmail.objects.create(
            parent_contact=existing, email_id="ada@example.com", is_primary=True
        )

        convert_to_deal(lead)

    assert Contact.objects.filter(first_name="Ada").count() == 1


def test_an_existing_organization_is_reused(alice, lead):
    with session_user(alice.name):
        CRMOrganization.objects.create(organization_name="Acme Corp", website="old.example")
        deal = convert_to_deal(lead)

    assert CRMOrganization.objects.filter(organization_name="Acme Corp").count() == 1
    assert deal.organization_id == "Acme Corp"
    # Reuse, not overwrite: the existing record keeps its own values.
    assert CRMOrganization.objects.get(pk="Acme Corp").website == "old.example"


def test_a_lead_with_no_organization_converts_without_one(alice, statuses):
    with session_user(alice.name):
        # lead_owner is the access column (decision 19) - a lead without one is
        # invisible to its own creator, so the permission check would reject it.
        bare = CRMLead.objects.create(
            first_name="Solo", email="solo@example.com", status=statuses["new"], lead_owner=alice
        )
        deal = convert_to_deal(bare)

    assert deal.organization_id is None


# --- contact_exists -----------------------------------------------------------------


def test_contact_exists_finds_by_email(alice, lead):
    with session_user(alice.name):
        existing = Contact.objects.create(first_name="Ada")
        ContactEmail.objects.create(parent_contact=existing, email_id="ada@example.com")

    assert contact_exists(lead, throw=False) == existing.pk


def test_contact_exists_raises_with_the_upstream_message(alice, lead):
    with session_user(alice.name):
        existing = Contact.objects.create(first_name="Ada")
        ContactEmail.objects.create(parent_contact=existing, email_id="ada@example.com")

    with pytest.raises(ValidationError, match="Contact already exists with Email: ada@example.com"):
        contact_exists(lead, throw=True)


def test_contact_exists_falls_back_to_mobile(alice, lead):
    with session_user(alice.name):
        existing = Contact.objects.create(first_name="Ada")
        ContactPhone.objects.create(parent_contact=existing, phone="555-0100")

    assert contact_exists(lead, throw=False) == existing.pk


def test_contact_exists_returns_false_when_nothing_matches(alice, lead):
    assert contact_exists(lead, throw=False) is False


# --- SLA carry-over ------------------------------------------------------------------


def test_the_sla_block_transfers_only_once_responded(alice, lead):
    """``crm_lead.py:355-366``. The SLA columns are excluded from the generic copy and
    re-added *only* when the lead already has a first response."""
    from django.utils import timezone

    CRMLead.objects.filter(pk=lead.pk).update(
        first_responded_on=timezone.now(), first_response_time=120
    )
    lead.refresh_from_db()

    with session_user(alice.name):
        deal = convert_to_deal(lead)

    assert deal.first_responded_on is not None
    assert deal.first_response_time == 120


def test_no_sla_block_without_a_first_response(alice, lead):
    with session_user(alice.name):
        deal = convert_to_deal(lead)

    assert deal.first_responded_on is None


# --- assignment carry-over ------------------------------------------------------------


def test_lead_assignees_transfer_to_the_deal(alice, lead, make_user):
    helper = make_user("helper@example.com", roles=["Sales User"])
    with session_user(alice.name):
        lead.assign_agent(helper.name)
        deal = convert_to_deal(lead)

    from frappe_core.assignment import get_assigned_users

    assert helper.name in get_assigned_users("CRM Deal", deal.pk)


# --- the status-log consequence --------------------------------------------------------


def test_the_move_to_qualified_writes_no_status_log(alice, lead):
    """Upstream sets the status with ``db_set``, which skips ``validate`` - so
    ``add_status_change_log`` never runs for the conversion. Faithful, and surprising
    enough to pin: the lead's history shows no move to Qualified.
    """
    before = CRMStatusChangeLog.objects.filter(parenttype="CRM Lead", parent=lead.pk).count()

    with session_user(alice.name):
        convert_to_deal(lead)

    after = CRMStatusChangeLog.objects.filter(parenttype="CRM Lead", parent=lead.pk).count()
    assert after == before


# --- overrides and atomicity -------------------------------------------------------------


def test_caller_overrides_win(alice, lead, make_user):
    other = make_user("other@example.com", roles=["Sales User"])
    with session_user(alice.name):
        deal = convert_to_deal(lead, deal={"deal_owner_id": other.name})

    assert deal.deal_owner_id == other.name


def test_a_failure_rolls_the_whole_conversion_back(alice, lead, monkeypatch):
    """A lead marked converted with no deal is worse than a failed conversion."""
    import crm_app.conversion as conversion

    def boom(*args, **kwargs):
        raise RuntimeError("deal creation failed")

    monkeypatch.setattr(conversion, "create_deal", boom)

    with session_user(alice.name), pytest.raises(RuntimeError):
        convert_to_deal(lead)

    lead.refresh_from_db()
    assert lead.converted is False
    assert not CRMDeal.objects.filter(lead_id=lead.pk).exists()
    assert not CRMOrganization.objects.filter(organization_name="Acme Corp").exists()
