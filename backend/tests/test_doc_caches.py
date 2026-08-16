"""C3 and C8 - the two unwritten caches, and the missing child-row cascade.

**C3.** ``_assign`` has had a writer since phase 0; ``_comments`` and ``_user_tags`` were
ported as columns with no maintainer, so the comment preview in every list view was
permanently blank and tags could not be set at all.

The two are not the same shape: ``_comments`` is a *cache* over ``Comment`` rows and is
rebuilt by signal, while ``_user_tags`` is the *storage* itself - Frappe has no
per-document tag table (``frappe/desk/doctype/tag/tag.py:105-118``).

**C8.** The three polymorphic child tables carry no foreign key, because each is embedded
by both CRM Lead and CRM Deal. Nothing cascaded, so deleting a parent left its rows
behind keyed to an id that no longer resolved.
"""

import pytest

from crm_app.models import CRMLead, CRMLeadStatus, CRMProducts, CRMStatusChangeLog
from frappe_core.doc_caches import add_tag, get_tags, remove_all_tags, remove_tag
from frappe_core.session import session_user
from frappe_platform.models import Comment, Tag

pytestmark = pytest.mark.django_db


@pytest.fixture
def status(administrator):
    with session_user(administrator.name):
        return CRMLeadStatus.objects.create(lead_status="New", type="Open")


@pytest.fixture
def lead(alice, status):
    with session_user(alice.name):
        return CRMLead.objects.create(first_name="Ada", lead_owner=alice, status=status)


def _comment(lead, content, **kwargs):
    return Comment.objects.create(
        reference_doctype="CRM Lead",
        reference_name=lead.pk,
        content=content,
        comment_type=kwargs.pop("comment_type", "Comment"),
        **kwargs,
    )


# --- C3: _comments -----------------------------------------------------------------


def test_adding_a_comment_fills_the_cache(alice, lead):
    with session_user(alice.name):
        _comment(lead, "First note")

    lead.refresh_from_db()
    assert len(lead._comments) == 1
    assert lead._comments[0]["comment"] == "First note"
    assert lead._comments[0]["by"] == alice.name


def test_the_cache_holds_the_comment_name(alice, lead):
    with session_user(alice.name):
        comment = _comment(lead, "Note")

    lead.refresh_from_db()
    assert lead._comments[0]["name"] == comment.pk


def test_deleting_a_comment_removes_it_from_the_cache(alice, lead):
    with session_user(alice.name):
        comment = _comment(lead, "Note")
        comment.delete()

    lead.refresh_from_db()
    assert lead._comments == []


def test_editing_a_comment_updates_the_cache(alice, lead):
    with session_user(alice.name):
        comment = _comment(lead, "Original")
        comment.content = "Edited"
        comment.save()

    lead.refresh_from_db()
    assert lead._comments[0]["comment"] == "Edited"
    assert len(lead._comments) == 1


def test_a_long_comment_is_truncated_in_the_cache(alice, lead):
    """``comment.py:130-131`` - 97 characters plus an ellipsis, and only in the cache."""
    long_content = "x" * 150
    with session_user(alice.name):
        comment = _comment(lead, long_content)

    lead.refresh_from_db()
    cached = lead._comments[0]["comment"]
    assert cached == "x" * 97 + "..."
    # The stored comment itself is untouched.
    comment.refresh_from_db()
    assert comment.content == long_content


def test_a_comment_at_the_limit_is_not_truncated(alice, lead):
    with session_user(alice.name):
        _comment(lead, "y" * 100)

    lead.refresh_from_db()
    assert lead._comments[0]["comment"] == "y" * 100


def test_non_comment_types_are_excluded(alice, lead):
    """``comment.py:127-128`` - likes and assignments share the table but are not
    comments."""
    with session_user(alice.name):
        _comment(lead, "A like", comment_type="Like")
        _comment(lead, "An assignment", comment_type="Assignment")
        _comment(lead, "A real comment")

    lead.refresh_from_db()
    assert [c["comment"] for c in lead._comments] == ["A real comment"]


def test_the_cache_is_capped_at_one_hundred(alice, lead):
    """``comment.py:195`` - ``_comments[-100:]``."""
    with session_user(alice.name):
        for i in range(105):
            _comment(lead, f"Note {i}")

    lead.refresh_from_db()
    assert len(lead._comments) == 100
    # The most recent survive, not the oldest.
    assert lead._comments[-1]["comment"] == "Note 104"


def test_the_cache_write_does_not_bump_modified(alice, lead):
    """A cache refresh is not a document edit (``tag.py:114``).

    Exercises ``rebuild_comment_cache`` **directly** rather than through a comment
    insert. Phase 5 added ``update_modified_background``, which deliberately *does* bump
    ``modified`` when someone comments — that is why a lead rises to the top of the list
    (``crm/utils/__init__.py:238-253``). Triggering via a comment would therefore conflate
    the two writes and this test would be asserting the opposite of upstream.

    What it protects is unchanged: the cache write itself must not touch ``modified``.
    The phase-5 behaviour has its own test,
    ``test_phase5_async.py::test_commenting_bumps_modified_so_the_lead_rises``.
    """
    from frappe_core.doc_caches import rebuild_comment_cache

    with session_user(alice.name):
        _comment(lead, "Note")

    before = CRMLead.objects.values_list("modified", flat=True).get(pk=lead.pk)
    rebuild_comment_cache("CRM Lead", lead.pk)
    after = CRMLead.objects.values_list("modified", flat=True).get(pk=lead.pk)
    assert before == after


