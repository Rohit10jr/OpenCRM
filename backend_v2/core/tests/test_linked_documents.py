import json

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.mixins.linked import linked_documents
from tests_support.models import (
    DynamicReference,
    PointingDocument,
    Widget,
    WidgetNote,
    WidgetRow,
)


pytestmark = pytest.mark.django_db
WIDGETS = "/api/v1/test-widgets/"


def save(document, user):
    document.save(user=user)
    return document


def linked_url(name):
    return f"{WIDGETS}{name}/linked-documents/"


def linked(client, name):
    response = client.get(linked_url(name))
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]


def test_lists_direct_and_dynamic_references(auth_api, alice):
    target = save(Widget(widget_name="Target", widget_owner=alice), alice)
    pointer = save(PointingDocument(widget=target), alice)
    reference = save(
        DynamicReference(
            reference_doctype=target.DOCTYPE,
            reference_name=target.pk,
        ),
        alice,
    )

    assert linked(auth_api, target.pk) == [
        {
            "doc": pointer.DOCTYPE,
            "title": pointer.pk,
            "reference_docname": pointer.pk,
            "reference_doctype": pointer.DOCTYPE,
        },
        {
            "doc": reference.DOCTYPE,
            "title": reference.pk,
            "reference_docname": reference.pk,
            "reference_doctype": reference.DOCTYPE,
        },
    ]


def test_source_list_rules_hide_direct_references(auth_api, alice, bob):
    target = save(Widget(widget_name="Target", widget_owner=alice), alice)
    visible = save(PointingDocument(widget=target), alice)
    save(PointingDocument(widget=target), bob)

    assert [row["reference_docname"] for row in linked(auth_api, target.pk)] == [
        visible.pk
    ]


def test_dialog_deduplicates_by_name_alone_across_models(auth_api, alice):
    target = save(Widget(widget_name="Target", widget_owner=alice), alice)
    save(PointingDocument(name="shared-name", widget=target), alice)
    save(
        DynamicReference(
            name="shared-name",
            reference_doctype=target.DOCTYPE,
            reference_name=target.pk,
        ),
        alice,
    )

    rows = linked(auth_api, target.pk)

    assert len(rows) == 1
    assert rows[0]["reference_docname"] == "shared-name"


def test_scan_query_count_does_not_grow_with_target_names(alice):
    def measure(count):
        targets = [
            save(Widget(widget_name=f"Target {index}", widget_owner=alice), alice)
            for index in range(count)
        ]
        for target in targets:
            save(PointingDocument(widget=target), alice)
            save(
                DynamicReference(
                    reference_doctype=target.DOCTYPE,
                    reference_name=target.pk,
                ),
                alice,
            )
        with CaptureQueriesContext(connection) as captured:
            rows = linked_documents(Widget, [target.pk for target in targets], alice)
        assert len(rows) == count * 2
        return len(captured)

    assert measure(1) == measure(5)


