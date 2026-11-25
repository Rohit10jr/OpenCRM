"""CRM Organization's shared actions (specs/CONTACTS.md §8, PE-24 to PE-26, PE-29, PE-31,
PE-34; milestone 6b). The mixins are tested on `tests_support`; these pin what they do with
the organization's own rules and links.

Ported (REBUILD_PLAN S14) from ``backend/tests/test_rename.py``: the stamps kept (`:129-134`)
and validate_rename's refusals (`:140-160`); the cases with a Deal (`:30-55`) wait for SALES.
`frappe.client.rename_doc` is `POST /api/v1/organizations/<name>/rename/`. New: PE-31 sets
`organization_name`, an Address's Dynamic Link and the text Links naming it follow (PE-5), and
each action's refusal to a caller with no CRM role.
"""

import json
from urllib.parse import quote

import pytest

from configuration.models import Country
from contacts.models import Address, CRMOrganization, DynamicLink

pytestmark = pytest.mark.django_db
ORGS = "/api/v1/organizations/"


def at(name, action=""):
    return f"{ORGS}{quote(name)}/{action}"


def organization(user, **fields):
    org = CRMOrganization(**fields)
    org.save(user=user)
    return org


@pytest.fixture
def org(administrator):
    return organization(administrator, organization_name="ZZ Contact Org")


@pytest.fixture
def outsider(api_as, make_user):
    return api_as(make_user("outsider@example.com"))


@pytest.fixture
def system_manager(api_as, make_user):
    return api_as(make_user("sysman@example.com", roles=["System Manager"]))


@pytest.fixture
def address(administrator, org):
    a = Address(
        address_title="ZZ HQ", address_type="Office", address_line1="1 St",
        city="Pune", country=Country.objects.get(pk="India"),
    )
    a.save(user=administrator)
    DynamicLink(
        name="zz-org-link", parent=a.pk, parenttype="Address", parentfield="links",
        link_doctype="CRM Organization", link_name=org.pk, idx=1,
    ).save(user=administrator)
    return a


def rename(client, old, new, **extra):
    return client.post(at(old, "rename/"), {"new_name": new, **extra}, format="json")


# --- rename (PE-24, PE-31) ------------------------------------------------------------------


def test_rename_sets_the_name_field_and_moves_the_links(auth_api, administrator, org, address):
    """PE-31 sets `organization_name`; the Address's Dynamic Link row naming it follows
    (`DYNAMIC_LINK_FIELDS`, PE-5)."""
    response = rename(auth_api, "ZZ Contact Org", "ZZ Renamed Org")
    assert response.status_code == 200, response.content[:300]
    assert response.json() == {"message": "ZZ Renamed Org"}
    renamed = CRMOrganization.objects.get(pk="ZZ Renamed Org")
    assert renamed.organization_name == "ZZ Renamed Org"
    assert not CRMOrganization.objects.filter(pk="ZZ Contact Org").exists()
    assert DynamicLink.objects.get(pk="zz-org-link").link_name == "ZZ Renamed Org"


def test_the_renamed_row_keeps_its_stamps(auth_api, org):
    """`test_rename.py:129-134`."""
    rename(auth_api, "ZZ Contact Org", "ZZ Renamed Org")
    renamed = CRMOrganization.objects.get(pk="ZZ Renamed Org")
    assert renamed.owner_id == org.owner_id
    assert renamed.creation == org.creation


def test_renaming_a_missing_document(auth_api):
    """`test_rename.py:140-145`."""
    response = rename(auth_api, "ZZ Nobody", "ZZ Whoever")
    assert response.status_code == 417
    assert response.json()["message"] == "Can't rename ZZ Nobody to ZZ Whoever because ZZ Nobody doesn't exist."


def test_renaming_to_the_same_name(auth_api, org):
    """`test_rename.py:148-153`."""
    response = rename(auth_api, "ZZ Contact Org", "ZZ Contact Org")
    assert response.status_code == 417
    assert response.json()["message"] == "No changes made because old and new name are the same."


def test_renaming_onto_an_existing_name(auth_api, administrator, org):
    """`test_rename.py:156-`."""
    organization(administrator, organization_name="ZZ Taken")
    response = rename(auth_api, "ZZ Contact Org", "ZZ Taken")
    assert response.status_code == 417
    assert response.json()["message"] == "Another CRM Organization with name ZZ Taken exists, select another name"


def test_an_outsider_may_not_rename(outsider, org):
    response = rename(outsider, "ZZ Contact Org", "ZZ X")
    assert response.status_code == 417
    assert response.json()["message"] == "You need write permission on CRM Organization ZZ Contact Org to rename"


# --- bulk delete ----------------------------------------------------------------------------


def test_organization_bulk_delete_does_not_clear_contacts():
    from contacts.views import CRMOrganizationViewSet

    assert CRMOrganizationViewSet.bulk_delete_remove_contact is False


