"""The contact page's email and number dropdowns (FINDINGS 67; specs/CONTACTS.md §4;
milestone 4).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_contact_numbers.py``: `:25-85` here;
`:100-150` (edit and remove a row) with the row routes; `:88-94` (the list filter) waits
for milestone 7. `frappe.client.insert` of a Contact is `POST /api/v1/contacts/`;
`crm.api.contact.create_new` and `set_as_primary` are `POST /api/v1/contacts/<name>/
create-new-email-or-phone/` and `.../set-as-primary/`, `field` and `value` in the body.
"""

from urllib.parse import quote

import pytest

from contacts.models import Contact, ContactEmail, ContactPhone

pytestmark = pytest.mark.django_db

CONTACTS = "/api/v1/contacts/"
FIRST, SECOND = "+91 98765 11111", "+91 98765 22222"


def act(client, name, action, **payload):
    return client.post(f"{CONTACTS}{quote(name)}/{action}/", payload, format="json")


@pytest.fixture
def contact(auth_api):
    """As the New Contact dialog sends it, then a second number and a second address."""
    response = auth_api.post(
        CONTACTS,
        {
            "first_name": "ZZ Numbers",
            "email_ids": [{"email_id": "first@example.com", "is_primary": 1}],
            "phone_nos": [{"phone": FIRST, "is_primary_mobile_no": 1}],
        },
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    name = response.json()["message"]["name"]
    assert act(auth_api, name, "create-new-email-or-phone", field="phone", value=SECOND).status_code == 200
    assert (
        act(auth_api, name, "create-new-email-or-phone", field="email", value="second@example.com").status_code
        == 200
    )
    return Contact.objects.get(pk=name)


def primaries(contact, flag="is_primary_mobile_no"):
    return list(
        ContactPhone.objects.filter(parent_contact=contact, **{flag: True}).values_list("phone", flat=True)
    )


# --- picking ------------------------------------------------------------------------------


def test_picking_another_number_makes_it_the_only_primary(auth_api, contact):
    response = act(auth_api, contact.pk, "set-as-primary", field="mobile_no", value=SECOND)
    assert response.status_code == 200, response.content[:300]
    contact.refresh_from_db()
    assert contact.mobile_no == SECOND
    assert primaries(contact) == [SECOND]

    back = act(auth_api, contact.pk, "set-as-primary", field="mobile_no", value=FIRST)
    assert back.status_code == 200
    contact.refresh_from_db()
    assert contact.mobile_no == FIRST and primaries(contact) == [FIRST]


def test_picking_another_email_makes_it_the_only_primary(auth_api, contact):
    response = act(auth_api, contact.pk, "set-as-primary", field="email", value="second@example.com")
    assert response.status_code == 200, response.content[:300]
    contact.refresh_from_db()
    assert contact.email_id == "second@example.com"
    flagged = ContactEmail.objects.filter(parent_contact=contact, is_primary=True)
    assert [row.email_id for row in flagged] == ["second@example.com"]


def test_the_primary_phone_is_a_separate_flag(auth_api, contact):
    """`field="phone"` sets `is_primary_phone` and leaves the mobile flag alone."""
    response = act(auth_api, contact.pk, "set-as-primary", field="phone", value=SECOND)
    assert response.status_code == 200
    contact.refresh_from_db()
    assert (contact.phone, contact.mobile_no) == (SECOND, FIRST)
    assert primaries(contact, "is_primary_phone") == [SECOND]


# --- editing and removing (ported `:100-150`) ------------------------------------------------
# `frappe.client.set_value` / `delete` on the child doctype are `PATCH` / `DELETE
# /api/v1/contacts/<name>/phone-nos/<row>/` and `.../email-ids/<row>/`; the value is in the
# body as `{"<fieldname>": <value>}`.


def row_url(contact, table, row):
    return f"{CONTACTS}{quote(contact.pk)}/{table}/{row.pk}/"


def test_a_number_is_edited_through_its_contact(auth_api, contact):
    row = ContactPhone.objects.get(parent_contact=contact, phone=FIRST)
    response = auth_api.patch(row_url(contact, "phone-nos", row), {"phone": "+91 90000 00000"}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"]["name"] == contact.pk
    contact.refresh_from_db()
    assert contact.mobile_no == "+91 90000 00000", "it was the primary, so the contact follows"


def test_an_email_edit_is_still_validated(auth_api, contact):
    row = ContactEmail.objects.get(parent_contact=contact, email_id="second@example.com")
    response = auth_api.patch(row_url(contact, "email-ids", row), {"email_id": "not-an-email"}, format="json")
    assert response.status_code == 417
    row.refresh_from_db()
    assert row.email_id == "second@example.com"


def test_only_standard_fields_is_refused(auth_api, contact):
    row = ContactPhone.objects.get(parent_contact=contact, phone=FIRST)
    response = auth_api.patch(row_url(contact, "phone-nos", row), {"idx": 9}, format="json")
    assert response.status_code == 417
    assert "Cannot edit standard fields" in response.json()["message"]


def test_a_number_is_removed_through_its_contact(auth_api, contact):
    row = ContactPhone.objects.get(parent_contact=contact, phone=FIRST)
    response = auth_api.delete(row_url(contact, "phone-nos", row))
    assert response.status_code == 200, response.content[:300]
    assert response.json() == {"message": None}
    assert not ContactPhone.objects.filter(pk=row.pk).exists()
    contact.refresh_from_db()
    assert contact.mobile_no == "", "the primary went, and a number is not promoted on its own"


def test_removing_the_primary_email_promotes_the_one_that_is_left(auth_api, contact):
    row = ContactEmail.objects.get(parent_contact=contact, email_id="first@example.com")
    assert auth_api.delete(row_url(contact, "email-ids", row)).status_code == 200
    contact.refresh_from_db()
    assert contact.email_id == "second@example.com"


def test_other_child_tables_are_still_not_reachable(auth_api, contact):
    """Only the two tables have a row route: a Dynamic Link row is not one."""
    response = auth_api.patch(f"{CONTACTS}{quote(contact.pk)}/links/x/", {"link_name": "y"}, format="json")
    assert response.status_code == 404
