import json

import pytest

from tests_support.models import Widget


pytestmark = pytest.mark.django_db
WIDGETS = "/api/v1/test-widgets/"


@pytest.fixture
def widget(alice):
    document = Widget(widget_name="Wire", widget_owner=alice)
    document.save(user=alice)
    return document


def assign(widget, user, actor):
    widget._assign = [user.name]
    widget.save(user=actor)


def test_the_document_route_sends_json_strings(auth_api, widget, alice, bob):
    assign(widget, bob, alice)
    data = auth_api.get(f"{WIDGETS}{widget.pk}/").json()["message"]
    assert isinstance(data["_assign"], str)
    assert json.loads(data["_assign"]) == [bob.name]
    assert data["_liked_by"] == "[]"
    assert data["_comments"] == "[]"


def test_list_rows_send_json_strings_too(auth_api, widget, alice, bob):
    assign(widget, bob, alice)
    response = auth_api.get(
        WIDGETS,
        {"fields": json.dumps(["name", "_assign", "_liked_by"])},
    )
    row = next(r for r in response.json()["message"] if r["name"] == widget.pk)
    assert json.loads(row["_assign"]) == [bob.name]
    assert row["_liked_by"] == "[]"


def test_the_frontend_parse_round_trips_an_empty_cache(auth_api, widget):
    data = auth_api.get(f"{WIDGETS}{widget.pk}/").json()["message"]
    assert json.loads(data["_assign"]) == []
    assert json.loads(data["_liked_by"]) == []


def test_the_column_is_still_filterable_as_text(auth_api, widget, alice, bob):
    assign(widget, bob, alice)
    response = auth_api.get(
        WIDGETS,
        {
            "fields": json.dumps(["name"]),
            "filters": json.dumps([["_assign", "like", f"%{bob.name}%"]]),
        },
    )
    assert [row["name"] for row in response.json()["message"]] == [widget.pk]
