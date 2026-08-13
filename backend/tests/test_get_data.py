"""Acceptance criterion 6 - ``crm.api.doc.get_data`` returns data + columns + rows.

PHASE_0_FOUNDATION.md section 6b, ported from ``crm/api/doc.py:256-541``.
"""

import json

import pytest

from frappe_core.api.doc import get_data
from frappe_core.session import session_user
from tests_support.models import Widget

pytestmark = pytest.mark.django_db

METHOD_URL = "/api/method/crm.api.doc.get_data"

#: Every key upstream returns (``crm/api/doc.py:522-541``). The frontend destructures
#: these, so a missing key is a broken screen.
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
def clean_registry_hooks():
    """Restore an entry's hooks - the registry is process-global."""
    from frappe_core import registry

    entry = registry.get_entry("Phase Zero Widget")
    saved = (entry.list_columns_provider, entry.filterable_fields_provider)
    yield entry
    entry.list_columns_provider, entry.filterable_fields_provider = saved


@pytest.fixture
def widgets(alice, bob):
    with session_user(alice.name):
        Widget.objects.create(widget_name="Alpha", status="Open", widget_owner=alice)
        Widget.objects.create(widget_name="Beta", status="Open", widget_owner=bob)
        Widget.objects.create(widget_name="Gamma", status="Closed", widget_owner=alice)
    return Widget.objects.all()


def call(**kwargs):
    kwargs.setdefault("doctype", "Phase Zero Widget")
    kwargs.setdefault("filters", {})
    kwargs.setdefault("order_by", "modified desc")
    return get_data(**kwargs)


# --- criterion 6 --------------------------------------------------------------


def test_returns_data_columns_and_rows(widgets, alice):
    with session_user(alice.name):
        result = call()
    assert result["data"], "list branch must return rows"
    assert result["columns"], "list branch must return columns"
    assert result["rows"], "list branch must return the row fieldnames"


def test_response_has_every_upstream_key(widgets, alice):
    with session_user(alice.name):
        result = call()
    assert set(result) == EXPECTED_KEYS


def test_columns_come_from_the_controller_default(widgets, alice):
    with session_user(alice.name):
        result = call()
    assert [c["key"] for c in result["columns"]] == ["widget_name", "status", "modified"]


def test_every_column_key_is_present_in_rows(widgets, alice):
    """Upstream lines 341-343 - the frontend reads values by row key."""
    with session_user(alice.name):
        result = call()
    for column in result["columns"]:
        assert column["key"] in result["rows"]


def test_standard_fields_are_appended_to_rows(widgets, alice):
    """Upstream lines 478-483."""
    with session_user(alice.name):
        result = call()
    for fieldname in ("name", "creation", "modified", "modified_by", "_assign", "owner", "_liked_by"):
        assert fieldname in result["rows"]


def test_fields_block_describes_the_doctype(widgets, alice):
    with session_user(alice.name):
        result = call()
    by_name = {f["fieldname"]: f for f in result["fields"]}
    assert by_name["widget_name"]["fieldtype"] == "Data"
    assert by_name["widget_owner"]["fieldtype"] == "Link"
    assert by_name["widget_owner"]["options"] == "User"
    assert by_name["active"]["fieldtype"] == "Check"


def test_total_count_ignores_pagination(widgets, alice):
    with session_user(alice.name):
        result = call(page_length=1)
    assert result["row_count"] == 1
    assert result["total_count"] == 3


def test_custom_columns_mark_the_view_as_not_default(widgets, alice):
    """Upstream lines 309-313."""
    with session_user(alice.name):
        result = call(
            columns=[{"label": "Widget", "type": "Data", "key": "widget_name", "width": "10rem"}],
            rows=["name", "widget_name"],
        )
    assert result["is_default"] is False
    assert [c["key"] for c in result["columns"]] == ["widget_name"]


def test_default_view_is_flagged_default(widgets, alice):
    with session_user(alice.name):
        assert call()["is_default"] is True


