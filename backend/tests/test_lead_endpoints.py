"""crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal - "Convert to Deal" on a lead and
the list's bulk action (crm_lead.py:494-516). The conversion has lived in
crm_app.conversion since phase 3; nothing exposed it at this name, so the button
answered 404 (docs/http/14_unserved_paths.http, 1.2).
"""

import pytest

from crm_app.models import CRMContacts, CRMDeal, CRMDealStatus, CRMLead, CRMLeadStatus, CRMOrganization
from frappe_core.session import session_user
from frappe_platform.models import Contact, ContactEmail

pytestmark = pytest.mark.django_db

PATH = "/api/method/crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal"


@pytest.fixture(autouse=True)
def statuses(administrator):
    with session_user(administrator.name):
        CRMLeadStatus.objects.create(lead_status="New", type="Open")
        CRMLeadStatus.objects.create(lead_status="Qualified", type="Open")
        CRMDealStatus.objects.create(deal_status="Qualification", type="Open")


@pytest.fixture
def lead(alice):
    with session_user(alice.name):
        return CRMLead.objects.create(
            first_name="ZZ Ada", last_name="Byron", email="ada@zz.test", mobile_no="+1 555",
            organization="ZZ Analytical", lead_owner=alice,
        )


def test_convert_to_deal_creates_the_deal_and_reports_its_name(auth_api, lead):
    response = auth_api.post(PATH, {"lead": lead.name, "deal": {"next_step": "ZZ demo"}}, format="json")
    assert response.status_code == 200, response.content[:300]
    deal = CRMDeal.objects.get(pk=response.json()["message"])
    assert deal.lead_id == lead.name
    assert deal.next_step == "ZZ demo"
    assert deal.organization_id == "ZZ Analytical"
    assert CRMContacts.objects.get(parent_deal=deal).contact.email_id == "ada@zz.test"
    lead.refresh_from_db()
    assert lead.converted is True
    assert lead.status_id == "Qualified"


def test_an_existing_contact_and_organization_are_used_instead(auth_api, lead, administrator):
    with session_user(administrator.name):
        org = CRMOrganization.objects.create(organization_name="ZZ Other Org")
        contact = Contact.objects.create(first_name="ZZ Known", last_name="Person")
        ContactEmail.objects.create(parent_contact=contact, email_id="known@zz.test", is_primary=True)
    response = auth_api.post(
        PATH,
        {"lead": lead.name, "existing_contact": contact.pk, "existing_organization": org.pk},
        format="json",
    )
    deal = CRMDeal.objects.get(pk=response.json()["message"])
    assert deal.organization_id == org.pk
    assert CRMContacts.objects.get(parent_deal=deal).contact_id == contact.pk


def test_the_deal_form_may_arrive_as_json_or_empty(auth_api, lead, alice):
    """A JSON string is decoded like every other ``call()`` argument; an empty string
    means no overrides, which is what the modal sends when nothing was filled in."""
    response = auth_api.post(PATH, {"lead": lead.name, "deal": '{"next_step": "ZZ str"}'}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert CRMDeal.objects.get(pk=response.json()["message"]).next_step == "ZZ str"

    with session_user(alice.name):
        second = CRMLead.objects.create(first_name="ZZ Second", lead_owner=alice)
    response = auth_api.post(PATH, {"lead": second.name, "deal": ""}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert CRMDeal.objects.get(pk=response.json()["message"]).next_step == ""


def test_converting_needs_write_on_the_lead(api_as, bob, lead):
    response = api_as(bob).post(PATH, {"lead": lead.name}, format="json")
    assert response.status_code == 403
    assert response.json()["message"] == "Not allowed to convert Lead to Deal"


def test_a_missing_lead_is_not_found(auth_api):
    response = auth_api.post(PATH, {"lead": "CRM-LEAD-2099-00001"}, format="json")
    assert response.status_code == 404
    assert response.json()["exc_type"] == "DoesNotExistError"
