import json

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.mixins import linked as linked_mixin
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


def test_a_child_parent_fk_is_not_a_link_to_its_own_parent(auth_api, alice):
    target = save(Widget(widget_name="Target", widget_owner=alice), alice)
    save(WidgetRow(parent=target, value="belongs here"), alice)

    assert linked(auth_api, target.pk) == []


def test_child_links_list_only_object_readable_actual_parents(
    auth_api, alice, bob
):
    target = save(Widget(widget_name="Target", widget_owner=alice), alice)
    allowed = save(
        Widget(widget_name="List denied but object allowed", widget_owner=bob), bob
    )
    denied = save(
        Widget(widget_name="Object denied", widget_owner=bob, status="Private"), bob
    )
    save(WidgetRow(parent=allowed, value="allowed", related_widget=target), bob)
    save(WidgetRow(parent=denied, value="denied", related_widget=target), bob)

    rows = linked(auth_api, target.pk)

    assert [row["reference_docname"] for row in rows] == [allowed.pk]
    assert rows[0]["reference_doctype"] == Widget.DOCTYPE


def test_polymorphic_child_link_lists_its_actual_parent(auth_api, alice, bob):
    target = save(Widget(widget_name="Target", widget_owner=alice), alice)
    parent = save(Widget(widget_name="Parent", widget_owner=bob), bob)
    save(
        WidgetNote(
            parent=parent.pk,
            parenttype=Widget.DOCTYPE,
            parentfield="poly_rows",
            value=target.pk,
        ),
        bob,
    )

    assert [row["reference_docname"] for row in linked(auth_api, target.pk)] == [
        parent.pk
    ]


def test_parent_scan_ignores_a_second_non_reference_pair(
    auth_api, alice, monkeypatch
):
    target = save(Widget(widget_name="Target", widget_owner=alice), alice)
    source = save(
        DynamicReference(
            reference_doctype="Other",
            reference_name="other",
            _user_tags=target.DOCTYPE,
            _comments=target.pk,
        ),
        alice,
    )
    monkeypatch.setattr(
        DynamicReference,
        "DYNAMIC_LINK_FIELDS",
        (
            ("reference_doctype", "reference_name"),
            ("_user_tags", "_comments"),
        ),
    )

    assert source.pk not in {
        row["reference_docname"] for row in linked(auth_api, target.pk)
    }


def test_cancelled_polymorphic_child_link_is_not_listed(auth_api, alice, bob):
    target = save(Widget(widget_name="Target", widget_owner=alice), alice)
    parent = save(Widget(widget_name="Parent", widget_owner=bob), bob)
    save(
        WidgetNote(
            parent=parent.pk,
            parenttype=Widget.DOCTYPE,
            parentfield="poly_rows",
            value=target.pk,
            docstatus=2,
        ),
        bob,
    )

    assert linked(auth_api, target.pk) == []


def test_polymorphic_child_link_with_ignored_parenttype_is_not_listed(
    auth_api, alice, bob, monkeypatch
):
    target = save(Widget(widget_name="Target", widget_owner=alice), alice)
    parent = save(Widget(widget_name="Ignored parent", widget_owner=bob), bob)
    save(
        WidgetNote(
            parent=parent.pk,
            parenttype=Widget.DOCTYPE,
            parentfield="poly_rows",
            value=target.pk,
        ),
        bob,
    )
    monkeypatch.setattr(
        linked_mixin,
        "IGNORE_LINKS_ON_DELETE",
        linked_mixin.IGNORE_LINKS_ON_DELETE | {Widget.DOCTYPE},
    )

    assert linked(auth_api, target.pk) == []


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


def test_dialog_uses_old_phase_and_doctype_order_before_deduplication(
    auth_api, alice, monkeypatch
):
    target = save(Widget(widget_name="Target", widget_owner=alice), alice)
    fk_parent = save(
        Widget(widget_name="FK child parent", widget_owner=alice), alice
    )
    dynamic_parent_a = save(
        Widget(widget_name="Dynamic child parent A", widget_owner=alice), alice
    )
    dynamic_parent_z = save(
        Widget(widget_name="Dynamic child parent Z", widget_owner=alice), alice
    )
    monkeypatch.setattr(WidgetRow, "DOCTYPE", "A Child FK Source")
    monkeypatch.setattr(DynamicReference, "DOCTYPE", "B Parent Pair Source")
    monkeypatch.setattr(WidgetNote, "DOCTYPE", "C Child Pair Source")
    monkeypatch.setattr(PointingDocument, "DOCTYPE", "Z Direct FK Source")
    save(WidgetRow(parent=fk_parent, value="fk", related_widget=target), alice)
    save(PointingDocument(name="shared-name", widget=target), alice)
    save(
        DynamicReference(
            name="shared-name",
            reference_doctype=target.DOCTYPE,
            reference_name=target.pk,
        ),
        alice,
    )
    save(
        WidgetNote(
            name="z-row",
            parent=dynamic_parent_z.pk,
            parenttype=Widget.DOCTYPE,
            parentfield="poly_rows",
            value=target.pk,
        ),
        alice,
    )
    save(
        WidgetNote(
            name="a-row",
            parent=dynamic_parent_a.pk,
            parenttype=Widget.DOCTYPE,
            parentfield="poly_rows",
            value=target.pk,
        ),
        alice,
    )

    assert linked(auth_api, target.pk) == [
        {
            "doc": Widget.DOCTYPE,
            "title": fk_parent.pk,
            "reference_docname": fk_parent.pk,
            "reference_doctype": Widget.DOCTYPE,
        },
        {
            "doc": "B Parent Pair Source",
            "title": "shared-name",
            "reference_docname": "shared-name",
            "reference_doctype": "B Parent Pair Source",
        },
        {
            "doc": Widget.DOCTYPE,
            "title": dynamic_parent_a.pk,
            "reference_docname": dynamic_parent_a.pk,
            "reference_doctype": Widget.DOCTYPE,
        },
        {
            "doc": Widget.DOCTYPE,
            "title": dynamic_parent_z.pk,
            "reference_docname": dynamic_parent_z.pk,
            "reference_doctype": Widget.DOCTYPE,
        },
    ]