def test_hidden_columns_are_dropped(widgets, alice):
    with session_user(alice.name):
        result = call(
            columns=[
                {"label": "Widget", "type": "Data", "key": "widget_name"},
                {"label": "Secret", "type": "Data", "key": "notes", "hidden": True},
            ],
            rows=["name"],
        )
    assert [c["key"] for c in result["columns"]] == ["widget_name"]


def test_liked_by_column_width_is_narrowed(widgets, alice):
    """Upstream lines 346-347 - the only column-specific fixup."""
    with session_user(alice.name):
        result = call(
            columns=[{"label": "Like", "type": "Data", "key": "_liked_by", "width": "10rem"}],
            rows=["name"],
        )
    assert result["columns"][0]["width"] == "50px"


# --- filters ------------------------------------------------------------------


def test_filters_are_applied(widgets, alice):
    with session_user(alice.name):
        result = call(filters={"status": "Closed"})
    assert [r["widget_name"] for r in result["data"]] == ["Gamma"]


def test_me_token_is_resolved(widgets, alice):
    with session_user(alice.name):
        result = call(filters={"widget_owner": "@me"})
    assert sorted(r["widget_name"] for r in result["data"]) == ["Alpha", "Gamma"]


def test_default_filters_are_merged(widgets, alice):
    """Upstream lines 295-297 - ``filters.update(default_filters)``."""
    with session_user(alice.name):
        result = call(filters={}, default_filters={"status": "Open"})
    assert sorted(r["widget_name"] for r in result["data"]) == ["Alpha", "Beta"]


def test_default_filters_win_over_user_filters(widgets, alice):
    """dict.update() semantics: the default overwrites the same key."""
    with session_user(alice.name):
        result = call(filters={"status": "Closed"}, default_filters={"status": "Open"})
    assert sorted(r["widget_name"] for r in result["data"]) == ["Alpha", "Beta"]


def test_list_form_filters_are_not_silently_dropped(widgets, alice):
    """Codex phase-0 finding 2.

    An earlier revision coerced ``filters`` through a dict cast, so the list-of-tuples
    grammar became ``{}`` and the caller got an *unfiltered* list back. Silently
    widening a result set is the worst possible failure mode for a filter.
    """
    with session_user(alice.name):
        result = call(filters=[["status", "=", "Closed"]])
    assert [r["widget_name"] for r in result["data"]] == ["Gamma"]
    assert result["total_count"] == 1


def test_doctype_qualified_list_filters_work(widgets, alice):
    with session_user(alice.name):
        result = call(filters=[["Phase Zero Widget", "status", "=", "Closed"]])
    assert [r["widget_name"] for r in result["data"]] == ["Gamma"]


def test_me_resolves_in_list_form_filters(widgets, alice):
    with session_user(alice.name):
        result = call(filters=[["widget_owner", "=", "@me"]])
    assert sorted(r["widget_name"] for r in result["data"]) == ["Alpha", "Gamma"]


def test_default_filters_merge_into_list_form(widgets, alice):
    with session_user(alice.name):
        result = call(filters=[["status", "=", "Open"]], default_filters={"widget_name": "Alpha"})
    assert [r["widget_name"] for r in result["data"]] == ["Alpha"]


def test_list_form_filters_reach_the_kanban_branch(widgets, alice):
    with session_user(alice.name):
        result = call(
            filters=[["status", "=", "Open"]],
            view={"view_type": "kanban"},
            column_field="status",
            kanban_columns=[{"name": "Open"}, {"name": "Closed"}],
        )
    counts = {e["column"]["name"]: e["column"].get("count") for e in result["data"]}
    assert counts["Open"] == 2
    # Filtered to Open, so the Closed column must come back empty rather than ignoring
    # the caller's filter.
    assert counts.get("Closed") in (0, None)


