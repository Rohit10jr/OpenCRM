"""Contact naming - decision 13, resolved against the framework source.

Frappe declares no ``autoname`` for Contact; naming is a controller method
(``frappe/contacts/doctype/contact/contact.py:54-63``), which is a **seventh** strategy
beyond the six in ``PHASE_0_FOUNDATION.md`` section 2::

    def autoname(self):
        self.name = self._get_full_name()          # company is a FALLBACK
        for link in self.links:                    # first Dynamic Link only
            self.name = self.name + "-" + link.link_name.strip()
            break
        if frappe.db.exists("Contact", self.name):
            self.name = append_number_if_name_exists("Contact", self.name)

Phase 1 guessed this and got three details wrong. Each test below names the one it
pins, because the frontend routes on this value (``/contacts/:contactId``) and every
lead and deal stores it as a Link.
"""

import pytest

from frappe_core.naming import NameError_, append_number_if_name_exists
from frappe_platform.models import Contact

pytestmark = pytest.mark.django_db


# --- company_name is a fallback, never a suffix --------------------------------
# frappe/contacts/doctype/contact/contact.py:463-473


def test_company_is_not_appended_when_the_person_has_a_name():
    """The defect that mattered.

    Every CRM contact carries ``company_name`` (``crm_lead.py:219`` sets it from the
    lead's organization), so the old ``-<company>`` suffix fired on essentially every
    record: "John Smith" became "John Smith-Acme Corp". Upstream names it "John Smith".
    """
    contact = Contact.objects.create(
        first_name="John", last_name="Smith", company_name="Acme Corp"
    )
    assert contact.pk == "John Smith"


def test_company_is_used_when_there_is_no_person_name():
    """``if not full_name and company: full_name = company`` - contact.py:470-471."""
    contact = Contact.objects.create(company_name="Acme Corp")
    assert contact.pk == "Acme Corp"


def test_middle_name_is_included_and_parts_are_space_joined():
    contact = Contact.objects.create(
        first_name="Ada", middle_name="King", last_name="Lovelace"
    )
    assert contact.pk == "Ada King Lovelace"


def test_blank_parts_collapse_rather_than_doubling_the_space():
    """``" ".join(filter(None, ...))`` - a missing middle name leaves one space."""
    contact = Contact.objects.create(first_name="Ada", middle_name="", last_name="Lovelace")
    assert contact.pk == "Ada Lovelace"


def test_parts_are_stripped():
    contact = Contact.objects.create(first_name="  Ada  ", last_name="  Lovelace  ")
    assert contact.pk == "Ada Lovelace"


def test_a_contact_with_no_name_at_all_is_rejected():
    """Upstream reaches ``validate_name`` with "" and raises "No Name Specified".

    We deliberately do **not** fall back to the email address as the earlier
    implementation did. CRM always supplies a name - ``crm_lead.py:214`` uses
    ``first_name or lead_name``, and ``lead_name`` itself falls back to the email local
    part - so raising cannot strand a real CRM flow.
    """
    with pytest.raises(NameError_, match="No Name Specified"):
        Contact.objects.create(email_id="ada@example.com")


# --- collision numbering -------------------------------------------------------
# frappe/model/naming.py:506-530


def test_first_collision_gets_suffix_1_not_2():
    """The off-by-one. Upstream's ``count = "1"`` when no numbered sibling exists."""
    Contact.objects.create(first_name="John", last_name="Smith")
    second = Contact.objects.create(first_name="John", last_name="Smith")
    assert second.pk == "John Smith-1"


def test_further_collisions_increment():
    for _ in range(3):
        Contact.objects.create(first_name="John", last_name="Smith")
    assert set(Contact.objects.values_list("pk", flat=True)) == {
        "John Smith",
        "John Smith-1",
        "John Smith-2",
    }


def test_numbering_continues_from_the_highest_existing_suffix():
    """Upstream takes ``last + 1``, not the first free slot."""
    Contact.objects.create(first_name="John", last_name="Smith")
    Contact.objects.create(first_name="John", last_name="Smith")  # -1
    Contact.objects.create(first_name="John", last_name="Smith")  # -2
    Contact.objects.filter(pk="John Smith-1").delete()

    latest = Contact.objects.create(first_name="John", last_name="Smith")
    assert latest.pk == "John Smith-3"


def test_double_digit_suffixes_sort_above_single_digit():
    """``ORDER BY length(name) DESC, name DESC`` exists so ``-10`` beats ``-9``.

    A plain lexical sort would pick "-9" and hand back "-10" forever.
    """
    for _ in range(11):  # "Dup", then Dup-1 .. Dup-10
        Contact.objects.create(first_name="Dup")

    names = set(Contact.objects.values_list("pk", flat=True))
    assert "Dup-10" in names
    assert Contact.objects.create(first_name="Dup").pk == "Dup-11"


def test_helper_returns_the_value_untouched_when_free():
    assert append_number_if_name_exists(Contact, "Nobody Here") == "Nobody Here"


# --- the links seam -------------------------------------------------------------


def test_links_suffix_is_empty_until_dynamic_link_is_ported():
    """Upstream appends ``-<links[0].link_name>``; ``Dynamic Link`` is not ported yet.

    This is not a divergence today: no CRM path populates ``links`` on create
    (``crm_lead.py:213``, ``crm_deal.py:427``, ``install.py``, ``demo/``), so upstream's
    suffix does not fire for CRM contacts either. The seam exists so that porting
    Dynamic Link - also needed for ``CRM Call Log.links`` - makes naming faithful with
    no other change.
    """
    contact = Contact.objects.create(first_name="John", last_name="Smith")
    assert contact.name_links_suffix() == ""
    assert contact.pk == "John Smith"


# --- the name still has to pass validate_name -----------------------------------


def test_a_generated_contact_name_is_validated():
    with pytest.raises(NameError_, match="cannot contain special characters"):
        Contact.objects.create(first_name="<script>", last_name="alert")


# --- User: the same investigation, a different platform doctype -----------------
# frappe/core/doctype/user/user.py:150-156


def test_user_name_is_lowercased(make_user):
    """``self.email = self.email.strip().lower(); self.name = self.email``.

    Without this, ``owner``, ``ToDo.allocated_to``, ``_assign`` entries and every
    ``@me`` filter - all string comparisons on this value - miss silently whenever the
    casing differs from what was stored.
    """
    user = make_user("John@Example.COM")
    assert user.name == "john@example.com"


def test_user_name_is_stripped(make_user):
    assert make_user("  ada@example.com  ").name == "ada@example.com"


def test_user_email_field_is_normalised_too(make_user):
    assert make_user("John@Example.COM", email="John@Example.COM").email == "john@example.com"


def test_case_variants_are_the_same_user(make_user):
    """The consequence of the bug: two rows for one person."""
    make_user("ada@example.com")
    from frappe_platform.models import User

    assert User.objects.filter(pk="ada@example.com").count() == 1
    assert not User.objects.filter(pk="Ada@Example.com").exists()


def test_the_builtins_keep_their_capitalised_names():
    """Administrator and Guest are named from ``first_name``, not an email
    (user.py:152-153), so the lowercasing must not touch them - ``owner`` defaults to
    ``Guest`` outside a request and every role check compares "Administrator" exactly.
    """
    from frappe_platform.models import User

    assert User.objects.get(pk="Administrator").name == "Administrator"
    assert User.objects.get(pk="Guest").name == "Guest"
