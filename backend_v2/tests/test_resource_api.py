"""Ports the old generic-resource request cases to the client-reference routes."""

import json

import pytest

from tests_support.models import FieldDocument, Widget


pytestmark = pytest.mark.django_db
URL = "/api/v1/test-widgets/"


def save(document, user):
    document.save(user=user)
    return document


@pytest.fixture
def widgets(alice):
    return (
        save(Widget(widget_name="Alpha", status="Open", widget_owner=alice), alice),
        save(Widget(widget_name="Beta", status="Open", widget_owner=alice), alice),
        save(Widget(widget_name="Gamma", status="Closed", widget_owner=alice), alice),
    )


def rows(response):
    assert response.status_code == 200
    assert set(response.json()) == {"message"}
    return response.json()["message"]


def test_list_with_filters_and_fields(auth_api, widgets):
    result = rows(
        auth_api.get(
            URL,
            {
                "filters": json.dumps([["status", "=", "Open"]]),
                "fields": json.dumps(["name", "widget_name"]),
            },
        )
    )
    assert sorted(item["widget_name"] for item in result) == ["Alpha", "Beta"]
    assert set(result[0]) == {"name", "widget_name"}


def test_list_with_doctype_qualified_and_dict_filters(auth_api, widgets):
    qualified = rows(
        auth_api.get(
            URL,
            {
                "filters": json.dumps(
                    [["Foundation Widget", "status", "=", "Closed"]]
                ),
                "fields": json.dumps(["widget_name"]),
            },
        )
    )
    mapping = rows(
        auth_api.get(
            URL,
            {
                "filters": json.dumps({"status": "Closed"}),
                "fields": json.dumps(["widget_name"]),
            },
        )
    )
    assert qualified == mapping == [{"widget_name": "Gamma"}]


def test_fields_star_returns_every_readable_field(auth_api, widgets):
    row = rows(auth_api.get(URL, {"fields": json.dumps(["*"])}))[0]
    for key in ("name", "owner", "modified", "docstatus", "_assign", "widget_name"):
        assert key in row


def test_unknown_field_is_rejected(auth_api, widgets):
    response = auth_api.get(URL, {"fields": json.dumps(["nonexistent"])})
    assert response.status_code == 417
    assert response.json()["exc_type"] == "ValidationError"


@pytest.mark.parametrize(
    ("order_by", "expected"),
    [
        ("widget_name desc", ["Gamma", "Beta", "Alpha"]),
        ("widget_name", ["Alpha", "Beta", "Gamma"]),
        ("`tabFoundation Widget`.widget_name desc", ["Gamma", "Beta", "Alpha"]),
    ],
)
def test_order_by(auth_api, widgets, order_by, expected):
    result = rows(
        auth_api.get(
            URL,
            {"fields": json.dumps(["widget_name"]), "order_by": order_by},
        )
    )
    assert [item["widget_name"] for item in result] == expected


def test_pagination_and_or_filters(auth_api, widgets):
    page = rows(
        auth_api.get(
            URL,
            {
                "fields": json.dumps(["widget_name"]),
                "order_by": "widget_name asc",
                "limit_start": 1,
                "limit_page_length": 1,
            },
        )
    )
    union = rows(
        auth_api.get(
            URL,
            {
                "fields": json.dumps(["widget_name"]),
                "or_filters": json.dumps(
                    [["widget_name", "=", "Alpha"], ["status", "=", "Closed"]]
                ),
            },
        )
    )
    assert page == [{"widget_name": "Beta"}]
    assert sorted(item["widget_name"] for item in union) == ["Alpha", "Gamma"]


def test_read_single_and_missing_document(auth_api, widgets):
    response = auth_api.get(f"{URL}{widgets[0].pk}/")
    assert response.status_code == 200
    assert response.json()["message"]["widget_name"] == "Alpha"
    missing = auth_api.get(URL + "missing/")
    assert missing.status_code == 404
    assert missing.json()["exc_type"] == "DoesNotExistError"


def test_create_returns_200_generated_name_and_owner(auth_api, alice):
    response = auth_api.post(URL, {"widget_name": "Created"}, format="json")
    assert response.status_code == 200
    document = response.json()["message"]
    assert document["name"].startswith("WIDGET-")
    assert document["owner"] == alice.name


def test_patch_updates_and_stamps_modified_by(auth_api, widgets, alice):
    response = auth_api.patch(
        f"{URL}{widgets[0].pk}/", {"widget_name": "Updated"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["message"]["widget_name"] == "Updated"
    assert response.json()["message"]["modified_by"] == alice.name


def test_delete_returns_null_message(auth_api, widgets):
    response = auth_api.delete(f"{URL}{widgets[0].pk}/")
    assert response.status_code == 200
    assert response.json() == {"message": None}


def test_owner_cannot_be_set_by_client(auth_api, bob):
    response = auth_api.post(
        URL, {"widget_name": "Owned", "owner": bob.name}, format="json"
    )
    assert response.json()["message"]["owner"] != bob.name


def test_prompt_name_create_missing_and_duplicate(auth_api):
    url = "/api/v1/test-prompts/"
    created = auth_api.post(url, {"name": "Chosen", "label": "one"}, format="json")
    assert created.status_code == 200
    assert created.json()["message"]["name"] == "Chosen"
    missing = auth_api.post(url, {"label": "none"}, format="json")
    assert missing.status_code == 417
    duplicate = auth_api.post(
        url, {"name": "Chosen", "label": "two"}, format="json"
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["message"] == (
        "Foundation Prompt <strong>Chosen</strong> already exists"
    )


def test_duplicate_field_name_does_not_overwrite(auth_api, alice):
    save(FieldDocument(title="Same"), alice)
    response = auth_api.post(
        "/api/v1/test-fields/", {"title": "Same"}, format="json"
    )
    assert response.status_code == 409
    assert FieldDocument.objects.filter(pk="Same").count() == 1


def test_unauthenticated_list_is_rejected(api):
    response = api.get(URL)
    assert response.status_code == 401
    assert response.json()["message"] == "Not permitted"


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("order_by", "widget_owner__name asc"),
        ("fields", json.dumps(["widget_owner__name"])),
        ("group_by", "widget_owner__name"),
        ("order_by", "widget_name sideways"),
    ],
)
def test_query_parameters_cannot_traverse_or_use_bogus_direction(
    auth_api, widgets, parameter, value
):
    response = auth_api.get(URL, {parameter: value})
    assert response.status_code == 417