def test_source_read_refusal_and_missing_source_keep_old_wording(
    auth_api, alice
):
    private = save(
        Widget(widget_name="Private", widget_owner=alice, status="Private"), alice
    )

    refused = auth_api.get(linked_url(private.pk))
    missing = auth_api.get(linked_url("missing"))

    assert refused.status_code == 403
    assert refused.json()["message"] == (
        f"No permission for {Widget.DOCTYPE} {private.pk}"
    )
    assert missing.status_code == 404
    assert missing.json()["message"] == f"{Widget.DOCTYPE} missing not found"


def test_unlink_skips_bad_items_and_clears_allowed_reference_shapes(
    auth_api, alice, bob
):
    target = save(Widget(widget_name="Target", widget_owner=alice), alice)
    pointer = save(PointingDocument(widget=target), alice)
    reference = save(
        DynamicReference(
            reference_doctype=target.DOCTYPE,
            reference_name=target.pk,
        ),
        alice,
    )
    denied = save(PointingDocument(widget=target), bob)
    pointer_modified = pointer.modified
    reference_modified = reference.modified
    items = [
        "not-a-dict",
        {},
        {"doctype": "Unknown", "docname": "x"},
        {"doctype": pointer.DOCTYPE, "docname": "missing"},
        {"doctype": denied.DOCTYPE, "docname": denied.pk},
        {"doctype": pointer.DOCTYPE, "docname": pointer.pk},
        {"doctype": reference.DOCTYPE, "docname": reference.pk},
    ]

    response = auth_api.post(
        linked_url(target.pk), {"items": json.dumps(items)}, format="json"
    )

    assert response.status_code == 200
    assert response.json() == {"message": "success"}
    pointer.refresh_from_db()
    reference.refresh_from_db()
    denied.refresh_from_db()
    assert pointer.widget_id is None
    assert (reference.reference_doctype, reference.reference_name) == ("", "")
    assert denied.widget_id == target.pk
    assert pointer.modified == pointer_modified
    assert reference.modified == reference_modified


def test_unlink_without_the_target_still_clears_only_the_reference_pair(
    auth_api, alice
):
    target = save(Widget(widget_name="Target", widget_owner=alice), alice)
    pointer = save(PointingDocument(widget=target), alice)

    response = auth_api.post(
        linked_url(target.pk),
        {"items": [{"doctype": pointer.DOCTYPE, "docname": pointer.pk}]},
        format="json",
    )

    assert response.json() == {"message": "success"}
    pointer.refresh_from_db()
    assert pointer.widget_id is None


def test_unlink_leaves_a_second_declared_dynamic_pair_untouched(
    auth_api, alice, monkeypatch
):
    target = save(Widget(widget_name="Target", widget_owner=alice), alice)
    reference = save(
        DynamicReference(
            reference_doctype=target.DOCTYPE,
            reference_name=target.pk,
            _user_tags="Second Doctype",
            _comments="second-name",
        ),
        alice,
    )
    monkeypatch.setattr(
        DynamicReference,
        "DYNAMIC_LINK_FIELDS",
        (
            ("reference_doctype", "reference_name"),
            ("_user_tags", "_comments"),
        ),
    )

    response = auth_api.post(
        linked_url(target.pk),
        {
            "items": [
                {"doctype": reference.DOCTYPE, "docname": reference.pk}
            ]
        },
        format="json",
    )

    assert response.json() == {"message": "success"}
    reference.refresh_from_db()
    assert (reference.reference_doctype, reference.reference_name) == ("", "")
    assert (reference._user_tags, reference._comments) == (
        "Second Doctype",
        "second-name",
    )


def test_delete_keeps_an_unlinked_item_that_another_document_names(
    auth_api, alice
):
    target = save(Widget(widget_name="Target", widget_owner=alice), alice)
    item = save(
        DynamicReference(
            reference_doctype=target.DOCTYPE,
            reference_name=target.pk,
        ),
        alice,
    )
    save(
        DynamicReference(
            reference_doctype=item.DOCTYPE,
            reference_name=item.pk,
        ),
        alice,
    )

    response = auth_api.post(
        linked_url(target.pk),
        {
            "items": [{"doctype": item.DOCTYPE, "docname": item.pk}],
            "delete": True,
        },
        format="json",
    )

    assert response.json() == {"message": "success"}
    item.refresh_from_db()
    assert (item.reference_doctype, item.reference_name) == ("", "")


def test_delete_removes_an_unlinked_item_with_no_remaining_reference(
    auth_api, alice
):
    target = save(Widget(widget_name="Target", widget_owner=alice), alice)
    item = save(
        DynamicReference(
            reference_doctype=target.DOCTYPE,
            reference_name=target.pk,
        ),
        alice,
    )

    response = auth_api.post(
        linked_url(target.pk),
        {
            "items": [{"doctype": item.DOCTYPE, "docname": item.pk}],
            "delete": True,
        },
        format="json",
    )

    assert response.json() == {"message": "success"}
    assert not DynamicReference.objects.filter(pk=item.pk).exists()


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


def test_slashed_name_routes_to_the_action(auth_api, alice):
    target = save(Widget(name="R/GA", widget_name="Slash", widget_owner=alice), alice)

    response = auth_api.get(linked_url(target.pk))

    assert response.status_code == 200
    assert response.json() == {"message": []}