# --- C3: _user_tags ------------------------------------------------------------------


def test_adding_a_tag_stores_it_with_a_leading_comma(alice, lead):
    """``tag.py:110-112`` - ``"," + ",".join(...)``.

    The leading comma is what makes upstream's ``_user_tags LIKE '%,tag,%'`` search work
    (``tag.py:62``), so it is reproduced exactly rather than tidied away.
    """
    with session_user(alice.name):
        add_tag(lead, "urgent")

    lead.refresh_from_db()
    assert lead._user_tags == ",urgent"


def test_several_tags_accumulate(alice, lead):
    with session_user(alice.name):
        add_tag(lead, "urgent")
        add_tag(lead, "vip")

    lead.refresh_from_db()
    assert lead._user_tags == ",urgent,vip"
    assert get_tags(lead) == ["urgent", "vip"]


def test_adding_the_same_tag_twice_is_a_no_op(alice, lead):
    with session_user(alice.name):
        add_tag(lead, "urgent")
        add_tag(lead, "urgent")

    lead.refresh_from_db()
    assert lead._user_tags == ",urgent"


def test_adding_a_tag_creates_the_Tag_row(alice, lead):
    with session_user(alice.name):
        add_tag(lead, "urgent")

    assert Tag.objects.filter(pk="urgent").exists()


def test_removing_a_tag_is_case_insensitive(alice, lead):
    """``tag.py:99`` - ``x.lower() != tag.lower()``."""
    with session_user(alice.name):
        add_tag(lead, "Urgent")
        remove_tag(lead, "URGENT")

    lead.refresh_from_db()
    assert lead._user_tags == ""


def test_remove_all_clears_the_column(alice, lead):
    with session_user(alice.name):
        add_tag(lead, "a")
        add_tag(lead, "b")
        remove_all_tags(lead)

    lead.refresh_from_db()
    assert lead._user_tags == ""
    assert get_tags(lead) == []


def test_tagging_does_not_bump_modified(alice, lead):
    before = CRMLead.objects.values_list("modified", flat=True).get(pk=lead.pk)

    with session_user(alice.name):
        add_tag(lead, "urgent")

    after = CRMLead.objects.values_list("modified", flat=True).get(pk=lead.pk)
    assert before == after


# --- C8: the polymorphic cascade -------------------------------------------------------


def test_deleting_a_lead_removes_its_polymorphic_children(alice, lead):
    """The three multi-parent child tables have no FK, so Django cascades nothing."""
    with session_user(alice.name):
        CRMProducts.objects.create(
            parenttype="CRM Lead", parent=str(lead.pk), idx=1,
            product_name="Widget", rate=10,
        )

    assert CRMStatusChangeLog.objects.filter(parent=str(lead.pk)).exists()

    pk = lead.pk
    with session_user(alice.name):
        lead.delete()

    assert not CRMProducts.objects.filter(parent=str(pk)).exists()
    assert not CRMStatusChangeLog.objects.filter(parent=str(pk)).exists()


def test_another_leads_children_are_untouched(alice, status):
    """The filter is on ``parenttype`` *and* ``parent`` - deleting one lead must not
    take another's rows with it."""
    with session_user(alice.name):
        keep = CRMLead.objects.create(first_name="Keep", lead_owner=alice, status=status)
        drop = CRMLead.objects.create(first_name="Drop", lead_owner=alice, status=status)
        CRMProducts.objects.create(
            parenttype="CRM Lead", parent=str(keep.pk), idx=1,
            product_name="Widget", rate=10,
        )
        CRMProducts.objects.create(
            parenttype="CRM Lead", parent=str(drop.pk), idx=1,
            product_name="Widget", rate=10,
        )

        drop.delete()

    assert CRMProducts.objects.filter(parent=str(keep.pk)).exists()
    assert not CRMProducts.objects.filter(parent=str(drop.pk)).exists()


def test_a_deals_rows_are_untouched_when_a_lead_of_the_same_id_goes(alice, status):
    """``parenttype`` matters: the same ``parent`` string can belong to either doctype."""
    from crm_app.models import CRMDeal, CRMDealStatus

    with session_user(alice.name):
        deal_status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deal = CRMDeal.objects.create(deal_owner=alice, status=deal_status)
        lead = CRMLead.objects.create(first_name="Ada", lead_owner=alice, status=status)

        # Deliberately reuse the lead's id as the deal child's parent string.
        CRMProducts.objects.create(
            parenttype="CRM Deal", parent=str(deal.pk), idx=1,
            product_name="Widget", rate=10,
        )
        CRMProducts.objects.create(
            parenttype="CRM Lead", parent=str(lead.pk), idx=1,
            product_name="Widget", rate=10,
        )

        lead.delete()

    assert CRMProducts.objects.filter(parenttype="CRM Deal", parent=str(deal.pk)).exists()
