"""`get_data` and saved views: the caller's standard view, `is_default` from a named
view, group-by options, form scripts, PE-12e (specs/CONFIGURATION.md 4.8; temp A-40).

Twins (REBUILD_PLAN S14) on `test-widgets/list-view/` of
``backend/tests/test_phase4_metadata.py:223`` (one user's saved view is invisible to
another) and `:251-339` (the four-step column resolution, the views, the form scripts),
whose CRM Lead cases wait for SALES; ``backend/tests/test_get_data.py:301`` (a saved view
with empty lists falls back) and `:385` (group-by options). New: `is_default` under the
read rule (PE-21) and PE-12e.
"""

import pytest

from configuration.models import CRMFormScript, CRMViewSettings
from configuration.view_settings import create_or_update_standard_view, create_view
from tests_support.models import Widget

pytestmark = pytest.mark.django_db

URL = "/api/v1/test-widgets/list-view/"
DOCTYPE = "Foundation Widget"


@pytest.fixture
def widgets(alice):
    for name, status in (("Alpha", "Open"), ("Beta", "Open"), ("Gamma", "Closed")):
        Widget(widget_name=name, status=status, widget_owner=alice).save(user=alice)


def standard(user, columns, rows, view_type="list"):
    return create_or_update_standard_view(
        {"doctype": DOCTYPE, "type": view_type, "columns": columns, "rows": rows}, user=user
    )["name"]


def call(client, **inputs):
    inputs.setdefault("filters", {})
    inputs.setdefault("order_by", "modified desc")
    response = client.post(URL, inputs, format="json")
    assert response.status_code == 200, response.json()
    return response.json()["message"]


def keys(result):
    return [column["key"] for column in result["columns"]]


# --- twins: the four steps ---------------------------------------------------------------


def test_step1_explicit_columns_win_over_a_saved_view(widgets, alice, auth_api):
    standard(alice, [{"key": "status", "label": "Status"}], ["name", "status"])
    result = call(auth_api, columns=[{"key": "widget_name", "label": "W", "type": "Data"}], rows=["name"])
    assert keys(result) == ["widget_name"]
    assert result["is_default"] is False


def test_step2_the_callers_saved_view_is_used(widgets, alice, auth_api):
    standard(alice, [{"key": "status", "label": "Status"}], ["name", "status"])
    result = call(auth_api)
    assert keys(result) == ["status"]
    assert result["is_default"] is False


def test_one_users_saved_view_is_invisible_to_another(widgets, alice, bob, api_as):
    standard(alice, [{"key": "status", "label": "Status"}], ["name", "status"])
    assert keys(call(api_as(bob))) == ["widget_name", "status", "modified"]


def test_step3_the_definition_when_there_is_no_saved_view(widgets, auth_api):
    result = call(auth_api)
    assert keys(result) == ["widget_name", "status", "modified"]
    assert result["is_default"] is True


def test_a_saved_view_for_another_view_type_does_not_apply(widgets, alice, auth_api):
    standard(alice, [{"key": "status"}], ["name", "status"], view_type="kanban")
    assert keys(call(auth_api)) != ["status"]


def test_a_saved_view_with_empty_lists_falls_back(widgets, alice, auth_api):
    name = standard(alice, [{"key": "status"}], ["name"])
    CRMViewSettings.objects.filter(pk=name).update(columns="[]", rows="[]")
    assert keys(call(auth_api)) == ["widget_name", "status", "modified"]


def test_the_newest_standard_view_wins(widgets, alice, auth_api):
    older = standard(alice, [{"key": "status"}], ["name", "status"])
    newer = create_view({"doctype": DOCTYPE, "label": "B", "columns": [{"key": "widget_name"}]}, user=alice)["name"]
    CRMViewSettings.objects.filter(pk=newer).update(is_standard=True)
    CRMViewSettings.objects.filter(pk=older).update(modified="2000-01-01T00:00:00Z")
    assert keys(call(auth_api)) == ["widget_name"]


# --- twins: views and form scripts -------------------------------------------------------


