"""Address and Dynamic Link (specs/CONTACTS.md §3, §4; milestone 2).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_address.py``: `:68-82` (the name is
title-type, numbered on a collision; the title is mandatory), `:84-97` (the labels, from
the model), `:253-261` (everyone writes, only a System Manager deletes; the old PUT is
PATCH), and `:243-250` twinned on a link to a test Widget (the old case links an
organization, which waits for §6 A). The countries come from CONFIGURATION's migration.
The rest of the old file needs Organization or Contact. New: the save steps, the search
filters, the Dynamic Link refusal.
"""

import pytest

from configuration import field_meta
from configuration.models import Country
from contacts.models import Address, DynamicLink
from tests_support.models import Widget

pytestmark = pytest.mark.django_db

ADDRESSES = "/api/v1/addresses/"


@pytest.fixture
def india():
    return Country.objects.get(pk="India")


def make_address(user, country, title="Head Office", address_type="Office", **fields):
    address = Address(
        address_title=title,
        address_type=address_type,
        address_line1="1 Main Street",
        city="Pune",
        country=country,
        **fields,
    )
    address.save(user=user)
    return address


def link(user, address, doctype, name, idx=1):
    row = DynamicLink(
        parenttype="Address",
        parent=str(address.pk),
        parentfield="links",
        idx=idx,
        link_doctype=doctype,
        link_name=name,
    )
    row.save(user=user)
    return row


# --- ported ------------------------------------------------------------------------------


def test_the_name_is_title_dash_type_then_numbered_on_a_collision(india, administrator):
    names = [make_address(administrator, india).pk for _ in range(3)]
    assert names == ["Head Office-Office", "Head Office-Office-1", "Head Office-Office-2"]


def test_the_title_is_mandatory(india, administrator, auth_api):
    response = auth_api.post(
        ADDRESSES,
        {"address_title": "", "address_type": "Office", "address_line1": "1", "city": "Pune", "country": "India"},
        format="json",
    )
    assert response.status_code == 417
    assert response.json()["message"] == "Address Title is mandatory."


def test_the_labels_and_link_targets_are_upstreams():
    fields = {f["fieldname"]: f for f in field_meta.get_fields("Address")}
    assert fields["address_line1"]["label"] == "Address Line 1"
    assert fields["city"]["label"] == "City/Town"
    assert fields["state"]["label"] == "State/Province"
    assert fields["pincode"]["label"] == "Postal Code"
    assert fields["country"]["fieldtype"] == "Link"
    assert fields["country"]["options"] == "Country"
    assert fields["address_type"]["fieldtype"] == "Select"
    assert "Billing" in fields["address_type"]["options"].split("\n")


def test_everyone_writes_but_only_a_system_manager_deletes(api_as, alice, administrator, india):
    address = make_address(administrator, india)
    client = api_as(alice)
    response = client.patch(f"{ADDRESSES}{address.pk}/", {"city": "Mumbai"}, format="json")
    assert response.status_code == 200, response.json()
    assert client.delete(f"{ADDRESSES}{address.pk}/").status_code == 403
    assert Address.objects.filter(pk=address.pk).exists()


def test_deleting_an_address_removes_its_link_rows(api_as, administrator, alice, india):
    widget = Widget(widget_name="W", widget_owner=alice)
    widget.save(user=alice)
    address = make_address(administrator, india)
    link(administrator, address, widget.DOCTYPE, widget.pk)
    response = api_as(administrator).delete(f"{ADDRESSES}{address.pk}/")
    assert response.status_code == 200, response.json()
    assert not Address.objects.filter(pk=address.pk).exists()
    assert not DynamicLink.objects.filter(parenttype="Address", parent=address.pk).exists()


# --- new: the resource and its rows ------------------------------------------------------


def test_an_address_is_created_with_its_link_rows(auth_api, india):
    response = auth_api.post(
        ADDRESSES,
        {
            "address_title": "Branch",
            "address_type": "Billing",
            "address_line1": "2 Side Street",
            "city": "Pune",
            "country": "India",
            "links": [{"link_doctype": "Foundation Widget", "link_name": "W-1"}],
        },
        format="json",
    )
    assert response.status_code == 200, response.json()
    body = response.json()["message"]
    assert body["name"] == "Branch-Billing"
    assert [(row["link_doctype"], row["link_name"]) for row in body["links"]] == [("Foundation Widget", "W-1")]


def test_duplicate_links_are_reduced_to_the_first(administrator, india):
    address = make_address(administrator, india)
    link(administrator, address, "Foundation Widget", "W-1", idx=1)
    link(administrator, address, "Foundation Widget", "W-1", idx=2)
    address.save(user=administrator)
    assert address.link_rows().count() == 1


def test_link_title_is_the_name_without_a_title_field(administrator, india):
    address = make_address(administrator, india)
    link(administrator, address, "Foundation Widget", "W-1")
    address.save(user=administrator)
    assert address.link_rows().get().link_title == "W-1"


def test_a_preferred_flag_clears_it_on_the_other_enabled_addresses(administrator, india):
    first = make_address(administrator, india, title="One", is_primary_address=True)
    link(administrator, first, "Foundation Widget", "W-1")
    disabled = make_address(administrator, india, title="Off", is_primary_address=True, disabled=True)
    link(administrator, disabled, "Foundation Widget", "W-1")
    second = make_address(administrator, india, title="Two", is_primary_address=True)
    link(administrator, second, "Foundation Widget", "W-1")
    second.save(user=administrator)
    first.refresh_from_db()
    disabled.refresh_from_db()
    assert (first.is_primary_address, disabled.is_primary_address) == (False, True)


def test_a_record_a_dynamic_link_names_cannot_be_deleted(api_as, alice, administrator, india):
    widget = Widget(widget_name="Linked", widget_owner=alice)
    widget.save(user=alice)
    address = make_address(administrator, india)
    link(administrator, address, widget.DOCTYPE, widget.pk)
    response = api_as(alice).delete(f"/api/v1/test-widgets/{widget.pk}/")
    assert response.status_code == 417
    assert response.json()["exc_type"] == "LinkExistsError"
    assert response.json()["message"].endswith(f"is linked with Address {address.pk} at Row: 1")
    assert Widget.objects.filter(pk=widget.pk).exists()


# --- new: search -------------------------------------------------------------------------


def search(client, **inputs):
    response = client.get(f"{ADDRESSES}search/", inputs)
    assert response.status_code == 200, response.json()
    return sorted(row["value"] for row in response.json()["message"])


def test_search_reads_the_link_filters(auth_api, administrator, india):
    mine = make_address(administrator, india, title="Mine")
    link(administrator, mine, "Foundation Widget", "W-1")
    make_address(administrator, india, title="Other")
    filters = '{"link_doctype": "Foundation Widget", "link_name": "W-1"}'
    assert search(auth_api, filters=filters) == [mine.pk]
    listed = '[["link_doctype", "=", "Foundation Widget"], ["link_name", "=", "W-1"]]'
    assert search(auth_api, filters=listed) == [mine.pk]


def test_search_hides_disabled_addresses(auth_api, administrator, india):
    shown = make_address(administrator, india, title="Shown")
    make_address(administrator, india, title="Hidden", disabled=True)
    assert search(auth_api) == [shown.pk]
