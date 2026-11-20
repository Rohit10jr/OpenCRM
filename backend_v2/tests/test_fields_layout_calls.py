"""The layout calls (specs/CONFIGURATION.md 4.6; temp A-37).

`get_fields_layout`, `get_sidepanel_sections` and `save_fields_layout` are
`GET /api/v1/fields-layouts/layout/`, `GET .../sidepanel-sections/` and
`POST .../save/`. The old cases run on CRM Lead, CRM Deal and CRM Task (SALES and
ACTIVITIES); these are in-unit twins on FCRM Settings and CRM Dropdown Item (the Grid
Row editor), plus the new rules: the doctype checked (PE-14, PE-15), fields the caller
may not read left out (PE-16), field lists of fieldnames (PE-18), invalid JSON (PE-12c).
"""

import json

import pytest

from configuration import field_meta
from configuration.fields_layout import get_field_obj
from configuration.models import CRMFieldsLayout

pytestmark = pytest.mark.django_db

LAYOUT = "/api/v1/fields-layouts/layout/"
SIDEPANEL = "/api/v1/fields-layouts/sidepanel-sections/"
SAVE = "/api/v1/fields-layouts/save/"


@pytest.fixture
def manager(make_user):
    return make_user("mgr@example.com", roles=["Sales Manager"])


def fieldnames(tabs) -> list[str]:
    return [
        field["fieldname"]
        for tab in tabs
        for section in tab.get("sections", [])
        for column in section.get("columns", [])
        for field in column.get("fields", [])
    ]


def store(administrator, dt, type, layout):
    CRMFieldsLayout(dt=dt, type=type, layout=json.dumps(layout)).save(user=administrator)


# --- get_fields_layout -------------------------------------------------------------------


def test_without_a_row_the_default_layout_follows_the_file(api_as, manager):
    tabs = api_as(manager).get(LAYOUT, {"doctype": "FCRM Settings", "type": "Quick Entry"}).json()["message"]
    in_file_order = [
        f["fieldname"]
        for f in field_meta.get_fields("FCRM Settings")
        if f["fieldtype"] not in ("Tab Break", "Section Break", "Column Break")
    ]
    assert fieldnames(tabs) == in_file_order
    assert all("sections" in tab for tab in tabs)


def test_a_stored_sections_only_layout_is_wrapped_as_first_tab(auth_api, administrator):
    store(administrator, "FCRM Settings", "Quick Entry", [{"name": "s", "columns": [{"name": "c", "fields": ["brand_name"]}]}])
    tabs = auth_api.get(LAYOUT, {"doctype": "FCRM Settings", "type": "Quick Entry"}).json()["message"]
    assert tabs[0]["name"] == "first_tab"
    assert fieldnames(tabs) == ["brand_name"]
    assert tabs[0]["sections"][0]["columns"][0]["fields"][0]["fieldtype"] == "Data"


def test_unknown_fieldnames_are_dropped(auth_api, administrator):
    store(administrator, "FCRM Settings", "Quick Entry", [{"columns": [{"fields": ["brand_name", "no_such_field"]}]}])
    tabs = auth_api.get(LAYOUT, {"doctype": "FCRM Settings", "type": "Quick Entry"}).json()["message"]
    assert fieldnames(tabs) == ["brand_name"]


def test_required_fields_has_no_default_and_never_answers_an_empty_list(auth_api):
    tabs = auth_api.get(LAYOUT, {"doctype": "FCRM Settings", "type": "Required Fields"}).json()["message"]
    assert tabs and tabs[0]["name"] == "first_tab"


def test_the_grid_row_layout_answers_for_a_child_table(auth_api, administrator):
    """PE-15: the grid row editor asks for its child table's layout."""
    store(administrator, "CRM Dropdown Item", "Grid Row", [{"columns": [{"fields": ["label", "route"]}]}])
    response = auth_api.get(
        LAYOUT, {"doctype": "CRM Dropdown Item", "type": "Grid Row", "parent_doctype": "FCRM Settings"}
    )
    assert response.status_code == 200, response.content[:300]
    assert fieldnames(response.json()["message"]) == ["label", "route"]


