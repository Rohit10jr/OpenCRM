import json
from unittest.mock import Mock

import pytest

from core.mixins.bulk_update import bulk_update_documents
from core.tasks import bulk_update_docs
from tests_support.models import Widget
from tests_support.serializers import WidgetSerializer
from tests_support.views import WidgetViewSet


pytestmark = pytest.mark.django_db
URL = "/api/v1/test-widgets/bulk-update/"


def save(document, user):
    document.save(user=user)
    return document


def test_get_is_method_not_allowed(auth_api):
    assert auth_api.get(URL).status_code == 405


def make_widgets(user, count, *, status="Open", prefix="Widget"):
    return [
        save(Widget(widget_name=f"{prefix} {index}", status=status), user)
        for index in range(count)
    ]


def update(client, names, **extra):
    return client.post(
        URL,
        {
            "docnames": names,
            "action": "update",
            "data": {"notes": "changed"},
            **extra,
        },
        format="json",
    )


def test_inline_update_ports_the_old_success_case(auth_api, alice):
    documents = make_widgets(alice, 3)
    response = update(auth_api, [item.name for item in documents])
    assert response.status_code == 200
    assert response.json() == {"message": []}
    assert all(Widget.objects.get(pk=item.pk).notes == "changed" for item in documents)


def test_nineteen_run_inline_and_return_failed_names(auth_api):
    names = [f"missing-{index}" for index in range(19)]
    assert update(auth_api, names).json() == {"message": names}


