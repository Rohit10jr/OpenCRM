"""The org tree is an input to the permission engine, so writing it is writing your own
permissions.

`org_hierarchy` resolves "records owned by anyone in my subtree" against
`CRM Sales Hierarchy` on every Lead and Deal read. With no rule on that table, a Sales
User could add themselves as a node and reparent a colleague underneath. Observed end to
end before the fix:

    GET  /api/resource/CRM Deal/<bob's deal>     -> 403
    POST /api/resource/CRM Sales Hierarchy       -> 201    (alice adds herself)
    PUT  .../CRM Sales Hierarchy/<bob's node>    -> 200    (reports_to = alice)
    GET  /api/resource/CRM Deal/<bob's deal>     -> 200    deal_value: 777777

Worse than the `ToDo` escalation it resembles: that one took a named record at a time,
this takes a whole subtree in one call, and the nested-set maintenance rebuilds
`lft`/`rgt` for the attacker on the way through. Nothing errors - it reads as an ordinary
org-chart edit.

**Only the feature flag kept it from being live.** `enable_sales_hierarchy` is off by
default, and `org_hierarchy` skips the tree entirely when it is. Any organisation using
the feature was exposed. The flag itself became manager-writable in A4, so it could not be
turned on by the caller.

Upstream: System Manager creates, writes and deletes; Sales Manager and Sales User read
only (`crm_sales_hierarchy.json`). Reproduced exactly.
"""

import pytest

from crm_app.models import CRMDeal, CRMDealStatus, CRMSalesHierarchy, FCRMSettings
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def hierarchy_on(administrator, bob):
    """A tree with bob in it, the feature enabled, and alice outside."""
    with session_user(administrator.name):
        FCRMSettings.objects.update_or_create(
            pk="FCRM Settings", defaults={"enable_sales_hierarchy": True}
        )
        return CRMSalesHierarchy.objects.create(user=bob, full_name="Bob")


@pytest.fixture
def bobs_deal(administrator, bob):
    with session_user(administrator.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        return CRMDeal.objects.create(status=status, deal_owner=bob, deal_value=777777)


def test_a_user_cannot_write_themselves_into_the_org_tree(alice, hierarchy_on, api_as):
    """**The escalation, at its first step.** Returned 201 before the rule."""
    response = api_as(alice).post(
        "/api/resource/CRM Sales Hierarchy",
        {"user": alice.name, "full_name": "Alice"},
        format="json",
    )
    assert response.status_code == 403
    assert not CRMSalesHierarchy.objects.filter(user=alice).exists()


def test_a_user_cannot_reparent_a_colleague_under_themselves(
    alice, bob, hierarchy_on, bobs_deal, api_as
):
    """The second step, tested independently: even given a node, the reparent must fail.

    Both steps are asserted because either one alone closes the attack, and a future
    change that loosens one while the other still holds would leave this file passing for
    the wrong reason.
    """
    with session_user("Administrator"):
        alice_node = CRMSalesHierarchy.objects.create(user=alice, full_name="Alice")

    client = api_as(alice)
    assert client.get(f"/api/resource/CRM Deal/{bobs_deal.name}").status_code == 403

    moved = client.put(
        f"/api/resource/CRM Sales Hierarchy/{hierarchy_on.name}",
        {"reports_to": alice_node.name},
        format="json",
    )
    assert moved.status_code == 403

    hierarchy_on.refresh_from_db()
    assert hierarchy_on.reports_to_id is None
    assert client.get(f"/api/resource/CRM Deal/{bobs_deal.name}").status_code == 403


def test_a_user_cannot_delete_a_node(alice, hierarchy_on, api_as):
    """Deleting a manager's node collapses their subtree - the same engine, in reverse."""
    assert api_as(alice).delete(
        f"/api/resource/CRM Sales Hierarchy/{hierarchy_on.name}"
    ).status_code == 403
    assert CRMSalesHierarchy.objects.filter(pk=hierarchy_on.name).exists()


def test_the_method_endpoint_is_covered_by_the_same_rule(alice, hierarchy_on, api_as):
    response = api_as(alice).post(
        "/api/method/frappe.client.set_value",
        {
            "doctype": "CRM Sales Hierarchy",
            "name": hierarchy_on.name,
            "fieldname": {"full_name": "Pwned"},
        },
        format="json",
    )
    assert response.status_code == 403


def test_a_sales_manager_cannot_restructure_the_chart(make_user, hierarchy_on, api_as):
    """**Deliberately tighter than the manager pair used elsewhere in this port.**

    The chart is what decides what a Sales Manager can see, so letting one edit it would
    be the same escalation with a longer run-up. Upstream agrees: `crm_sales_hierarchy.json`
    gives Sales Manager `read: 1` and nothing else.
    """
    manager = make_user("mgr@example.com", roles=["Sales Manager"])

    assert api_as(manager).post(
        "/api/resource/CRM Sales Hierarchy",
        {"user": manager.name, "full_name": "Manager"},
        format="json",
    ).status_code == 403


def test_a_system_manager_can_manage_the_chart(make_user, api_as):
    admin = make_user("sysmgr@example.com", roles=["System Manager"])

    assert api_as(admin).post(
        "/api/resource/CRM Sales Hierarchy",
        {"user": admin.name, "full_name": "Sys Mgr"},
        format="json",
    ).status_code == 201


def test_everyone_can_still_read_the_chart(alice, hierarchy_on, api_as):
    """Upstream grants Sales User `read: 1`, and the Hierarchy settings screen renders
    the tree. Only writes were ever the problem."""
    rows = api_as(alice).get("/api/resource/CRM Sales Hierarchy").json()["data"]
    assert [r["full_name"] for r in rows] == ["Bob"]
