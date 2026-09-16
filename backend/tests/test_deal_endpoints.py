"""The deal endpoints the frontend calls by their doctype-module path: create_deal,
get_deal_contacts, add_contact, remove_contact, set_primary_contact.

Ported from crm/fcrm/doctype/crm_deal/crm_deal.py:358-475 and crm_deal/api.py (main).
Until now every one of them answered 404 (docs/http/14_unserved_paths.http, 1.1 and
1.3 to 1.6).
"""

import pytest

from crm_app.models import CRMContacts, CRMDeal, CRMDealStatus, CRMOrganization
from frappe_core.session import session_user
from frappe_platform.models import Contact, ContactEmail, ContactPhone

pytestmark = pytest.mark.django_db

BASE = "/api/method/crm.fcrm.doctype.crm_deal."


def call(client, path, payload):
    return client.post(BASE + path, payload, format="json")


@pytest.fixture(autouse=True)
def statuses(administrator):
    with session_user(administrator.name):
        CRMDealStatus.objects.create(deal_status="Qualification", type="Open", position=1)


@pytest.fixture
def deal(alice):
    with session_user(alice.name):
        return CRMDeal.objects.create(deal_owner=alice, status_id="Qualification")


@pytest.fixture
def contacts(administrator):
    with session_user(administrator.name):
        jane = Contact.objects.create(first_name="ZZ Jane", last_name="Roe", image="/files/j.png")
        ContactEmail.objects.create(parent_contact=jane, email_id="jane@zz.test", is_primary=True)
        ContactPhone.objects.create(parent_contact=jane, phone="+1 111", is_primary_mobile_no=True)
        john = Contact.objects.create(first_name="ZZ John", last_name="Doe")
        ContactEmail.objects.create(parent_contact=john, email_id="john@zz.test", is_primary=True)
    return jane, john


# --- the contacts panel and its three buttons -------------------------------------------


def test_add_contact_appends_a_row_and_the_deal_derives_from_it(auth_api, deal, contacts):
    jane, _ = contacts
    response = call(auth_api, "crm_deal.add_contact", {"deal": deal.name, "contact": jane.name})
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"] is True
    row = CRMContacts.objects.get(parent_deal=deal)
    assert row.contact_id == jane.name
    assert row.is_primary is True, "a lone contact is the primary (crm_deal.py:120-125)"
    deal.refresh_from_db()
    assert deal.email == "jane@zz.test"
    assert deal.mobile_no == "+1 111"


def test_get_deal_contacts_flattens_each_contact(auth_api, deal, contacts):
    jane, john = contacts
    call(auth_api, "crm_deal.add_contact", {"deal": deal.name, "contact": jane.name})
    call(auth_api, "crm_deal.add_contact", {"deal": deal.name, "contact": john.name})

    response = call(auth_api, "api.get_deal_contacts", {"name": deal.name})

    assert response.status_code == 200, response.content[:300]
    rows = response.json()["message"]
    assert rows[0] == {
        "name": jane.name, "image": "/files/j.png", "full_name": "ZZ Jane Roe",
        "email": "jane@zz.test", "mobile_no": "+1 111", "is_primary": True,
    }
    assert rows[1]["name"] == john.name and rows[1]["is_primary"] is False


def test_set_primary_contact_promotes_one_and_demotes_the_rest(auth_api, deal, contacts):
    jane, john = contacts
    call(auth_api, "crm_deal.add_contact", {"deal": deal.name, "contact": jane.name})
    call(auth_api, "crm_deal.add_contact", {"deal": deal.name, "contact": john.name})

    response = call(auth_api, "crm_deal.set_primary_contact", {"deal": deal.name, "contact": john.name})

    assert response.json()["message"] is True
    flags = dict(CRMContacts.objects.filter(parent_deal=deal).values_list("contact_id", "is_primary"))
    assert flags == {jane.name: False, john.name: True}
    deal.refresh_from_db()
    assert deal.email == "john@zz.test"


