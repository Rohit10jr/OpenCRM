"""Contact's `user` from the User with the contact's email (specs/CONTACTS.md §11.2;
owner, temp A-48 6.2, A-65, A-67). New: the old backend leaves `user` as sent.
Upstream: v15 `frappe/contacts/doctype/contact/contact.py:65-71,131-133`.
"""

import datetime

import pytest
from django.utils import timezone

from accounts.models import User
from contacts.models import Contact, ContactEmail

pytestmark = pytest.mark.django_db


def contact_with_email(administrator, email, **fields):
    contact = Contact.objects.create_for_user(user=administrator, first_name="Ada", **fields)
    ContactEmail(parent_contact=contact, email_id=email, is_primary=True).save(user=administrator)
    contact.refresh_from_db()
    return contact


def test_user_is_filled_once_the_email_is_set(administrator, make_user):
    ada = make_user("ada@example.com", email="ada@example.com")
    contact = contact_with_email(administrator, "ada@example.com")
    assert contact.email_id == "ada@example.com"
    assert contact.user_id == ada.pk


def test_a_later_save_with_the_email_fills_it(administrator, make_user):
    contact = Contact.objects.create_for_user(user=administrator, first_name="Ada")
    assert contact.user_id is None
    ada = make_user("ada@example.com", email="ada@example.com")
    ContactEmail(parent_contact=contact, email_id="ada@example.com", is_primary=True).save(
        user=administrator
    )
    contact.refresh_from_db()
    contact.save(user=administrator)
    contact.refresh_from_db()
    assert contact.user_id == ada.pk


def test_an_explicit_user_is_kept(administrator, make_user):
    make_user("ada@example.com", email="ada@example.com")
    other = make_user("other@example.com", email="other@example.com")
    contact = Contact.objects.create_for_user(user=administrator, first_name="Ada", user_id=other.pk)
    ContactEmail(parent_contact=contact, email_id="ada@example.com", is_primary=True).save(
        user=administrator
    )
    contact.refresh_from_db()
    assert contact.user_id == other.pk


def test_no_matching_user_leaves_it_empty(administrator):
    contact = contact_with_email(administrator, "nobody@example.com")
    assert contact.user_id is None


def test_a_mixed_case_email_matches(administrator, make_user):
    """Q2 (A-65): ignoring case, as upstream's `=` on its default MariaDB collation."""
    ada = make_user("ada@example.com", email="ada@example.com")
    contact = contact_with_email(administrator, "Ada@Example.COM")
    assert contact.user_id == ada.pk


def test_of_two_users_with_the_email_the_most_recently_modified_wins(administrator, make_user):
    """A-67: upstream's get_value orders by `modified` desc (v15 database.py:623)."""
    older = make_user("first@example.com", email="shared@example.com")
    newer = make_user("second@example.com", email="shared@example.com")
    User.objects.filter(pk=older.pk).update(modified=timezone.now() - datetime.timedelta(days=1))
    User.objects.filter(pk=newer.pk).update(modified=timezone.now())
    contact = contact_with_email(administrator, "shared@example.com")
    assert contact.user_id == newer.pk


def test_the_row_signal_fills_it_without_a_contact_save(administrator, make_user):
    """§11.2: wherever `email_id` is worked out; the row signal writes with update()."""
    ada = make_user("ada@example.com", email="ada@example.com")
    contact = Contact.objects.create_for_user(user=administrator, first_name="Ada")
    modified = Contact.objects.get(pk=contact.pk).modified
    ContactEmail(parent_contact=contact, email_id="ada@example.com").save(user=administrator)
    row = Contact.objects.get(pk=contact.pk)
    assert (row.email_id, row.user_id) == ("ada@example.com", ada.pk)
    assert row.modified == modified
