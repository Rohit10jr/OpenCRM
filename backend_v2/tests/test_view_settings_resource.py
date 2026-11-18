"""CRM View Settings as a resource (specs/CONFIGURATION.md 4.7; temp A-39).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_phase4_metadata.py:778-829``: a
private view is invisible to another user in the list and by name, a public one is
visible to everyone, another user's view cannot be edited. The old
`/api/resource/CRM View Settings` is `/api/v1/view-settings/`, answering under
`message` (API_CONTRACT); the old PUT is PATCH, and
`:804` makes its public view with the model, the `public` call being CF7b's.
`:551` (the eight calls are registered) is covered by `tests/guards/test_route_map.py`
over the built route-map rows, and ``test_permissions.py:777`` (the doctype has a row
rule) by `tests/guards/test_resource_access.py` (`Access.ruled()`). New: the
rules for managers, PE-19 (the four fields the dedicated calls set) and PE-12d (a JSON
column that is not JSON).
"""

import pytest

from configuration.models import CRMViewSettings

pytestmark = pytest.mark.django_db

VIEWS = "/api/v1/view-settings/"


@pytest.fixture
def manager(make_user):
    return make_user("mgr@example.com", roles=["Sales Manager"])


@pytest.fixture
def sysman(make_user):
    return make_user("sysman@example.com", roles=["System Manager"])


def make_view(owner, **fields):
    """A saved view `owner` made, as the old `make_standard_view` stores one."""
    values = {"dt": "CRM Lead", "type": "list", "user": owner, "label": "Mine"}
    values.update(fields)
    view = CRMViewSettings(**values)
    view.save(user=owner)
    return view


def names(response):
    return [row["name"] for row in response.json()["message"]]


# --- ported ------------------------------------------------------------------------------


def test_a_private_saved_view_is_invisible_through_the_generic_route(alice, bob, api_as):
    make_view(alice, is_standard=True, columns='[{"key": "email"}]', rows='["name", "email"]')
    response = api_as(bob).get(VIEWS)
    assert response.status_code == 200
    assert response.json()["message"] == []


def test_a_private_saved_view_cannot_be_read_by_name(alice, bob, api_as):
    view = make_view(alice, is_standard=True)
    assert api_as(bob).get(f"{VIEWS}{view.pk}/").status_code == 403


def test_a_public_saved_view_is_visible_to_everyone(alice, bob, api_as):
    view = make_view(alice, label="Shared")
    view.public, view.user = True, None
    view.save(user=alice)
    assert names(api_as(bob).get(VIEWS)) == [view.pk]


def test_another_users_saved_view_cannot_be_edited_through_the_generic_route(alice, bob, api_as):
    view = make_view(alice, is_standard=True)
    response = api_as(bob).patch(f"{VIEWS}{view.pk}/", {"label": "Hijacked"}, format="json")
    assert response.status_code == 403
    assert CRMViewSettings.objects.get(pk=view.pk).label != "Hijacked"


# --- new: the rules ----------------------------------------------------------------------


def test_an_ownerless_view_is_readable_by_everyone(alice, bob, api_as):
    view = make_view(alice, user=None)
    assert api_as(bob).get(f"{VIEWS}{view.pk}/").status_code == 200


@pytest.mark.parametrize("reader", ["administrator", "sysman"])
def test_administrator_and_system_manager_read_and_write_every_view(alice, api_as, request, reader):
    view = make_view(alice)
    client = api_as(request.getfixturevalue(reader))
    assert names(client.get(VIEWS)) == [view.pk]
    assert client.patch(f"{VIEWS}{view.pk}/", {"label": "Theirs"}, format="json").status_code == 200


def test_a_sales_manager_edits_a_public_view_but_not_a_private_one(alice, manager, api_as):
    shared = make_view(alice, public=True)
    private = make_view(alice)
    client = api_as(manager)
    assert client.patch(f"{VIEWS}{shared.pk}/", {"label": "Edited"}, format="json").status_code == 200
    assert client.patch(f"{VIEWS}{private.pk}/", {"label": "Edited"}, format="json").status_code == 403


