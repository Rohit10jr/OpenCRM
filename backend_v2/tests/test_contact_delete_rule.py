"""Contact: who may do what (specs/CONTACTS.md §4, §11.3, §11.5; FINDINGS 86; PE-29,
PE-34; milestone 3).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_contact_delete_rule.py:38-75``: the
resource route and `frappe.client.delete` are both `DELETE /api/v1/contacts/<name>/`;
`:78-92` (bulk delete) waits for milestone 6a. New: PE-29's matrix for a caller with no
CRM role, and the deletes a Contact now refuses (an Address, a Salutation or a Gender it
names; owner, A-74).
"""

from urllib.parse import quote

import pytest

from configuration.models import Country
from contacts.models import Address, Contact, Salutation

pytestmark = pytest.mark.django_db
CONTACTS = "/api/v1/contacts/"


@pytest.fixture
def grace(make_user):
    return make_user("grace@example.com", first_name="Grace", roles=["Sales Manager", "Sales User"])


@pytest.fixture
def outsider(make_user):
    return make_user("outsider@example.com")


def contact_by(user, first_name, **fields):
    return Contact.objects.create_for_user(user=user, first_name=first_name, last_name="Tester", **fields)


def url(contact):
    return f"{CONTACTS}{quote(contact.pk)}/"


# --- ported -------------------------------------------------------------------------------


def test_a_rep_reads_and_edits_any_contact_but_deletes_only_her_own(api_as, alice, administrator):
    theirs = contact_by(administrator, "Admins")
    mine = contact_by(alice, "Alices")
    client = api_as(alice)

    assert client.get(url(theirs)).status_code == 200
    response = client.patch(url(theirs), {"last_name": "Edited"}, format="json")
    assert response.status_code == 200, response.content[:300]

    assert client.delete(url(theirs)).status_code == 403
    assert Contact.objects.filter(pk=theirs.pk).exists(), "not hers to delete"

    assert client.delete(url(mine)).status_code == 200
    assert not Contact.objects.filter(pk=mine.pk).exists(), "the All row with if_owner"


def test_a_manager_is_refused_like_a_rep(api_as, grace, administrator):
    theirs = contact_by(administrator, "Admins")
    response = api_as(grace).delete(url(theirs))
    assert response.status_code == 403, response.content[:300]
    assert response.json()["exc_type"] == "PermissionError"
    assert Contact.objects.filter(pk=theirs.pk).exists()


def test_a_system_manager_deletes_anyones(api_as, alice, administrator):
    hers = contact_by(alice, "Alices")
    assert api_as(administrator).delete(url(hers)).status_code == 200
    assert not Contact.objects.filter(pk=hers.pk).exists()


def test_a_real_system_manager_deletes_another_users_contact(api_as, alice, make_user):
    """A-79 finding 6: the has_role branch, not the Administrator fixture."""
    boss = make_user("boss@example.com", roles=["System Manager"])
    hers = contact_by(alice, "Alices")
    assert api_as(boss).delete(url(hers)).status_code == 200
    assert not Contact.objects.filter(pk=hers.pk).exists()


@pytest.mark.parametrize("role", ["Sales User", "Sales Manager", "System Manager"])
def test_each_crm_role_reaches_contacts(api_as, make_user, administrator, role):
    contact = contact_by(administrator, "Reached")
    client = api_as(make_user("crm@example.com", roles=[role]))
    assert [r["name"] for r in client.get(CONTACTS).json()["message"]] == [contact.pk]
    assert client.get(url(contact)).status_code == 200


# --- PE-29: a caller with no CRM role ------------------------------------------------------


def test_an_outsider_reads_no_value(api_as, outsider, administrator):
    contact = contact_by(administrator, "Admins")
    response = api_as(outsider).get(
        f"{CONTACTS}value/", {"fieldname": "first_name", "filters": f'{{"name": "{contact.pk}"}}'}
    )
    assert response.status_code == 200
    assert response.json()["message"] == {}


def test_an_outsider_lists_and_finds_no_contact(api_as, outsider, administrator):
    contact_by(administrator, "Admins")
    client = api_as(outsider)
    assert client.get(CONTACTS).json()["message"] == []
    assert client.get(f"{CONTACTS}search/", {"txt": "Admins"}).json()["message"] == []


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_an_outsider_is_refused_a_contact_by_name(api_as, outsider, administrator, method):
    theirs = contact_by(administrator, "Admins")
    client = api_as(outsider)
    response = (
        client.patch(url(theirs), {"last_name": "X"}, format="json")
        if method == "patch"
        else getattr(client, method)(url(theirs))
    )
    assert response.status_code == 403
    assert response.json()["message"] == f"No permission for Contact {theirs.pk}"
    assert Contact.objects.get(pk=theirs.pk).last_name == "Tester"


def test_an_outsider_cannot_create_a_contact(api_as, outsider):
    response = api_as(outsider).post(CONTACTS, {"first_name": "Nope"}, format="json")
    assert response.status_code == 403
    assert response.json()["message"] == "Not permitted to create Contact"
    assert not Contact.objects.filter(first_name="Nope").exists()


def test_an_owner_with_no_crm_role_cannot_delete_their_own(api_as, outsider):
    """§11.5: the CRM-role gate comes before upstream's All/if_owner delete row."""
    own = contact_by(outsider, "Mine")
    assert api_as(outsider).delete(url(own)).status_code == 403
    assert Contact.objects.filter(pk=own.pk).exists()


# --- PE-34: what a contact now refuses to let go ------------------------------------------


def test_an_address_a_contact_names_cannot_be_deleted(api_as, administrator):
    address = Address(
        address_title="Home", address_type="Personal", address_line1="1 Main St",
        city="Pune", country=Country.objects.get(pk="India"),
    )
    address.save(user=administrator)
    contact = contact_by(administrator, "Housed", address=address)

    response = api_as(administrator).delete(f"/api/v1/addresses/{quote(address.pk)}/")
    assert response.status_code == 417
    assert response.json()["message"] == "You can disable this Address instead of deleting it."

    Contact.objects.filter(pk=contact.pk).update(address=None)
    assert api_as(administrator).delete(f"/api/v1/addresses/{quote(address.pk)}/").status_code == 200


def test_a_salutation_a_contact_names_cannot_be_deleted(api_as, administrator):
    contact = contact_by(administrator, "Titled", salutation="Dr")
    response = api_as(administrator).delete("/api/v1/salutations/Dr/")
    assert response.status_code == 417
    assert response.json()["message"] == (
        f"Cannot delete or cancel because Salutation Dr is linked with Contact {contact.pk}"
    )
    assert Salutation.objects.filter(pk="Dr").exists()


def test_a_gender_a_contact_names_cannot_be_deleted(api_as, administrator):
    """A-79 finding 7."""
    from contacts.models import Gender

    contact = contact_by(administrator, "Gendered", gender="Female")
    response = api_as(administrator).delete("/api/v1/genders/Female/")
    assert response.status_code == 417
    assert response.json()["message"] == (
        f"Cannot delete or cancel because Gender Female is linked with Contact {contact.pk}"
    )
    assert Gender.objects.filter(pk="Female").exists()
