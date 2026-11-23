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
