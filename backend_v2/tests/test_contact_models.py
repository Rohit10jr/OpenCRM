"""Contact on the model (specs/CONTACTS.md §4; milestone 3).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_platform_models.py:148-223`` (the
Contact half; `:226-244`, `default_list_data`, waits for milestone 7) and
``backend/tests/test_crm_behaviour.py:424-430`` (the rows serialise inline).
`session_user` + `objects.create` is `create_for_user`; the old registry serializer is
`ContactSerializer`. `:210-214` ("first email wins") passes together with
`test_contact_rules.py`'s "two unflagged rows give an empty column" only because of
the rules (c) and (f) of §4: the first row is promoted when it is the lone one, and
the second row's signal finds it already primary.
"""

import pytest

from contacts.models import Contact, ContactEmail, ContactPhone
from contacts.serializers import ContactSerializer

pytestmark = pytest.mark.django_db


@pytest.fixture
def contact(alice):
    return Contact.objects.create_for_user(user=alice, first_name="Jane", last_name="Doe")


def test_contact_full_name_is_derived(contact):
    assert contact.full_name == "Jane Doe"


def test_contact_is_named_from_its_full_name(contact):
    assert contact.name == "Jane Doe"


def test_contact_name_collision_gets_a_numeric_suffix(alice, contact):
    second = Contact.objects.create_for_user(user=alice, first_name="Jane", last_name="Doe")
    assert second.name == "Jane Doe-1"


def test_contact_name_does_not_include_the_company(alice):
    c = Contact.objects.create_for_user(
        user=alice, first_name="Jane", last_name="Doe", company_name="Acme"
    )
    assert c.name == "Jane Doe"


def test_primary_email_is_denormalised_onto_the_contact(alice, contact):
    ContactEmail.objects.create_for_user(
        user=alice, parent_contact=contact, email_id="jane@acme.com", is_primary=True
    )
    contact.refresh_from_db()
    assert contact.email_id == "jane@acme.com"


def test_primary_mobile_is_denormalised_onto_the_contact(alice, contact):
    ContactPhone.objects.create_for_user(
        user=alice, parent_contact=contact, phone="+15550001", is_primary_mobile_no=True
    )
    contact.refresh_from_db()
    assert contact.mobile_no == "+15550001"


def test_primary_phone_and_mobile_are_separate(alice, contact):
    ContactPhone.objects.create_for_user(
        user=alice, parent_contact=contact, phone="+15550001", is_primary_mobile_no=True
    )
    ContactPhone.objects.create_for_user(
        user=alice, parent_contact=contact, phone="+15550002", is_primary_phone=True
    )
    contact.refresh_from_db()
    assert contact.mobile_no == "+15550001"
    assert contact.phone == "+15550002"


def test_first_email_wins_when_none_is_flagged_primary(alice, contact):
    ContactEmail.objects.create_for_user(user=alice, parent_contact=contact, email_id="first@acme.com")
    ContactEmail.objects.create_for_user(user=alice, parent_contact=contact, email_id="second@acme.com")
    contact.refresh_from_db()
    assert contact.email_id == "first@acme.com"


def test_removing_the_primary_email_clears_the_cache(alice, contact):
    email = ContactEmail.objects.create_for_user(
        user=alice, parent_contact=contact, email_id="jane@acme.com", is_primary=True
    )
    email.delete()
    contact.refresh_from_db()
    assert contact.email_id == ""


def test_contact_children_serialise_inline(alice):
    """Ported from `test_crm_behaviour.py:424-430`."""
    c = Contact.objects.create_for_user(user=alice, first_name="Grace", last_name="Hopper")
    ContactEmail.objects.create_for_user(
        user=alice, parent_contact=c, email_id="grace@navy.mil", is_primary=True
    )
    data = ContactSerializer(c, context={"user": alice}).data
    assert data["email_ids"][0]["email_id"] == "grace@navy.mil"
