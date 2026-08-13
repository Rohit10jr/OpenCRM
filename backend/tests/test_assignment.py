"""``_assign`` is a cache of ``ToDo`` - PHASE_0_FOUNDATION.md section 3.

Phase 0 owns the sync mechanism; phase 1 cluster 1 owns the ``ToDo`` model. These tests
run against ``tests_support.TodoDoc``, which has Frappe's field names.

The load-bearing assertion is the last group: the permission view of assignment and the
display cache deliberately disagree, which is why phase 2 must query ToDo directly.
"""

import pytest

from frappe_core.assignment import (
    INACTIVE_FOR_DISPLAY,
    INACTIVE_FOR_PERMISSION,
    get_assigned_users,
    parse_assign,
    rebuild_assign_cache,
)
from frappe_core.session import session_user
from frappe_platform.models import ToDo
from tests_support.models import Widget

pytestmark = pytest.mark.django_db

DOCTYPE = "Phase Zero Widget"


@pytest.fixture
def widget(alice):
    with session_user(alice.name):
        return Widget.objects.create(widget_name="Target")


def assign(widget, user, status="Open"):
    return ToDo.objects.create(
        reference_type=DOCTYPE,
        reference_name=widget.name,
        allocated_to=user,
        status=status,
    )


# --- the cache tracks ToDo ----------------------------------------------------


def test_assign_starts_empty(widget):
    assert widget._assign == []


def test_creating_a_todo_populates_assign(widget, alice):
    assign(widget, alice)
    widget.refresh_from_db()
    assert widget._assign == [alice.name]


def test_a_second_todo_appends(widget, alice, bob):
    assign(widget, alice)
    assign(widget, bob)
    widget.refresh_from_db()
    assert sorted(widget._assign) == sorted([alice.name, bob.name])


def test_deleting_a_todo_removes_the_user(widget, alice, bob):
    todo = assign(widget, alice)
    assign(widget, bob)
    todo.delete()
    widget.refresh_from_db()
    assert widget._assign == [bob.name]


def test_cancelling_a_todo_removes_the_user(widget, alice):
    todo = assign(widget, alice)
    todo.status = "Cancelled"
    todo.save()
    widget.refresh_from_db()
    assert widget._assign == []


def test_closing_a_todo_removes_it_from_the_display_cache(widget, alice):
    """``crm/api/doc.py:615`` excludes Closed as well as Cancelled."""
    todo = assign(widget, alice)
    todo.status = "Closed"
    todo.save()
    widget.refresh_from_db()
    assert widget._assign == []


def test_duplicate_assignments_are_collapsed(widget, alice):
    assign(widget, alice)
    assign(widget, alice)
    widget.refresh_from_db()
    assert widget._assign == [alice.name]


def test_cache_refresh_does_not_bump_modified(widget, alice):
    """It is a cache refresh, not a document edit - the list sorts on ``modified``."""
    before = Widget.objects.get(pk=widget.pk).modified
    assign(widget, alice)
    assert Widget.objects.get(pk=widget.pk).modified == before


def test_todos_for_other_documents_do_not_leak(widget, alice, bob):
    with session_user(alice.name):
        other = Widget.objects.create(widget_name="Other")
    assign(other, bob)
    widget.refresh_from_db()
    assert widget._assign == []


def test_repointing_a_todo_clears_the_old_documents_cache(widget, alice):
    """Codex phase-0 finding 5.

    A ToDo can be moved to a different document. Rebuilding only the new target leaves
    the old one advertising an assignee it no longer has - a stale cache that looks
    authoritative.
    """
    with session_user(alice.name):
        other = Widget.objects.create(widget_name="Other")

    todo = assign(widget, alice)
    widget.refresh_from_db()
    assert widget._assign == [alice.name]

    todo.reference_name = other.name
    todo.save()

    widget.refresh_from_db()
    other.refresh_from_db()
    assert widget._assign == [], "old document must be cleared"
    assert other._assign == [alice.name], "new document must be populated"


def test_repointing_a_todo_across_doctypes_clears_the_old_document(widget, alice):
    todo = assign(widget, alice)
    todo.reference_type = "Phase Zero Hash"
    todo.reference_name = "somewhere-else"
    todo.save()
    widget.refresh_from_db()
    assert widget._assign == []


def test_rebuild_is_idempotent(widget, alice):
    assign(widget, alice)
    rebuild_assign_cache(DOCTYPE, widget.name)
    rebuild_assign_cache(DOCTYPE, widget.name)
    widget.refresh_from_db()
    assert widget._assign == [alice.name]


def test_rebuild_on_an_unregistered_doctype_is_a_no_op():
    assert rebuild_assign_cache("Not A DocType", "x") is None


# --- the two "active" definitions differ, deliberately ------------------------


def test_display_and_permission_status_filters_differ():
    assert INACTIVE_FOR_DISPLAY == ("Closed", "Cancelled")
    assert INACTIVE_FOR_PERMISSION == ("Cancelled",)


def test_a_closed_todo_still_grants_access_but_is_not_displayed(widget, alice):
    """The divergence phase 2 depends on.

    ``crm/api/doc.py:608-625`` hides Closed assignments from the UI, while
    PHASE_2_PERMISSIONS.md section 2 revokes access only on Cancelled. Reading
    ``_assign`` for access control would therefore deny a user who should still see the
    row - which is why the permission layer must query ToDo.
    """
    todo = assign(widget, alice)
    todo.status = "Closed"
    todo.save()

    assert get_assigned_users(DOCTYPE, widget.name) == []
    assert get_assigned_users(DOCTYPE, widget.name, for_permission=True) == [alice.name]

    widget.refresh_from_db()
    assert widget._assign == [], "the cache follows the display definition"


def test_a_cancelled_todo_grants_no_access(widget, alice):
    """PHASE_2_PERMISSIONS.md section 2 - the required filter."""
    todo = assign(widget, alice)
    todo.status = "Cancelled"
    todo.save()
    assert get_assigned_users(DOCTYPE, widget.name, for_permission=True) == []


# --- assign is a cache, not a source of truth ---------------------------------


def test_assign_can_be_stale_and_todo_still_wins(widget, alice):
    """Someone writing ``_assign`` directly must not change who is assigned."""
    Widget.objects.filter(pk=widget.pk).update(_assign=["attacker@example.com"])
    assert get_assigned_users(DOCTYPE, widget.name, for_permission=True) == []
    rebuild_assign_cache(DOCTYPE, widget.name)
    widget.refresh_from_db()
    assert widget._assign == []


# --- parse_assign tolerates both representations ------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, []),
        ("", []),
        ([], []),
        (["a@b.com"], ["a@b.com"]),
        ('["a@b.com"]', ["a@b.com"]),  # Frappe stores a JSON string
        ("not json", []),
        ('{"a": 1}', []),
    ],
)
def test_parse_assign(value, expected):
    assert parse_assign(value) == expected
