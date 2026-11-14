import threading

import pytest
from django.db import connections, transaction
from django.test.utils import CaptureQueriesContext

from core.exceptions import (
    FilterError,
    NestedSetRecursionError,
    api_exception_handler,
)
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


def assert_tree_lock_precedes_delete(queries):
    statements = [query["sql"] for query in queries]
    lock_index = next(
        index
        for index, statement in enumerate(statements)
        if "pg_advisory_xact_lock" in statement
    )
    delete_index = next(
        index
        for index, statement in enumerate(statements)
        if 'DELETE FROM "tests_support_testtree"' in statement
    )
    assert lock_index < delete_index, statements


def test_instance_delete_locks_tree_before_deleting_row(administrator):
    node = TreeNode(name="Root")
    node.save(user=administrator)

    with CaptureQueriesContext(connections["default"]) as queries:
        node.delete()

    assert_tree_lock_precedes_delete(queries)


def test_queryset_delete_locks_tree_before_deleting_row(administrator):
    node = TreeNode(name="Root")
    node.save(user=administrator)

    with CaptureQueriesContext(connections["default"]) as queries:
        TreeNode.objects.filter(pk=node.pk).delete()

    assert_tree_lock_precedes_delete(queries)


def test_a_rootless_cycle_keeps_its_old_bounds_when_save_is_bypassed(administrator):
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

    # PE-4 prevents this through save(); a direct update can still make the old
    # rootless cycle, whose bounds the parity rebuild deliberately leaves alone.
    TreeNode.rebuild_tree()

    assert bounds("Cycle A") == (101, 102)
    assert bounds("Cycle B") == (103, 104)
    assert bounds("Root") == (1, 4)
    assert bounds("Child") == (2, 3)


def assert_loop_error(caught):
    error = caught.value
    assert error.message == "Item cannot be added to its own descendants"
    assert error.exc_type == "NestedSetRecursionError"
    assert error.http_status_code == 417
    assert error.title == "Message"
    response = api_exception_handler(error, {})
    assert response.status_code == 417
    assert response.data["message"] == "Item cannot be added to its own descendants"
    assert response.data["exc_type"] == "NestedSetRecursionError"


def test_own_parent_is_refused_with_upstream_error(tree, administrator):
    _, europe, _, _ = tree
    europe.parent_node = europe

    with pytest.raises(NestedSetRecursionError) as caught:
        europe.save(user=administrator)

    assert_loop_error(caught)
    europe.refresh_from_db()
    assert europe.parent_node_id == "World"


def test_descendant_as_parent_is_refused_with_upstream_error(tree, administrator):
    _, europe, _, berlin = tree
    europe.parent_node = berlin

    with pytest.raises(NestedSetRecursionError) as caught:
        europe.save(user=administrator)

    assert_loop_error(caught)
    europe.refresh_from_db()
    assert europe.parent_node_id == "World"


def test_sibling_and_ancestor_as_parent_are_accepted(tree, administrator):
    world, europe, asia, berlin = tree
    europe.parent_node = asia
    europe.save(user=administrator)
    berlin.parent_node = world
    berlin.save(user=administrator)

    europe.refresh_from_db()
    berlin.refresh_from_db()
    assert europe.parent_node_id == "Asia"
    assert berlin.parent_node_id == "World"
    assert valid_nested_set()


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


@pytest.mark.django_db(transaction=True)
def test_concurrent_reparents_cannot_form_a_loop(administrator):
    root = TreeNode(name="Root")
    root.save(user=administrator)
    left = TreeNode(name="Left", parent_node=root)
    left.save(user=administrator)
    right = TreeNode(name="Right", parent_node=root)
    right.save(user=administrator)
    barrier = threading.Barrier(2)
    outcomes = []

    def reparent(name, parent_name):
        try:
            node = TreeNode.objects.get(pk=name)
            barrier.wait(timeout=10)
            node.parent_node_id = parent_name
            node.save(user=administrator.pk)
        except NestedSetRecursionError as exc:
            outcomes.append(("refused", exc.message, exc.exc_type))
        except BaseException as exc:  # surfaced in the assertion below
            outcomes.append(("error", repr(exc)))
        else:
            outcomes.append(("saved", name))
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=reparent, args=("Left", "Right")),
        threading.Thread(target=reparent, args=("Right", "Left")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(outcome[0] for outcome in outcomes) == ["refused", "saved"]
    refused = next(outcome for outcome in outcomes if outcome[0] == "refused")
    assert refused[1:] == (
        "Item cannot be added to its own descendants",
        "NestedSetRecursionError",
    )
    left.refresh_from_db()
    right.refresh_from_db()
    assert (left.parent_node_id, right.parent_node_id) in {
        ("Right", "Root"),
        ("Root", "Left"),
    }
    assert valid_nested_set()
