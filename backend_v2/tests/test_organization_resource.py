"""The CRM Organization resource and `get_organizations` (specs/CONTACTS.md §3, §4 "CRM
Organization", §11.3, §11.5; PE-29, PE-34; milestone 5).

Ported (REBUILD_PLAN S14) from ``backend/tests/``: `test_envelope.py:165-185` (an Industry
an organization names), `test_null_as_blank.py:22-67` (null empties a field; set_value and
the resource PUT are both `PATCH /api/v1/organizations/<name>/`), `test_name_lookup.py:
61-93` (the duplicate sentence; `frappe.client.insert` is the same `POST`),
`test_route_surface_review.py:173-200` (a Sales User creates and reads one),
`test_versions.py:173-182` (no history), `test_address.py:103-128` (the address dialog),
and `test_phase3_endpoints.py`'s `get_organizations` (served). New: PE-29's matrix as for
CRM Industry, `directory/`'s shape, and the Address an organization names (PE-34).
"""

import json
from urllib.parse import quote

import pytest

from configuration.models import Country
from contacts.models import Address, CRMIndustry, CRMOrganization
from core.models import Version

pytestmark = pytest.mark.django_db
ORGS = "/api/v1/organizations/"
LOGO = "/files/acme.png"


def org_url(name, action=""):
    return f"{ORGS}{quote(name)}/{action}"


def organization(user, **fields):
    org = CRMOrganization(**fields)
    org.save(user=user)
    return org


@pytest.fixture
def acme(administrator):
    return organization(
        administrator,
        organization_name="Acme",
        organization_logo=LOGO,
        website="https://acme.example.com",
        no_of_employees="11-50",
    )


@pytest.fixture
def outsider(make_user):
    return make_user("outsider@example.com")


# --- ported ---------------------------------------------------------------------------------


def test_deleting_an_industry_an_organization_names_is_a_link_exists_error(administrator, api_as):
    """`test_envelope.py:165-185`."""
    industry = CRMIndustry(industry="ZZ Fintech")
    industry.save(user=administrator)
    organization(administrator, organization_name="ZZ Acme", industry=industry)

    response = api_as(administrator).delete(f"/api/v1/industries/{quote('ZZ Fintech')}/")
    assert response.status_code == 417
    body = response.json()
    assert body["exc_type"] == "LinkExistsError"
    assert body["message"] == (
        "Cannot delete or cancel because CRM Industry ZZ Fintech is linked with CRM Organization ZZ Acme"
    )
    assert CRMIndustry.objects.filter(pk="ZZ Fintech").exists()


