"""Nested-set maintenance for ``CRM Sales Hierarchy``.

PHASE_2_PERMISSIONS.md section 3. Phase 1 ported ``lft``/``rgt`` as columns; nothing
wrote them, so a hierarchy built through the API would have had every bound ``NULL`` and
the subtree clause would have matched nothing. This fills that in.

**Why a full rebuild rather than django-treebeard.** The spec suggests treebeard
(``MP_Node``/``NS_Node``). Two reasons this does not use it:

1. Treebeard owns the columns it maintains (``path``/``depth``/``numchild`` for MP,
   its own ``lft``/``rgt``/``tree_id`` for NS) and expects to own node creation through
   ``add_root``/``add_child``. Our rows arrive through the generic ``/api/resource/``
   endpoint with ``reports_to`` set, which is not treebeard's write path.
2. The schema we must match is Frappe's ``lft``/``rgt`` + ``reports_to``, and the read
   query is a single range scan either way. Treebeard would have added a second
   representation to keep in sync with the one the wire format already fixes.

Confirmed against the framework since: Frappe maintains ``lft``/``rgt`` **incrementally**
(``frappe/utils/nestedset.py:update_add_node`` / ``update_move_node``) and reserves
``rebuild_tree`` for repair. That approach locks the *parent row* -
``for_update=True`` at ``nestedset.py:77``, ``.for_update()`` at ``:110`` and ``:138`` -
because each write only disturbs one subtree region. It is a third write path, matching
neither treebeard nor our generic ``/api/resource/`` endpoint, which reinforces the
choice above rather than undermining it.

The rebuild is O(n) over the whole tree on every hierarchy write. Sales hierarchies are
small (one row per user) and change rarely, whereas the *read* path runs on every list
request - so the cost is deliberately pushed to the write side. Reads stay one indexed
range scan.

**Concurrency.** A rebuild rewrites every bound, so Frappe's parent-row lock is the wrong
shape here - two writers must not interleave at all. The hazard is concurrent *inserts*:
rebuilding a fixed node set twice is harmless, because the walk derives bounds from
``reports_to`` alone and both writers reach the same answer. The damage happens when one
transaction walks ``n`` nodes while another walks ``n+1`` - each writes only the rows it
read, so the newcomer keeps bounds from one walk while its siblings keep bounds from the
other. That is not merely a malformed tree: ``lft``/``rgt`` decide **which rows a user can
see**, so overlapping bounds are a permission defect.

``select_for_update()`` does **not** fix this, which is worth stating because it is the
obvious first answer. A row lock only covers rows the query already matched; the second
writer blocks, then re-reads *those* rows and still cannot see the row the first writer
inserted - the classic phantom. It walks ``n`` nodes regardless and the bounds still
collide. Verified by test before and after.

The serialisation therefore has to be taken **before the read**, over the operation rather
than over any row set: a transaction-scoped advisory lock. It is released automatically at
commit or rollback, takes no table lock, and blocks a second rebuild until the first has
committed - at which point that rebuild reads a set that includes the new row.
"""

from __future__ import annotations

from django.db import connection, transaction
from django.db.models.signals import post_delete, post_save

#: Arbitrary but stable key for ``pg_advisory_xact_lock``. Any other advisory lock in
#: this codebase must use a different one.
_HIERARCHY_LOCK_KEY = 8_724_100_1


def rebuild_sales_hierarchy() -> None:
    """Recompute every ``lft``/``rgt`` from ``reports_to`` by depth-first walk.

    Serialised by a transaction-scoped advisory lock taken before the read. See the
    module docstring for why the lock has to precede the read rather than accompany it.
    """
    from crm_app.models import CRMSalesHierarchy

    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_HIERARCHY_LOCK_KEY])
        _rebuild_locked(CRMSalesHierarchy)


def _rebuild_locked(CRMSalesHierarchy) -> None:
    """Caller must hold the advisory lock."""
    nodes = list(CRMSalesHierarchy._default_manager.order_by("name"))
    if not nodes:
        return

    children: dict[str | None, list] = {}
    by_pk = {node.pk: node for node in nodes}
    for node in nodes:
        parent = node.reports_to_id
        # A dangling or self-referential parent is treated as a root rather than being
        # allowed to break the walk.
        if parent not in by_pk or parent == node.pk:
            parent = None
        children.setdefault(parent, []).append(node)

    counter = 0
    updated: list = []

    def visit(node, depth: int = 0) -> None:
        nonlocal counter
        if depth > len(nodes):  # cycle guard
            return
        counter += 1
        node.lft = counter
        for child in children.get(node.pk, []):
            visit(child, depth + 1)
        counter += 1
        node.rgt = counter
        updated.append(node)

    for root in children.get(None, []):
        visit(root)

    if updated:
        CRMSalesHierarchy._default_manager.bulk_update(updated, ["lft", "rgt"])


def _on_hierarchy_write(sender, instance, **kwargs):
    # Rebuilt inline rather than deferred to on_commit: the bounds must be correct for
    # any query later in the *same* transaction, and a test running inside one would
    # otherwise never see the rebuild happen at all.
    rebuild_sales_hierarchy()


def connect_signals() -> None:
    from crm_app.models import CRMSalesHierarchy

    post_save.connect(
        _on_hierarchy_write, sender=CRMSalesHierarchy, dispatch_uid="crm.hierarchy.save"
    )
    post_delete.connect(
        _on_hierarchy_write, sender=CRMSalesHierarchy, dispatch_uid="crm.hierarchy.delete"
    )
