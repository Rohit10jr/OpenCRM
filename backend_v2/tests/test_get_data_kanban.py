"""`get_data`'s kanban branch on `test-widgets/list-view/` (specs/CONFIGURATION.md 4.8;
temp A-40).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_get_data.py:223-282`` and
`:396-425`; twins of ``backend/tests/test_phase4_metadata.py:347`` (a Link column field:
Widget's owner, a User), `:362` (a field with choices: Widget's `priority`), `:403` and
`:422` (a manual card order, and that it is filtered by the caller's rules), and of
``test_kanban_counts.py``'s "`all_count` is ruled". New: the column field checked up
front, PE-22's served target, PE-12e, the definition's kanban defaults.
"""

import pytest

from tests_support.models import Widget

pytestmark = pytest.mark.django_db

URL = "/api/v1/test-widgets/list-view/"
KANBAN = {"view_type": "kanban"}
OPEN_CLOSED = [{"name": "Open"}, {"name": "Closed"}]


@pytest.fixture
def widgets(alice):
    made = {}
    for name, status in (("Alpha", "Open"), ("Beta", "Open"), ("Gamma", "Closed")):
        widget = Widget(widget_name=name, status=status, widget_owner=alice)
        widget.save(user=alice)
        made[name] = widget
    return made


def call(client, **inputs):
    inputs.setdefault("filters", {})
    inputs.setdefault("order_by", "modified desc")
    inputs.setdefault("view", KANBAN)
    response = client.post(URL, inputs, format="json")
    assert response.status_code == 200, response.json()
    return response.json()["message"]


def by_column(result):
    return {e["column"]["name"]: sorted(r["widget_name"] for r in e["data"]) for e in result["data"]}


# --- ported ------------------------------------------------------------------------------


def test_list_form_filters_reach_the_kanban_branch(widgets, auth_api):
    result = call(auth_api, filters=[["status", "=", "Open"]], column_field="status", kanban_columns=OPEN_CLOSED)
    counts = {e["column"]["name"]: e["column"].get("count") for e in result["data"]}
    assert counts["Open"] == 2
    assert counts.get("Closed") in (0, None)


def test_kanban_does_not_invert_a_non_equality_filter_on_the_column_field(widgets, auth_api):
    result = call(auth_api, filters=[["status", "!=", "Closed"]], column_field="status", kanban_columns=OPEN_CLOSED)
    assert by_column(result) == {"Open": ["Alpha", "Beta"], "Closed": []}


def test_kanban_equality_filter_selects_only_the_matching_column(widgets, auth_api):
    result = call(auth_api, filters={"status": "Closed"}, column_field="status", kanban_columns=OPEN_CLOSED)
    assert by_column(result) == {"Open": [], "Closed": ["Gamma"]}


def test_kanban_keeps_unrelated_filters_per_column(widgets, auth_api):
    result = call(auth_api, filters=[["widget_name", "=", "Alpha"]], column_field="status", kanban_columns=OPEN_CLOSED)
    assert by_column(result) == {"Open": ["Alpha"], "Closed": []}


def test_kanban_branch_returns_one_entry_per_column(widgets, auth_api):
    result = call(auth_api, column_field="status", kanban_columns=OPEN_CLOSED, kanban_fields=["widget_name"])
    assert result["view_type"] == "kanban"
    assert [e["column"]["name"] for e in result["data"]] == ["Open", "Closed"]
    assert [e["column"]["count"] for e in result["data"]] == [2, 1]
    assert result["row_count"] == 2  # the number of columns, as the old code answers


def test_kanban_columns_carry_an_all_count(widgets, auth_api):
    result = call(auth_api, column_field="status", kanban_columns=[{"name": "Open"}])
    assert result["data"][0]["column"]["all_count"] == 2


def test_kanban_resolves_columns_from_a_link_target(widgets, alice, bob, auth_api):
    resolved = [c["name"] for c in call(auth_api, column_field="widget_owner")["kanban_columns"]]
    assert alice.name in resolved and bob.name in resolved


