from unittest.mock import Mock

import pytest
from django.conf import settings
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.exceptions import PermissionError
from core.mixins.bulk_delete import authorize_bulk_delete, perform_bulk_delete
from core.resources import PRODUCTION_URLCONF
from core.tasks import delete_bulk_docs
from tests_support.models import (
    DynamicReference,
    PointingDocument,
    Widget,
    WidgetRow,
)
from tests_support.views import WidgetViewSet


pytestmark = pytest.mark.django_db
URL = "/api/v1/test-widgets/bulk-delete/"


def save(document, user):
    document.save(user=user)
    return document


def widgets(user, count, prefix="Widget"):
    return [
        save(Widget(widget_name=f"{prefix} {index}", widget_owner=user), user)
        for index in range(count)
    ]


def delete(client, items=None, **extra):
    data = extra
    if items is not None:
        data["items"] = items
    return client.post(URL, data, format="json")


@pytest.mark.parametrize(
    ("items", "message"),
    [(None, "Items are required"), ([], "Items are required"), ("one", "Items must be a list")],
)
def test_input_refusals_keep_the_old_417_messages(auth_api, items, message):
    response = delete(auth_api, items)
    assert response.status_code == 417
    assert response.json()["message"] == message


def test_inline_delete_drops_missing_names_and_returns_success(auth_api, alice):
    first, second = widgets(alice, 2)
    response = delete(auth_api, [first.pk, "missing", second.pk])
    assert response.status_code == 200
    assert response.json() == {"message": "success"}
    assert not Widget.objects.filter(pk__in=[first.pk, second.pk]).exists()


def test_an_invisible_name_refuses_the_whole_batch(auth_api, alice, bob):
    mine = widgets(alice, 1, "Mine")[0]
    hidden = widgets(bob, 1, "Hidden")[0]
    response = delete(auth_api, [mine.pk, hidden.pk])
    assert response.status_code == 403
    assert response.json()["message"] == (
        f"No permission to delete {Widget.DOCTYPE} {hidden.pk}"
    )
    assert Widget.objects.filter(pk__in=[mine.pk, hidden.pk]).count() == 2


def test_an_object_denied_name_refuses_the_whole_batch(auth_api, alice, monkeypatch):
    allowed, denied = widgets(alice, 2)

    def rule(user, document, ptype):
        return False if ptype == "delete" and document.pk == denied.pk else None

    monkeypatch.setattr(WidgetViewSet, "has_object_rule", staticmethod(rule))
    response = delete(auth_api, [allowed.pk, denied.pk])
    assert response.status_code == 403
    assert response.json()["message"] == (
        f"No permission to delete {Widget.DOCTYPE} {denied.pk}"
    )
    assert Widget.objects.filter(pk__in=[allowed.pk, denied.pk]).count() == 2


@pytest.mark.parametrize("count", [10, 11])
def test_threshold_counts_existing_authorized_targets(
    auth_api, alice, monkeypatch, count
):
    documents = widgets(alice, count)
    names = [document.pk for document in documents]
    delay = Mock()
    monkeypatch.setattr("core.tasks.delete_bulk_docs.delay", delay)
    response = delete(auth_api, ["missing", *names])
    assert response.json() == {"message": "success"}
    if count == 10:
        delay.assert_not_called()
        assert not Widget.objects.filter(pk__in=names).exists()
    else:
        delay.assert_called_once_with(
            "tests_support.views.WidgetViewSet",
            names,
            False,
            alice.name,
            "config.test_urls",
        )
        assert Widget.objects.filter(pk__in=names).count() == 11


def test_worker_reauthorizes_after_delete_access_is_lost(alice, monkeypatch):
    document = widgets(alice, 1)[0]
    monkeypatch.setattr(
        WidgetViewSet,
        "has_object_rule",
        staticmethod(lambda user, row, ptype: False if ptype == "delete" else None),
    )
    with pytest.raises(PermissionError, match="No permission to delete"):
        delete_bulk_docs(
            "tests_support.views.WidgetViewSet",
            [document.pk],
            user_name=alice.name,
            urlconf="config.test_urls",
        )
    assert Widget.objects.filter(pk=document.pk).exists()


def test_worker_deletes_what_the_requesting_user_may_delete(alice):
    document = widgets(alice, 1)[0]
    assert delete_bulk_docs(
        "tests_support.views.WidgetViewSet",
        [document.pk],
        user_name=alice.name,
        urlconf="config.test_urls",
    ) == "success"
    assert not Widget.objects.filter(pk=document.pk).exists()


def test_worker_refuses_an_unknown_urlconf_before_deleting(alice):
    document = widgets(alice, 1)[0]

    with pytest.raises(ValueError, match="unknown.config.urls"):
        delete_bulk_docs(
            "tests_support.views.WidgetViewSet",
            [document.pk],
            user_name=alice.name,
            urlconf="unknown.config.urls",
        )

    assert Widget.objects.filter(pk=document.pk).exists()


