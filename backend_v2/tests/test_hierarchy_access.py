"""Ported from ``backend/tests/test_hierarchy_access.py`` (REBUILD_PLAN S14).

Writing the org tree is writing your own permissions: System Manager alone creates,
writes and deletes; everyone reads (upstream `crm_sales_hierarchy.json`).

`/api/resource/CRM Sales Hierarchy` becomes `/api/v1/sales-hierarchies/`, PUT and
`frappe.client.set_value` become PATCH, and a create answers the collection route's 200
(it replaces `frappe.client.insert`). The old ``hierarchy_on`` fixture also switched on
FCRM Settings' flag, which only the deal read in the reparent case needs: that case
(old ``:64``) needs CRM Deal and is SALES' (specs/ACCOUNTS.md section 2). Here the
fixture creates bob's node alone; the refusals do not depend on the flag.
"""

import pytest

from accounts.models import CRMSalesHierarchy
from core.exceptions import NestedSetRecursionError

pytestmark = pytest.mark.django_db
NODES = "/api/v1/sales-hierarchies/"


@pytest.fixture
def bobs_node(administrator, bob):
    node = CRMSalesHierarchy(user=bob, full_name="Bob")
    node.save(user=administrator)
    return node


def test_a_user_cannot_write_themselves_into_the_org_tree(alice, bobs_node, api_as):
    response = api_as(alice).post(
        NODES, {"user": alice.name, "full_name": "Alice"}, format="json"
    )
    assert response.status_code == 403
    assert not CRMSalesHierarchy.objects.filter(user=alice).exists()


def test_a_user_cannot_reparent_a_colleague_under_themselves(
    alice, administrator, bobs_node, api_as
):
    alice_node = CRMSalesHierarchy(user=alice, full_name="Alice")
    alice_node.save(user=administrator)

    moved = api_as(alice).patch(
        f"{NODES}{bobs_node.name}/", {"reports_to": alice_node.name}, format="json"
    )
    assert moved.status_code == 403

    bobs_node.refresh_from_db()
    assert bobs_node.reports_to_id is None


def test_a_user_cannot_delete_a_node(alice, bobs_node, api_as):
    assert api_as(alice).delete(f"{NODES}{bobs_node.name}/").status_code == 403
    assert CRMSalesHierarchy.objects.filter(pk=bobs_node.name).exists()


def test_the_set_value_path_is_covered_by_the_same_rule(alice, bobs_node, api_as):
    response = api_as(alice).patch(
        f"{NODES}{bobs_node.name}/", {"full_name": "Pwned"}, format="json"
    )
    assert response.status_code == 403


def test_a_sales_manager_cannot_restructure_the_chart(make_user, bobs_node, api_as):
    manager = make_user("mgr@example.com", roles=["Sales Manager"])

    assert api_as(manager).post(
        NODES, {"user": manager.name, "full_name": "Manager"}, format="json"
    ).status_code == 403


def test_a_system_manager_can_manage_the_chart(make_user, api_as):
    admin = make_user("sysmgr@example.com", roles=["System Manager"])

    assert api_as(admin).post(
        NODES, {"user": admin.name, "full_name": "Sys Mgr"}, format="json"
    ).status_code == 200


def test_everyone_can_still_read_the_chart(alice, bobs_node, api_as):
    rows = api_as(alice).get(NODES, {"fields": '["full_name"]'}).json()["message"]
    assert [row["full_name"] for row in rows] == ["Bob"]


# --- ACCOUNTS additions (specs/ACCOUNTS.md section 4.7) ---------------------------------


def test_full_name_is_fetched_from_the_user(administrator, make_user):
    user = make_user("fetch@example.com", first_name="Fetched", last_name="Name")
    node = CRMSalesHierarchy(user=user)
    node.save(user=administrator)
    assert node.full_name == "Fetched Name"


def test_a_parent_loop_is_refused_on_the_hierarchy(administrator, alice, bob):
    """PE-4 (approved) on this model: the old backend accepted it."""
    top = CRMSalesHierarchy(user=alice)
    top.save(user=administrator)
    below = CRMSalesHierarchy(user=bob, reports_to=top)
    below.save(user=administrator)

    top.reports_to = below
    with pytest.raises(NestedSetRecursionError, match="Item cannot be added to its own descendants"):
        top.save(user=administrator)


def test_deleting_a_user_rebuilds_the_bounds_of_their_reports(administrator, make_user):
    """A cascade delete skips TreeDocument.delete; core's post_delete receiver rebuilds,
    as the old backend's did (crm_app/permissions/tree.py:172-180)."""
    boss = make_user("boss@example.com")
    report = make_user("report@example.com")
    top = CRMSalesHierarchy(user=boss)
    top.save(user=administrator)
    below = CRMSalesHierarchy(user=report, reports_to=top)
    below.save(user=administrator)

    boss.delete()

    below.refresh_from_db()
    assert below.reports_to_id is None
    assert (below.lft, below.rgt) == (1, 2)
