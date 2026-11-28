"""`get_data`'s list path on `test-widgets/list-view/` (specs/CONFIGURATION.md 4.8;
temp A-40).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_get_data.py``: every list-path case.
The old `crm.api.doc.get_data` with `doctype` is the resource's own `list-view/` route;
the old in-process `call()` is a POST to it. Widget's list rule (own or ownerless
widgets) is v2's, so Beta is ownerless where the old fixture gave it to Bob: Alice sees
all three, and `@me` still tells them apart. Widget's definition is `WidgetListView`,
whose hidden field (`notes`) stands in for the old monkeypatched `get_hidden_fields`
(`:322`, `:345`). `:284` runs on the second resource, which has no definition; `:442`
and `:448` become the route's 401 and 404. The saved view (`:301`), group-by options
(`:385`) and kanban (`:223-282`, `:396-425`) cases come with CF8c and CF8d.
"""

import json

import pytest

from configuration.list_engine import selectable
from tests_support.models import SearchableDocument, Widget

pytestmark = pytest.mark.django_db

URL = "/api/v1/test-widgets/list-view/"

#: Every key upstream returns (`crm/api/doc.py:522-541`).
EXPECTED_KEYS = {
    "data",
    "columns",
    "rows",
    "fields",
    "column_field",
    "title_field",
    "kanban_columns",
    "kanban_fields",
    "group_by_field",
    "page_length",
    "page_length_count",
    "is_default",
    "views",
    "total_count",
    "row_count",
    "form_script",
    "list_script",
    "view_type",
}


@pytest.fixture
def widgets(alice):
    for name, status, owner in (("Alpha", "Open", alice), ("Beta", "Open", None), ("Gamma", "Closed", alice)):
        Widget(widget_name=name, status=status, widget_owner=owner).save(user=alice)
    return Widget.objects.all()


def call(client, url=URL, **inputs):
    inputs.setdefault("filters", {})
    inputs.setdefault("order_by", "modified desc")
    response = client.post(url, inputs, format="json")
    assert response.status_code == 200, response.json()
    return response.json()["message"]


def names(result):
    return sorted(row["widget_name"] for row in result["data"])


# --- ported: the answer ------------------------------------------------------------------


def test_returns_data_columns_and_rows(widgets, auth_api):
    result = call(auth_api)
    assert result["data"] and result["columns"] and result["rows"]


def test_response_has_every_upstream_key(widgets, auth_api):
    assert set(call(auth_api)) == EXPECTED_KEYS


def test_columns_come_from_the_definition(widgets, auth_api):
    """The old controller default; `notes` is the definition's hidden field."""
    assert [c["key"] for c in call(auth_api)["columns"]] == ["widget_name", "status", "modified"]


def test_every_column_key_is_present_in_rows(widgets, auth_api):
    result = call(auth_api)
    for column in result["columns"]:
        assert column["key"] in result["rows"]


def test_standard_fields_are_appended_to_rows(widgets, auth_api):
    rows = call(auth_api)["rows"]
    for fieldname in ("name", "creation", "modified", "modified_by", "_assign", "owner", "_liked_by"):
        assert fieldname in rows


def test_fields_block_describes_the_doctype(widgets, auth_api):
    by_name = {f["fieldname"]: f for f in call(auth_api)["fields"]}
    assert by_name["widget_name"]["fieldtype"] == "Data"
    assert by_name["widget_owner"]["fieldtype"] == "Link"
    assert by_name["widget_owner"]["options"] == "User"
    assert by_name["active"]["fieldtype"] == "Check"


def test_total_count_ignores_pagination(widgets, auth_api):
    result = call(auth_api, page_length=1)
    assert (result["row_count"], result["total_count"]) == (1, 3)


def test_custom_columns_mark_the_view_as_not_default(widgets, auth_api):
    result = call(
        auth_api,
        columns=[{"label": "Widget", "type": "Data", "key": "widget_name", "width": "10rem"}],
        rows=["name", "widget_name"],
    )
    assert result["is_default"] is False
    assert [c["key"] for c in result["columns"]] == ["widget_name"]