def test_kanban_does_not_invert_a_non_equality_filter_on_the_column_field(widgets, alice):
    """Codex round-2 finding A.

    ``status != Closed`` with ``column_field="status"``: dropping the operator made
    this behave as ``status == Closed``, i.e. the exact inverse of what was asked. The
    Closed column must be empty and the Open column must keep its rows.
    """
    with session_user(alice.name):
        result = call(
            filters=[["status", "!=", "Closed"]],
            view={"view_type": "kanban"},
            column_field="status",
            kanban_columns=[{"name": "Open"}, {"name": "Closed"}],
        )
    by_column = {e["column"]["name"]: [r["widget_name"] for r in e["data"]] for e in result["data"]}
    assert sorted(by_column["Open"]) == ["Alpha", "Beta"]
    assert by_column["Closed"] == [], "the != filter must still exclude Closed"


def test_kanban_equality_filter_selects_only_the_matching_column(widgets, alice):
    """Upstream's behaviour for the equality case, preserved exactly."""
    with session_user(alice.name):
        result = call(
            filters={"status": "Closed"},
            view={"view_type": "kanban"},
            column_field="status",
            kanban_columns=[{"name": "Open"}, {"name": "Closed"}],
        )
    by_column = {e["column"]["name"]: [r["widget_name"] for r in e["data"]] for e in result["data"]}
    assert by_column["Open"] == []
    assert by_column["Closed"] == ["Gamma"]


def test_kanban_keeps_unrelated_filters_per_column(widgets, alice):
    with session_user(alice.name):
        result = call(
            filters=[["widget_name", "=", "Alpha"]],
            view={"view_type": "kanban"},
            column_field="status",
            kanban_columns=[{"name": "Open"}, {"name": "Closed"}],
        )
    by_column = {e["column"]["name"]: [r["widget_name"] for r in e["data"]] for e in result["data"]}
    assert by_column["Open"] == ["Alpha"]
    assert by_column["Closed"] == []


def test_doctype_without_default_list_data_still_gets_columns_and_rows(alice):
    """Codex round-2 finding B.

    ``Phase Zero Hash`` defines no ``default_list_data``. The fallback assigned early
    must not then be overwritten with the empty default.
    """
    from tests_support.models import HashDoc

    with session_user(alice.name):
        HashDoc.objects.create(label="x")
        result = get_data(doctype="Phase Zero Hash", filters={}, order_by="modified desc")

    assert [c["key"] for c in result["columns"]] == ["name", "modified"]
    assert "name" in result["rows"] and "modified" in result["rows"]
    assert len(result["data"]) == 1


def test_a_saved_view_returning_empty_columns_falls_back(alice, widgets, clean_registry_hooks):
    """A malformed saved view must not produce a column-less list."""
    from frappe_core import registry

    registry.register_metadata_hooks(
        "Phase Zero Widget",
        list_columns_provider=lambda dt, u, vt: {"columns": [], "rows": []},
    )
    with session_user(alice.name):
        result = call()
    assert result["columns"], "must fall back rather than render no columns"
    assert result["rows"]


def test_a_bad_filters_type_raises_rather_than_returning_everything(alice):
    from frappe_core.exceptions import ValidationError

    with session_user(alice.name), pytest.raises(ValidationError):
        call(filters=42)


def test_hidden_fields_declared_on_the_model_are_dropped(widgets, alice):
    """Codex phase-0 finding 4.

    Upstream decides hidden from the doctype field metadata
    (``crm/api/doc.py:350-352``), not from a flag on the column dict.
    """
    from tests_support.models import Widget

    Widget.get_hidden_fields = staticmethod(lambda: ["notes"])
    try:
        with session_user(alice.name):
            result = call(
                columns=[
                    {"label": "Widget", "type": "Data", "key": "widget_name"},
                    {"label": "Notes", "type": "Text", "key": "notes"},
                ],
                rows=["name"],
            )
        assert [c["key"] for c in result["columns"]] == ["widget_name"]
    finally:
        del Widget.get_hidden_fields


