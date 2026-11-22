"""Contact naming (specs/CONTACTS.md §4 Naming; milestone 3).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_contact_naming.py:31-158``; the User
half (`:161-197`) is ACCOUNTS'. `Contact.objects.create(...)` is
`create_for_user(user=administrator, ...)`, since every v2 save names its actor.
"""

import pytest

from contacts.models import Contact
from core.exceptions import NameError as FrappeNameError
from core.exceptions import ValidationError
from core.naming import append_number_if_name_exists

pytestmark = pytest.mark.django_db


@pytest.fixture
def make(administrator):
    def _make(**fields):
        return Contact.objects.create_for_user(user=administrator, **fields)

    return _make


# frappe/contacts/doctype/contact/contact.py:463-473


def test_company_is_not_appended_when_the_person_has_a_name(make):
    contact = make(first_name="John", last_name="Smith", company_name="Acme Corp")
    assert contact.pk == "John Smith"


def test_company_is_used_when_there_is_no_person_name(make):
    assert make(company_name="Acme Corp").pk == "Acme Corp"


def test_middle_name_is_included_and_parts_are_space_joined(make):
    assert make(first_name="Ada", middle_name="King", last_name="Lovelace").pk == "Ada King Lovelace"


def test_blank_parts_collapse_rather_than_doubling_the_space(make):
    assert make(first_name="Ada", middle_name="", last_name="Lovelace").pk == "Ada Lovelace"


def test_parts_are_stripped(make):
    assert make(first_name="  Ada  ", last_name="  Lovelace  ").pk == "Ada Lovelace"


def test_a_contact_with_no_name_at_all_is_rejected(make):
    with pytest.raises(ValidationError, match="No Name Specified"):
        make(email_id="ada@example.com")


# --- collision numbering (frappe/model/naming.py:506-530) ---------------------------------


def test_first_collision_gets_suffix_1_not_2(make):
    make(first_name="John", last_name="Smith")
    assert make(first_name="John", last_name="Smith").pk == "John Smith-1"


def test_further_collisions_increment(make):
    for _ in range(3):
        make(first_name="John", last_name="Smith")
    assert set(Contact.objects.values_list("pk", flat=True)) == {
        "John Smith",
        "John Smith-1",
        "John Smith-2",
    }


def test_numbering_continues_from_the_highest_existing_suffix(make):
    make(first_name="John", last_name="Smith")
    make(first_name="John", last_name="Smith")  # -1
    make(first_name="John", last_name="Smith")  # -2
    Contact.objects.filter(pk="John Smith-1").delete()
    assert make(first_name="John", last_name="Smith").pk == "John Smith-3"


def test_double_digit_suffixes_sort_above_single_digit(make):
    for _ in range(11):  # "Dup", then Dup-1 .. Dup-10
        make(first_name="Dup")
    assert "Dup-10" in set(Contact.objects.values_list("pk", flat=True))
    assert make(first_name="Dup").pk == "Dup-11"


def test_helper_returns_the_value_untouched_when_free():
    assert append_number_if_name_exists(Contact, "Nobody Here") == "Nobody Here"


# --- the links seam -------------------------------------------------------------------------


def test_links_suffix_is_empty(make):
    """Contact has no `links` table (as `backend/`), so upstream's suffix never fires."""
    contact = make(first_name="John", last_name="Smith")
    assert contact.name_links_suffix() == ""
    assert contact.pk == "John Smith"


# --- the name still has to pass validate_name ---------------------------------------------


def test_a_generated_contact_name_is_validated(make):
    with pytest.raises(FrappeNameError, match="cannot contain special characters"):
        make(first_name="<script>", last_name="alert")


def test_full_name_is_recomputed_on_every_save(make, administrator):
    contact = make(first_name="Ada", last_name="Lovelace")
    contact.last_name = "Byron"
    contact.save(user=administrator)
    contact.refresh_from_db()
    assert (contact.pk, contact.full_name) == ("Ada Lovelace", "Ada Byron")