@pytest.mark.parametrize("count", [20, 500])
def test_queue_bands_return_null_and_pass_plain_arguments(
    auth_api, alice, monkeypatch, count
):
    delay = Mock()
    monkeypatch.setattr("core.tasks.bulk_update_docs.delay", delay)
    names = [f"name-{index}" for index in range(count)]
    response = auth_api.post(
        URL + '?docnames=["query-value"]&task_id=query&doctype=Wrong',
        {
            "docnames": names,
            "action": "update",
            "data": '{"notes": "queued"}',
            "task_id": "body-wins-and-is-ignored",
            "surplus": "ignored",
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.json() == {"message": None}
    delay.assert_called_once_with(
        "tests_support.views.WidgetViewSet",
        names,
        "update",
        {"notes": "queued"},
        alice.name,
    )


def test_501_is_refused_with_the_old_title_and_text(auth_api):
    response = update(auth_api, [f"name-{index}" for index in range(501)])
    assert response.status_code == 417
    body = response.json()
    assert body["exc_type"] == "ValidationError"
    assert body["message"] == "Bulk operations only support up to 500 documents."
    assert json.loads(json.loads(body["_server_messages"])[0])["title"] == (
        "Too Many Documents"
    )


@pytest.mark.parametrize("as_json", [False, True])
def test_scalar_name_and_both_data_forms_are_accepted(auth_api, alice, as_json):
    document = make_widgets(alice, 1)[0]
    data = {"widget_name": "Updated"}
    response = auth_api.post(
        URL,
        {
            "docnames": document.name,
            "action": "update",
            "data": json.dumps(data) if as_json else data,
            "task_id": "ignored",
        },
        format="json",
    )
    assert response.json() == {"message": []}
    document.refresh_from_db()
    assert document.widget_name == "Updated"


def test_missing_and_write_denied_names_fail_while_the_rest_save(auth_api, alice):
    denied = make_widgets(alice, 1, status="Locked", prefix="Denied")[0]
    allowed = make_widgets(alice, 1, prefix="Allowed")[0]
    response = update(auth_api, ["missing", denied.name, allowed.name])
    assert response.json() == {"message": ["missing", denied.name]}
    denied.refresh_from_db()
    allowed.refresh_from_db()
    assert denied.notes == ""
    assert allowed.notes == "changed"


@pytest.mark.parametrize("action", ["submit", "cancel", "invented"])
def test_non_update_actions_fail_every_document(auth_api, alice, action):
    names = [item.name for item in make_widgets(alice, 2)]
    response = auth_api.post(URL, {"docnames": names, "action": action}, format="json")
    assert response.json() == {"message": names}


def test_one_serializer_exception_does_not_undo_other_documents(
    auth_api, alice, monkeypatch
):
    first, broken, last = make_widgets(alice, 3)
    original = WidgetSerializer.update

    def sometimes_raise(self, instance, validated_data):
        result = original(self, instance, validated_data)
        if instance.pk == broken.pk:
            raise RuntimeError("one row broke")
        return result

    monkeypatch.setattr(WidgetSerializer, "update", sometimes_raise)
    response = update(auth_api, [first.name, broken.name, last.name])
    assert response.json() == {"message": [broken.name]}
    assert Widget.objects.get(pk=first.pk).notes == "changed"
    assert Widget.objects.get(pk=broken.pk).notes == ""
    assert Widget.objects.get(pk=last.pk).notes == "changed"


def test_action_defaults_to_submit(auth_api, alice):
    document = make_widgets(alice, 1)[0]
    response = auth_api.post(URL, {"docnames": document.name}, format="json")
    assert response.json() == {"message": [document.name]}


def test_task_rechecks_the_requesters_current_write_rule(alice, monkeypatch):
    document = make_widgets(alice, 1)[0]

    def lost_write(user, candidate, ptype):
        return False if ptype == "write" and user.pk == alice.pk else None

    monkeypatch.setattr(WidgetViewSet, "has_object_rule", staticmethod(lost_write))
    failed = bulk_update_docs(
        "tests_support.views.WidgetViewSet",
        [document.name],
        "update",
        {"notes": "forbidden"},
        alice.name,
    )
    assert failed == [document.name]
    document.refresh_from_db()
    assert document.notes == ""


@pytest.mark.parametrize("user_name", [None, "missing@example.com"])
def test_task_denies_a_missing_requesting_user(alice, user_name):
    document = make_widgets(alice, 1)[0]
    assert bulk_update_docs(
        "tests_support.views.WidgetViewSet",
        [document.name],
        "update",
        {"notes": "forbidden"},
        user_name,
    ) == [document.name]


def test_task_denies_a_disabled_requesting_user(alice):
    document = make_widgets(alice, 1)[0]
    alice.enabled = False
    alice.save()
    assert bulk_update_docs(
        "tests_support.views.WidgetViewSet",
        [document.name],
        "update",
        {"notes": "forbidden"},
        alice.name,
    ) == [document.name]


@pytest.mark.parametrize(
    "path",
    ["core.views.DocumentViewSet", "tests_support.views.FieldDocumentViewSet"],
)
def test_task_refuses_a_class_that_is_not_an_opted_in_document_viewset(path):
    with pytest.raises(TypeError, match="opted-in DocumentViewSet"):
        bulk_update_docs(path, [], user_name="missing@example.com")


def test_inline_and_task_saves_stamp_the_requesting_user(alice, bob, auth_api):
    inline, queued = make_widgets(bob, 2)
    assert update(auth_api, inline.name).json() == {"message": []}
    assert (
        bulk_update_docs(
            "tests_support.views.WidgetViewSet",
            [queued.name],
            "update",
            {"notes": "task"},
            alice.name,
        )
        == []
    )
    inline.refresh_from_db()
    queued.refresh_from_db()
    assert inline.modified_by_id == alice.name
    assert queued.modified_by_id == alice.name


def test_slashed_name_is_updated(auth_api, alice):
    document = save(Widget(name="R/GA", widget_name="Slash"), alice)
    response = auth_api.post(
        URL,
        {"docnames": "R/GA", "action": "update", "data": {"notes": "slash"}},
        format="json",
    )
    assert response.json() == {"message": []}
    document.refresh_from_db()
    assert document.notes == "slash"


def test_destination_is_rechecked_with_the_requesting_user(alice):
    document = make_widgets(alice, 1)[0]
    assert bulk_update_documents(
        WidgetViewSet,
        [document.name],
        "update",
        {"status": "Locked"},
        alice,
    ) == [document.name]
    document.refresh_from_db()
    assert document.status == "Open"
