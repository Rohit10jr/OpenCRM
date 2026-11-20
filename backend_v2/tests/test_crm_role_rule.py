"""PE-29 (owner, 20 Nov 2026; temp A-48 2d): CRM Industry and Address answer only to
Sales User, Sales Manager, System Manager or Administrator. A signed-in caller with none
of these gets an empty list and 403, on every route of the two resources. New: the old
backend lets every signed-in user in, so no old test covers the refusal.
"""

import pytest

from configuration.models import Country
from contacts.models import Address, CRMIndustry

pytestmark = pytest.mark.django_db

INDUSTRIES = "/api/v1/industries/"
ADDRESSES = "/api/v1/addresses/"
DEPOT = {
    "address_title": "Depot",
    "address_type": "Office",
    "address_line1": "2 Side St",
    "city": "Pune",
    "country": "India",
}


@pytest.fixture
def outsider(make_user):
    """Signed in, with no CRM role."""
    return make_user("outsider@example.com")


@pytest.fixture
def industry(administrator):
    row = CRMIndustry(industry="Robotics")
    row.save(user=administrator)
    return row


@pytest.fixture
def address(administrator):
    row = Address(
        address_title="Head Office", address_type="Office", address_line1="1 Main St",
        city="Pune", country=Country.objects.get(pk="India"),
    )
    row.save(user=administrator)
    return row


def _search(client, base, text):
    return client.get(f"{base}search/", {"txt": text})


# --- CRM Industry ---------------------------------------------------------------------------


def test_an_outsider_lists_no_industry(outsider, industry, api_as):
    response = api_as(outsider).get(INDUSTRIES)
    assert response.status_code == 200
    assert response.json()["message"] == []


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_an_outsider_is_refused_an_industry_by_name(outsider, industry, api_as, method):
    client = api_as(outsider)
    path = f"{INDUSTRIES}{industry.name}/"
    response = client.patch(path, {}, format="json") if method == "patch" else getattr(client, method)(path)
    assert response.status_code == 403
    assert response.json()["message"] == f"No permission for CRM Industry {industry.name}"
    assert CRMIndustry.objects.filter(pk=industry.name).exists()


def test_an_outsider_cannot_create_an_industry(outsider, api_as):
    response = api_as(outsider).post(INDUSTRIES, {"industry": "Mining"}, format="json")
    assert response.status_code == 403
    assert response.json()["message"] == "Not permitted to create CRM Industry"
    assert not CRMIndustry.objects.filter(pk="Mining").exists()


def test_an_outsider_finds_no_industry_by_search_or_value(outsider, industry, api_as):
    client = api_as(outsider)
    assert _search(client, INDUSTRIES, "Robo").json()["message"] == []
    value = client.get(f"{INDUSTRIES}value/", {"fieldname": "industry", "filters": '{"name": "Robotics"}'})
    assert value.status_code == 200
    assert value.json()["message"] == {}


@pytest.mark.parametrize("role", ["Sales User", "Sales Manager", "System Manager"])
def test_each_crm_role_reaches_industries(make_user, industry, api_as, role):
    client = api_as(make_user("crm@example.com", roles=[role]))
    assert [r["name"] for r in client.get(INDUSTRIES).json()["message"]] == ["Robotics"]
    assert client.get(f"{INDUSTRIES}{industry.name}/").status_code == 200


def test_administrator_reaches_industries(administrator, industry, api_as):
    assert api_as(administrator).get(f"{INDUSTRIES}{industry.name}/").status_code == 200


# --- Address --------------------------------------------------------------------------------


def test_an_outsider_lists_no_address(outsider, address, api_as):
    response = api_as(outsider).get(ADDRESSES)
    assert response.status_code == 200
    assert response.json()["message"] == []


@pytest.mark.parametrize("method", ["get", "patch"])
def test_an_outsider_is_refused_an_address_by_name(outsider, address, api_as, method):
    client = api_as(outsider)
    path = f"{ADDRESSES}{address.name}/"
    response = (
        client.patch(path, {"city": "Delhi"}, format="json") if method == "patch" else client.get(path)
    )
    assert response.status_code == 403
    assert response.json()["message"] == f"No permission for Address {address.name}"
    address.refresh_from_db()
    assert address.city == "Pune"


def test_an_outsider_cannot_create_an_address(outsider, api_as):
    response = api_as(outsider).post(
        ADDRESSES, DEPOT, format="json"
    )
    assert response.status_code == 403
    assert response.json()["message"] == "Not permitted to create Address"
    assert not Address.objects.filter(address_title="Depot").exists()


def test_an_outsider_finds_no_address_by_search(outsider, address, api_as):
    assert _search(api_as(outsider), ADDRESSES, "Head").json()["message"] == []


def test_a_sales_user_still_reads_writes_and_creates_an_address(alice, address, api_as):
    client = api_as(alice)
    assert client.get(f"{ADDRESSES}{address.name}/").status_code == 200
    assert client.patch(f"{ADDRESSES}{address.name}/", {"city": "Delhi"}, format="json").status_code == 200
    created = client.post(
        ADDRESSES, DEPOT, format="json"
    )
    assert created.status_code == 200
