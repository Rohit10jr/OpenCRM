import json
from urllib.parse import quote

import pytest

from tests_support.models import (
    DynamicReference,
    FieldDocument,
    PointingDocument,
    Widget,
    WidgetNote,
)


pytestmark = pytest.mark.django_db
WIDGETS = "/api/v1/test-widgets/"
FIELDS = "/api/v1/test-fields/"


def save(document, user):
    document.save(user=user)
    return document


@pytest.fixture
def widgets(alice, bob):
    return (
        save(Widget(widget_name="Alpha", status="Open", widget_owner=alice), alice),
        save(Widget(widget_name="Beta", status="Open", widget_owner=bob), bob),
        save(Widget(widget_name="Gamma", status="Closed", widget_owner=alice), alice),
    )


def test_list_uses_client_envelope_filters_fields_and_pagination(auth_api, widgets):
    response = auth_api.get(
        WIDGETS,
        {
            "filters": json.dumps([["status", "=", "Open"]]),
            "fields": json.dumps(["name", "widget_name"]),
            "order_by": "widget_name asc",
            "limit_start": 0,
            "limit_page_length": 1,
        },
    )
    assert response.status_code == 200
    assert list(response.json()) == ["message"]
    assert [row["widget_name"] for row in response.json()["message"]] == ["Alpha"]


def test_or_filters_and_group_by_are_validated(auth_api, widgets):
    response = auth_api.get(
        WIDGETS,
        {
            "or_filters": json.dumps(
                [["widget_name", "=", "Alpha"], ["status", "=", "Closed"]]
            ),
            "fields": json.dumps(["widget_name"]),
            "group_by": "status",
        },
    )
    assert sorted(row["widget_name"] for row in response.json()["message"]) == [
        "Alpha",
        "Gamma",
    ]


def test_row_outside_list_rule_is_returned_when_object_rule_allows(auth_api, widgets):
    hidden = widgets[1]
    response = auth_api.get(f"{WIDGETS}{hidden.pk}/")
    assert response.status_code == 200
    assert response.json()["message"]["name"] == hidden.pk


def test_object_rule_refusal_is_forbidden(auth_api, alice, bob):
    refused = save(
        Widget(widget_name="Private", status="Private", widget_owner=bob), alice
    )
    response = auth_api.get(f"{WIDGETS}{refused.pk}/")
    assert response.status_code == 403
    assert response.json()["message"] == (
        f"No permission for Foundation Widget {refused.pk}"
    )


def test_missing_name_is_not_found(auth_api):
    response = auth_api.get(f"{WIDGETS}999999/")
    assert response.status_code == 404
    assert response.json()["message"] == "Foundation Widget 999999 not found"


def test_create_is_200_and_payload_aware_rule_refuses(auth_api):
    response = auth_api.post(
        WIDGETS, {"widget_name": "Allowed", "status": "Open"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["message"]["widget_name"] == "Allowed"

    refused = auth_api.post(
        WIDGETS, {"widget_name": "Denied", "status": "Forbidden"}, format="json"
    )
    assert refused.status_code == 403
    assert refused.json()["message"] == "Not permitted to create Foundation Widget"


def test_destination_recheck_sees_document_as_patch_would_leave_it(auth_api, widgets):
    response = auth_api.patch(
        f"{WIDGETS}{widgets[0].pk}/", {"status": "Locked"}, format="json"
    )
    assert response.status_code == 403
    assert response.json()["message"] == "Not permitted to move Foundation Widget there"
    widgets[0].refresh_from_db()
    assert widgets[0].status == "Open"


def test_patch_updates_and_put_is_not_served(auth_api, widgets):
    url = f"{WIDGETS}{widgets[0].pk}/"
    patched = auth_api.patch(url, {"widget_name": "Changed"}, format="json")
    assert patched.status_code == 200
    assert patched.json()["message"]["widget_name"] == "Changed"
    assert auth_api.put(url, {"widget_name": "No"}, format="json").status_code == 405


def test_optional_trailing_slash(auth_api, widgets):
    assert auth_api.get(WIDGETS.removesuffix("/")).status_code == 200
    assert auth_api.get(f"{WIDGETS}{widgets[0].pk}").status_code == 200


def test_slashed_name_is_read_updated_and_deleted(auth_api, alice):
    document = save(FieldDocument(title="R/GA"), alice)
    url = FIELDS + quote(str(document.pk)) + "/"
    assert auth_api.get(url).json()["message"]["name"] == "R/GA"
    assert auth_api.patch(url, {"title": "R/GA"}, format="json").status_code == 200
    assert auth_api.delete(url).json() == {"message": None}
    assert not FieldDocument.objects.filter(pk="R/GA").exists()


def test_record_named_like_collection_action_is_unreachable(auth_api, alice):
    save(FieldDocument(title="search"), alice)
    assert auth_api.get(FIELDS + "search/").json() == {"message": []}


def test_static_link_refuses_delete_as_link_exists(auth_api, widgets, alice):
    save(PointingDocument(widget=widgets[0]), alice)
    response = auth_api.delete(f"{WIDGETS}{widgets[0].pk}/")
    assert response.status_code == 417
    assert response.json()["exc_type"] == "LinkExistsError"


def test_dynamic_link_refuses_delete_before_row_is_removed(auth_api, widgets, alice):
    save(
        DynamicReference(
            reference_doctype="Foundation Widget",
            reference_name=widgets[0].pk,
        ),
        alice,
    )
    response = auth_api.delete(f"{WIDGETS}{widgets[0].pk}/")
    assert response.status_code == 417
    assert response.json()["message"].startswith(
        "Cannot delete or cancel because Foundation Widget"
    )
    assert Widget.objects.filter(pk=widgets[0].pk).exists()


def test_polymorphic_children_are_removed_with_parent(auth_api, widgets, alice):
    child = save(
        WidgetNote(
            parent=widgets[0].pk,
            parenttype="Foundation Widget",
            parentfield="poly_rows",
            value="child",
        ),
        alice,
    )
    assert auth_api.delete(f"{WIDGETS}{widgets[0].pk}/").status_code == 200
    assert not WidgetNote.objects.filter(pk=child.pk).exists()
