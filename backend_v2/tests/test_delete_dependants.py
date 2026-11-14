import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core import children
from core.children import delete_references_batch, references_handled
from core.models import Version
from tests_support.models import TrackedDocument, Widget, WidgetNote, WidgetRow
from tests_support.serializers import WidgetSerializer


pytestmark = pytest.mark.django_db
WIDGETS = "/api/v1/test-widgets/"


@pytest.fixture
def widget_with_dependants(auth_api):
    response = auth_api.post(
        WIDGETS,
        {
            "widget_name": "Doomed",
            "poly_rows": [{"value": "remove"}],
        },
        format="json",
    )
    return Widget.objects.get(pk=response.json()["message"]["name"])


def test_delete_takes_polymorphic_children_with_the_parent(
    auth_api, widget_with_dependants
):
    response = auth_api.delete(f"{WIDGETS}{widget_with_dependants.pk}/")
    assert response.status_code == 200, response.content[:300]
    assert response.json() == {"message": None}
    assert not Widget.objects.filter(pk=widget_with_dependants.pk).exists()
    assert not WidgetNote.objects.filter(parent=widget_with_dependants.pk).exists()


def test_the_orm_delete_path_cleans_up_too(widget_with_dependants):
    name = widget_with_dependants.pk
    widget_with_dependants.delete()
    assert not WidgetNote.objects.filter(parent=name).exists()


def test_deleting_a_tracked_document_removes_only_its_versions(alice):
    doomed = TrackedDocument(label="Doomed")
    doomed.save(user=alice)
    survivor = TrackedDocument(label="Survivor")
    survivor.save(user=alice)
    doomed_version = Version(
        ref_doctype=doomed.DOCTYPE, docname=doomed.pk, data="{}"
    )
    doomed_version.save(user=alice)
    survivor_version = Version(
        ref_doctype=survivor.DOCTYPE, docname=survivor.pk, data="{}"
    )
    survivor_version.save(user=alice)

    doomed.delete()

    assert not Version.objects.filter(pk=doomed_version.pk).exists()
    assert Version.objects.filter(pk=survivor_version.pk).exists()


def test_deleting_references_uses_a_constant_query_count(alice):
    def measure(count):
        names = []
        for number in range(count):
            document = TrackedDocument(label=f"Batch {count}-{number}")
            document.save(user=alice)
            names.append(document.pk)
            version = Version(
                ref_doctype=document.DOCTYPE, docname=document.pk, data="{}"
            )
            version.save(user=alice)

        with CaptureQueriesContext(connection) as captured:
            touched = delete_references_batch(TrackedDocument.DOCTYPE, names)

        assert touched == count
        assert not Version.objects.filter(
            ref_doctype=TrackedDocument.DOCTYPE, docname__in=names
        ).exists()
        return len(captured)

    one = measure(1)
    five = measure(5)

    assert one == five, f"query count grew with references: {one} -> {five}"


def test_references_handled_makes_the_per_row_hook_stand_down(alice):
    document = TrackedDocument(label="Handled")
    document.save(user=alice)
    version = Version(
        ref_doctype=document.DOCTYPE, docname=document.pk, data="{}"
    )
    version.save(user=alice)

    with references_handled():
        document.delete()

    assert Version.objects.filter(pk=version.pk).exists()


def test_deleting_a_version_does_not_run_reference_cleanup(alice, monkeypatch):
    version = Version(ref_doctype=TrackedDocument.DOCTYPE, docname="gone", data="{}")
    version.save(user=alice)
    calls = []
    monkeypatch.setattr(
        children,
        "delete_references",
        lambda instance: calls.append(instance.pk),
    )

    version.delete()

    assert calls == []


def test_deleting_a_child_row_does_not_query_versions(alice):
    widget = Widget(widget_name="Child cleanup")
    widget.save(user=alice)
    row = WidgetRow(parent=widget, value="remove")
    row.save(user=alice)

    with CaptureQueriesContext(connection) as captured:
        row.delete()

    version_table = Version._meta.db_table.lower()
    assert not any(
        version_table in query["sql"].lower() for query in captured.captured_queries
    )


def test_replacing_child_rows_does_not_query_versions(alice):
    serializer = WidgetSerializer(
        data={"rows": [{"value": "old"}]}, context={"user": alice}
    )
    assert serializer.is_valid(), serializer.errors
    widget = serializer.save(user=alice)
    replacement = WidgetSerializer(
        widget,
        data={"rows": [{"value": "new"}]},
        partial=True,
        context={"user": alice},
    )
    assert replacement.is_valid(), replacement.errors

    with CaptureQueriesContext(connection) as captured:
        replacement.save(user=alice)

    version_table = Version._meta.db_table.lower()
    assert not any(
        version_table in query["sql"].lower() for query in captured.captured_queries
    )
