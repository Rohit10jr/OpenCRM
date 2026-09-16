"""The territory tree is a maintained nested set: FINDINGS.md 14.

``CRM Territory`` is ``is_tree`` upstream, so ``frappe/utils/nestedset.py`` keeps
``lft``/``rgt`` on every write (siblings ordered by name, as ``rebuild_node`` does)
and the ``descendants of`` / ``ancestors of`` filter operators resolve through them.
"""

from urllib.parse import quote

import pytest

from crm_app.models import CRMOrganization, CRMTerritory
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

ORGS = "/api/resource/" + quote("CRM Organization")


@pytest.fixture
def tree(administrator):
    with session_user(administrator.name):
        world = CRMTerritory.objects.create(territory_name="ZZ World", is_group=True)
        europe = CRMTerritory.objects.create(
            territory_name="ZZ Europe", is_group=True, parent_crm_territory=world
        )
        asia = CRMTerritory.objects.create(
            territory_name="ZZ Asia", is_group=True, parent_crm_territory=world
        )
        berlin = CRMTerritory.objects.create(territory_name="ZZ Berlin", parent_crm_territory=europe)
        CRMOrganization.objects.create(organization_name="ZZ Berlin Org", territory=berlin)
        CRMOrganization.objects.create(organization_name="ZZ Asia Org", territory=asia)
        CRMOrganization.objects.create(organization_name="ZZ Nowhere Org")
    return world, europe, asia, berlin


def _bounds(name):
    node = CRMTerritory.objects.get(pk=name)
    return node.lft, node.rgt


def test_lft_and_rgt_are_written_on_every_node(tree):
    """Depth-first, siblings by name: World(1,8) > Asia(2,3), Europe(4,7) > Berlin(5,6)."""
    assert _bounds("ZZ World") == (1, 8)
    assert _bounds("ZZ Asia") == (2, 3)
    assert _bounds("ZZ Europe") == (4, 7)
    assert _bounds("ZZ Berlin") == (5, 6)


def test_reparenting_rebuilds_the_bounds(tree):
    world, europe, asia, berlin = tree
    berlin.parent_crm_territory = asia
    berlin.save()
    assert _bounds("ZZ Asia") == (2, 5)
    assert _bounds("ZZ Berlin") == (3, 4)
    assert _bounds("ZZ Europe") == (6, 7)


def test_descendants_of_finds_organizations_below_a_group(auth_api, tree):
    response = auth_api.get(
        ORGS + '?fields=["name"]&filters=[["territory","descendants of","ZZ World"]]&order_by=name asc'
    )
    assert response.status_code == 200, response.content[:300]
    assert [row["name"] for row in response.json()["data"]] == ["ZZ Asia Org", "ZZ Berlin Org"]


def test_descendants_of_excludes_the_node_itself_unless_inclusive(auth_api, tree):
    with session_user("Administrator"):
        CRMOrganization.objects.create(organization_name="ZZ Europe Org", territory=tree[1])
    excluded = auth_api.get(
        ORGS + '?fields=["name"]&filters=[["territory","descendants of","ZZ Europe"]]'
    ).json()["data"]
    assert [row["name"] for row in excluded] == ["ZZ Berlin Org"]
    included = auth_api.get(
        ORGS + '?fields=["name"]&filters=[["territory","descendants of (inclusive)","ZZ Europe"]]&order_by=name asc'
    ).json()["data"]
    assert [row["name"] for row in included] == ["ZZ Berlin Org", "ZZ Europe Org"]


def test_ancestors_of_walks_up(auth_api, tree):
    with session_user("Administrator"):
        CRMOrganization.objects.create(organization_name="ZZ Europe Org", territory=tree[1])
    response = auth_api.get(
        ORGS + '?fields=["name"]&filters=[["territory","ancestors of","ZZ Berlin"]]&order_by=name asc'
    )
    assert [row["name"] for row in response.json()["data"]] == ["ZZ Europe Org"]


def test_a_missing_node_matches_nothing(auth_api, tree):
    response = auth_api.get(
        ORGS + '?fields=["name"]&filters=[["territory","descendants of","ZZ Nowhere"]]'
    )
    assert response.status_code == 200
    assert response.json()["data"] == []
