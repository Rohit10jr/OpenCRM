"""Contact's shared actions (specs/CONTACTS.md §8, PE-24, PE-25, PE-26, PE-29, PE-34;
milestone 6a). The mixins are tested on `tests_support` (SHARED_ACTIONS, CONTACTS
milestone 0); these pin what they do with Contact's own rules and links.

From `docs/http/05_contacts_organizations.http` 5.3-5.4, 5.6-5.7 (rename). New: each
action's refusal to a caller with no CRM role, and the bulk delete of a contact an
Address links (old `crm_app/api/doc.py:691-715`: with `remove_contact` only the
document's `contact` and `contacts` are cleared, so the Dynamic Link refuses the batch).
Upstream refuses that contact for the same reason, but answers 200 "success" with a
"Failed to delete" message and deletes the rest of the batch (v15
`frappe/desk/reportview.py:631-666`); v2 keeps the old backend's one-transaction batch
(FINDINGS 76, `temp` A-82).
"""

import json
from urllib.parse import quote

import pytest

from configuration.models import Country
from contacts.models import Address, Contact, ContactEmail, ContactPhone, DynamicLink
from contacts.views import ContactViewSet

pytestmark = pytest.mark.django_db
CONTACTS = "/api/v1/contacts/"


@pytest.fixture
def outsider(api_as, make_user):
    return api_as(make_user("outsider@example.com"))


@pytest.fixture
def system_manager(make_user):
    return make_user("sysman@example.com", roles=["System Manager"])


@pytest.fixture
def jane(alice):
    c = Contact.objects.create_for_user(user=alice, first_name="ZZ Jane", last_name="Roe")
    ContactEmail.objects.create_for_user(user=alice, parent_contact=c, email_id="j@zz.test", is_primary=True, idx=1)
    ContactPhone.objects.create_for_user(user=alice, parent_contact=c, phone="+1 1", is_primary_mobile_no=True, idx=1)
    return c


@pytest.fixture
def address(alice, jane):
    country = Country.objects.first() or Country.objects.create_for_user(user=alice, name="Narnia")
    a = Address.objects.create_for_user(
        user=alice, address_title="ZZ Home", address_line1="1 St", city="X", country=country
    )
    DynamicLink.objects.create_for_user(
        user=alice,
        name="zz-link",
        parent=a.pk,
        parenttype="Address",
        parentfield="links",
        link_doctype="Contact",
        link_name=jane.pk,
        idx=1,
    )
    return a


def at(contact, action=""):
    return f"{CONTACTS}{quote(contact.pk)}/{action}"


# --- rename (PE-24) -------------------------------------------------------------------------