@pytest.mark.parametrize("doctype", ["No Such Doctype", "Version"])
def test_pe14_an_unknown_or_withheld_doctype_is_not_found(auth_api, doctype):
    response = auth_api.get(LAYOUT, {"doctype": doctype, "type": "Quick Entry"})
    assert response.status_code == 404
    assert response.json()["message"] == f"DocType {doctype} not found"


def test_pe16_a_restricted_field_is_left_out_for_a_non_manager(auth_api, api_as, manager):
    params = {"doctype": "FCRM Settings", "type": "Quick Entry"}
    assert "access_key" not in fieldnames(auth_api.get(LAYOUT, params).json()["message"])
    assert "access_key" in fieldnames(api_as(manager).get(LAYOUT, params).json()["message"])


def test_pe18_a_non_fieldname_entry_is_left_out_on_read(auth_api, administrator):
    CRMFieldsLayout(
        dt="FCRM Settings",
        type="Quick Entry",
        layout=json.dumps([{"columns": [{"fields": ["brand_name", {"fieldname": "x"}]}]}]),
    ).save(user=administrator)
    tabs = auth_api.get(LAYOUT, {"doctype": "FCRM Settings", "type": "Quick Entry"}).json()["message"]
    assert fieldnames(tabs) == ["brand_name"]


# --- get_sidepanel_sections --------------------------------------------------------------


def test_the_side_panel_expands_each_field(auth_api, administrator):
    store(administrator, "FCRM Settings", "Side Panel", [{"label": "Details", "columns": [{"fields": ["brand_name", "currency"]}]}])
    sections = auth_api.get(SIDEPANEL, {"doctype": "FCRM Settings"}).json()["message"]
    assert sections[0]["name"] == "Details"
    brand, currency = sections[0]["columns"][0]["fields"]
    assert brand["placeholder"].startswith("Add ")
    assert currency["placeholder"].startswith("Select ")


def test_the_side_panel_without_a_row_is_empty(auth_api):
    assert auth_api.get(SIDEPANEL, {"doctype": "FCRM Settings"}).json() == {"message": []}


def test_pe15_the_side_panel_is_not_for_a_child_table(auth_api):
    assert auth_api.get(SIDEPANEL, {"doctype": "CRM Dropdown Item"}).status_code == 404


@pytest.mark.parametrize("doctype", ["No Such Doctype", "Version"])
def test_pe14_the_side_panel_refuses_an_unknown_or_withheld_doctype(auth_api, doctype):
    response = auth_api.get(SIDEPANEL, {"doctype": doctype})
    assert response.status_code == 404
    assert response.json()["message"] == f"DocType {doctype} not found"


def test_pe18_a_non_fieldname_entry_is_left_out_of_the_side_panel(auth_api, administrator):
    CRMFieldsLayout(
        dt="FCRM Settings",
        type="Side Panel",
        layout=json.dumps([{"label": "D", "columns": [{"fields": ["brand_name", {"fieldname": "x"}, 3]}]}]),
    ).save(user=administrator)
    sections = auth_api.get(SIDEPANEL, {"doctype": "FCRM Settings"}).json()["message"]
    assert [f["fieldname"] for f in sections[0]["columns"][0]["fields"]] == ["brand_name"]


def test_pe16_a_restricted_field_is_left_out_of_the_side_panel(auth_api, api_as, manager, administrator):
    store(administrator, "FCRM Settings", "Side Panel", [{"label": "D", "columns": [{"fields": ["brand_name", "access_key"]}]}])

    def panel(client):
        sections = client.get(SIDEPANEL, {"doctype": "FCRM Settings"}).json()["message"]
        return [f["fieldname"] for f in sections[0]["columns"][0]["fields"]]

    assert panel(auth_api) == ["brand_name"]
    assert panel(api_as(manager)) == ["brand_name", "access_key"]


def test_pe16_a_restricted_field_is_left_out_of_the_required_fields_section(
    auth_api, api_as, manager, monkeypatch
):
    """No served doctype has a required field yet, so two are marked required here."""
    real = field_meta.get_fields

    def with_required(doctype):
        fields = [dict(f) for f in real(doctype)]
        for field in fields:
            if field["fieldname"] in ("brand_name", "access_key"):
                field["reqd"] = 1
        return fields

    monkeypatch.setattr(field_meta, "get_fields", with_required)
    params = {"doctype": "FCRM Settings", "type": "Required Fields"}
    assert fieldnames(auth_api.get(LAYOUT, params).json()["message"]) == ["brand_name"]
    assert fieldnames(api_as(manager).get(LAYOUT, params).json()["message"]) == ["brand_name", "access_key"]