def test_remove_contact_drops_the_row(auth_api, deal, contacts):
    jane, john = contacts
    call(auth_api, "crm_deal.add_contact", {"deal": deal.name, "contact": jane.name})
    call(auth_api, "crm_deal.add_contact", {"deal": deal.name, "contact": john.name})

    response = call(auth_api, "crm_deal.remove_contact", {"deal": deal.name, "contact": jane.name})

    assert response.json()["message"] is True
    assert list(CRMContacts.objects.filter(parent_deal=deal).values_list("contact_id", flat=True)) == [john.name]


def test_removing_the_primary_leaves_the_lone_survivor_primary(auth_api, deal, contacts):
    jane, john = contacts
    call(auth_api, "crm_deal.add_contact", {"deal": deal.name, "contact": jane.name})
    call(auth_api, "crm_deal.add_contact", {"deal": deal.name, "contact": john.name})
    deal.refresh_from_db()
    assert deal.email == "jane@zz.test", "jane was primary"

    call(auth_api, "crm_deal.remove_contact", {"deal": deal.name, "contact": jane.name})

    row = CRMContacts.objects.get(parent_deal=deal)
    assert row.contact_id == john.name and row.is_primary is True, "crm_deal.py:114-118"
    deal.refresh_from_db()
    assert deal.email == "john@zz.test" and deal.mobile_no == ""


def test_set_primary_contact_to_a_stranger_demotes_every_row(auth_api, deal, contacts, administrator):
    jane, john = contacts
    with session_user(administrator.name):
        stranger = Contact.objects.create(first_name="ZZ Stranger")
    call(auth_api, "crm_deal.add_contact", {"deal": deal.name, "contact": jane.name})
    call(auth_api, "crm_deal.add_contact", {"deal": deal.name, "contact": john.name})

    response = call(auth_api, "crm_deal.set_primary_contact", {"deal": deal.name, "contact": stranger.name})

    assert response.json()["message"] is True, "upstream compares, it does not validate"
    flags = set(CRMContacts.objects.filter(parent_deal=deal).values_list("is_primary", flat=True))
    assert flags == {False}, "crm_deal.py:120-125: every row that is not the named one is demoted"
    deal.refresh_from_db()
    assert deal.email == "" and deal.mobile_no == "", "crm_deal.py:127-149: no primary, cleared"


def test_a_contact_that_does_not_exist_is_a_link_error(auth_api, deal):
    response = call(auth_api, "crm_deal.add_contact", {"deal": deal.name, "contact": "ZZ Nobody"})
    assert response.status_code == 417
    assert response.json()["exc_type"] == "LinkValidationError"


@pytest.mark.parametrize(
    "path,sentence",
    [
        ("crm_deal.add_contact", "Not allowed to add contact to Deal"),
        ("crm_deal.remove_contact", "Not allowed to remove contact from Deal"),
        ("crm_deal.set_primary_contact", "Not allowed to set primary contact for Deal"),
    ],
)
def test_the_buttons_need_write_on_the_deal(api_as, bob, deal, contacts, path, sentence):
    response = call(api_as(bob), path, {"deal": deal.name, "contact": contacts[0].name})
    assert response.status_code == 403
    assert response.json()["message"] == sentence


# --- create_deal: the "Create Deal" modal -------------------------------------------------


def test_create_deal_makes_the_contact_and_organization_it_was_given(auth_api, alice):
    response = call(
        auth_api,
        "crm_deal.create_deal",
        {
            "doc": {
                "first_name": "ZZ Ada", "last_name": "Byron", "email": "ada@zz.test",
                "mobile_no": "+1 555", "organization_name": "ZZ Analytical", "website": "zz.test",
                "deal_owner": alice.name, "status": "Qualification", "next_step": "ZZ call",
            }
        },
    )
    assert response.status_code == 200, response.content[:300]
    deal = CRMDeal.objects.get(pk=response.json()["message"])
    assert deal.organization_id == "ZZ Analytical"
    assert CRMOrganization.objects.get(pk="ZZ Analytical").website == "zz.test"
    contact = Contact.objects.get(pk="ZZ Ada Byron")
    assert contact.company_name == "ZZ Analytical"
    assert contact.email_id == "ada@zz.test" and contact.mobile_no == "+1 555"
    row = CRMContacts.objects.get(parent_deal=deal)
    assert row.contact_id == contact.pk and row.is_primary is True
    assert deal.email == "ada@zz.test"
    assert deal.next_step == "ZZ call"