@pytest.mark.parametrize(
    ("urlconf", "expected"),
    [(None, PRODUCTION_URLCONF), (settings.ROOT_URLCONF, settings.ROOT_URLCONF)],
)
def test_worker_accepts_known_urlconfs(alice, monkeypatch, urlconf, expected):
    perform = Mock()
    monkeypatch.setattr("core.mixins.bulk_delete.perform_bulk_delete", perform)

    assert delete_bulk_docs(
        "tests_support.views.WidgetViewSet",
        [],
        user_name=alice.name,
        urlconf=urlconf,
    ) == "success"

    perform.assert_called_once_with(WidgetViewSet, [], alice, False, expected)


@pytest.mark.parametrize("user_name", [None, "missing@example.com"])
def test_worker_denies_a_missing_requesting_user(alice, user_name):
    document = widgets(alice, 1)[0]
    with pytest.raises(PermissionError, match="No permission to delete"):
        delete_bulk_docs(
            "tests_support.views.WidgetViewSet",
            [document.pk],
            user_name=user_name,
            urlconf="config.test_urls",
        )
    assert Widget.objects.filter(pk=document.pk).exists()


@pytest.mark.parametrize(
    "path", ["core.views.DocumentViewSet", "tests_support.views.FieldDocumentViewSet"]
)
def test_worker_refuses_a_bad_viewset_path(path):
    with pytest.raises(TypeError, match="opted-in DocumentViewSet"):
        delete_bulk_docs(path, [], user_name="missing@example.com")


def test_writable_links_are_cleared(auth_api, alice):
    target = widgets(alice, 1)[0]
    pointer = save(PointingDocument(widget=target), alice)
    assert delete(auth_api, [target.pk]).json() == {"message": "success"}
    pointer.refresh_from_db()
    assert pointer.widget_id is None


def test_unwritable_link_refuses_and_rolls_back_clearing(auth_api, alice, bob):
    target = widgets(alice, 1)[0]
    writable = save(PointingDocument(widget=target), alice)
    blocked = save(PointingDocument(widget=target), bob)
    response = delete(auth_api, [target.pk])
    assert response.status_code == 417
    writable.refresh_from_db()
    blocked.refresh_from_db()
    assert writable.widget_id == target.pk
    assert blocked.widget_id == target.pk
    assert Widget.objects.filter(pk=target.pk).exists()


def test_a_child_row_link_uses_its_actual_parents_write_rule(auth_api, alice):
    target, parent = widgets(alice, 2)
    parent.status = "Locked"
    parent.save(user=alice)
    row = save(WidgetRow(parent=parent, value="child", related_widget=target), alice)

    response = delete(auth_api, [target.pk])

    assert response.status_code == 417
    row.refresh_from_db()
    assert row.related_widget_id == target.pk
    assert Widget.objects.filter(pk=target.pk).exists()


def test_delete_linked_deletes_unreferenced_and_keeps_referenced_items(auth_api, alice):
    first, second = widgets(alice, 2)
    doomed = save(
        DynamicReference(reference_doctype=first.DOCTYPE, reference_name=first.pk), alice
    )
    kept = save(
        DynamicReference(reference_doctype=second.DOCTYPE, reference_name=second.pk), alice
    )
    save(
        DynamicReference(reference_doctype=kept.DOCTYPE, reference_name=kept.pk), alice
    )
    response = delete(auth_api, [first.pk, second.pk], delete_linked=True)
    assert response.json() == {"message": "success"}
    assert not DynamicReference.objects.filter(pk=doomed.pk).exists()
    kept.refresh_from_db()
    assert (kept.reference_doctype, kept.reference_name) == ("", "")


def test_worker_is_idempotent_and_slashed_names_work(auth_api, alice):
    document = save(Widget(name="R/GA", widget_name="Slash", widget_owner=alice), alice)
    assert delete(auth_api, [document.pk]).json() == {"message": "success"}
    assert delete_bulk_docs(
        "tests_support.views.WidgetViewSet",
        [document.pk],
        user_name=alice.name,
        urlconf="config.test_urls",
    ) == "success"


def test_authorize_and_perform_query_counts_are_batch_bounded(alice):
    def measure(count):
        documents = widgets(alice, count, f"Batch {count}")
        names = [document.pk for document in documents]
        with CaptureQueriesContext(connection) as authorization:
            targets = authorize_bulk_delete(WidgetViewSet, names, alice)
        with CaptureQueriesContext(connection) as performance:
            perform_bulk_delete(
                WidgetViewSet, targets, alice, urlconf="config.test_urls"
            )
        return len(authorization), len(performance)

    assert measure(1) == measure(5)


def test_get_is_method_not_allowed_for_both_bulk_actions(auth_api):
    assert auth_api.get(URL).status_code == 405
    assert auth_api.get("/api/v1/test-widgets/bulk-update/").status_code == 405
