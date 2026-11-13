import threading

import pytest
from django.db import connections, transaction

from core.exceptions import FilterError
from core.query import fetch_rows
from tests_support.models import TestTree as TreeNode
from tests_support.models import TreeItem

pytestmark = pytest.mark.django_db


@pytest.fixture
def tree(administrator):
    world = TreeNode(name="World")
    world.save(user=administrator)
    europe = TreeNode(name="Europe", parent_node=world)
    europe.save(user=administrator)
    asia = TreeNode(name="Asia", parent_node=world)
    asia.save(user=administrator)
    berlin = TreeNode(name="Berlin", parent_node=europe)
    berlin.save(user=administrator)
    for name, node in (("world", world), ("europe", europe), ("asia", asia), ("berlin", berlin)):
        item = TreeItem(name=name, tree=node, label=name)
        item.save(user=administrator)
    return world, europe, asia, berlin


def bounds(name):
    node = TreeNode.objects.get(pk=name)
    return node.lft, node.rgt


def labels(rows):
    return sorted(row["label"] for row in rows)


def test_rebuild_writes_contiguous_bounds_with_siblings_by_name(tree):
    assert bounds("World") == (1, 8)
    assert bounds("Asia") == (2, 3)
    assert bounds("Europe") == (4, 7)
    assert bounds("Berlin") == (5, 6)
    all_bounds = [value for node in TreeNode.objects.all() for value in (node.lft, node.rgt)]
    assert sorted(all_bounds) == list(range(1, 9))


def test_reparenting_rebuilds_bounds(tree, administrator):
    _, _, asia, berlin = tree
    berlin.parent_node = asia
    berlin.save(user=administrator)
    assert bounds("Asia") == (2, 5)
    assert bounds("Berlin") == (3, 4)
    assert bounds("Europe") == (6, 7)


def test_delete_rebuilds_bounds(tree):
    _, _, _, berlin = tree
    TreeItem.objects.filter(tree=berlin).delete()
    TreeNode.objects.filter(pk=berlin.pk).delete()
    assert bounds("World") == (1, 6)
    assert bounds("Asia") == (2, 3)
    assert bounds("Europe") == (4, 5)


def test_a_rootless_cycle_keeps_its_old_bounds_as_backend_does(administrator):
    root = TreeNode(name="Root")
    root.save(user=administrator)
    child = TreeNode(name="Child", parent_node=root)
    child.save(user=administrator)
    cycle_a = TreeNode(name="Cycle A")
    cycle_a.save(user=administrator)
    cycle_b = TreeNode(name="Cycle B", parent_node=cycle_a)
    cycle_b.save(user=administrator)

    TreeNode.objects.filter(pk=cycle_a.pk).update(
        parent_node=cycle_b, lft=101, rgt=102
    )
    TreeNode.objects.filter(pk=cycle_b.pk).update(lft=103, rgt=104)
    TreeNode.objects.filter(pk=root.pk).update(lft=201, rgt=202)
    TreeNode.objects.filter(pk=child.pk).update(lft=203, rgt=204)

    # PE-4 records the proposed improvement; parity keeps rootless-cycle bounds stale.
    TreeNode.rebuild_tree()

    assert bounds("Cycle A") == (101, 102)
    assert bounds("Cycle B") == (103, 104)
    assert bounds("Root") == (1, 4)
    assert bounds("Child") == (2, 3)


@pytest.mark.parametrize(
    "operator,value,expected",
    [
        ("descendants of", "World", ["asia", "berlin", "europe"]),
        ("descendants of (inclusive)", "Europe", ["berlin", "europe"]),
        ("not descendants of (inclusive)", "Europe", ["asia", "world"]),
        ("ancestors of", "Berlin", ["europe", "world"]),
        ("not ancestors of (inclusive)", "Berlin", ["asia"]),
    ],
)
def test_tree_operators(tree, administrator, operator, value, expected):
    rows = fetch_rows(
        TreeItem.objects.all(),
        user=administrator,
        fields=["label"],
        filters={"tree": [operator, value]},
        limit_page_length=0,
    )
    assert labels(rows) == expected


def test_missing_tree_node_matches_nothing(tree, administrator):
    rows = fetch_rows(
        TreeItem.objects.all(), user=administrator, fields=["label"],
        filters={"tree": ["descendants of", "Missing"]},
    )
    assert rows == []


@pytest.mark.parametrize("field", ["widget", "label"])
def test_tree_operator_refuses_non_tree_relation_and_plain_column(administrator, field):
    with pytest.raises(FilterError, match=rf"'{field}' is not a tree field"):
        fetch_rows(
            TreeItem.objects.all(), user=administrator, fields=["label"],
            filters={field: ["descendants of", "x"]},
        )


def valid_nested_set():
    rows = list(TreeNode.objects.values_list("pk", "lft", "rgt"))
    bounds_list = [bound for _, left, right in rows for bound in (left, right)]
    return (
        all(left is not None and right is not None and left < right for _, left, right in rows)
        and len(bounds_list) == len(set(bounds_list))
        and sorted(bounds_list) == list(range(1, 2 * len(rows) + 1))
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_inserts_leave_a_valid_nested_set(administrator):
    root = TreeNode(name="Root")
    root.save(user=administrator)
    barrier = threading.Barrier(6)
    errors = []

    def add_node(number):
        try:
            barrier.wait(timeout=10)
            with transaction.atomic():
                node = TreeNode(name=f"Node {number}", parent_node_id=root.pk)
                node.save(user=administrator)
        except BaseException as exc:  # surfaced in the assertion below
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=add_node, args=(number,)) for number in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, f"concurrent insert raised: {errors!r}"
    assert TreeNode.objects.count() == 7
    assert valid_nested_set()
    root.refresh_from_db()
    assert TreeNode.objects.filter(lft__gte=root.lft, rgt__lte=root.rgt).count() == 7
