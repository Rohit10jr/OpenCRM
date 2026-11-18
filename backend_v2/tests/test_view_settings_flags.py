"""The saved-view flag calls: pin, public, set_as_default and the kanban column refresh
(specs/CONFIGURATION.md 4.7; temp A-39).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_phase4_metadata.py``: `:599`
(publishing clears the owner and the pin; rewritten for PE-20: the view is made
ownerless first, so the manager may read it), `:616` (public needs Sales Manager), `:626`
and `:640` (one default per user, nobody else's touched), `:681` (a list view has no
kanban columns), and `:654` twinned: CRM Deal Status waits for SALES, so the board here
is grouped by a Link to User and the new column is a new user. New: PE-20, PE-21, how
`value` is read, and two parity facts.
"""

import json

import pytest

from configuration.models import CRMViewSettings
from configuration.view_settings import create_view

pytestmark = pytest.mark.django_db

DEFAULT = "/api/v1/view-settings/set-as-default/"


def url(name, action):
    return f"/api/v1/view-settings/{name}/{action}/"


@pytest.fixture
def manager(make_user):
    return make_user("mgr@example.com", roles=["Sales Manager"])


@pytest.fixture
def sysman(make_user):
    return make_user("sysman@example.com", roles=["System Manager"])


def make(user, **view):
    view.setdefault("doctype", "CRM Lead")
    view.setdefault("type", "list")
    view.setdefault("label", "V")
    return create_view(view, user=user)["name"]


def row(name):
    return CRMViewSettings.objects.get(pk=name)


# --- ported ------------------------------------------------------------------------------


def test_making_a_view_public_clears_its_owner_and_pin(alice, manager, api_as):
    name = make(alice)
    assert api_as(alice).post(url(name, "pin"), {"value": True}, format="json").status_code == 200
    CRMViewSettings.objects.filter(pk=name).update(user=None)  # readable by the manager
    assert api_as(manager).post(url(name, "public"), {"value": True}, format="json").status_code == 200
    view = row(name)
    assert (view.public, view.pinned, view.user_id) == (True, False, None)


def test_public_requires_sales_manager(alice, api_as):
    name = make(alice)
    response = api_as(alice).post(url(name, "public"), {"value": True}, format="json")
    assert response.status_code == 403
    assert response.json()["message"] == "Not permitted"


def test_set_as_default_clears_the_previous_default(alice, auth_api):
    first, second = make(alice, label="A"), make(alice, label="B")
    auth_api.post(DEFAULT, {"name": first}, format="json")
    auth_api.post(DEFAULT, {"name": second}, format="json")
    assert (row(first).is_default, row(second).is_default) == (False, True)


def test_set_as_default_does_not_touch_another_users_default(alice, bob, api_as):
    theirs = make(bob, label="Theirs")
    api_as(bob).post(DEFAULT, {"name": theirs}, format="json")
    mine = make(alice, label="Mine")
    api_as(alice).post(DEFAULT, {"name": mine}, format="json")
    assert row(theirs).is_default is True


def test_fetch_and_update_kanban_columns_marks_new_ones_deleted(alice, make_user, auth_api):
    name = make(alice, doctype="CRM View Settings", type="kanban", column_field="user")
    newcomer = make_user("newcomer@example.com", roles=["Sales User"])
    response = auth_api.post(url(name, "kanban-columns"))
    assert response.status_code == 200
    columns = {c["name"]: c for c in json.loads(response.json()["message"])}
    assert columns[alice.name].get("delete") is None
    assert columns[newcomer.name]["delete"] is True
    assert json.loads(row(name).kanban_columns) == list(columns.values())


def test_fetch_and_update_kanban_columns_ignores_a_list_view(alice, auth_api):
    name = make(alice)
    assert auth_api.post(url(name, "kanban-columns")).json() == {"message": None}


# --- new: public (PE-20) -----------------------------------------------------------------


def test_public_is_not_granted_to_system_manager(alice, sysman, api_as):
    """Parity: Administrator or Sales Manager only (`view_settings.py:216`)."""
    name = make(alice)
    assert api_as(sysman).post(url(name, "public"), {"value": True}, format="json").status_code == 403


def test_public_checks_the_role_before_the_view(auth_api):
    assert auth_api.post(url(999999, "public"), {"value": True}, format="json").status_code == 403


def test_public_on_a_missing_view_is_404(manager, api_as):
    response = api_as(manager).post(url(999999, "public"), {"value": True}, format="json")
    assert response.status_code == 404
    assert response.json()["message"] == "CRM View Settings 999999 not found"


