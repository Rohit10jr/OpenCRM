"""The nested-set rebuild must not interleave - gate blocker A2.

``lft``/``rgt`` decide **which rows a user can see** (``org_hierarchy.py`` builds the
subtree clause from them), so two writers racing is not merely a malformed tree, it is a
permission defect: a manager can briefly see nothing, or someone else's subtree.

Frappe serialises the same hazard with ``SELECT ... FOR UPDATE`` on the parent row
(``frappe/utils/nestedset.py:77``, ``:110``, ``:138``), which works because it updates one
subtree region incrementally. Our rebuild rewrites every bound, so it locks the whole
table instead.

**The hazard is concurrent inserts, not concurrent rebuilds.** Rebuilding a *fixed* node
set twice is harmless - the walk derives bounds from ``reports_to`` alone, so both
writers compute the same answer. The damage happens when one transaction walks ``n``
nodes while another walks ``n+1``: each writes only the rows it read, so the newcomer
keeps bounds from one walk while its siblings keep bounds from the other, and the two
sets overlap.

An earlier version of this file spawned concurrent ``rebuild_sales_hierarchy()`` calls
over a static tree and passed with the lock removed - a vacuous test. The test below is
verified to fail without ``select_for_update``.
"""

import threading

import pytest
from django.db import connections, transaction

from crm_app.models import CRMSalesHierarchy
from crm_app.permissions.tree import rebuild_sales_hierarchy
from frappe_platform.models import User


def _bounds_are_a_valid_nested_set() -> tuple[bool, str]:
    rows = list(CRMSalesHierarchy.objects.values_list("pk", "lft", "rgt"))
    if not rows:
        return False, "no rows"

    for pk, lft, rgt in rows:
        if lft is None or rgt is None:
            return False, f"{pk} has an unset bound"
        if lft >= rgt:
            return False, f"{pk} has crossed bounds lft={lft} rgt={rgt}"

    bounds = [b for _, lft, rgt in rows for b in (lft, rgt)]
    if len(bounds) != len(set(bounds)):
        return False, f"duplicate bounds: {sorted(bounds)}"
    if sorted(bounds) != list(range(1, 2 * len(rows) + 1)):
        return False, f"bounds are not contiguous 1..2n: {sorted(bounds)}"
    return True, ""


@pytest.mark.django_db(transaction=True)
def test_concurrent_inserts_leave_a_valid_nested_set():
    """Eight threads each add a node; every insert triggers a rebuild via the signal.

    Without serialisation the walks overlap and bounds collide. Verified: this fails
    with ``select_for_update`` removed from ``_rebuild_locked``.
    """
    root_user = User.objects.create_user("root@example.com")
    root = CRMSalesHierarchy.objects.create(user=root_user, full_name="Root")

    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def add_member(i: int):
        try:
            user = User.objects.create_user(f"m{i}@example.com")
            barrier.wait(timeout=10)  # maximise overlap
            with transaction.atomic():
                CRMSalesHierarchy.objects.create(
                    user=user, full_name=f"M{i}", reports_to=root
                )
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=add_member, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"insert raised under concurrency: {errors!r}"
    assert CRMSalesHierarchy.objects.count() == 9

    ok, why = _bounds_are_a_valid_nested_set()
    assert ok, f"nested set is corrupt after concurrent inserts: {why}"


@pytest.mark.django_db(transaction=True)
def test_the_subtree_range_still_selects_every_child():
    """The consequence the bounds exist for.

    A corrupt tree does not merely look wrong - the manager's ``lft``/``rgt`` range stops
    covering its reports, and those rows vanish from the manager's list.
    """
    root_user = User.objects.create_user("boss@example.com")
    root = CRMSalesHierarchy.objects.create(user=root_user, full_name="Boss")

    def add_member(i: int):
        try:
            user = User.objects.create_user(f"rep{i}@example.com")
            with transaction.atomic():
                CRMSalesHierarchy.objects.create(
                    user=user, full_name=f"Rep{i}", reports_to=root
                )
        finally:
            connections.close_all()

    threads = [threading.Thread(target=add_member, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    rebuild_sales_hierarchy()
    root.refresh_from_db()

    inside = CRMSalesHierarchy.objects.filter(lft__gte=root.lft, lft__lte=root.rgt)
    assert inside.count() == 7, (
        "the manager's range does not cover every report - those rows would disappear "
        "from the manager's list view"
    )
