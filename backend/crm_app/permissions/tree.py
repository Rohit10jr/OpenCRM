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

The rebuild is O(n) over the whole tree on every hierarchy write. Sales hierarchies are
small (one row per user) and change rarely, whereas the *read* path runs on every list
request - so the cost is deliberately pushed to the write side. Reads stay one indexed
range scan.
"""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save


def rebuild_sales_hierarchy() -> None:
    """Recompute every ``lft``/``rgt`` from ``reports_to`` by depth-first walk."""
    from crm_app.models import CRMSalesHierarchy

    nodes = list(CRMSalesHierarchy._default_manager.all().order_by("name"))
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