def test_pe20_public_acts_on_a_view_the_caller_may_read(alice, manager, api_as):
    name = make(alice)
    response = api_as(manager).post(url(name, "public"), {"value": True}, format="json")
    assert response.status_code == 403
    assert response.json()["message"] == "Not permitted"
    assert (row(name).public, row(name).user_id) == (False, alice.name)


def test_unpublishing_gives_the_view_to_the_caller(alice, manager, api_as):
    name = make(alice)
    CRMViewSettings.objects.filter(pk=name).update(public=True, user=None)
    api_as(manager).post(url(name, "public"), {"value": False}, format="json")
    assert (row(name).public, row(name).user_id) == (False, manager.name)


# --- new: pin ----------------------------------------------------------------------------


def test_pin_needs_the_write_rule(alice, bob, api_as):
    name = make(alice)
    assert api_as(bob).post(url(name, "pin"), {"value": True}, format="json").status_code == 403
    assert api_as(bob).post(url("abc", "pin"), {"value": True}, format="json").status_code == 404


def test_a_sales_manager_pinning_a_public_view_pins_it_for_everyone(alice, manager, api_as):
    """Parity (A-39): `pinned` is the view's, not the caller's."""
    name = make(alice)
    CRMViewSettings.objects.filter(pk=name).update(public=True, user=None)
    api_as(manager).post(url(name, "pin"), {"value": True}, format="json")
    assert row(name).pinned is True


@pytest.mark.parametrize(
    ("body", "query", "pinned"),
    [
        ({"value": True}, "", True),
        ({"value": False}, "", False),
        ({"value": 0}, "", False),
        ({"value": "0"}, "", True),
        ({"value": "false"}, "", True),
        ({}, "?value=0", False),
        ({}, "?value=false", False),
        ({}, "?value=1", True),
    ],
)
def test_value_is_read_as_backend_reads_it(alice, auth_api, body, query, pinned):
    """`bool(value)` on the raw payload; a query value is parsed as JSON first."""
    name = make(alice)
    CRMViewSettings.objects.filter(pk=name).update(pinned=not pinned)
    auth_api.post(url(name, "pin") + query, body, format="json")
    assert row(name).pinned is pinned


# --- new: set_as_default (PE-21) ---------------------------------------------------------


def test_pe21_set_as_default_with_a_name_acts_on_the_callers_own_view(alice, bob, api_as):
    theirs = make(bob)
    response = api_as(alice).post(DEFAULT, {"name": theirs}, format="json")
    assert response.status_code == 403
    assert response.json()["message"] == "Not permitted"
    assert row(theirs).is_default is False


def test_pe21_a_public_view_is_not_the_callers_own(alice, api_as):
    name = make(alice)
    CRMViewSettings.objects.filter(pk=name).update(public=True, user=None)
    assert api_as(alice).post(DEFAULT, {"name": name}, format="json").status_code == 403


@pytest.mark.parametrize("name", [999999, "abc"])
def test_set_as_default_of_a_missing_view_is_404(auth_api, name):
    response = auth_api.post(DEFAULT, {"name": name}, format="json")
    assert response.status_code == 404
    assert response.json()["message"] == f"CRM View Settings {name} not found"


def test_set_as_default_without_a_name_makes_the_standard_view_default(alice, auth_api):
    other = make(alice)
    CRMViewSettings.objects.filter(pk=other).update(is_default=True)
    response = auth_api.post(DEFAULT, {"doctype": "CRM Lead", "type": "kanban"}, format="json")
    assert response.json() == {"message": None}
    standard = CRMViewSettings.objects.get(user=alice, is_standard=True, type="kanban")
    assert (standard.is_default, row(other).is_default) == (True, False)


# --- new: the kanban refresh (PE-21) -----------------------------------------------------


def test_pe21_the_kanban_refresh_needs_the_read_rule(alice, bob, api_as):
    name = make(alice, doctype="CRM View Settings", type="kanban", column_field="user")
    response = api_as(bob).post(url(name, "kanban-columns"))
    assert response.status_code == 403
    assert response.json()["message"] == "Not permitted"


def test_pe21_a_reader_who_may_not_write_gets_the_columns_unsaved(alice, bob, api_as):
    name = make(alice, doctype="CRM View Settings", type="kanban", column_field="user")
    CRMViewSettings.objects.filter(pk=name).update(public=True, user=None, kanban_columns="[]")
    response = api_as(bob).post(url(name, "kanban-columns"))
    assert response.status_code == 200
    assert {c["name"] for c in json.loads(response.json()["message"])} >= {alice.name, bob.name}
    assert row(name).kanban_columns == "[]"


@pytest.mark.parametrize("name", [999999, "abc"])
def test_the_kanban_refresh_of_a_missing_view_answers_null(auth_api, name):
    assert auth_api.post(url(name, "kanban-columns")).json() == {"message": None}
