"""The contact calls beyond the dropdown flows (specs/CONTACTS.md §4 "The contact calls",
"Primary email and phone" (h)-(i), PE-12f, PE-29, PE-35; milestone 4). New: no old test
covers `search_emails`, the 403-before-404 order, PE-12f or PE-35 through these paths.
Ported: ``backend/tests/test_contact_rules.py:172-180`` (a missing contact).
"""

from urllib.parse import quote

import pytest

from contacts.models import Contact, ContactEmail, ContactPhone

pytestmark = pytest.mark.django_db
CONTACTS = "/api/v1/contacts/"


def act(client, name, action, **payload):
    return client.post(f"{CONTACTS}{quote(name)}/{action}/", payload, format="json")


@pytest.fixture
def contact(alice):
    return Contact.objects.create_for_user(user=alice, first_name="ZZ", last_name="Jane")


@pytest.fixture
def outsider(make_user):
    return make_user("outsider@example.com")


# --- the contact check comes first --------------------------------------------------------


@pytest.mark.parametrize("action", ["create-new-email-or-phone", "set-as-primary"])
def test_a_missing_contact_is_not_permitted(auth_api, action):
    """Ported from `test_contact_rules.py:172-180`: 403, not the base 404."""
    response = act(auth_api, "ZZ Nobody", action, field="email", value="x@y.test")
    assert response.status_code == 403
    assert response.json()["exc_type"] == "PermissionError"
    assert response.json()["message"] == "Not permitted"


@pytest.mark.parametrize("action", ["create-new-email-or-phone", "set-as-primary"])
def test_the_contact_is_checked_before_the_field(auth_api, action):
    response = act(auth_api, "ZZ Nobody", action, field="banana", value="x")
    assert response.status_code == 403


@pytest.mark.parametrize("action", ["create-new-email-or-phone", "set-as-primary"])
def test_an_outsider_is_not_permitted(api_as, outsider, contact, action):
    """PE-29: a caller with no CRM role gets the same 403."""
    response = act(api_as(outsider), contact.pk, action, field="email", value="x@y.test")
    assert response.status_code == 403
    assert response.json()["message"] == "Not permitted"


@pytest.mark.parametrize("action", ["create-new-email-or-phone", "set-as-primary"])
def test_an_unknown_field_is_417(auth_api, contact, action):
    response = act(auth_api, contact.pk, action, field="banana", value="x")
    assert response.status_code == 417
    assert response.json()["message"] == "Invalid field"


# --- PE-12f -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload,message",
    [({"value": "x@y.test"}, "Field is required"), ({"field": "email"}, "Value is required")],
)
@pytest.mark.parametrize("action", ["create-new-email-or-phone", "set-as-primary"])
def test_pe12f_a_missing_argument_is_417(auth_api, contact, action, payload, message):
    response = act(auth_api, contact.pk, action, **payload)
    assert response.status_code == 417
    assert response.json()["message"] == message


def test_pe12f_search_emails_needs_txt(auth_api):
    response = auth_api.get(f"{CONTACTS}search-emails/")
    assert response.status_code == 417
    assert response.json()["message"] == "Search text is required"


# --- create_new and set_as_primary ----------------------------------------------------------


def test_create_new_makes_the_first_row_primary_and_keeps_idx_0(auth_api, contact):
    assert act(auth_api, contact.pk, "create-new-email-or-phone", field="email", value="a@zz.test").json() == {
        "message": True
    }
    act(auth_api, contact.pk, "create-new-email-or-phone", field="email", value="b@zz.test")
    rows = list(ContactEmail.objects.filter(parent_contact=contact).order_by("email_id"))
    assert [(r.email_id, r.is_primary, r.idx) for r in rows] == [("a@zz.test", True, 0), ("b@zz.test", False, 0)]
    contact.refresh_from_db()
    assert contact.email_id == "a@zz.test"


