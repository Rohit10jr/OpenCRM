"""Ported from ``backend/tests/test_hierarchy_concurrency.py`` (REBUILD_PLAN S14).

``lft``/``rgt`` decide which rows a user can see, so racing writers are a permission
defect. ``core/tests/test_tree.py:232`` proves the lock on the generic test tree; these
cases prove it on CRM Sales Hierarchy itself (specs/ACCOUNTS.md section 3: extend, do not
duplicate). ``objects.create`` becomes ``save(user=...)``, and the old explicit
``rebuild_sales_hierarchy()`` becomes the model's ``rebuild_tree()``.
"""

import threading

import pytest
from django.contrib.auth import get_user_model
from django.db import connections, transaction

from accounts.models import CRMSalesHierarchy

User = get_user_model()
ACTOR = "Administrator"


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


def _node(user, full_name, reports_to=None):
    node = CRMSalesHierarchy(user=user, full_name=full_name, reports_to=reports_to)
    node.save(user=ACTOR)
    return node


@pytest.mark.django_db(transaction=True)
def test_concurrent_inserts_leave_a_valid_nested_set(administrator):
    root = _node(User.objects.create_user("root@example.com"), "Root")
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def add_member(i: int):
        try:
            user = User.objects.create_user(f"m{i}@example.com")
            barrier.wait(timeout=10)
            with transaction.atomic():
                _node(user, f"M{i}", root)
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=add_member, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, f"insert raised under concurrency: {errors!r}"
    assert CRMSalesHierarchy.objects.count() == 9
    ok, why = _bounds_are_a_valid_nested_set()
    assert ok, f"nested set is corrupt after concurrent inserts: {why}"


@pytest.mark.django_db(transaction=True)
def test_the_subtree_range_still_selects_every_child(administrator):
    root = _node(User.objects.create_user("boss@example.com"), "Boss")

    def add_member(i: int):
        try:
            user = User.objects.create_user(f"rep{i}@example.com")
            with transaction.atomic():
                _node(user, f"Rep{i}", root)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=add_member, args=(i,)) for i in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    CRMSalesHierarchy.rebuild_tree()
    root.refresh_from_db()

    inside = CRMSalesHierarchy.objects.filter(lft__gte=root.lft, lft__lte=root.rgt)
    assert inside.count() == 7, (
        "the manager's range does not cover every report - those rows would disappear "
        "from the manager's list view"
    )