def test_a_sales_user_bulk_deletes_organizations(auth_api, administrator, org):
    other = organization(administrator, organization_name="ZZ Other")
    response = auth_api.post(f"{ORGS}bulk-delete/", {"items": json.dumps([org.pk, other.pk])}, format="json")
    assert response.json() == {"message": "success"}, response.content[:300]
    assert not CRMOrganization.objects.filter(pk__in=[org.pk, other.pk]).exists()


def test_an_outsider_may_not_bulk_delete(outsider, org):
    response = outsider.post(f"{ORGS}bulk-delete/", {"items": json.dumps([org.pk])}, format="json")
    assert response.status_code == 403
    assert response.json()["message"] == f"No permission to delete CRM Organization {org.pk}"
    assert CRMOrganization.objects.filter(pk=org.pk).exists()


def test_bulk_delete_of_an_organization_an_address_links_is_refused(auth_api, org, address):
    """The clearing blanks reference fields and direct Link fields only; a link held by a
    child row (the Address's Dynamic Link) is deliberately left (old `doc.py`
    `_clear_reference`, `_clear_link_fields`; upstream bug 63), so the dynamic check
    refuses the batch and nothing goes, as for a Contact (6a)."""
    response = auth_api.post(f"{ORGS}bulk-delete/", {"items": json.dumps([org.pk])}, format="json")
    assert response.status_code == 417
    assert response.json()["exc_type"] == "LinkExistsError"
    assert response.json()["message"] == (
        f"Cannot delete or cancel because CRM Organization {org.pk} is linked with Address {address.pk} at Row: 1"
    )
    assert CRMOrganization.objects.filter(pk=org.pk).exists()
    assert DynamicLink.objects.filter(pk="zz-org-link").exists()


# --- linked documents -----------------------------------------------------------------------


def test_linked_documents_lists_the_address(auth_api, org, address):
    response = auth_api.get(at(org.pk, "linked-documents/"))
    assert response.json()["message"] == [
        {"doc": "Address", "title": address.pk, "reference_docname": address.pk, "reference_doctype": "Address"}
    ]


def test_an_outsider_is_refused_the_linked_documents(outsider, org):
    response = outsider.get(at(org.pk, "linked-documents/"))
    assert response.status_code == 403
    assert response.json()["message"] == f"No permission for CRM Organization {org.pk}"


def test_a_rep_may_not_delete_the_linked_address(auth_api, org, address):
    """PE-26: Address delete is System Manager's; the rep's unlink with delete skips it."""
    response = auth_api.post(
        at(org.pk, "linked-documents/"),
        {"items": [{"doctype": "Address", "docname": address.pk}], "delete": True},
        format="json",
    )
    assert response.json() == {"message": "success"}
    assert Address.objects.filter(pk=address.pk).exists()


def test_a_system_manager_deletes_the_linked_address(system_manager, org, address):
    response = system_manager.post(
        at(org.pk, "linked-documents/"),
        {"items": [{"doctype": "Address", "docname": address.pk}], "delete": True},
        format="json",
    )
    assert response.json() == {"message": "success"}
    assert not Address.objects.filter(pk=address.pk).exists()


def test_an_address_the_organization_names_is_skipped(system_manager, org, address):
    """PE-34: the organization's own `address` names it, so the linked delete skips it."""
    CRMOrganization.objects.filter(pk=org.pk).update(address=address.pk)
    response = system_manager.post(
        at(org.pk, "linked-documents/"),
        {"items": [{"doctype": "Address", "docname": address.pk}], "delete": True},
        format="json",
    )
    assert response.json() == {"message": "success"}
    assert Address.objects.filter(pk=address.pk).exists()


# --- bulk update and export -----------------------------------------------------------------


def bulk_update(client, names, values):
    return client.post(
        f"{ORGS}bulk-update/",
        {"docnames": json.dumps(names), "action": "update", "data": json.dumps(values)},
        format="json",
    )


def test_bulk_update_writes_through_the_rules(auth_api, outsider, org):
    assert bulk_update(outsider, [org.pk], {"website": "x.test"}).json() == {"message": [org.pk]}
    org.refresh_from_db()
    assert org.website == ""
    assert bulk_update(auth_api, [org.pk], {"website": "x.test"}).json() == {"message": []}
    org.refresh_from_db()
    assert org.website == "x.test"


def test_export_reads_through_the_list_rule(auth_api, outsider, org):
    params = {"file_format_type": "CSV", "fields": json.dumps(["name", "website"])}
    assert outsider.get(f"{ORGS}export/", params).content == b'"Sr","ID","Website"\r\n'
    rows = auth_api.get(f"{ORGS}export/", params).content.decode().splitlines()
    assert rows == ['"Sr","ID","Website"', f'1,"{org.pk}",""']