def test_removing_a_hidden_column_does_not_skip_the_next_one(widgets, alice):
    """Upstream mutates the list it is iterating; we must not replicate that."""
    from tests_support.models import Widget

    Widget.get_hidden_fields = staticmethod(lambda: ["notes"])
    try:
        with session_user(alice.name):
            result = call(
                columns=[
                    {"label": "Notes", "type": "Text", "key": "notes"},
                    {"label": "Status", "type": "Data", "key": "status"},
                    {"label": "Widget", "type": "Data", "key": "widget_name"},
                ],
                rows=["name"],
            )
        assert [c["key"] for c in result["columns"]] == ["status", "widget_name"]
    finally:
        del Widget.get_hidden_fields


def test_json_encoded_arguments_are_accepted(widgets, alice):
    """The frontend posts these as JSON strings, not native structures."""
    with session_user(alice.name):
        result = call(
            filters=json.dumps({"status": "Open"}),
            rows=json.dumps(["name", "widget_name"]),
            columns=json.dumps([{"label": "W", "type": "Data", "key": "widget_name"}]),
        )
    assert sorted(r["widget_name"] for r in result["data"]) == ["Alpha", "Beta"]


# --- group_by -----------------------------------------------------------------


def test_group_by_field_is_added_to_rows(widgets, alice):
    with session_user(alice.name):
        result = call(view={"view_type": "group_by", "group_by_field": "status"})
    assert "status" in result["rows"]


def test_group_by_returns_a_descriptor_with_sorted_options(widgets, alice):
    with session_user(alice.name):
        result = call(view={"view_type": "group_by", "group_by_field": "status"})
    descriptor = result["group_by_field"]
    assert descriptor["fieldname"] == "status"
    assert descriptor["options"] == ["Closed", "Open"]


# --- kanban -------------------------------------------------------------------


def test_kanban_branch_returns_one_entry_per_column(widgets, alice):
    with session_user(alice.name):
        result = call(
            view={"view_type": "kanban"},
            column_field="status",
            kanban_columns=[{"name": "Open"}, {"name": "Closed"}],
            kanban_fields=["widget_name"],
        )
    assert result["view_type"] == "kanban"
    assert [entry["column"]["name"] for entry in result["data"]] == ["Open", "Closed"]
    assert [entry["column"]["count"] for entry in result["data"]] == [2, 1]


def test_kanban_columns_carry_an_all_count(widgets, alice):
    with session_user(alice.name):
        result = call(
            view={"view_type": "kanban"},
            column_field="status",
            kanban_columns=[{"name": "Open"}],
        )
    assert result["data"][0]["column"]["all_count"] == 2


def test_kanban_resolves_columns_from_a_link_target(widgets, alice, bob):
    """Upstream lines 374-383 - a Link column_field enumerates its target table."""
    with session_user(alice.name):
        result = call(view={"view_type": "kanban"}, column_field="widget_owner")
    resolved = [c["name"] for c in result["kanban_columns"]]
    assert alice.name in resolved and bob.name in resolved


# --- through the HTTP method dispatcher ---------------------------------------


def test_reachable_over_api_method(auth_api, widgets):
    response = auth_api.post(
        METHOD_URL,
        {"doctype": "Phase Zero Widget", "filters": {}, "order_by": "modified desc"},
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"message"}, "/api/method/* must be enveloped as {'message': ...}"
    assert set(body["message"]) == EXPECTED_KEYS


def test_method_dispatch_requires_authentication(api):
    response = api.post(METHOD_URL, {"doctype": "Phase Zero Widget"}, format="json")
    assert response.status_code == 401
    assert response.json()["exc_type"] == "AuthenticationError"


def test_unknown_method_is_a_frappe_404(auth_api):
    response = auth_api.post("/api/method/crm.api.doc.no_such_method", {}, format="json")
    assert response.status_code == 404
    assert response.json()["exc_type"] == "DoesNotExistError"


def test_surplus_parameters_are_ignored(auth_api, widgets):
    """Frappe passes the whole payload as kwargs and ignores what it cannot bind."""
    response = auth_api.post(
        METHOD_URL,
        {"doctype": "Phase Zero Widget", "cmd": "legacy", "_": "1730000000"},
        format="json",
    )
    assert response.status_code == 200
