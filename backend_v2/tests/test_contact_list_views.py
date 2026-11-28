"""The Contacts and Organizations list views (specs/CONTACTS.md §10 row 7; CONFIGURATION
§4.8; milestone 7).

Ported (REBUILD_PLAN S14) from ``backend/tests/``: `test_platform_models.py:226-244`
(Contact's definition is the override's) and `test_phase4_metadata.py:283-287` (a doctype
with no definition falls back to Name and Last Modified; CRM Industry, which serves no
list view, through `list_definition_for`). `crm.api.doc.get_data` with `doctype` is each
resource's `list-view/`. New: Organization's definition verbatim (no old test pins it),
both resources answer their list view, and a caller with no CRM role lists nothing there
(PE-29).
"""

import pytest

from configuration.list_views import ListView, list_definition_for
from contacts.list_views import ContactListView, OrganizationListView
from contacts.models import Contact, CRMOrganization

pytestmark = pytest.mark.django_db


def list_view(client, resource, **inputs):
    inputs.setdefault("filters", {})
    inputs.setdefault("order_by", "modified desc")
    response = client.post(f"/api/v1/{resource}/list-view/", inputs, format="json")
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]


# --- the definitions ------------------------------------------------------------------------


def test_contact_default_list_data_matches_the_override():
    """`test_platform_models.py:226-244`: verbatim from `crm/overrides/contact.py`; the
    labels and widths pinned too (A-87 finding 6)."""
    assert ContactListView.default_columns() == [
        {"label": "Name", "type": "Data", "key": "full_name", "width": "17rem"},
        {"label": "Email", "type": "Data", "key": "email_id", "width": "12rem"},
        {"label": "Phone", "type": "Data", "key": "mobile_no", "width": "12rem"},
        {"label": "Organization", "type": "Data", "key": "company_name", "width": "12rem"},
        {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
    ]
    assert ContactListView.default_rows() == [
        "name",
        "full_name",
        "company_name",
        "email_id",
        "mobile_no",
        "modified",
        "image",
    ]


def test_organization_default_list_data_is_the_old_one_with_upstreams_currency():
    """Old `core_sales.py:141-160`, widths and all, with upstream's `currency` in the rows
    (`crm_organization.py:79-88`; PE-38)."""
    assert OrganizationListView.default_columns() == [
        {"label": "Organization", "type": "Data", "key": "organization_name", "width": "11rem"},
        {"label": "Website", "type": "Data", "key": "website", "width": "14rem"},
        {"label": "Industry", "type": "Link", "key": "industry", "width": "14rem"},
        {"label": "Annual Revenue", "type": "Currency", "key": "annual_revenue", "width": "14rem"},
        {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
    ]
    assert OrganizationListView.default_rows() == [
        "name",
        "organization_name",
        "organization_logo",
        "website",
        "industry",
        "currency",
        "annual_revenue",
        "modified",
    ]


def test_an_organizations_list_row_carries_its_currency(auth_api, administrator):
    """PE-38: the list formats `annual_revenue` with the row's own `currency`
    (`Organizations.vue:114-116`)."""
    CRMOrganization(organization_name="ZZ Euro Org", currency="EUR", annual_revenue="1000000").save(
        user=administrator
    )
    row = list_view(auth_api, "organizations")["data"][0]
    assert (row["currency"], row["annual_revenue"]) == ("EUR", 1000000.0)


def test_the_saved_views_find_each_definition():
    assert list_definition_for("Contact") is ContactListView
    assert list_definition_for("CRM Organization") is OrganizationListView


def test_a_doctype_with_no_definition_falls_back_to_name_and_last_modified():
    """`test_phase4_metadata.py:283-287`: CRM Industry defines none."""
    assert list_definition_for("CRM Industry") is ListView
    assert [c["key"] for c in ListView.default_columns()] == ["name", "modified"]


# --- the routes -----------------------------------------------------------------------------


def test_the_contacts_list_view_answers_its_columns_and_rows(auth_api, alice):
    Contact.objects.create_for_user(user=alice, first_name="ZZ Listed")
    result = list_view(auth_api, "contacts")
    assert [c["key"] for c in result["columns"]] == [c["key"] for c in ContactListView.default_columns()]
    rows = ContactListView.default_rows()
    assert result["rows"][: len(rows)] == rows, "the definition's rows, then the engine's standard fields"
    assert [row["full_name"] for row in result["data"]] == ["ZZ Listed"]


def test_the_organizations_list_view_answers_its_columns_and_rows(auth_api, administrator):
    CRMOrganization(organization_name="ZZ Listed Org").save(user=administrator)
    result = list_view(auth_api, "organizations")
    assert [c["key"] for c in result["columns"]] == [c["key"] for c in OrganizationListView.default_columns()]
    rows = OrganizationListView.default_rows()
    assert result["rows"][: len(rows)] == rows
    assert [row["name"] for row in result["data"]] == ["ZZ Listed Org"]


@pytest.mark.parametrize("resource", ["contacts", "organizations"])
def test_an_outsider_lists_nothing_in_the_list_view(api_as, make_user, alice, administrator, resource):
    """PE-29: the list rule under the list engine too."""
    Contact.objects.create_for_user(user=alice, first_name="ZZ Hidden")
    CRMOrganization(organization_name="ZZ Hidden Org").save(user=administrator)
    result = list_view(api_as(make_user("outsider@example.com")), resource)
    assert result["data"] == []
    assert result["total_count"] == 0