def test_remove_image_clears_the_logo(auth_api, acme):
    """`test_null_as_blank.py:33-43`: what the Remove Image menu item sends."""
    response = auth_api.patch(org_url(acme.pk), {"organization_logo": None}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"]["organization_logo"] == ""
    acme.refresh_from_db()
    assert acme.organization_logo == ""


def test_null_empties_text_and_select_fields(auth_api, acme):
    """`test_null_as_blank.py:46-54`."""
    response = auth_api.patch(
        org_url(acme.pk), {"organization_logo": None, "website": None, "no_of_employees": None}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
    acme.refresh_from_db()
    assert (acme.organization_logo, acme.website, acme.no_of_employees) == ("", "", "")


def test_a_field_left_out_is_untouched(auth_api, acme):
    """`test_null_as_blank.py:57-67`."""
    assert auth_api.patch(org_url(acme.pk), {"website": None}, format="json").status_code == 200
    acme.refresh_from_db()
    assert acme.website == ""
    assert acme.organization_logo == LOGO


def test_a_duplicate_name_answers_upstreams_sentence(api_as, administrator):
    """`test_name_lookup.py:61-93`: "<DocType> <strong>name</strong> already exists",
    titled "Duplicate Name"."""
    organization(administrator, organization_name="ZZ Twice")
    response = api_as(administrator).post(ORGS, {"organization_name": "ZZ Twice"}, format="json")
    assert response.status_code == 409, response.content[:300]
    body = response.json()
    assert body["exc_type"] == "DuplicateEntryError"
    assert body["message"] == "CRM Organization <strong>ZZ Twice</strong> already exists"
    assert json.loads(json.loads(body["_server_messages"])[0])["title"] == "Duplicate Name"
    assert CRMOrganization.objects.filter(organization_name="ZZ Twice").count() == 1


def test_a_sales_user_creates_and_reads_an_organization(auth_api):
    """`test_route_surface_review.py:173-200` (201 and "data" there; the new route's
    envelope is 200 and "message")."""
    response = auth_api.post(ORGS, {"organization_name": "Route Review Org"}, format="json")
    assert response.status_code == 200, response.content[:300]
    name = response.json()["message"]["name"]
    assert auth_api.get(org_url(name)).status_code == 200


def test_an_organization_writes_no_history(alice, administrator):
    """`test_versions.py:173-182`."""
    org = organization(administrator, organization_name="Acme Corp")
    reloaded = CRMOrganization.objects.get(pk=org.pk)
    reloaded.website = "changed.example"
    reloaded.save(user=alice)
    assert Version.objects.filter(ref_doctype="CRM Organization").count() == 0


def test_the_address_dialog_creates_one_and_the_organization_takes_it(api_as, alice, acme):
    """`test_address.py:103-128`: `showAddressModal` inserts an Address, then the
    organization's `address` takes its name."""
    client = api_as(alice)
    response = client.post(
        "/api/v1/addresses/",
        {
            "address_title": "Acme HQ",
            "address_type": "Office",
            "address_line1": "1 Main Street",
            "city": "Pune",
            "country": "India",
        },
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    name = response.json()["message"]["name"]
    assert name == "Acme HQ-Office"
    response = client.patch(org_url("Acme"), {"address": name}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert CRMOrganization.objects.get(pk="Acme").address == name


# --- PE-34: the Address an organization names -----------------------------------------------


def test_an_address_an_organization_names_cannot_be_deleted(api_as, administrator, acme):
    address = Address(
        address_title="Depot", address_type="Office", address_line1="2 Side St",
        city="Pune", country=Country.objects.get(pk="India"),
    )
    address.save(user=administrator)
    CRMOrganization.objects.filter(pk=acme.pk).update(address=address.pk)

    response = api_as(administrator).delete(f"/api/v1/addresses/{quote(address.pk)}/")
    assert response.status_code == 417
    assert response.json()["message"] == "You can disable this Address instead of deleting it."

    CRMOrganization.objects.filter(pk=acme.pk).update(address="")
    assert api_as(administrator).delete(f"/api/v1/addresses/{quote(address.pk)}/").status_code == 200


# --- directory/ (get_organizations) ---------------------------------------------------------


def test_the_directory_lists_every_organization_by_name_in_the_list_shape(auth_api, administrator, acme):
    """`session.py:158-170`: every column, ordered by name, no limit; decimals as numbers
    and the caches as JSON text, as a list answers."""
    organization(administrator, organization_name="Beta", annual_revenue="1500.5")
    rows = auth_api.get(f"{ORGS}directory/").json()["message"]
    assert [row["name"] for row in rows] == ["Acme", "Beta"]
    beta = rows[1]
    assert beta["annual_revenue"] == 1500.5
    assert beta["_assign"] == "[]"
    assert {"organization_name", "website", "territory", "currency", "exchange_rate"} <= set(beta)


def test_the_directory_has_no_limit(auth_api, administrator):
    for n in range(25):
        organization(administrator, organization_name=f"Bulk {n:02d}")
    assert len(auth_api.get(f"{ORGS}directory/").json()["message"]) == 25


def test_an_outsider_is_refused_the_directory(api_as, outsider, acme):
    response = api_as(outsider).get(f"{ORGS}directory/")
    assert response.status_code == 403
    assert response.json()["message"] == "You are not permitted to access CRM resources."


# --- PE-29 ----------------------------------------------------------------------------------


def test_an_outsider_lists_no_organization(api_as, outsider, acme):
    response = api_as(outsider).get(ORGS)
    assert response.status_code == 200
    assert response.json()["message"] == []


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_an_outsider_is_refused_an_organization_by_name(api_as, outsider, acme, method):
    client = api_as(outsider)
    path = org_url(acme.pk)
    response = client.patch(path, {}, format="json") if method == "patch" else getattr(client, method)(path)
    assert response.status_code == 403
    assert response.json()["message"] == "No permission for CRM Organization Acme"
    assert CRMOrganization.objects.filter(pk="Acme").exists()


def test_an_outsider_cannot_create_an_organization(api_as, outsider):
    response = api_as(outsider).post(ORGS, {"organization_name": "ZZ Nope"}, format="json")
    assert response.status_code == 403
    assert response.json()["message"] == "Not permitted to create CRM Organization"
    assert not CRMOrganization.objects.filter(pk="ZZ Nope").exists()


def test_an_outsider_finds_no_organization_by_search_or_value(api_as, outsider, acme):
    client = api_as(outsider)
    assert client.get(f"{ORGS}search/", {"txt": "Ac"}).json()["message"] == []
    value = client.get(f"{ORGS}value/", {"fieldname": "website", "filters": '{"name": "Acme"}'})
    assert value.status_code == 200
    assert value.json()["message"] == {}


def test_an_outsider_is_allowed_nothing_on_an_organization(api_as, outsider, acme):
    permissions = api_as(outsider).get(org_url(acme.pk, "permissions/")).json()["message"]["permissions"]
    assert permissions and not any(permissions.values())


@pytest.mark.parametrize("role", ["Sales User", "Sales Manager", "System Manager"])
def test_each_crm_role_reaches_organizations(make_user, api_as, acme, role):
    client = api_as(make_user("crm@example.com", roles=[role]))
    assert [r["name"] for r in client.get(ORGS).json()["message"]] == ["Acme"]
    assert client.get(org_url(acme.pk)).status_code == 200
    assert [r["name"] for r in client.get(f"{ORGS}directory/").json()["message"]] == ["Acme"]


def test_search_matches_the_name(auth_api, acme):
    response = auth_api.get(f"{ORGS}search/", {"txt": "Acm"})
    assert [row["value"] for row in response.json()["message"]] == ["Acme"]
