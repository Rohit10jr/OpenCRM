"""Contact's primary rules on a document save, email validation, and a delete that
validates nothing (specs/CONTACTS.md §4; FINDINGS 10, 11, 23; milestone 3).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_contact_rules.py``: `:36-107`,
`:112-118`, `:150-166`, `:197-228`. `PUT /api/resource/Contact/<name>` is
`PATCH /api/v1/contacts/<name>/`, the answer under `message`; a create answers 200, not
201. Waiting: `:121-147` (Lead, Deal: SALES), `:172-180` (`create_new`: milestone 4),
`:183-191` (comments: ACTIVITIES).
"""

from urllib.parse import quote

import pytest

from contacts.models import Contact, ContactEmail, ContactPhone

pytestmark = pytest.mark.django_db

CONTACTS = "/api/v1/contacts/"


@pytest.fixture
def contact(alice):
    return Contact.objects.create_for_user(user=alice, first_name="ZZ", last_name="Jane")


def _patch(client, contact, body):
    return client.patch(f"{CONTACTS}{quote(contact.name)}/", body, format="json")


# --- 10: the primary rules ---------------------------------------------------------------


def test_a_lone_email_row_becomes_primary_and_the_column_follows(auth_api, contact):
    data = _patch(auth_api, contact, {"email_ids": [{"email_id": "acme@zz.test"}]}).json()["message"]
    assert data["email_ids"][0]["is_primary"] is True
    assert data["email_id"] == "acme@zz.test"
    assert ContactEmail.objects.get(parent_contact=contact).is_primary is True


def test_a_bare_email_column_with_no_rows_is_cleared(auth_api, contact):
    data = _patch(auth_api, contact, {"email_id": "orphan@zz.test"}).json()["message"]
    assert data["email_id"] == ""


def test_two_rows_with_no_primary_leave_the_column_empty(auth_api, contact):
    data = _patch(
        auth_api, contact, {"email_ids": [{"email_id": "a@zz.test"}, {"email_id": "b@zz.test"}]}
    ).json()["message"]
    assert data["email_id"] == ""
    assert [row["is_primary"] for row in data["email_ids"]] == [False, False]


def test_two_primary_emails_are_refused(auth_api, contact):
    response = _patch(
        auth_api,
        contact,
        {"email_ids": [{"email_id": "a@zz.test", "is_primary": 1}, {"email_id": "b@zz.test", "is_primary": 1}]},
    )
    assert response.status_code == 417
    assert response.json()["message"] == "Only one <strong>Email ID</strong> can be set as primary."


def test_phone_and_mobile_follow_their_own_flags(auth_api, contact):
    data = _patch(
        auth_api,
        contact,
        {"phone_nos": [{"phone": "+1 333", "is_primary_mobile_no": 1}, {"phone": "+1 444", "is_primary_phone": 1}]},
    ).json()["message"]
    assert data["mobile_no"] == "+1 333"
    assert data["phone"] == "+1 444"


def test_a_lone_phone_row_is_not_made_primary(auth_api, contact):
    data = _patch(auth_api, contact, {"phone_nos": [{"phone": "+1 333"}]}).json()["message"]
    assert data["mobile_no"] == ""
    assert data["phone"] == ""


@pytest.mark.parametrize(
    "flag,label", [("is_primary_phone", "Phone"), ("is_primary_mobile_no", "Mobile No")]
)
def test_two_primary_numbers_are_refused(auth_api, contact, flag, label):
    response = _patch(
        auth_api, contact, {"phone_nos": [{"phone": "+1 1", flag: 1}, {"phone": "+1 2", flag: 1}]}
    )
    assert response.status_code == 417
    assert response.json()["message"] == f"Only one <strong>{label}</strong> can be set as primary."


def test_rows_sent_on_create_are_applied_by_the_first_save(auth_api, alice):
    response = auth_api.post(
        CONTACTS,
        {"first_name": "ZZ", "last_name": "New", "email_ids": [{"email_id": "new@zz.test"}]},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    data = response.json()["message"]
    assert data["email_ids"][0]["is_primary"] is True
    assert data["email_id"] == "new@zz.test"


# --- 11: email addresses are validated --------------------------------------------------


def test_an_email_row_that_is_not_an_address_is_refused(auth_api, contact):
    response = _patch(auth_api, contact, {"email_ids": [{"email_id": "not-an-email"}]})
    assert response.status_code == 417
    body = response.json()
    assert body["exc_type"] == "InvalidEmailAddressError"
    assert body["message"] == "not-an-email is not a valid Email Address"


def test_a_semicolon_is_not_a_separator(auth_api, contact):
    response = _patch(auth_api, contact, {"email_ids": [{"email_id": "a@zz.test;b@zz.test"}]})
    assert response.status_code == 417
    assert response.json()["exc_type"] == "InvalidEmailAddressError"


def test_the_invalid_address_is_html_escaped(auth_api, contact):
    response = _patch(auth_api, contact, {"email_ids": [{"email_id": "<b>x</b>"}]})
    assert response.json()["message"] == "&lt;b&gt;x&lt;/b&gt; is not a valid Email Address"


def test_a_display_name_form_is_accepted(auth_api, contact):
    response = _patch(auth_api, contact, {"email_ids": [{"email_id": "Jane <jane@zz.test>"}]})
    assert response.status_code == 200, response.content[:300]


# --- 23: a delete never validates the rows it removes ------------------------------------


def test_a_contact_whose_rows_would_fail_a_save_can_still_be_deleted(api_as, administrator, contact):
    ContactPhone.objects.bulk_create(
        [
            ContactPhone(name="zz-row-1", parent_contact=contact, phone="+1 1", is_primary_phone=True),
            ContactPhone(name="zz-row-2", parent_contact=contact, phone="+1 1", is_primary_phone=True),
        ]
    )
    response = api_as(administrator).delete(f"{CONTACTS}{quote(contact.name)}/")
    assert response.status_code == 200, response.content[:300]
    assert not Contact.objects.filter(pk=contact.pk).exists()
    assert not ContactPhone.objects.filter(parent_contact_id=contact.pk).exists()


def test_a_row_deleted_on_its_own_still_resyncs_the_contact(auth_api, contact):
    _patch(auth_api, contact, {"email_ids": [{"email_id": "acme@zz.test"}]})
    contact.refresh_from_db()
    assert contact.email_id == "acme@zz.test"

    ContactEmail.objects.get(parent_contact=contact).delete()

    contact.refresh_from_db()
    assert contact.email_id == ""
