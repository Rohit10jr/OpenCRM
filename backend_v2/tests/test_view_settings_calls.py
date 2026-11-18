"""The saved-view calls that answer a view: create, update, delete and the standard view
(specs/CONFIGURATION.md 4.7; temp A-39).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_phase4_metadata.py``: `:213` (one
standard view per user and type), `:573` (only the owner updates a private view),
`:584` (a Sales Manager updates a public view; the view is made public with the model,
the `public` call being CF7c's), `:689` (delete needs the write rule), `:699` (route
names). `CRM Lead` is stored text there and here: no view call checks the doctype.
`:562` waits for SALES (CRM Lead's default rows). New: the routes, the seam to
milestone 8, the kanban default columns, PE-12d.
"""

import json

import pytest

from configuration.models import CRMViewSettings
from configuration.view_settings import (
    create_or_update_standard_view,
    get_route_name,
    kanban_link_columns,
)

pytestmark = pytest.mark.django_db

CREATE = "/api/v1/view-settings/create-view/"
UPDATE = "/api/v1/view-settings/update-view/"
STANDARD = "/api/v1/view-settings/standard-view/"


def delete_url(name):
    return f"/api/v1/view-settings/{name}/delete-view/"


@pytest.fixture
def manager(make_user):
    return make_user("mgr@example.com", roles=["Sales Manager"])


def make_standard_view(user, columns, rows, view_type="list", doctype="CRM Lead"):
    return create_or_update_standard_view(
        {"doctype": doctype, "type": view_type, "columns": columns, "rows": rows}, user=user
    )


def create(client, **view):
    view.setdefault("doctype", "CRM Lead")
    view.setdefault("type", "list")
    response = client.post(CREATE, {"view": view}, format="json")
    assert response.status_code == 200, response.json()
    return response.json()["message"]


# --- ported ------------------------------------------------------------------------------


def test_saved_view_persists_per_user_and_type(alice, bob):
    make_standard_view(alice, [{"key": "email", "label": "Email"}], ["name", "email"])
    make_standard_view(bob, [{"key": "status", "label": "Status"}], ["name", "status"])
    assert CRMViewSettings.objects.filter(dt="CRM Lead", is_standard=True).count() == 2
    assert CRMViewSettings.objects.filter(user=alice).count() == 1


def test_only_the_owner_can_update_a_private_view(alice, bob, api_as):
    view = create(api_as(alice), label="Mine")
    response = api_as(bob).post(
        UPDATE, {"view": {"name": view["name"], "doctype": "CRM Lead", "label": "Stolen"}}, format="json"
    )
    assert response.status_code == 403
    assert response.json()["message"] == "Not permitted"
    assert CRMViewSettings.objects.get(pk=view["name"]).label == "Mine"


def test_a_sales_manager_can_edit_a_public_view(alice, manager, api_as):
    view = create(api_as(alice), label="Shared")
    CRMViewSettings.objects.filter(pk=view["name"]).update(public=True, user=None)
    response = api_as(manager).post(
        UPDATE, {"view": {"name": view["name"], "doctype": "CRM Lead", "label": "Renamed"}}, format="json"
    )
    assert response.status_code == 200
    assert CRMViewSettings.objects.get(pk=view["name"]).label == "Renamed"


def test_delete_requires_permission(alice, bob, api_as):
    view = create(api_as(alice), label="Mine")
    response = api_as(bob).post(delete_url(view["name"]))
    assert response.status_code == 403
    assert CRMViewSettings.objects.filter(pk=view["name"]).exists()


def test_route_name_derivation():
    assert get_route_name("CRM Lead") == "Leads"
    assert get_route_name("CRM Deal") == "Deals"
    assert get_route_name("Contact") == "Contacts"


# --- new: create and update --------------------------------------------------------------


def test_create_answers_the_view_the_caller_owns(alice, auth_api):
    view = create(auth_api, label="Mine", rows=["dt"])
    assert view["user"] == alice.name
    assert isinstance(view["name"], int)
    assert view["route_name"] == "Leads"
    assert (view["public"], view["pinned"], view["is_standard"], view["is_default"]) == (
        False,
        False,
        False,
        False,
    )


def test_create_merges_the_served_doctypes_default_rows_and_columns(auth_api):
    view = create(auth_api, doctype="CRM Fields Layout", label="L", rows=["dt", "name"])
    assert json.loads(view["rows"]) == ["dt", "name"]
    assert [c["key"] for c in json.loads(view["columns"])] == ["name", "modified"]


def test_an_unknown_doctype_gets_no_defaults(auth_api):
    view = create(auth_api, doctype="No Such Doctype", label="L", rows=["a"])
    assert (json.loads(view["rows"]), json.loads(view["columns"])) == (["a"], [])
    assert view["route_name"] == "No Such Doctypes"


