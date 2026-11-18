"""Every way `get_data` names a field or a row goes through the resource's rules
(specs/CONFIGURATION.md 4.8; temp A-44 fixes 1, 4 and 6).

New: one test per protection the engine applies, each with a field or row the caller
may not use, and the manual order and unknown column field cases.
"""

import pytest

from tests_support.models import AutoIncrementDocumentFixture, Widget
from tests_support.views import WidgetViewSet

pytestmark = pytest.mark.django_db

URL = "/api/v1/test-widgets/list-view/"
KANBAN = {"view_type": "kanban"}


@pytest.fixture
def widgets(alice):
    made = {}
    for name, status in (("Alpha", "Open"), ("Beta", "Open"), ("Gamma", "Closed")):
        widget = Widget(widget_name=name, status=status, widget_owner=alice)
        widget.save(user=alice)
        made[name] = widget
    return made


@pytest.fixture
def narrow(monkeypatch):
    """Widget with `status` neither readable, filterable nor sortable."""
    readable = tuple(f for f in WidgetViewSet.readable_fields if f != "status")
    monkeypatch.setattr(WidgetViewSet, "readable_fields", readable)
    monkeypatch.setattr(WidgetViewSet, "filterable_fields", tuple(f for f in WidgetViewSet.filterable_fields if f != "status"))
    monkeypatch.setattr(WidgetViewSet, "sortable_fields", tuple(f for f in WidgetViewSet.sortable_fields if f != "status"))


def post(client, url=URL, **inputs):
    return client.post(url, inputs, format="json")


def refused(response):
    return response.status_code in (400, 417)


# --- fix 6: each protection --------------------------------------------------------------


def test_total_count_checks_the_filters(widgets, auth_api, narrow):
    """In a kanban with no column field the count is the only query that filters."""
    response = post(auth_api, view=KANBAN, filters={"status": "Open"})
    assert refused(response)


def test_the_link_targets_row_rule_applies(widgets, alice, auth_api):
    columns = post(auth_api, view=KANBAN, column_field="widget_owner").json()["message"]["kanban_columns"]
    names = {column["name"] for column in columns}
    assert alice.name in names
    assert "Administrator" not in names and "Guest" not in names


def test_the_list_fetch_checks_the_sort(widgets, auth_api, narrow):
    assert refused(post(auth_api, order_by="status desc"))


def test_the_column_fetch_checks_the_sort(widgets, auth_api, narrow):
    response = post(auth_api, view=KANBAN, kanban_columns=[{"name": "x"}], order_by="status desc")
    assert refused(response)


def test_the_column_fetch_checks_the_fields(widgets, auth_api, narrow):
    response = post(auth_api, view=KANBAN, kanban_columns=[{"name": "x"}], kanban_fields=["status"])
    assert refused(response)


def test_the_manual_order_fetch_checks_the_fields(widgets, auth_api, narrow):
    response = post(
        auth_api,
        view=KANBAN,
        kanban_columns=[{"name": "x", "order": [widgets["Alpha"].name]}],
        kanban_fields=["status"],
    )
    assert refused(response)


@pytest.mark.parametrize(
    "inputs",
    [
        {"view": KANBAN, "kanban_columns": [{"name": "x"}], "title_field": "status"},
        {"view": KANBAN, "kanban_columns": [{"name": "x"}], "kanban_fields": ["status"]},
        {"view": {"view_type": "group_by", "group_by_field": "status"}},
    ],
)
def test_an_unreadable_title_kanban_or_group_by_field_is_refused(widgets, auth_api, narrow, inputs):
    assert refused(post(auth_api, **inputs))


def test_pe16_the_fields_block_leaves_out_what_the_caller_may_not_read(widgets, auth_api, monkeypatch):
    from configuration import list_engine

    monkeypatch.setattr(list_engine, "hidden_from", lambda model, user: {"notes"})
    fields = {f["fieldname"] for f in post(auth_api).json()["message"]["fields"]}
    assert "notes" not in fields and "widget_name" in fields


# --- fix 1: a manual order on an integer key ---------------------------------------------


def test_a_manual_order_on_an_integer_key_skips_what_the_key_cannot_hold(alice, auth_api):
    one = AutoIncrementDocumentFixture(label="one")
    one.save(user=alice)
    response = post(
        auth_api,
        url="/api/v1/test-auto-increments/list-view/",
        view=KANBAN,
        kanban_columns=[{"name": "x", "order": ["abc", {}, None, str(one.name)]}],
    )
    assert response.status_code == 200, response.json()
    assert [row["name"] for row in response.json()["message"]["data"][0]["data"]] == [one.name]


def test_a_string_order_is_read_as_its_characters(widgets, auth_api):
    response = post(auth_api, view=KANBAN, kanban_columns=[{"name": "x", "order": "zz"}])
    assert response.status_code == 200


def test_an_order_that_is_an_object_is_417(widgets, auth_api):
    response = post(auth_api, view=KANBAN, kanban_columns=[{"name": "x", "order": {"a": 1}}])
    assert response.status_code == 417
    assert response.json()["message"] == "A column's order must be a list"


# --- fix 4: an unknown column field ------------------------------------------------------


def test_an_unknown_column_field_gives_an_empty_board(widgets, auth_api):
    result = post(auth_api, view=KANBAN, column_field="no_such_field").json()["message"]
    assert (result["kanban_columns"], result["data"]) == ([], [])


def test_an_unknown_column_field_with_columns_is_the_filters_refusal(widgets, auth_api):
    response = post(auth_api, view=KANBAN, column_field="no_such_field", kanban_columns=[{"name": "x"}])
    assert response.json()["message"] == "Unknown field 'no_such_field' for this document type"


def test_a_known_column_field_the_caller_may_not_filter_on_is_refused(widgets, auth_api):
    response = post(auth_api, view=KANBAN, column_field="due_date")
    assert response.json()["message"] == "Cannot filter on 'due_date'"
