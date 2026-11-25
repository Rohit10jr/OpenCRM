"""CRM Territory, a nested-set tree in CONTACTS (specs/CONTACTS.md §11.1; PE-29, PE-31,
PE-34, PE-37; milestone T).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_territory_tree.py:42-57`` (the bounds
and reparenting) on a territory-only fixture: the old ``tree`` fixture also creates
organizations (``:31-33``), whose filters (``:59-95``) wait for milestone 5. New: the
rename rebuild, the delete of a territory with children, a parent and its child deleted
together (A-79 finding 4), and PE-29's matrix as for CRM Industry
(``tests/test_crm_role_rule.py``).
"""

from urllib.parse import quote

import pytest
from django.db.models import ProtectedError

from contacts.models import CRMTerritory
from core.delete import check_static_links_batch

pytestmark = pytest.mark.django_db
TERRITORIES = "/api/v1/territories/"


def make(user, name, parent=None, is_group=False):
    row = CRMTerritory(territory_name=name, parent_crm_territory=parent, is_group=is_group)
    row.save(user=user)
    return row


@pytest.fixture
def tree(administrator):
    world = make(administrator, "ZZ World", is_group=True)
    europe = make(administrator, "ZZ Europe", world, is_group=True)
    asia = make(administrator, "ZZ Asia", world, is_group=True)
    berlin = make(administrator, "ZZ Berlin", europe)
    return world, europe, asia, berlin


def _bounds(name):
    node = CRMTerritory.objects.get(pk=name)
    return node.lft, node.rgt


def url(name, action=""):
    return f"{TERRITORIES}{quote(name)}/{action}"


# --- ported `:42-57` ------------------------------------------------------------------------


def test_lft_and_rgt_are_written_on_every_node(tree):
    """Depth-first, siblings by name: World(1,8) > Asia(2,3), Europe(4,7) > Berlin(5,6)."""
    assert _bounds("ZZ World") == (1, 8)
    assert _bounds("ZZ Asia") == (2, 3)
    assert _bounds("ZZ Europe") == (4, 7)
    assert _bounds("ZZ Berlin") == (5, 6)


def test_reparenting_rebuilds_the_bounds(tree, administrator):
    world, europe, asia, berlin = tree
    berlin.parent_crm_territory = asia
    berlin.save(user=administrator)
    assert _bounds("ZZ Asia") == (2, 5)
    assert _bounds("ZZ Berlin") == (3, 4)
    assert _bounds("ZZ Europe") == (6, 7)


# --- the resource ---------------------------------------------------------------------------


def test_a_territory_is_created_with_its_parent(auth_api, tree):
    response = auth_api.post(
        TERRITORIES, {"territory_name": "ZZ Paris", "parent_crm_territory": "ZZ Europe"}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"]["name"] == "ZZ Paris"
    assert _bounds("ZZ Europe") == (4, 9)
    assert _bounds("ZZ Paris") == (7, 8), "after Berlin, by name"


def test_renaming_a_group_moves_its_children_and_rebuilds_the_bounds(auth_api, tree):
    """§11.1 "Rename": PE-31 sets `territory_name`; the child's parent follows the FK
    repoint; the queryset delete of the old row fires the rebuild."""
    response = auth_api.post(url("ZZ Europe", "rename/"), {"new_name": "ZZ EU"}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert response.json() == {"message": "ZZ EU"}
    renamed = CRMTerritory.objects.get(pk="ZZ EU")
    assert renamed.territory_name == "ZZ EU"
    assert CRMTerritory.objects.get(pk="ZZ Berlin").parent_crm_territory_id == "ZZ EU"
    assert [_bounds(n) for n in ("ZZ World", "ZZ Asia", "ZZ EU", "ZZ Berlin")] == [(1, 8), (2, 3), (4, 7), (5, 6)]


def test_a_territory_with_children_cannot_be_deleted(auth_api, tree):
    """§11.1 "Delete" (05 6.4): the PROTECT parent link, through PE-34's static check."""
    response = auth_api.delete(url("ZZ Europe"))
    assert response.status_code == 417
    assert response.json()["exc_type"] == "LinkExistsError"
    assert response.json()["message"] == (
        "Cannot delete or cancel because CRM Territory ZZ Europe is linked with CRM Territory ZZ Berlin"
    )
    assert CRMTerritory.objects.filter(pk="ZZ Europe").exists()


def test_a_leaf_is_deleted_and_the_bounds_close_up(auth_api, tree):
    assert auth_api.delete(url("ZZ Berlin")).status_code == 200
    assert _bounds("ZZ Europe") == (4, 5)
    assert _bounds("ZZ World") == (1, 6)


def test_a_parent_and_its_child_together(tree):
    """A-79 finding 4 and the supervisor's note: the static check skips links within the
    batch, so a parent and its child pass it together; the database's PROTECT then
    decides on the delete itself. Territory serves no bulk delete (§11.1), so this is
    pinned on the two helpers the bulk delete would call."""
    world, europe, asia, berlin = tree
    check_static_links_batch([europe, berlin])  # no refusal
    with pytest.raises(ProtectedError):
        CRMTerritory._default_manager.filter(pk__in=[europe.pk, berlin.pk]).delete()


# --- PE-29 ----------------------------------------------------------------------------------


@pytest.fixture
def outsider(make_user):
    return make_user("outsider@example.com")


def test_an_outsider_lists_no_territory(outsider, tree, api_as):
    response = api_as(outsider).get(TERRITORIES)
    assert response.status_code == 200
    assert response.json()["message"] == []


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_an_outsider_is_refused_a_territory_by_name(outsider, tree, api_as, method):
    client = api_as(outsider)
    path = url("ZZ Berlin")
    response = client.patch(path, {}, format="json") if method == "patch" else getattr(client, method)(path)
    assert response.status_code == 403
    assert response.json()["message"] == "No permission for CRM Territory ZZ Berlin"
    assert CRMTerritory.objects.filter(pk="ZZ Berlin").exists()


def test_an_outsider_cannot_create_a_territory(outsider, api_as):
    response = api_as(outsider).post(TERRITORIES, {"territory_name": "ZZ Mars"}, format="json")
    assert response.status_code == 403
    assert response.json()["message"] == "Not permitted to create CRM Territory"
    assert not CRMTerritory.objects.filter(pk="ZZ Mars").exists()


def test_an_outsider_finds_no_territory_by_search_or_value(outsider, tree, api_as):
    client = api_as(outsider)
    assert client.get(f"{TERRITORIES}search/", {"txt": "ZZ"}).json()["message"] == []
    value = client.get(f"{TERRITORIES}value/", {"fieldname": "territory_name", "filters": '{"name": "ZZ Berlin"}'})
    assert value.status_code == 200
    assert value.json()["message"] == {}


@pytest.mark.parametrize("role", ["Sales User", "Sales Manager", "System Manager"])
def test_each_crm_role_reaches_territories(make_user, tree, api_as, role):
    client = api_as(make_user("crm@example.com", roles=[role]))
    listed = client.get(TERRITORIES).json()["message"]
    assert [r["name"] for r in listed] == ["ZZ Asia", "ZZ Berlin", "ZZ Europe", "ZZ World"]
    assert client.get(url("ZZ Berlin")).status_code == 200


def test_administrator_reaches_territories(administrator, tree, api_as):
    assert api_as(administrator).get(url("ZZ Berlin")).status_code == 200