def test_default_view_is_flagged_default(widgets, auth_api):
    assert call(auth_api)["is_default"] is True


def test_hidden_columns_are_dropped(widgets, auth_api):
    result = call(
        auth_api,
        columns=[
            {"label": "Widget", "type": "Data", "key": "widget_name"},
            {"label": "Secret", "type": "Data", "key": "amount", "hidden": True},
        ],
        rows=["name"],
    )
    assert [c["key"] for c in result["columns"]] == ["widget_name"]


def test_liked_by_column_width_is_narrowed(widgets, auth_api):
    result = call(
        auth_api,
        columns=[{"label": "Like", "type": "Data", "key": "_liked_by", "width": "10rem"}],
        rows=["name"],
    )
    assert result["columns"][0]["width"] == "50px"


# --- ported: filters ---------------------------------------------------------------------


def test_filters_are_applied(widgets, auth_api):
    assert names(call(auth_api, filters={"status": "Closed"})) == ["Gamma"]


def test_me_token_is_resolved(widgets, auth_api):
    assert names(call(auth_api, filters={"widget_owner": "@me"})) == ["Alpha", "Gamma"]


def test_default_filters_are_merged(widgets, auth_api):
    assert names(call(auth_api, filters={}, default_filters={"status": "Open"})) == ["Alpha", "Beta"]


def test_default_filters_win_over_user_filters(widgets, auth_api):
    result = call(auth_api, filters={"status": "Closed"}, default_filters={"status": "Open"})
    assert names(result) == ["Alpha", "Beta"]


def test_list_form_filters_are_not_silently_dropped(widgets, auth_api):
    result = call(auth_api, filters=[["status", "=", "Closed"]])
    assert names(result) == ["Gamma"]
    assert result["total_count"] == 1


def test_doctype_qualified_list_filters_work(widgets, auth_api):
    result = call(auth_api, filters=[["Foundation Widget", "status", "=", "Closed"]])
    assert names(result) == ["Gamma"]


def test_me_resolves_in_list_form_filters(widgets, auth_api):
    assert names(call(auth_api, filters=[["widget_owner", "=", "@me"]])) == ["Alpha", "Gamma"]


def test_default_filters_merge_into_list_form(widgets, auth_api):
    result = call(auth_api, filters=[["status", "=", "Open"]], default_filters={"widget_name": "Alpha"})
    assert names(result) == ["Alpha"]


def test_a_definitionless_resource_still_gets_columns_and_rows(alice, auth_api):
    """`:284`: a resource with no definition answers the fallback."""
    SearchableDocument(title="x").save(user=alice)
    result = call(auth_api, url="/api/v1/test-searchable-documents/list-view/")
    assert [c["key"] for c in result["columns"]] == ["name", "modified"]
    assert "name" in result["rows"] and "modified" in result["rows"]
    assert len(result["data"]) == 1


def test_a_bad_filters_type_is_refused_rather_than_returning_everything(auth_api):
    response = auth_api.post(URL, {"filters": 42}, format="json")
    assert response.status_code == 417
    assert response.json()["message"] == "Unsupported filters value of type int"


def test_the_definitions_hidden_fields_are_dropped(widgets, auth_api):
    result = call(
        auth_api,
        columns=[
            {"label": "Widget", "type": "Data", "key": "widget_name"},
            {"label": "Notes", "type": "Text", "key": "notes"},
        ],
        rows=["name"],
    )
    assert [c["key"] for c in result["columns"]] == ["widget_name"]


def test_removing_a_hidden_column_does_not_skip_the_next_one(widgets, auth_api):
    result = call(
        auth_api,
        columns=[
            {"label": "Notes", "type": "Text", "key": "notes"},
            {"label": "Status", "type": "Data", "key": "status"},
            {"label": "Widget", "type": "Data", "key": "widget_name"},
        ],
        rows=["name"],
    )
    assert [c["key"] for c in result["columns"]] == ["status", "widget_name"]


def test_json_encoded_arguments_are_accepted(widgets, auth_api):
    result = call(
        auth_api,
        filters=json.dumps({"status": "Open"}),
        rows=json.dumps(["name", "widget_name"]),
        columns=json.dumps([{"label": "W", "type": "Data", "key": "widget_name"}]),
    )
    assert names(result) == ["Alpha", "Beta"]