@pytest.mark.parametrize("field", ["mobile_no", "phone"])
def test_create_new_numbers_set_the_mobile_flag(auth_api, contact, field):
    act(auth_api, contact.pk, "create-new-email-or-phone", field=field, value="+1 1")
    row = ContactPhone.objects.get(parent_contact=contact)
    assert (row.is_primary_mobile_no, row.is_primary_phone) == (True, False)


def test_set_as_primary_with_no_matching_row_clears_every_flag(auth_api, contact):
    """With two rows: a lone row would be promoted again by the email rule (§4 (c)), as
    in the old backend, which runs the same derive."""
    act(auth_api, contact.pk, "create-new-email-or-phone", field="email", value="a@zz.test")
    act(auth_api, contact.pk, "create-new-email-or-phone", field="email", value="b@zz.test")
    response = act(auth_api, contact.pk, "set-as-primary", field="email", value="none@zz.test")
    assert response.json() == {"message": True}
    assert not ContactEmail.objects.filter(parent_contact=contact, is_primary=True).exists()
    contact.refresh_from_db()
    assert contact.email_id == ""


def test_set_as_primary_on_two_rows_of_one_value_is_refused_and_rolled_back(auth_api, alice, contact):
    ContactPhone.objects.bulk_create(
        [
            ContactPhone(name="zz-a", parent_contact=contact, phone="+1 1", is_primary_mobile_no=False),
            ContactPhone(name="zz-b", parent_contact=contact, phone="+1 1", is_primary_mobile_no=False),
        ]
    )
    response = act(auth_api, contact.pk, "set-as-primary", field="mobile_no", value="+1 1")
    assert response.status_code == 417
    assert response.json()["message"] == "Only one <strong>Mobile No</strong> can be set as primary."
    assert not ContactPhone.objects.filter(parent_contact=contact, is_primary_mobile_no=True).exists()


# --- PE-35 through both paths (§11.2) -------------------------------------------------------


def test_create_new_fills_user(auth_api, make_user, contact):
    ada = make_user("ada@example.com", email="ada@example.com")
    act(auth_api, contact.pk, "create-new-email-or-phone", field="email", value="ada@example.com")
    contact.refresh_from_db()
    assert contact.user_id == ada.pk


def test_set_as_primary_fills_user(auth_api, make_user, alice, contact):
    ada = make_user("ada@example.com", email="ada@example.com")
    ContactEmail.objects.bulk_create(
        [
            ContactEmail(name="zz-1", parent_contact=contact, email_id="other@example.com", is_primary=True),
            ContactEmail(name="zz-2", parent_contact=contact, email_id="ada@example.com", is_primary=False),
        ]
    )
    act(auth_api, contact.pk, "set-as-primary", field="email", value="ada@example.com")
    contact.refresh_from_db()
    assert (contact.email_id, contact.user_id) == ("ada@example.com", ada.pk)


# --- search_emails --------------------------------------------------------------------------


def _emails(alice):
    for first, email in (("Zed", "zed@zz.test"), ("Amy", "amy@zz.test"), ("Nobody", None)):
        c = Contact.objects.create_for_user(user=alice, first_name=first)
        if email:
            ContactEmail.objects.create_for_user(user=alice, parent_contact=c, email_id=email, is_primary=True)


def test_search_emails_answers_lists_ordered_by_email(auth_api, alice):
    _emails(alice)
    response = auth_api.get(f"{CONTACTS}search-emails/", {"txt": ""})
    assert response.status_code == 200
    assert response.json()["message"] == [["Amy", "amy@zz.test", "Amy"], ["Zed", "zed@zz.test", "Zed"]]


def test_search_emails_matches_on_name_email_or_full_name(auth_api, alice):
    _emails(alice)
    assert [row[0] for row in auth_api.get(f"{CONTACTS}search-emails/", {"txt": "zed"}).json()["message"]] == ["Zed"]


def test_search_emails_gives_an_outsider_nothing(api_as, outsider, alice):
    _emails(alice)
    response = api_as(outsider).get(f"{CONTACTS}search-emails/", {"txt": ""})
    assert response.json()["message"] == []