#: Parses, but walking its field lists passes the recursion limit (A-38 fix 8).
DEEP = "[" * 2000 + "]" * 2000


def test_pe12c_a_layout_too_deep_to_parse_is_invalid_json():
    """The parser itself gives up at this depth; that is 417 too, not a 500."""
    from configuration.layouts import parse_layout
    from core.exceptions import ValidationError

    with pytest.raises(ValidationError, match="Layout must be valid JSON"):
        parse_layout("[" * 50000 + "]" * 50000)


def test_pe12c_a_layout_nested_too_deep_is_refused_on_save(api_as, manager):
    response = api_as(manager).post(
        SAVE, {"doctype": "FCRM Settings", "type": "Quick Entry", "layout": DEEP}, format="json"
    )
    assert response.status_code == 417
    assert response.json()["message"] == "Layout must be valid JSON"


@pytest.mark.parametrize("url,type", [(LAYOUT, "Quick Entry"), (SIDEPANEL, "Side Panel")])
def test_pe12c_a_stored_layout_that_is_not_json_answers_417_on_read(auth_api, administrator, url, type):
    """Written around the save's check (the model save does not run it), as an old row
    might be."""
    CRMFieldsLayout(dt="FCRM Settings", type=type, layout=DEEP).save(user=administrator)
    response = auth_api.get(url, {"doctype": "FCRM Settings", "type": type})
    assert response.status_code == 417
    assert response.json()["message"] == "Layout must be valid JSON"


def test_get_field_obj_expands_select_options_and_marks_read_only():
    obj = get_field_obj({"fieldname": "t", "label": "T", "fieldtype": "Select", "options": "A\nB", "read_only": 1})
    assert obj["options"] == [{"label": "A", "value": "A"}, {"label": "B", "value": "B"}]
    assert obj["tooltip"] == "This field is read only and cannot be edited."


# --- save_fields_layout ------------------------------------------------------------------


def test_a_manager_saves_a_layout_and_gets_the_stored_string(api_as, manager):
    layout = [{"columns": [{"fields": ["label"]}]}]
    response = api_as(manager).post(
        SAVE, {"doctype": "CRM Dropdown Item", "type": "Grid Row", "layout": layout}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
    assert response.json() == {"message": json.dumps(layout)}
    assert CRMFieldsLayout.objects.get(pk="CRM Dropdown Item-Grid Row").layout == json.dumps(layout)


def test_a_sales_user_may_not_save_a_layout(auth_api):
    response = auth_api.post(
        SAVE, {"doctype": "FCRM Settings", "type": "Quick Entry", "layout": "[]"}, format="json"
    )
    assert response.status_code == 403
    assert response.json()["message"] == "Not permitted to modify fields layout"


def test_save_checks_roles_only(api_as, administrator):
    """Roles only, as backend/: Administrator without its groups is refused here."""
    administrator.groups.clear()
    administrator.clear_roles_cache()
    response = api_as(administrator).post(
        SAVE, {"doctype": "FCRM Settings", "type": "Quick Entry", "layout": "[]"}, format="json"
    )
    assert response.status_code == 403


def test_pe18_save_refuses_a_non_fieldname_entry(api_as, manager):
    layout = json.dumps([{"columns": [{"fields": [{"fieldname": "x"}]}]}])
    response = api_as(manager).post(
        SAVE, {"doctype": "FCRM Settings", "type": "Quick Entry", "layout": layout}, format="json"
    )
    assert response.status_code == 417
    assert response.json()["message"] == "A layout's field lists hold fieldnames only"


def test_pe12c_save_refuses_invalid_json(api_as, manager):
    response = api_as(manager).post(
        SAVE, {"doctype": "FCRM Settings", "type": "Quick Entry", "layout": "[oops"}, format="json"
    )
    assert response.status_code == 417
    assert not CRMFieldsLayout.objects.exists()


def test_save_refuses_an_unknown_doctype(api_as, manager):
    response = api_as(manager).post(
        SAVE, {"doctype": "No Such Doctype", "type": "Quick Entry", "layout": "[]"}, format="json"
    )
    assert response.status_code == 404