def test_rename_keeps_the_email_and_phone_rows_and_moves_the_links(auth_api, jane, address):
    """05 5.3-5.4; an Address naming the contact follows through its Dynamic Link."""
    response = auth_api.post(at(jane, "rename/"), {"new_name": "ZZ Jane Renamed"}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert response.json() == {"message": "ZZ Jane Renamed"}
    document = auth_api.get(f"{CONTACTS}ZZ%20Jane%20Renamed/").json()["message"]
    assert (len(document["email_ids"]), len(document["phone_nos"])) == (1, 1)
    assert DynamicLink.objects.get(pk="zz-link").link_name == "ZZ Jane Renamed"


def test_rename_onto_an_existing_contact_is_refused(auth_api, alice, jane):
    """05 5.6."""
    Contact.objects.create_for_user(user=alice, company_name="ZZ Acme Only")
    response = auth_api.post(at(jane, "rename/"), {"new_name": "ZZ Acme Only"}, format="json")
    assert response.status_code == 417
    assert response.json()["message"] == "Another Contact with name ZZ Acme Only exists, select another name"


def test_a_merge_is_refused(auth_api, alice, jane):
    """05 5.7."""
    Contact.objects.create_for_user(user=alice, company_name="ZZ Acme Only")
    response = auth_api.post(at(jane, "rename/"), {"new_name": "ZZ Acme Only", "merge": 1}, format="json")
    assert response.status_code == 417
    assert response.json()["message"] == "Merging documents is not supported"


def test_an_outsider_may_not_rename(outsider, jane):
    response = outsider.post(at(jane, "rename/"), {"new_name": "X"}, format="json")
    assert response.status_code == 417
    assert response.json()["message"] == f"You need write permission on Contact {jane.pk} to rename"
    assert Contact.objects.filter(pk=jane.pk).exists()


# --- bulk delete (PE-25) --------------------------------------------------------------------


def test_contact_bulk_delete_opts_in_to_remove_contact():
    """The old `remove_contact=(doctype == "Contact")` (`doc.py:703`). No routed doctype has
    a `contact` field or `contacts` table until SALES; the clearing itself is tested on
    `tests_support` (`core/tests/test_linked_contact_and_delete.py`)."""
    assert ContactViewSet.bulk_delete_remove_contact is True


def test_bulk_delete_of_a_contact_an_address_links_is_refused(auth_api, jane, address):
    """`remove_contact` leaves the Address's Dynamic Link, so the dynamic check refuses the
    batch and nothing is deleted (old `doc.py:691-715`; upstream refuses this item too,
    `delete_doc.py:141-153`, but answers 200 and deletes the rest)."""
    response = auth_api.post(f"{CONTACTS}bulk-delete/", {"items": json.dumps([jane.pk])}, format="json")
    assert response.status_code == 417
    assert response.json()["exc_type"] == "LinkExistsError"
    assert response.json()["message"] == (
        f"Cannot delete or cancel because Contact {jane.pk} is linked with Address {address.pk} at Row: 1"
    )
    assert Contact.objects.filter(pk=jane.pk).exists()
    assert DynamicLink.objects.filter(pk="zz-link").exists()


def test_an_outsider_may_not_bulk_delete(outsider, alice):
    mine = Contact.objects.create_for_user(user=alice, first_name="ZZ Mine")
    response = outsider.post(f"{CONTACTS}bulk-delete/", {"items": json.dumps([mine.pk])}, format="json")
    assert response.status_code == 403
    assert response.json()["message"] == f"No permission to delete Contact {mine.pk}"
    assert Contact.objects.filter(pk=mine.pk).exists()


def bulk_delete_linked(client, contact):
    return client.post(
        f"{CONTACTS}bulk-delete/", {"items": json.dumps([contact.pk]), "delete_linked": True}, format="json"
    )


def test_delete_linked_skips_an_address_a_rep_may_not_delete(auth_api, jane, address):
    """PE-26 on the bulk door: Address delete is System Manager's, so it is skipped, its
    link stays and the batch is refused; nothing goes."""
    response = bulk_delete_linked(auth_api, jane)
    assert response.status_code == 417
    assert response.json()["exc_type"] == "LinkExistsError"
    assert Address.objects.filter(pk=address.pk).exists()
    assert Contact.objects.filter(pk=jane.pk).exists()


def test_delete_linked_by_a_system_manager_deletes_the_address_then_the_contact(api_as, system_manager, jane, address):
    response = bulk_delete_linked(api_as(system_manager), jane)
    assert response.json() == {"message": "success"}, response.content[:300]
    assert not Address.objects.filter(pk=address.pk).exists()
    assert not DynamicLink.objects.filter(pk="zz-link").exists()
    assert not Contact.objects.filter(pk=jane.pk).exists()


# --- linked documents (PE-26) ---------------------------------------------------------------


def test_linked_documents_lists_the_address(auth_api, jane, address):
    response = auth_api.get(at(jane, "linked-documents/"))
    assert response.status_code == 200
    assert response.json()["message"] == [
        {"doc": "Address", "title": address.pk, "reference_docname": address.pk, "reference_doctype": "Address"}
    ]


def test_an_outsider_is_refused_the_linked_documents(outsider, jane):
    response = outsider.get(at(jane, "linked-documents/"))
    assert response.status_code == 403
    assert response.json()["message"] == f"No permission for Contact {jane.pk}"


def test_an_address_the_caller_may_not_delete_is_skipped(auth_api, jane, address):
    """PE-26: Address delete is System Manager's or Administrator's; a rep's unlink with
    `delete` skips it, and answers success."""
    response = auth_api.post(
        at(jane, "linked-documents/"),
        {"items": [{"doctype": "Address", "docname": address.pk}], "delete": True},
        format="json",
    )
    assert response.json() == {"message": "success"}
    assert Address.objects.filter(pk=address.pk).exists()


def unlink_delete(client, contact, address):
    return client.post(
        at(contact, "linked-documents/"),
        {"items": [{"doctype": "Address", "docname": address.pk}], "delete": True},
        format="json",
    )


def test_a_system_manager_unlink_with_delete_removes_the_address(api_as, system_manager, jane, address):
    """The positive control for the skip above."""
    assert unlink_delete(api_as(system_manager), jane, address).json() == {"message": "success"}
    assert not Address.objects.filter(pk=address.pk).exists()


def test_an_address_the_contact_names_is_skipped(api_as, system_manager, jane, address):
    """PE-34: the contact's own `address` names it, so the linked delete skips it."""
    Contact.objects.filter(pk=jane.pk).update(address=address)
    assert unlink_delete(api_as(system_manager), jane, address).json() == {"message": "success"}
    assert Address.objects.filter(pk=address.pk).exists()


def test_an_outsiders_unlink_changes_nothing(outsider, jane, address):
    """The POST never loads the contact; each item needs its own write rule, which an
    outsider lacks (upstream's `remove_linked_doc_reference` takes no source either)."""
    response = outsider.post(
        at(jane, "linked-documents/"), {"items": [{"doctype": "Address", "docname": address.pk}]}, format="json"
    )
    assert response.json() == {"message": "success"}
    assert DynamicLink.objects.get(pk="zz-link").link_name == jane.pk


# --- bulk update and export (PE-29) ---------------------------------------------------------


def bulk_update(client, names, values):
    return client.post(
        f"{CONTACTS}bulk-update/",
        {"docnames": json.dumps(names), "action": "update", "data": json.dumps(values)},
        format="json",
    )


def test_bulk_update_writes_through_the_contact_rules(auth_api, outsider, jane):
    refused = bulk_update(outsider, [jane.pk], {"designation": "Boss"})
    assert refused.json() == {"message": [jane.pk]}, "the failed names"
    jane.refresh_from_db()
    assert jane.designation == ""

    done = bulk_update(auth_api, [jane.pk], {"designation": "Boss"})
    assert done.json() == {"message": []}
    jane.refresh_from_db()
    assert jane.designation == "Boss"


def test_export_reads_through_the_list_rule(auth_api, outsider, jane):
    params = {"file_format_type": "CSV", "fields": json.dumps(["name", "first_name"])}
    assert outsider.get(f"{CONTACTS}export/", params).content == b'"Sr","ID","First Name"\r\n'
    rows = auth_api.get(f"{CONTACTS}export/", params).content.decode().splitlines()
    assert rows == ['"Sr","ID","First Name"', f'1,"{jane.pk}","ZZ Jane"']
