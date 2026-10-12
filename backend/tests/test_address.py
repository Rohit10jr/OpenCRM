"""Frappe's ``Address`` and ``Country``, ported for the ``address`` Link on organizations
and contacts: docs/FINDINGS.md 45.

The Vue app creates an address through the generic doctype dialog
(``Organization.vue:showAddressModal`` -> ``frappe.client.insert``) and then writes its
name onto the organization; its Link control searches ``Address`` and ``Country``.
Behaviour follows ``frappe/contacts/doctype/address/address.py``.
"""

from urllib.parse import quote

import pytest

from crm_app.models import CRMOrganization
from frappe_core import field_meta
from frappe_core.exceptions import ValidationError
from frappe_core.session import session_user
from frappe_platform.models import Address, Contact, Country, DynamicLink

pytestmark = pytest.mark.django_db

ADDRESSES = "/api/resource/" + quote("Address")


@pytest.fixture
def india(administrator):
    with session_user(administrator.name):
        country = Country(country_name="India", code="in", time_zones="Asia/Kolkata")
        country.save()
        return country


@pytest.fixture
def acme(administrator):
    with session_user(administrator.name):
        return CRMOrganization.objects.create(organization_name="Acme")


def make_address(country, title="Head Office", address_type="Office", **fields):
    address = Address(
        address_title=title,
        address_type=address_type,
        address_line1="1 Main Street",
        city="Pune",
        country=country,
        **fields,
    )
    address.save()
    return address


def link(address, doctype, name, idx=1):
    row = DynamicLink(
        parenttype="Address",
        parent=str(address.pk),
        parentfield="links",
        idx=idx,
        link_doctype=doctype,
        link_name=name,
    )
    row.save()
    return row


# --- naming and labels ------------------------------------------------------------------


def test_the_name_is_title_dash_type_then_numbered_on_a_collision(india, administrator):
    with session_user(administrator.name):
        first = make_address(india)
        second = make_address(india)
        third = make_address(india)
    assert first.pk == "Head Office-Office"
    assert second.pk == "Head Office-Office-1"
    assert third.pk == "Head Office-Office-2"


def test_the_title_is_mandatory(india, administrator):
    with session_user(administrator.name):
        with pytest.raises(ValidationError, match="Address Title is mandatory."):
            make_address(india, title="")


def test_the_labels_and_link_targets_are_upstreams():
    """The dialog reads them: this doctype has no entry in doctype_meta.json, so the
    labels come from the model, which carries address.json's."""
    fields = {f["fieldname"]: f for f in field_meta.get_fields("Address")}
    assert fields["address_line1"]["label"] == "Address Line 1"
    assert fields["city"]["label"] == "City/Town"
    assert fields["state"]["label"] == "State/Province"
    assert fields["pincode"]["label"] == "Postal Code"
    assert fields["country"]["fieldtype"] == "Link"
    assert fields["country"]["options"] == "Country"
    assert fields["address_type"]["fieldtype"] == "Select"
    assert "Billing" in fields["address_type"]["options"].split("\n")
    countries = {f["fieldname"]: f for f in field_meta.get_fields("Country")}
    assert countries["country_name"]["label"] == "Country Name"


# --- the frontend's path ----------------------------------------------------------------


