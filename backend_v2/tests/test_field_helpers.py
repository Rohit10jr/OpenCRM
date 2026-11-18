"""The four field helpers (specs/CONFIGURATION.md 4.5; temp A-35).

Ported (REBUILD_PLAN S14): ``backend/tests/test_bulk_edit_fields.py:61`` (an unknown
doctype is 404; its CRM Task cases are ACTIVITIES'), and from
``backend/tests/test_phase4_metadata.py`` the allowlist constants (`:94`, `:103`) and the
non-filterable case on a test model (`:152`), rewritten for `configuration`. The rest is
new: the in-unit shapes on FCRM Settings, PE-14, PE-15, PE-16, and existence following
the route map.
"""

import pytest

from configuration import field_helpers, metadata
from core.resources import clear_rules_cache

pytestmark = pytest.mark.django_db

ROUTES = {
    "fields": "/api/v1/meta/fields/",
    "sort": "/api/v1/meta/sort-options/",
    "filterable": "/api/v1/meta/filterable-fields/",
    "group_by": "/api/v1/meta/group-by-fields/",
}


def call(client, route, doctype, **params):
    return client.get(ROUTES[route], {"doctype": doctype, **params})


def fieldnames(rows):
    return [row["fieldname"] for row in rows]


# --- ported ------------------------------------------------------------------------------


def test_an_unknown_doctype_is_a_404(auth_api):
    response = call(auth_api, "fields", "Nonsense")
    assert response.status_code == 404


def test_filterable_allowlist_matches_the_source_exactly():
    assert field_helpers.FILTERABLE_FIELDTYPES == {
        "Check", "Data", "Float", "Int", "Currency", "Dynamic Link", "Link",
        "Long Text", "Select", "Small Text", "Text Editor", "Text", "Duration",
        "Rating", "Date", "Datetime",
    }


def test_group_by_allowlist_matches_the_source_exactly():
    assert field_helpers.GROUP_BY_FIELDTYPES == {
        "Check", "Data", "Float", "Int", "Currency", "Dynamic Link", "Link",
        "Select", "Duration", "Date", "Datetime",
    }


def test_get_non_filterable_fields_is_honoured(administrator):
    """The helpers read the model's declarations only, so a plain class stands in for a
    model that declares the staticmethod (no model is registered by this test)."""

    class NotesHidden:
        @staticmethod
        def get_non_filterable_fields():
            return ["widget_name"]

    filterable = fieldnames(
        field_helpers.get_filterable_fields("Foundation Widget", NotesHidden, administrator)
    )
    group_by = fieldnames(
        field_helpers.get_group_by_fields("Foundation Widget", NotesHidden, administrator)
    )
    assert "widget_name" not in filterable and "widget_name" not in group_by


# --- new: the shapes, on this unit's own doctypes ----------------------------------------


def test_sort_options_repeats_the_standard_fields_as_backend_does(auth_api):
    rows = call(auth_api, "sort", "FCRM Settings").json()["message"]
    names = fieldnames(rows)
    for standard in ("name", "creation", "modified", "modified_by", "owner"):
        assert names.count(standard) == 2, standard
    assert rows[-1] == {"label": "Owner", "fieldname": "owner", "value": "owner"}


def test_filterable_fields_start_with_the_nine_standard_ones(auth_api):
    rows = call(auth_api, "filterable", "FCRM Settings").json()["message"]
    assert fieldnames(rows)[:9] == [
        "name", "owner", "modified_by", "_user_tags", "_liked_by", "_comments", "_assign",
        "creation", "modified",
    ]
    assert all("options" in row for row in rows[9:])


def test_group_by_fields_end_with_the_standard_ones_without_duplicates(auth_api):
    rows = call(auth_api, "group_by", "FCRM Settings").json()["message"]
    names = fieldnames(rows)
    assert len(names) == len(set(names))
    assert names[-8:] == [
        "name", "creation", "modified", "modified_by", "owner", "_liked_by", "_assign",
        "_comments",
    ]


def test_get_fields_drops_layout_rows_unless_all_are_asked_for(auth_api):
    default = call(auth_api, "fields", "FCRM Settings").json()["message"]
    everything = call(auth_api, "fields", "FCRM Settings", allow_all_fieldtypes=1).json()["message"]
    assert not {"Tab Break", "Section Break", "Column Break"} & {f["fieldtype"] for f in default}
    assert {f["fieldtype"] for f in everything} & {"Tab Break", "Section Break", "Column Break"}
    for key in ("options", "description", "default", "hidden", "read_only", "reqd"):
        assert key in default[0], key


# --- the exceptions ----------------------------------------------------------------------


@pytest.mark.parametrize("route", list(ROUTES))
def test_pe15_a_child_table_is_not_found_by_the_helpers(auth_api, route):
    response = call(auth_api, route, "CRM Dropdown Item")
    assert response.status_code == 404
    assert response.json()["message"] == "DocType CRM Dropdown Item not found"


@pytest.mark.parametrize("route", list(ROUTES))
def test_pe14_a_withheld_doctype_is_not_found_by_the_helpers(auth_api, route):
    assert call(auth_api, route, "Version").status_code == 404


@pytest.mark.parametrize("route", list(ROUTES))
def test_pe16_a_restricted_field_is_offered_to_a_manager_only(auth_api, api_as, make_user, route):
    manager = make_user("mgr@example.com", roles=["Sales Manager"])
    assert "access_key" not in fieldnames(call(auth_api, route, "FCRM Settings").json()["message"])
    assert "access_key" in fieldnames(call(api_as(manager), route, "FCRM Settings").json()["message"])


@pytest.mark.parametrize("route", list(ROUTES))
def test_pe16_a_sensitive_field_is_offered_to_nobody(api_as, administrator, route):
    rows = call(api_as(administrator), route, "Email Account").json()["message"]
    assert not {"password", "api_secret"} & set(fieldnames(rows))


@pytest.mark.parametrize("route", list(ROUTES))
def test_the_helpers_need_a_session(api, route):
    assert call(api, route, "FCRM Settings").status_code == 401


def test_a_childs_existence_follows_the_route_map(monkeypatch):
    """No cache of its own (the supervisor's note on f6e6822): after the route map is
    cleared, a child whose parent is no longer routed does not exist."""
    from config import urls as production_urls

    assert metadata.served_model("CRM Dropdown Item") is not None
    monkeypatch.setattr(production_urls, "urlpatterns", [])
    clear_rules_cache()
    try:
        assert metadata.served_model("CRM Dropdown Item") is None
    finally:
        monkeypatch.undo()
        clear_rules_cache()
    assert metadata.served_model("CRM Dropdown Item") is not None