def test_update_keeps_an_empty_label_and_resets_what_it_omits(alice, auth_api):
    view = create(auth_api, label="Mine", icon="star", order_by="name asc")
    response = auth_api.post(UPDATE, {"view": {"name": view["name"], "label": ""}}, format="json")
    assert response.status_code == 200
    updated = response.json()["message"]
    assert (updated["label"], updated["icon"], updated["order_by"]) == ("Mine", "", "")
    assert updated["dt"] == "CRM Lead"


def test_update_never_changes_the_owner_or_flags(alice, bob, auth_api):
    view = create(auth_api, label="Mine")
    auth_api.post(
        UPDATE,
        {"view": {"name": view["name"], "user": bob.name, "public": 1, "is_default": 1, "pinned": 1}},
        format="json",
    )
    row = CRMViewSettings.objects.get(pk=view["name"])
    assert (row.user_id, row.public, row.is_default, row.pinned) == (alice.name, False, False, False)


@pytest.mark.parametrize("name", [999999, "abc"])
def test_update_of_a_missing_view_is_404(auth_api, name):
    response = auth_api.post(UPDATE, {"view": {"name": name, "label": "x"}}, format="json")
    assert response.status_code == 404
    assert response.json()["message"] == f"CRM View Settings {name} not found"


@pytest.mark.parametrize("url", [CREATE, STANDARD])
def test_pe12d_no_doctype_is_417(auth_api, url):
    response = auth_api.post(url, {"view": {"label": "x"}}, format="json")
    assert response.status_code == 417
    assert response.json()["message"] == "DocType is required"
    assert not CRMViewSettings.objects.exists()


# --- new: delete -------------------------------------------------------------------------


@pytest.mark.parametrize("name", [999999, "abc"])
def test_delete_of_a_missing_view_answers_null(auth_api, name):
    response = auth_api.post(delete_url(name))
    assert response.status_code == 200
    assert response.json() == {"message": None}


def test_the_owner_deletes_their_view(auth_api):
    view = create(auth_api, label="Mine")
    assert auth_api.post(delete_url(view["name"])).json() == {"message": None}
    assert not CRMViewSettings.objects.filter(pk=view["name"]).exists()


# --- new: the standard view --------------------------------------------------------------


@pytest.mark.parametrize(
    ("view_type", "label"), [("list", "List"), ("group_by", "Group By"), ("kanban", "Kanban")]
)
def test_the_standard_view_is_created_with_its_defaults(alice, auth_api, view_type, label):
    response = auth_api.post(STANDARD, {"view": {"doctype": "CRM Lead", "type": view_type}}, format="json")
    assert response.status_code == 200
    view = response.json()["message"]
    assert (view["label"], view["is_standard"], view["user"]) == (label, True, alice.name)
    assert (view["order_by"], view["group_by_field"], view["column_field"]) == (
        "modified desc",
        "owner",
        "status",
    )


def test_the_standard_view_is_updated_in_place(alice, auth_api):
    first = make_standard_view(alice, [{"key": "a"}], ["a"])
    second = make_standard_view(alice, [{"key": "b"}], ["b"])
    assert first["name"] == second["name"]
    assert json.loads(CRMViewSettings.objects.get(pk=first["name"]).columns) == [{"key": "b"}]


def test_the_standard_view_sets_is_default_without_clearing_other_defaults(alice, auth_api):
    """Parity (A-39): only `set_as_default` clears the caller's other defaults."""
    other = create(auth_api, label="Other")
    CRMViewSettings.objects.filter(pk=other["name"]).update(is_default=True)
    response = auth_api.post(
        STANDARD, {"view": {"doctype": "CRM Lead", "type": "list", "is_default": 1}}, format="json"
    )
    assert response.json()["message"]["is_default"] is True
    assert CRMViewSettings.objects.get(pk=other["name"]).is_default is True


# --- new: kanban default columns ---------------------------------------------------------


def test_a_kanban_on_a_select_field_gets_its_options(auth_api):
    view = create(auth_api, doctype="CRM Fields Layout", type="kanban", column_field="type", label="K")
    assert [c["name"] for c in json.loads(view["kanban_columns"])] == [
        "Quick Entry",
        "Side Panel",
        "Data Fields",
        "Grid Row",
        "Required Fields",
    ]


def test_a_kanban_on_a_link_field_gets_the_rows_the_caller_may_list(alice, bob, administrator):
    names = [c["name"] for c in kanban_link_columns("User", alice)]
    assert {alice.name, bob.name} <= set(names)
    assert "Administrator" not in names
    assert "Administrator" in [c["name"] for c in kanban_link_columns("User", administrator)]


def test_a_kanban_link_target_with_no_rules_gives_no_columns(alice):
    assert kanban_link_columns("DocType", alice) == []
    assert kanban_link_columns("No Such Doctype", alice) == []
