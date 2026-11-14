import datetime
from decimal import Decimal

import pytest

from core.models import Version
from core.versions import versions_for
from tests_support.models import TrackedDocument, Widget

pytestmark = pytest.mark.django_db


@pytest.fixture
def tracked(alice):
    document = TrackedDocument(
        label="First",
        amount=Decimal("50000.000000"),
        assigned_to=alice,
    )
    document.save(user=alice)
    return document


def _changes(document):
    return [
        change
        for version in versions_for(document.DOCTYPE, document.pk)
        for change in version.changes()
    ]


def test_creating_a_record_writes_no_version(alice):
    document = TrackedDocument(label="Created")
    document.save(user=alice)

    assert versions_for(document.DOCTYPE, document.pk) == []


def test_changing_a_tracked_value_is_recorded(alice, tracked):
    reloaded = TrackedDocument.objects.get(pk=tracked.pk)
    reloaded.amount = Decimal("80000.000000")
    reloaded.save(user=alice)

    assert _changes(reloaded) == [
        ["amount", "50000.000000", "80000.000000"]
    ]


def test_the_version_records_the_passed_user(bob, tracked):
    reloaded = TrackedDocument.objects.get(pk=tracked.pk)
    reloaded.label = "Changed"
    reloaded.save(user=bob)

    assert versions_for(reloaded.DOCTYPE, reloaded.pk)[0].owner_id == bob.name


def test_changing_a_relation_records_its_key(alice, bob, tracked):
    reloaded = TrackedDocument.objects.get(pk=tracked.pk)
    reloaded.assigned_to = bob
    reloaded.save(user=alice)

    assert ["assigned_to", alice.name, bob.name] in _changes(reloaded)


def test_several_fields_in_one_save_share_a_version(alice, tracked):
    reloaded = TrackedDocument.objects.get(pk=tracked.pk)
    reloaded.label = "Changed"
    reloaded.amount = Decimal("70000.000000")
    reloaded.save(user=alice)

    versions = versions_for(reloaded.DOCTYPE, reloaded.pk)
    assert len(versions) == 1
    assert {change[0] for change in versions[0].changes()} == {"label", "amount"}


def test_successive_saves_each_write_a_row(alice, tracked):
    for label in ("Second", "Third"):
        reloaded = TrackedDocument.objects.get(pk=tracked.pk)
        reloaded.label = label
        reloaded.save(user=alice)

    assert len(versions_for(tracked.DOCTYPE, tracked.pk)) == 2


def test_two_saves_diff_against_the_last_write(alice, tracked):
    reloaded = TrackedDocument.objects.get(pk=tracked.pk)
    reloaded.label = "Second"
    reloaded.save(user=alice)
    reloaded.label = "Third"
    reloaded.save(user=alice)

    assert _changes(reloaded) == [
        ["label", "First", "Second"],
        ["label", "Second", "Third"],
    ]


def test_saving_without_a_tracked_change_writes_nothing(alice, tracked):
    reloaded = TrackedDocument.objects.get(pk=tracked.pk)
    reloaded.notes = "Not tracked"
    reloaded.save(user=alice)

    assert versions_for(reloaded.DOCTYPE, reloaded.pk) == []


def test_a_model_with_no_tracked_fields_writes_nothing(alice):
    widget = Widget(widget_name="One")
    widget.save(user=alice)
    reloaded = Widget.objects.get(pk=widget.pk)
    reloaded.widget_name = "Two"
    reloaded.save(user=alice)

    assert Version.objects.filter(ref_doctype=widget.DOCTYPE).count() == 0


def test_non_json_values_are_formatted_as_strings(alice, tracked):
    reloaded = TrackedDocument.objects.get(pk=tracked.pk)
    reloaded.effective_date = datetime.date(2026, 11, 14)
    reloaded.save(user=alice)

    assert _changes(reloaded) == [
        ["effective_date", None, "2026-11-14"]
    ]


def test_version_names_are_ten_character_hashes(alice, tracked):
    reloaded = TrackedDocument.objects.get(pk=tracked.pk)
    reloaded.label = "Changed"
    reloaded.save(user=alice)

    assert len(versions_for(reloaded.DOCTYPE, reloaded.pk)[0].name) == 10