def test_the_answer_lists_the_callers_views(widgets, alice, auth_api):
    standard(alice, [{"key": "status"}], ["name", "status"])
    assert len(call(auth_api)["views"]) == 1


def test_an_enabled_form_script_is_served(widgets, administrator, auth_api):
    CRMFormScript(name="widget-form", dt=DOCTYPE, view="Form", enabled=True, script="class W {}").save(user=administrator)
    CRMFormScript(name="widget-list", dt=DOCTYPE, view="List", enabled=True, script="class L {}").save(user=administrator)
    result = call(auth_api)
    assert (result["form_script"], result["list_script"]) == ("class W {}", "class L {}")


def test_a_disabled_form_script_is_not_served(widgets, administrator, auth_api):
    CRMFormScript(name="off", dt=DOCTYPE, view="Form", enabled=False, script="nope").save(user=administrator)
    assert call(auth_api)["form_script"] is None


# --- is_default from a named view (PE-21) ------------------------------------------------


def test_a_named_view_that_loads_default_columns_reports_default(widgets, alice, auth_api):
    name = create_view({"doctype": DOCTYPE, "label": "D", "load_default_columns": 1}, user=alice)["name"]
    result = call(auth_api, columns=[{"key": "widget_name"}], rows=["name"], view={"custom_view_name": name})
    assert result["is_default"] is True


def test_pe21_another_users_private_view_counts_as_no_view(widgets, bob, auth_api):
    name = create_view({"doctype": DOCTYPE, "label": "D", "load_default_columns": 1}, user=bob)["name"]
    result = call(auth_api, columns=[{"key": "widget_name"}], rows=["name"], view={"custom_view_name": name})
    assert result["is_default"] is False


def test_pe12e_a_name_that_is_not_an_integer_counts_as_no_view(widgets, auth_api):
    result = call(auth_api, columns=[{"key": "widget_name"}], rows=["name"], view={"custom_view_name": "abc"})
    assert result["is_default"] is False


# --- group-by options --------------------------------------------------------------------


def test_group_by_returns_a_descriptor_with_sorted_options(widgets, auth_api):
    descriptor = call(auth_api, view={"view_type": "group_by", "group_by_field": "status"})["group_by_field"]
    assert descriptor["fieldname"] == "status"
    assert descriptor["options"] == ["Closed", "Open"]


def test_group_by_options_follow_a_descending_order(widgets, auth_api):
    result = call(auth_api, order_by="status desc", view={"view_type": "group_by", "group_by_field": "status"})
    assert result["group_by_field"]["options"] == ["Open", "Closed"]


def test_group_by_lists_an_empty_value_sorted_with_the_rest(widgets, alice, auth_api):
    """The old code appends "" and then sorts (`doc.py:610-623`), so it comes first."""
    Widget(widget_name="Delta", status="", widget_owner=alice).save(user=alice)
    result = call(auth_api, view={"view_type": "group_by", "group_by_field": "status"})
    assert result["group_by_field"]["options"] == ["", "Closed", "Open"]


# --- PE-12e ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        ({"columns": ["widget_name"]}, "Columns must be objects"),
        ({"rows": [{"a": 1}]}, "Rows must be fieldnames"),
        ({"kanban_columns": ["Open"]}, "Kanban columns must be objects"),
        ({"kanban_fields": [1]}, "Kanban fields must be fieldnames"),
    ],
)
def test_pe12e_an_entry_of_the_wrong_shape_is_417(widgets, auth_api, inputs, message):
    response = auth_api.post(URL, inputs, format="json")
    assert response.status_code == 417
    assert response.json()["message"] == message


def test_pe12e_a_stored_view_of_the_wrong_shape_is_417(widgets, alice, auth_api):
    name = standard(alice, [{"key": "status"}], ["name"])
    CRMViewSettings.objects.filter(pk=name).update(columns='["status"]')
    response = auth_api.post(URL, {}, format="json")
    assert response.status_code == 417
    assert response.json()["message"] == "Columns must be objects"
