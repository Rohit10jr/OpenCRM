"""The contact page's email and number dropdowns: docs/FINDINGS.md 67.

Each dropdown lists the contact's rows, marks the primary one, and lets the user add a
row, pick another as primary, edit one and remove one (``useContactFields.ts``). Picking
threw "Only one Mobile No can be set as primary." and left two rows flagged; editing and
removing answered 404. Shapes follow ``crm/api/contact.py:67-111`` and
``frappe/client.py:183-223``, ``551-572``.
"""

import pytest

from frappe_core.api.doc import get_data
from frappe_core.session import session_user
from frappe_platform.models import Contact, ContactEmail, ContactPhone

pytestmark = pytest.mark.django_db

FIRST, SECOND = "+91 98765 11111", "+91 98765 22222"


def call(client, method, **payload):
    return client.post(f"/api/method/{method}", payload, format="json")


@pytest.fixture
def contact(auth_api):
    """As the New Contact dialog sends it, then a second number and a second address."""
    response = call(
        auth_api,
        "frappe.client.insert",
        doc={
            "doctype": "Contact",
            "first_name": "ZZ Numbers",
            "email_ids": [{"email_id": "first@example.com", "is_primary": 1}],
            "phone_nos": [{"phone": FIRST, "is_primary_mobile_no": 1}],
        },
    )
    assert response.status_code == 200, response.content[:300]
    name = response.json()["message"]["name"]
    assert call(auth_api, "crm.api.contact.create_new", contact=name, field="phone", value=SECOND).status_code == 200
    assert (
        call(auth_api, "crm.api.contact.create_new", contact=name, field="email", value="second@example.com").status_code
        == 200
    )
    return Contact.objects.get(pk=name)


def primaries(contact, flag="is_primary_mobile_no"):
    return list(ContactPhone.objects.filter(parent_contact=contact, **{flag: True}).values_list("phone", flat=True))


# --------------------------------------------------------------------------- picking


def test_picking_another_number_makes_it_the_only_primary(auth_api, contact):
    response = call(auth_api, "crm.api.contact.set_as_primary", contact=contact.pk, field="mobile_no", value=SECOND)
    assert response.status_code == 200, response.content[:300]
    contact.refresh_from_db()
    assert contact.mobile_no == SECOND
    assert primaries(contact) == [SECOND]

    back = call(auth_api, "crm.api.contact.set_as_primary", contact=contact.pk, field="mobile_no", value=FIRST)
    assert back.status_code == 200
    contact.refresh_from_db()
    assert contact.mobile_no == FIRST and primaries(contact) == [FIRST]


def test_picking_another_email_makes_it_the_only_primary(auth_api, contact):
    response = call(
        auth_api, "crm.api.contact.set_as_primary", contact=contact.pk, field="email", value="second@example.com"
    )
    assert response.status_code == 200, response.content[:300]
    contact.refresh_from_db()
    assert contact.email_id == "second@example.com"
    flagged = ContactEmail.objects.filter(parent_contact=contact, is_primary=True)
    assert [row.email_id for row in flagged] == ["second@example.com"]


def test_the_primary_phone_is_a_separate_flag(auth_api, contact):
    """``field="phone"`` sets ``is_primary_phone`` and leaves the mobile flag alone."""
    response = call(auth_api, "crm.api.contact.set_as_primary", contact=contact.pk, field="phone", value=SECOND)
    assert response.status_code == 200
    contact.refresh_from_db()
    assert (contact.phone, contact.mobile_no) == (SECOND, FIRST)
    assert primaries(contact, "is_primary_phone") == [SECOND]


def test_the_list_filters_on_the_number_that_is_now_primary(auth_api, alice, contact):
    call(auth_api, "crm.api.contact.set_as_primary", contact=contact.pk, field="mobile_no", value=SECOND)
    with session_user(alice.name):
        result = get_data("Contact", filters={"mobile_no": ["like", "%22222%"]}, view={"view_type": "list"})
        other = get_data("Contact", filters={"mobile_no": ["like", "%11111%"]}, view={"view_type": "list"})
    assert [row["name"] for row in result["data"]] == [contact.pk]
    assert other["data"] == []


# --------------------------------------------------------------------------- editing and removing


def test_a_number_is_edited_through_its_contact(auth_api, contact):
    """``frappe.client.set_value`` on the child doctype; the answer is the contact."""
    row = ContactPhone.objects.get(parent_contact=contact, phone=FIRST)
    response = call(
        auth_api, "frappe.client.set_value", doctype="Contact Phone", name=row.pk, fieldname="phone", value="+91 90000 00000"
    )
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"]["name"] == contact.pk
    contact.refresh_from_db()
    assert contact.mobile_no == "+91 90000 00000", "it was the primary, so the contact follows"


def test_an_email_edit_is_still_validated(auth_api, contact):
    row = ContactEmail.objects.get(parent_contact=contact, email_id="second@example.com")
    response = call(
        auth_api, "frappe.client.set_value", doctype="Contact Email", name=row.pk, fieldname="email_id", value="not-an-email"
    )
    assert response.status_code == 417
    row.refresh_from_db()
    assert row.email_id == "second@example.com"


def test_only_standard_fields_is_refused(auth_api, contact):
    row = ContactPhone.objects.get(parent_contact=contact, phone=FIRST)
    response = call(auth_api, "frappe.client.set_value", doctype="Contact Phone", name=row.pk, fieldname={"idx": 9})
    assert response.status_code == 417
    assert "Cannot edit standard fields" in response.json()["exception"]


def test_a_number_is_removed_through_its_contact(auth_api, contact):
    row = ContactPhone.objects.get(parent_contact=contact, phone=FIRST)
    response = call(auth_api, "frappe.client.delete", doctype="Contact Phone", name=row.pk)
    assert response.status_code == 200, response.content[:300]
    assert not ContactPhone.objects.filter(pk=row.pk).exists()
    contact.refresh_from_db()
    assert contact.mobile_no == "", "the primary went, and a number is not promoted on its own"


def test_removing_the_primary_email_promotes_the_one_that_is_left(auth_api, contact):
    """``contact.py:183-187``: a lone email row becomes the primary."""
    row = ContactEmail.objects.get(parent_contact=contact, email_id="first@example.com")
    assert call(auth_api, "frappe.client.delete", doctype="Contact Email", name=row.pk).status_code == 200
    contact.refresh_from_db()
    assert contact.email_id == "second@example.com"


def test_other_child_tables_are_still_not_reachable(auth_api):
    """Opted in one at a time: a row that is not ``CLIENT_EDITABLE`` stays a 404."""
    response = call(auth_api, "frappe.client.set_value", doctype="Dynamic Link", name="x", fieldname="link_name", value="y")
    assert response.status_code == 404
    assert call(auth_api, "frappe.client.delete", doctype="Dynamic Link", name="x").status_code == 404
