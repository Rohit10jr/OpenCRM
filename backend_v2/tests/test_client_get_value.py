"""Port of the old generic value lookup tests to a resource route."""

import json

import pytest

from tests_support.models import Widget


pytestmark = pytest.mark.django_db
PATH = "/api/v1/test-widgets/value/"


@pytest.fixture
def widget(alice):
    row = Widget(
        widget_name="Won",
        status="Open",
        amount="100.000000",
        widget_owner=alice,
    )
    row.save(user=alice)
    return row


def get_value(client, **params):
    encoded = {
        key: json.dumps(value) if isinstance(value, (dict, list)) else value
        for key, value in params.items()
    }
    response = client.get(PATH, encoded)
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]


def test_the_forecasting_scripts_call(auth_api, widget):
    value = get_value(
        auth_api,
        fieldname="amount",
        filters={"name": widget.name},
    )
    assert value == {"amount": 100.0}


def test_several_fields_and_a_name_as_the_filter(auth_api, widget):
    value = get_value(
        auth_api,
        fieldname=["amount", "widget_name"],
        filters=widget.name,
    )
    assert value == {"amount": 100.0, "widget_name": "Won"}


def test_the_default_field_is_the_name(auth_api, widget):
    assert get_value(auth_api, filters=widget.name) == {"name": widget.name}


def test_without_as_dict_the_bare_values_come_back(auth_api, widget):
    one = get_value(
        auth_api, fieldname="amount", filters=widget.name, as_dict=0
    )
    assert one == 100.0
    several = get_value(
        auth_api,
        fieldname=["amount", "widget_name"],
        filters=widget.name,
        as_dict=0,
    )
    assert several == [100.0, "Won"]
    none = get_value(
        auth_api,
        fieldname="amount",
        filters="missing",
        as_dict=0,
    )
    assert none is None


def test_no_match_answers_an_empty_dict(auth_api, widget):
    assert get_value(auth_api, fieldname="amount", filters="missing") == {}


def test_an_unknown_resource_is_404(auth_api):
    response = auth_api.get("/api/v1/no-such-thing/value/", {"fieldname": "name"})
    assert response.status_code == 404
    assert response.json()["exc_type"] == "DoesNotExistError"


def test_parent_is_accepted_and_ignored(auth_api, widget):
    assert get_value(auth_api, filters=widget.name, parent="Anything") == {
        "name": widget.name
    }


def test_the_row_rules_apply(auth_api, bob):
    hidden = Widget(widget_name="Theirs", status="Open", widget_owner=bob)
    hidden.save(user=bob)
    assert get_value(auth_api, fieldname="widget_name", filters=hidden.name) == {}


def test_hidden_fields_are_refused_by_the_shared_query_layer(auth_api):
    response = auth_api.get(
        "/api/v1/test-secured/value/", {"fieldname": "manager_note"}
    )
    assert response.status_code == 417
    assert response.json()["message"] == "Field 'manager_note' is not readable"