def test_group_by_field_is_added_to_rows(widgets, auth_api):
    assert "status" in call(auth_api, view={"view_type": "group_by", "group_by_field": "status"})["rows"]


# --- ported: the route -------------------------------------------------------------------


def test_reachable_over_its_route(widgets, auth_api):
    response = auth_api.post(URL, {"filters": {}, "order_by": "modified desc"}, format="json")
    assert response.status_code == 200
    assert set(response.json()) == {"message"}
    assert set(response.json()["message"]) == EXPECTED_KEYS


def test_get_is_served_too(widgets, auth_api):
    response = auth_api.get(URL, {"filters": json.dumps({"status": "Open"})})
    assert response.status_code == 200
    assert names(response.json()["message"]) == ["Alpha", "Beta"]


def test_the_route_requires_authentication(api):
    response = api.post(URL, {}, format="json")
    assert response.status_code == 401


def test_a_resource_that_does_not_opt_in_has_no_list_view(auth_api):
    """The path is then the record route of a document called `list-view`: a GET is
    its 404, a POST its 405 (S25 (8))."""
    assert auth_api.get("/api/v1/test-pointers/list-view/").status_code == 404
    assert auth_api.post("/api/v1/test-pointers/list-view/", {}, format="json").status_code == 405


def test_surplus_parameters_are_ignored(widgets, auth_api):
    response = auth_api.post(URL, {"doctype": "Anything", "cmd": "legacy", "_": "1730000000"}, format="json")
    assert response.status_code == 200


def test_an_unknown_row_key_raises(widgets, auth_api):
    response = auth_api.post(
        URL,
        {"rows": json.dumps(["name", "no_such_column"]), "columns": json.dumps([{"label": "Name", "key": "name"}])},
        format="json",
    )
    assert response.status_code == 417
    assert response.json()["exc_type"] == "ValidationError"
    assert response.json()["message"] == "Unknown field 'no_such_column' for Foundation Widget"


def test_several_unknown_keys_are_all_named(widgets, auth_api):
    response = auth_api.post(
        URL,
        {"rows": json.dumps(["nope_one", "nope_two"]), "columns": json.dumps([{"label": "Name", "key": "name"}])},
        format="json",
    )
    assert response.json()["message"] == "Unknown fields 'nope_one', 'nope_two' for Foundation Widget"


def test_known_row_keys_still_work(widgets, auth_api):
    response = auth_api.post(
        URL,
        {"rows": json.dumps(["name", "widget_name", "status"]), "columns": json.dumps([{"label": "Name", "key": "widget_name"}])},
        format="json",
    )
    assert response.status_code == 200


def test_empty_rows_still_falls_back_to_name():
    assert selectable(Widget, []) == ["name"]


# --- new ---------------------------------------------------------------------------------


def test_the_list_rule_applies(alice, bob, api_as, widgets):
    """Root rule 11: Bob sees only the ownerless widget."""
    result = call(api_as(bob))
    assert names(result) == ["Beta"]
    assert result["total_count"] == 1


def test_a_row_the_caller_may_not_read_is_refused(widgets, auth_api, monkeypatch):
    from tests_support.views import WidgetViewSet

    monkeypatch.setattr(WidgetViewSet, "readable_fields", ("name", "modified", "widget_name"))
    response = auth_api.post(URL, {"rows": ["name", "status"], "columns": []}, format="json")
    assert response.status_code == 417


def test_a_filter_the_resource_does_not_list_is_refused(widgets, auth_api):
    response = auth_api.post(URL, {"filters": {"due_date": "2026-01-01"}}, format="json")
    assert response.status_code in (400, 417)


def test_the_answer_offers_the_callers_saved_views(widgets, alice, auth_api):
    from configuration.view_settings import create_view

    name = create_view({"doctype": "Foundation Widget", "label": "Mine"}, user=alice)["name"]
    assert [view["name"] for view in call(auth_api)["views"]] == [name]