# --- twins of test_phase4_metadata.py ----------------------------------------------------


def test_kanban_columns_from_a_field_with_choices(widgets, auth_api):
    result = call(auth_api, column_field="priority")
    assert [c["name"] for c in result["kanban_columns"]] == ["Low", "Medium", "High"]


def test_kanban_manual_order_is_honoured(widgets, auth_api):
    wanted = [widgets["Beta"].name, widgets["Alpha"].name]
    result = call(auth_api, column_field="status", kanban_columns=[{"name": "Open", "order": wanted}])
    assert [row["name"] for row in result["data"][0]["data"]] == wanted


def test_kanban_manual_order_is_permission_filtered(widgets, alice, bob, api_as):
    theirs = Widget(widget_name="Theirs", status="Open", widget_owner=bob)
    theirs.save(user=bob)
    mine = widgets["Alpha"].name
    result = call(api_as(alice), column_field="status", kanban_columns=[{"name": "Open", "order": [theirs.name, mine]}])
    names = [row["name"] for row in result["data"][0]["data"]]
    assert theirs.name not in names and mine in names


def test_all_count_is_ruled(widgets, bob, api_as):
    """`test_kanban_counts.py`: the column total counts only rows the caller may see."""
    Widget(widget_name="Theirs", status="Open", widget_owner=bob).save(user=bob)
    result = call(api_as(bob), column_field="status", kanban_columns=[{"name": "Open"}])
    assert result["data"][0]["column"]["all_count"] == 1


# --- new ---------------------------------------------------------------------------------


def test_the_definitions_kanban_defaults_apply(widgets, auth_api):
    result = call(auth_api, column_field="status", kanban_columns=[{"name": "Open"}])
    assert result["title_field"] == "widget_name"
    assert result["kanban_fields"] == ["status"]
    assert {"widget_name", "status"} <= set(result["rows"])


def test_a_deleted_column_is_answered_empty(widgets, auth_api):
    result = call(auth_api, column_field="status", kanban_columns=[{"name": "Open", "delete": True}])
    assert result["data"][0]["data"] == []
    assert "count" not in result["data"][0]["column"]


def test_a_column_page_length_of_zero_has_no_limit(widgets, auth_api):
    result = call(auth_api, column_field="status", kanban_columns=[{"name": "Open", "page_length": 0}])
    assert result["data"][0]["column"]["count"] == 2


def test_the_column_field_is_checked_before_any_column_is_built(widgets, auth_api):
    response = auth_api.post(URL, {"view": KANBAN, "column_field": "due_date"}, format="json")
    assert response.status_code in (400, 417)
    assert "due_date" in response.json()["message"]


def test_pe22_a_link_target_no_resource_serves_gives_no_columns(auth_api, monkeypatch):
    from configuration import list_engine

    monkeypatch.setattr(list_engine, "routed_rule_map", lambda: {})
    assert call(auth_api, column_field="widget_owner")["kanban_columns"] == []


def test_more_kanban_columns_than_a_page_holds_are_taken(auth_api):
    """PE-23 withdrawn (owner, 20 Nov 2026): no cap on sent columns, as `backend/`."""
    from core.query import MAX_PAGE_LENGTH

    columns = [{"name": str(index)} for index in range(MAX_PAGE_LENGTH + 1)]
    response = auth_api.post(
        URL, {"view": KANBAN, "column_field": "status", "kanban_columns": columns}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
    assert len(response.json()["message"]["data"]) == MAX_PAGE_LENGTH + 1


def test_pe12e_a_column_order_that_is_not_a_list_is_417(widgets, auth_api):
    response = auth_api.post(
        URL, {"view": KANBAN, "column_field": "status", "kanban_columns": [{"name": "Open", "order": 5}]}, format="json"
    )
    assert response.status_code == 417
    assert response.json()["message"] == "A column's order must be a list"
