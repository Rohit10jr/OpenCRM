"""CRM Fields Layout, CRM Form Script and CRM Global Settings as resources
(specs/CONFIGURATION.md 4.6; temp A-37).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_phase4_metadata.py:830-896`` (who
writes a form script and a layout; `:880` rewritten for PE-17: a Sales Manager is
refused), ``test_crm_behaviour.py:270`` (the five layout types),
``test_permissions.py:778`` and ``test_route_surface.py:77`` (the three rules). The old
`/api/resource/` routes are `/api/v1/fields-layouts/`, `form-scripts/`,
`global-settings/`; a resource create answers 200 under `message`. The rest is new.
"""

import json

import pytest

from configuration.form_scripts import get_form_script
from configuration.models import (
    LAYOUT_TYPES,
    CRMFieldsLayout,
    CRMFormScript,
    CRMGlobalSettings,
)

pytestmark = pytest.mark.django_db

LAYOUTS = "/api/v1/fields-layouts/"
SCRIPTS = "/api/v1/form-scripts/"
GLOBAL = "/api/v1/global-settings/"


@pytest.fixture
def manager(make_user):
    return make_user("mgr@example.com", roles=["Sales Manager"])


@pytest.fixture
def sysman(make_user):
    return make_user("sysman@example.com", roles=["System Manager"])


def make_script(administrator, name="ok", dt="CRM Lead", **fields):
    script = CRMFormScript(name=name, dt=dt, view="Form", enabled=True, script="run()", **fields)
    script.save(user=administrator)
    return script


# --- ported ------------------------------------------------------------------------------


def test_fields_layout_types_match_the_source():
    assert list(LAYOUT_TYPES) == [
        "Quick Entry",
        "Side Panel",
        "Data Fields",
        "Grid Row",
        "Required Fields",
    ]


def test_a_sales_user_cannot_create_a_form_script(auth_api):
    response = auth_api.post(
        SCRIPTS,
        {"name": "new", "dt": "CRM Lead", "view": "Form", "script": "run()", "enabled": True},
        format="json",
    )
    assert response.status_code == 403
    assert not CRMFormScript.objects.filter(pk="new").exists()


def test_a_sales_user_cannot_edit_an_existing_form_script(auth_api, administrator):
    make_script(administrator)
    response = auth_api.patch(f"{SCRIPTS}ok/", {"script": "other()"}, format="json")
    assert response.status_code == 403
    assert CRMFormScript.objects.get(pk="ok").script == "run()"


def test_a_sales_user_can_still_read_a_form_script(auth_api, administrator):
    make_script(administrator, name="readable")
    assert auth_api.get(f"{SCRIPTS}readable/").status_code == 200


def test_a_sales_manager_cannot_write_a_form_script(api_as, manager):
    """`:880` rewritten for PE-17: System Manager or Administrator only."""
    response = api_as(manager).post(
        SCRIPTS, {"name": "fine", "dt": "CRM Lead", "view": "Form", "script": "ok()"}, format="json"
    )
    assert response.status_code == 403
    assert not CRMFormScript.objects.filter(pk="fine").exists()


def test_a_sales_manager_cannot_change_or_delete_a_form_script(api_as, manager, administrator):
    """PE-17 on the other two writes."""
    make_script(administrator)
    client = api_as(manager)
    assert client.patch(f"{SCRIPTS}ok/", {"script": "other()"}, format="json").status_code == 403
    assert client.delete(f"{SCRIPTS}ok/").status_code == 403
    assert CRMFormScript.objects.get(pk="ok").script == "run()"


def test_pe12c_a_layout_nested_too_deep_is_refused_by_the_resource(api_as, manager):
    deep = "[" * 2000 + "]" * 2000
    response = api_as(manager).post(
        LAYOUTS, {"dt": "CRM Lead", "type": "Quick Entry", "layout": deep}, format="json"
    )
    assert response.status_code == 417
    assert response.json()["message"] == "Layout must be valid JSON"


def test_a_sales_user_cannot_write_a_fields_layout(auth_api):
    response = auth_api.post(
        LAYOUTS, {"dt": "CRM Lead", "type": "Quick Entry", "layout": "[]"}, format="json"
    )
    assert response.status_code == 403