def test_create_deal_reuses_a_contact_holding_the_email(auth_api, alice, contacts):
    jane, _ = contacts
    response = call(
        auth_api,
        "crm_deal.create_deal",
        {"doc": {"first_name": "Someone", "email": "jane@zz.test", "deal_owner": alice.name}},
    )
    deal = CRMDeal.objects.get(pk=response.json()["message"])
    assert CRMContacts.objects.get(parent_deal=deal).contact_id == jane.name
    assert Contact.objects.filter(first_name="Someone").count() == 0


def test_create_deal_reuses_an_organization_by_name(auth_api, alice, administrator):
    with session_user(administrator.name):
        CRMOrganization.objects.create(organization_name="ZZ Existing", website="old.test")
    response = call(
        auth_api,
        "crm_deal.create_deal",
        {"doc": {"organization_name": "ZZ Existing", "website": "new.test", "deal_owner": alice.name}},
    )
    deal = CRMDeal.objects.get(pk=response.json()["message"])
    assert deal.organization_id == "ZZ Existing"
    assert CRMOrganization.objects.get(pk="ZZ Existing").website == "old.test"


def test_create_deal_with_an_existing_contact_and_organization(auth_api, alice, contacts, administrator):
    with session_user(administrator.name):
        CRMOrganization.objects.create(organization_name="ZZ Org")
    response = call(
        auth_api,
        "crm_deal.create_deal",
        {"doc": {"contact": contacts[1].name, "organization": "ZZ Org", "deal_owner": alice.name}},
    )
    deal = CRMDeal.objects.get(pk=response.json()["message"])
    assert deal.organization_id == "ZZ Org"
    assert CRMContacts.objects.get(parent_deal=deal).contact_id == contacts[1].name
    assert deal.contact_id == contacts[1].name, (
        "upstream's deal.update(doc) keeps the modal's contact on the deal's own Link"
    )


def test_create_deal_reuses_a_contact_holding_the_mobile(auth_api, alice, contacts):
    jane, _ = contacts
    response = call(
        auth_api,
        "crm_deal.create_deal",
        {"doc": {"first_name": "Someone", "mobile_no": "+1 111", "deal_owner": alice.name}},
    )
    deal = CRMDeal.objects.get(pk=response.json()["message"])
    assert CRMContacts.objects.get(parent_deal=deal).contact_id == jane.name
    assert Contact.objects.filter(first_name="Someone").count() == 0


def test_create_deal_copies_the_organization_fields_the_modal_sends(auth_api, alice):
    response = call(
        auth_api,
        "crm_deal.create_deal",
        {"doc": {"organization_name": "ZZ Revenue", "website": "rev.test", "annual_revenue": 1200000, "deal_owner": alice.name}},
    )
    assert response.status_code == 200, response.content[:300]
    organization = CRMOrganization.objects.get(pk="ZZ Revenue")
    assert organization.website == "rev.test"
    assert organization.annual_revenue == 1200000


def test_create_deal_without_a_person_makes_no_contact(auth_api, alice):
    response = call(auth_api, "crm_deal.create_deal", {"doc": {"deal_owner": alice.name}})
    deal = CRMDeal.objects.get(pk=response.json()["message"])
    assert not CRMContacts.objects.filter(parent_deal=deal).exists()
    assert deal.organization_id is None


def test_create_deal_accepts_the_doc_as_a_json_string(auth_api, alice):
    response = call(
        auth_api, "crm_deal.create_deal", {"doc": '{"deal_owner": "%s", "next_step": "ZZ str"}' % alice.name}
    )
    assert response.status_code == 200, response.content[:300]
    assert CRMDeal.objects.get(pk=response.json()["message"]).next_step == "ZZ str"