def test_the_dialog_creates_one_and_the_organization_takes_it(api_as, alice, india, acme):
    """``showAddressModal`` -> ``frappe.client.insert`` -> ``organization.doc.address``."""
    client = api_as(alice)
    response = client.post(
        "/api/method/frappe.client.insert",
        {
            "doc": {
                "doctype": "Address",
                "address_title": "Acme HQ",
                "address_type": "Office",
                "address_line1": "1 Main Street",
                "city": "Pune",
                "country": "India",
            }
        },
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    name = response.json()["message"]["name"]
    assert name == "Acme HQ-Office"

    response = client.put(
        "/api/resource/" + quote("CRM Organization") + "/Acme", {"address": name}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
    assert CRMOrganization.objects.get(pk="Acme").address == name


def test_a_contact_takes_an_address_too(api_as, alice, india, administrator):
    """``contact.json``'s ``address`` Link, which the seeded Contact layouts name; the
    contact page sets it through the same dialog."""
    with session_user(administrator.name):
        address = make_address(india, "Ada Home", "Personal")
        contact = Contact.objects.create(first_name="Ada", last_name="Lovelace")
    fields = {f["fieldname"]: f for f in field_meta.get_fields("Contact")}
    assert (fields["address"]["fieldtype"], fields["address"]["options"]) == ("Link", "Address")

    response = api_as(alice).put(
        "/api/resource/Contact/" + quote(contact.pk), {"address": address.pk}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
    assert Contact.objects.get(pk=contact.pk).address_id == address.pk


def test_link_rows_get_the_documents_title_and_duplicates_collapse(api_as, administrator, india, acme):
    """``set_link_title`` and ``deduplicate_dynamic_links`` from upstream's ``validate``."""
    row = {"link_doctype": "CRM Organization", "link_name": "Acme"}
    response = api_as(administrator).post(
        ADDRESSES,
        {
            "address_title": "Acme HQ",
            "address_type": "Office",
            "address_line1": "1 Main Street",
            "city": "Pune",
            "country": "India",
            "links": [row, dict(row)],
        },
        format="json",
    )
    assert response.status_code in (200, 201), response.content[:300]
    address = Address.objects.get(pk="Acme HQ-Office")
    rows = list(address.link_rows())
    assert len(rows) == 1
    assert (rows[0].link_doctype, rows[0].link_name, rows[0].link_title) == (
        "CRM Organization", "Acme", "Acme",
    )
    assert address.has_link("CRM Organization", "Acme")


def test_a_preferred_flag_moves_to_the_address_that_last_claimed_it(india, acme, administrator):
    """``validate_preferred_address``: one preferred billing address per linked document."""
    with session_user(administrator.name):
        old = make_address(india, "Old", is_primary_address=True)
        link(old, "CRM Organization", "Acme")
        old.save()
        new = make_address(india, "New", is_primary_address=True)
        link(new, "CRM Organization", "Acme")
        new.save()
    old.refresh_from_db()
    new.refresh_from_db()
    assert not old.is_primary_address
    assert new.is_primary_address


def test_an_address_without_links_takes_the_owners_contact_links(alice, acme, india, administrator):
    """``link_address``: a portal user's own address attaches to their customer."""
    with session_user(administrator.name):
        contact = Contact.objects.create(first_name="Ada")
        Contact.objects.filter(pk=contact.pk).update(email_id=alice.name)
        DynamicLink(
            parenttype="Contact", parent=str(contact.pk), parentfield="links", idx=1,
            link_doctype="CRM Organization", link_name="Acme",
        ).save()
    with session_user(alice.name):
        address = make_address(india, "Home", "Personal")
    assert address.has_link("CRM Organization", "Acme")


# --- the Link control's search ----------------------------------------------------------


def test_search_link_narrows_to_a_documents_addresses_and_hides_disabled_ones(
    auth_api, administrator, india, acme
):
    """``address_query``: ``link_doctype`` and ``link_name`` select through the link
    rows; ``search_widget`` hides a disabled address unless asked."""
    with session_user(administrator.name):
        linked = make_address(india, "Linked")
        link(linked, "CRM Organization", "Acme")
        make_address(india, "Loose")
        off = make_address(india, "Off", disabled=True)
        link(off, "CRM Organization", "Acme")

    def search(filters):
        response = auth_api.post(
            "/api/method/frappe.desk.search.search_link",
            {"doctype": "Address", "txt": "", "filters": filters},
            format="json",
        )
        assert response.status_code == 200, response.content[:300]
        return sorted(r["value"] for r in response.json()["message"])

    assert search({"link_doctype": "CRM Organization", "link_name": "Acme"}) == [linked.pk]
    assert search({}) == [linked.pk, "Loose-Office"]
    assert search({"include_disabled": 1}) == [linked.pk, "Loose-Office", off.pk]


def test_the_country_picker_searches_countries(auth_api, india):
    response = auth_api.post(
        "/api/method/frappe.desk.search.search_link",
        {"doctype": "Country", "txt": "ind"},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    assert [r["value"] for r in response.json()["message"]] == ["India"]


# --- permissions and deletion -----------------------------------------------------------


def test_deleting_an_address_removes_its_link_rows(api_as, administrator, india, acme):
    with session_user(administrator.name):
        address = make_address(india)
        link(address, "CRM Organization", "Acme")
    response = api_as(administrator).delete(f"{ADDRESSES}/{quote(address.pk)}")
    assert response.status_code in (200, 202, 204), response.content[:300]
    assert not Address.objects.filter(pk=address.pk).exists()
    assert not DynamicLink.objects.filter(parenttype="Address", parent=address.pk).exists()


def test_everyone_writes_but_only_a_system_manager_deletes(api_as, alice, administrator, india):
    """``address.json``: read, write and create for every role; delete for System Manager."""
    with session_user(administrator.name):
        address = make_address(india)
    client = api_as(alice)
    response = client.put(f"{ADDRESSES}/{quote(address.pk)}", {"city": "Mumbai"}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert client.delete(f"{ADDRESSES}/{quote(address.pk)}").status_code == 403
    assert Address.objects.filter(pk=address.pk).exists()


def test_countries_are_read_only_below_system_manager(api_as, alice, india):
    """``country.json``: everyone reads; System Manager maintains the list."""
    client = api_as(alice)
    countries = "/api/resource/Country"
    assert client.get(f"{countries}/India").status_code == 200
    assert client.put(f"{countries}/India", {"code": "xx"}, format="json").status_code == 403
    assert client.post(countries, {"country_name": "Atlantis", "code": "at"}, format="json").status_code == 403
