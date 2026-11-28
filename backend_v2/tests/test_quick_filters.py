"""Quick filters (specs/CONFIGURATION.md 4.6; temp A-37).

`get_quick_filters` and `update_quick_filters` are `GET /api/v1/meta/quick-filters/` and
`POST /api/v1/meta/quick-filters/update/`. Ported (S14) from
``backend/tests/test_phase3_endpoints.py:1054-1115``: the fallback table against the
upstream JSONs, a write read back, the blank Select option. The old cases name CRM Deal,
CRM Lead and CRM Call Log, which wait for SALES and TELEPHONY; these run on CRM Fields
Layout and FCRM Settings. New: the doctype checked (PE-14, PE-15), fields the caller
may not read left out (PE-16), a stored entry that is not a string skipped (PE-12c).
"""

import json

import pytest

from configuration.models import CRMGlobalSettings
from configuration.quick_filters import QUICK_FILTER_FALLBACK
from tests.upstream_source import CRM_DOCTYPE_DIR

GET = "/api/v1/meta/quick-filters/"
UPDATE = "/api/v1/meta/quick-filters/update/"


@pytest.fixture
def manager(make_user):
    return make_user("mgr@example.com", roles=["Sales Manager"])


def names(response) -> list[str]:
    return [f["fieldname"] for f in response.json()["message"]]


def store(administrator, dt, selected, name=None):
    row = CRMGlobalSettings(dt=dt, type="Quick Filters", json=selected)
    if name:
        row.name = name
    row.save(user=administrator)
    return row


# --- ported ------------------------------------------------------------------------------


def test_the_fallback_table_matches_the_upstream_json():
    if not CRM_DOCTYPE_DIR.exists():
        pytest.skip("CRM source not available")
    expected: dict[str, list[str]] = {}
    for directory in sorted(CRM_DOCTYPE_DIR.iterdir()):
        path = directory / f"{directory.name}.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        fields = [f["fieldname"] for f in doc.get("fields", []) if f.get("in_standard_filter")]
        if fields:
            expected[doc["name"]] = fields
    assert QUICK_FILTER_FALLBACK == expected


@pytest.mark.django_db
def test_quick_filters_fall_back_to_the_standard_filter_fields(auth_api):
    response = auth_api.get(GET, {"doctype": "CRM Fields Layout"})
    assert response.status_code == 200
    assert names(response) == ["dt", "type"]


@pytest.mark.django_db
def test_select_quick_filters_get_a_blank_option(auth_api):
    options = auth_api.get(GET, {"doctype": "CRM Fields Layout"}).json()["message"][1]["options"]
    assert options[0] == {"label": "", "value": ""}
    assert options[1] == {"label": "Quick Entry", "value": "Quick Entry"}


@pytest.mark.django_db
def test_update_quick_filters_is_read_back_by_get_quick_filters(auth_api):
    response = auth_api.post(
        UPDATE, {"quick_filters": ["type"], "old_filters": [], "doctype": "CRM Fields Layout"}, format="json"
    )
    assert response.status_code == 200
    assert response.json() == {"message": None}
    assert names(auth_api.get(GET, {"doctype": "CRM Fields Layout"})) == ["type"]


# --- new ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_update_takes_json_strings_and_rewrites_the_one_row(auth_api):
    for selected in (["dt"], ["name", "type"]):
        auth_api.post(
            UPDATE,
            {"quick_filters": json.dumps(selected), "old_filters": "[]", "doctype": "CRM Fields Layout"},
            format="json",
        )
    # The six defaults and the one row for CRM Fields Layout (CONFIGURATION §10.6).
    assert CRMGlobalSettings.objects.count() == 7
    first = auth_api.get(GET, {"doctype": "CRM Fields Layout", "cached": 0}).json()["message"][0]
    assert first == {"label": "Name", "fieldname": "name", "fieldtype": "Data", "options": None}


@pytest.mark.django_db
def test_the_first_row_by_name_wins(auth_api, administrator):
    store(administrator, "CRM Fields Layout", ["type"], name="b-row")
    store(administrator, "CRM Fields Layout", ["dt"], name="a-row")
    assert names(auth_api.get(GET, {"doctype": "CRM Fields Layout"})) == ["dt"]


@pytest.mark.django_db
def test_pe12c_a_stored_entry_that_is_not_a_string_is_skipped(auth_api, administrator):
    store(administrator, "CRM Fields Layout", ["dt", 5, {"fieldname": "type"}, ["type"], "no_such"])
    response = auth_api.get(GET, {"doctype": "CRM Fields Layout"})
    assert response.status_code == 200
    assert names(response) == ["dt"]


@pytest.mark.django_db
def test_a_stored_json_string_is_parsed(auth_api, administrator):
    """Old `doc.py:171-172`: a resource PATCH can store the list as a string."""
    store(administrator, "CRM Fields Layout", '["type", "dt"]')
    assert names(auth_api.get(GET, {"doctype": "CRM Fields Layout"})) == ["type", "dt"]


@pytest.mark.django_db
@pytest.mark.parametrize("stored", ["[not json", '{"dt": 1}', ""])
def test_pe12c_a_stored_string_that_is_not_a_list_counts_as_no_entries(auth_api, administrator, stored):
    store(administrator, "CRM Fields Layout", stored)
    response = auth_api.get(GET, {"doctype": "CRM Fields Layout"})
    assert response.status_code == 200
    assert response.json() == {"message": []}


@pytest.mark.django_db
def test_pe12c_a_stored_dict_counts_as_no_entries(auth_api, administrator):
    """`backend/` reads a dict's keys as fieldnames (`doc.py:170-177`); v2 answers []."""
    store(administrator, "CRM Fields Layout", {"dt": 1, "type": 2})
    assert auth_api.get(GET, {"doctype": "CRM Fields Layout"}).json() == {"message": []}


@pytest.mark.django_db
def test_pe16_a_restricted_field_is_left_out_for_a_non_manager(auth_api, api_as, manager, administrator):
    store(administrator, "FCRM Settings", ["brand_name", "access_key"])
    assert names(auth_api.get(GET, {"doctype": "FCRM Settings"})) == ["brand_name"]
    assert names(api_as(manager).get(GET, {"doctype": "FCRM Settings"})) == ["brand_name", "access_key"]


@pytest.mark.django_db
@pytest.mark.parametrize("doctype", ["No Such Doctype", "Version", "CRM Dropdown Item"])
def test_pe14_pe15_an_unknown_withheld_or_child_doctype_is_not_found(auth_api, doctype):
    assert auth_api.get(GET, {"doctype": doctype}).status_code == 404
    response = auth_api.post(
        UPDATE, {"quick_filters": ["x"], "old_filters": [], "doctype": doctype}, format="json"
    )
    assert response.status_code == 404
    assert response.json()["message"] == f"DocType {doctype} not found"
    assert CRMGlobalSettings.objects.count() == 6  # the defaults only (CONFIGURATION §10.6)