def test_the_owner_writes_and_deletes_their_view(alice, api_as):
    view = make_view(alice)
    client = api_as(alice)
    assert client.patch(f"{VIEWS}{view.pk}/", {"label": "Renamed"}, format="json").status_code == 200
    assert client.delete(f"{VIEWS}{view.pk}/").status_code in (200, 202, 204)
    assert not CRMViewSettings.objects.filter(pk=view.pk).exists()


def test_another_user_cannot_delete_a_public_view(alice, bob, api_as):
    view = make_view(alice, public=True)
    assert api_as(bob).delete(f"{VIEWS}{view.pk}/").status_code == 403
    assert CRMViewSettings.objects.filter(pk=view.pk).exists()


def test_the_name_is_an_integer(auth_api):
    response = auth_api.post(VIEWS, {"dt": "CRM Lead", "label": "New"}, format="json")
    assert response.status_code == 200
    assert isinstance(response.json()["message"]["name"], int)


# --- new: PE-19 --------------------------------------------------------------------------


def test_pe19_a_created_view_belongs_to_the_caller(alice, bob, auth_api):
    response = auth_api.post(
        VIEWS,
        {
            "dt": "CRM Lead",
            "label": "New",
            "user": bob.name,
            "public": True,
            "is_standard": True,
            "is_default": True,
        },
        format="json",
    )
    assert response.status_code == 200
    view = CRMViewSettings.objects.get(pk=response.json()["message"]["name"])
    assert view.user_id == alice.name
    assert (view.public, view.is_standard, view.is_default) == (False, False, False)


def test_pe19_a_patch_cannot_change_the_four_fields_but_can_pin(alice, bob, api_as):
    view = make_view(alice)
    response = api_as(alice).patch(
        f"{VIEWS}{view.pk}/",
        {"user": bob.name, "public": True, "is_standard": True, "is_default": True, "pinned": True},
        format="json",
    )
    assert response.status_code == 200
    view.refresh_from_db()
    assert view.user_id == alice.name
    assert (view.public, view.is_standard, view.is_default) == (False, False, False)
    assert view.pinned is True


def test_pe19_a_manager_cannot_publish_through_the_resource(alice, manager, api_as):
    view = make_view(alice, public=True)
    api_as(manager).patch(f"{VIEWS}{view.pk}/", {"public": False, "user": manager.name}, format="json")
    view.refresh_from_db()
    assert (view.public, view.user_id) == (True, alice.name)


# --- new: PE-12d -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fieldname", "label"),
    [
        ("filters", "Filters"),
        ("columns", "Columns"),
        ("rows", "Rows"),
        ("kanban_columns", "Kanban Columns"),
        ("kanban_fields", "Kanban Fields"),
    ],
)
def test_pe12d_a_json_column_that_is_not_json_is_refused(alice, auth_api, fieldname, label):
    response = auth_api.post(VIEWS, {"dt": "CRM Lead", fieldname: "[not json"}, format="json")
    assert response.status_code == 417
    assert response.json()["message"] == f"{label} must be valid JSON"
    view = make_view(alice, **{fieldname: "[]"})
    response = auth_api.patch(f"{VIEWS}{view.pk}/", {fieldname: "{"}, format="json")
    assert response.status_code == 417
    assert not CRMViewSettings.objects.exclude(pk=view.pk).exists()
    assert getattr(CRMViewSettings.objects.get(pk=view.pk), fieldname) == "[]"


def test_pe12d_valid_json_and_blank_are_stored_as_written(auth_api):
    response = auth_api.post(
        VIEWS, {"dt": "CRM Lead", "columns": '[{"key": "name"}]', "rows": ""}, format="json"
    )
    assert response.status_code == 200
    view = CRMViewSettings.objects.get(pk=response.json()["message"]["name"])
    assert (view.columns, view.rows) == ('[{"key": "name"}]', "")


def test_dt_and_route_name_are_not_checked(auth_api):
    response = auth_api.post(VIEWS, {"dt": "No Such Doctype", "route_name": "??"}, format="json")
    assert response.status_code == 200