def test_global_settings_are_open_to_every_role(auth_api):
    response = auth_api.post(
        GLOBAL, {"dt": "CRM Lead", "type": "Quick Filters", "json": ["status"]}, format="json"
    )
    assert response.status_code == 200, response.content[:300]


# --- new: the rules (spec section 4.6) ---------------------------------------------------


def test_a_system_manager_writes_a_form_script(api_as, sysman):
    response = api_as(sysman).post(
        SCRIPTS, {"name": "mine", "dt": "CRM Lead", "view": "Form", "script": "ok()"}, format="json"
    )
    assert response.status_code == 200, response.content[:300]


def test_administrator_writes_a_form_script_without_its_groups(api_as, administrator):
    administrator.groups.clear()
    administrator.clear_roles_cache()
    response = api_as(administrator).post(
        SCRIPTS, {"name": "admin", "dt": "CRM Lead", "view": "Form", "script": "ok()"}, format="json"
    )
    assert response.status_code == 200, response.content[:300]


def test_a_sales_manager_writes_a_fields_layout(api_as, manager):
    response = api_as(manager).post(
        LAYOUTS, {"dt": "CRM Task", "type": "Side Panel", "layout": "[]"}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"]["name"] == "CRM Task-Side Panel"


def test_everyone_reads_a_fields_layout(auth_api, administrator):
    CRMFieldsLayout(dt="CRM Task", type="Data Fields", layout="[]").save(user=administrator)
    assert auth_api.get(f"{LAYOUTS}CRM Task-Data Fields/").status_code == 200


# --- PE-18 and PE-12c on the resource ----------------------------------------------------


def test_pe18_a_layout_field_list_holds_fieldnames_only(api_as, manager):
    layout = [{"name": "s", "columns": [{"name": "c", "fields": ["status", {"fieldname": "x"}]}]}]
    response = api_as(manager).post(
        LAYOUTS, {"dt": "CRM Task", "type": "Side Panel", "layout": json.dumps(layout)}, format="json"
    )
    assert response.status_code == 417
    assert response.json()["message"] == "A layout's field lists hold fieldnames only"
    assert CRMFieldsLayout.objects.count() == 14  # only the defaults


def test_pe18_a_patch_is_checked_too(api_as, manager, administrator):
    CRMFieldsLayout(dt="CRM Task", type="Side Panel", layout="[]").save(user=administrator)
    bad = json.dumps([{"columns": [{"fields": [1]}]}])
    response = api_as(manager).patch(f"{LAYOUTS}CRM Task-Side Panel/", {"layout": bad}, format="json")
    assert response.status_code == 417


def test_pe12c_a_layout_that_is_not_json_is_refused(api_as, manager):
    response = api_as(manager).post(
        LAYOUTS, {"dt": "CRM Lead", "type": "Quick Entry", "layout": "[not json"}, format="json"
    )
    assert response.status_code == 417
    assert response.json()["message"] == "Layout must be valid JSON"


# --- get_form_script, an internal helper ------------------------------------------------


def test_get_form_script_shapes(administrator):
    # CRM Task: the standard scripts are CRM Lead's and CRM Deal's (CONFIGURATION §10.6).
    assert get_form_script("CRM Task") is None
    make_script(administrator, name="a", dt="CRM Task")
    assert get_form_script("CRM Task") == "run()"
    make_script(administrator, name="b", dt="CRM Task")
    CRMFormScript.objects.filter(pk="b").update(script="second()")
    assert get_form_script("CRM Task") == ["run()", "second()"]


def test_get_form_script_skips_disabled_and_other_views(administrator):
    make_script(administrator, name="a", dt="CRM Task")
    CRMFormScript.objects.filter(pk="a").update(enabled=False)
    make_script(administrator, name="b", dt="CRM Task")
    CRMFormScript.objects.filter(pk="b").update(view="List")
    assert get_form_script("CRM Task") is None
    assert get_form_script("CRM Task", "List") == "run()"


def test_global_settings_rows_hold_a_json_list(auth_api):
    auth_api.post(GLOBAL, {"dt": "CRM Lead", "type": "Quick Filters", "json": ["status"]}, format="json")
    # The defaults' CRM Lead row holds another list (CONFIGURATION §10.6).
    assert CRMGlobalSettings.objects.get(dt="CRM Lead", type="Quick Filters", json=["status"])
