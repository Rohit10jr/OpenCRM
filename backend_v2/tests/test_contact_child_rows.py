"""The Contact Email and Contact Phone row routes (specs/CONTACTS.md §4 "The child-row
routes", DECISIONS 60; PE-24's second sentence; PE-29; milestone 4). New: what the old
route's lookup and refusals answer, and the caches never written.
"""

from urllib.parse import quote

import pytest

from contacts.models import Contact, ContactEmail, ContactPhone

pytestmark = pytest.mark.django_db
CONTACTS = "/api/v1/contacts/"


@pytest.fixture
def contact(alice):
    c = Contact.objects.create_for_user(user=alice, first_name="Row", last_name="Owner")
    ContactEmail.objects.create_for_user(user=alice, parent_contact=c, email_id="a@zz.test", is_primary=True)
    ContactPhone.objects.create_for_user(user=alice, parent_contact=c, phone="+1 1", is_primary_mobile_no=True)
    return c


@pytest.fixture
def other(alice):
    c = Contact.objects.create_for_user(user=alice, first_name="Other", last_name="Owner")
    ContactEmail.objects.create_for_user(user=alice, parent_contact=c, email_id="o@zz.test", is_primary=True)
    return c


def url(contact, table, row_name):
    return f"{CONTACTS}{quote(contact.pk)}/{table}/{row_name}/"


def email_row(contact):
    return ContactEmail.objects.get(parent_contact=contact)


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_a_missing_row_is_404(auth_api, contact, method):
    response = getattr(auth_api, method)(url(contact, "email-ids", "nope"), {}, format="json")
    assert response.status_code == 404
    assert response.json()["message"] == "Contact Email nope not found"


def test_a_row_of_another_contact_is_404(auth_api, contact, other):
    row = email_row(other)
    response = auth_api.patch(url(contact, "email-ids", row.pk), {"email_id": "x@zz.test"}, format="json")
    assert response.status_code == 404
    assert response.json()["message"] == f"Contact Email {row.pk} not found"


def test_a_row_of_the_other_table_is_404(auth_api, contact):
    row = email_row(contact)
    response = auth_api.patch(url(contact, "phone-nos", row.pk), {"phone": "+1 9"}, format="json")
    assert response.status_code == 404
    assert response.json()["message"] == f"Contact Phone {row.pk} not found"


def test_a_missing_contact_is_404(auth_api, contact):
    row = email_row(contact)
    response = auth_api.patch(f"{CONTACTS}Nobody/email-ids/{row.pk}/", {"email_id": "x@zz.test"}, format="json")
    assert response.status_code == 404
    assert response.json()["message"] == f"Contact Email {row.pk} not found", "the row route, not the detail route"


def test_query_parameters_are_not_values(auth_api, contact):
    """The body only, as the document PATCH: `?email_id=` is not written, and a
    cache-buster does not turn standard fields alone into a write."""
    row = email_row(contact)
    standard = auth_api.patch(url(contact, "email-ids", row.pk) + "?_=1", {"idx": 9}, format="json")
    assert standard.status_code == 417
    assert "Cannot edit standard fields" in standard.json()["message"]
    query = auth_api.patch(url(contact, "email-ids", row.pk) + "?email_id=q@zz.test", {}, format="json")
    assert query.status_code == 200
    row.refresh_from_db()
    assert row.email_id == "a@zz.test"


def test_a_refused_edit_is_403_and_a_refused_delete_404(api_as, make_user, contact):
    """PE-29: a caller with no CRM role may not write the contact."""
    outsider = api_as(make_user("outsider@example.com"))
    row = email_row(contact)
    edit = outsider.patch(url(contact, "email-ids", row.pk), {"email_id": "x@zz.test"}, format="json")
    assert edit.status_code == 403
    assert edit.json()["message"] == "Not permitted to write Contact"
    removal = outsider.delete(url(contact, "email-ids", row.pk))
    assert removal.status_code == 404
    assert removal.json()["message"] == "DocType Contact Email not found"
    assert ContactEmail.objects.filter(pk=row.pk).exists()


def test_an_empty_body_answers_the_contact(auth_api, contact):
    row = email_row(contact)
    response = auth_api.patch(url(contact, "email-ids", row.pk), {}, format="json")
    assert response.status_code == 200
    assert response.json()["message"]["name"] == contact.pk


def test_unknown_keys_and_the_caches_and_the_parent_are_ignored(auth_api, contact, other):
    row = email_row(contact)
    response = auth_api.patch(
        url(contact, "email-ids", row.pk),
        {
            "email_id": "new@zz.test",
            "banana": 1,
            "_assign": ["someone@example.com"],
            "parent_contact": other.pk,
        },
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    row.refresh_from_db()
    assert (row.email_id, row._assign, row.parent_contact_id) == ("new@zz.test", [], contact.pk)


def test_a_name_with_a_slash_is_reached(auth_api, alice):
    c = Contact.objects.create_for_user(user=alice, company_name="R/GA")
    ContactEmail.objects.create_for_user(user=alice, parent_contact=c, email_id="r@zz.test", is_primary=True)
    row = email_row(c)
    response = auth_api.patch(f"{CONTACTS}R/GA/email-ids/{row.pk}/", {"email_id": "rg@zz.test"}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"]["email_id"] == "rg@zz.test"
