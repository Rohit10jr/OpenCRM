"""Product reconciliation — filling the seam phase 5 left.

`crm_app/tasks.py:_reconcile_products` has raised `NotImplementedError` since phase 5. This
is what goes behind it.

**It is also the first live caller of `crm_product_sync_complete`.** `KNOWN_ISSUES.md` §5
records that no Celery task had ever published to a browser end to end, because the only
publishing task returned early at this seam. It no longer does.

## Direction

Upstream reconciles a local `Item` table against `CRM Product` in both directions
(`reconcile_job.py:21-37`). This port has no `Item` table — that is ERPNext's model, and
porting it is explicitly out of scope — so reconciliation is **one-directional**: for each
CRM Product without an `erpnext_item_code`, look for a matching Item on the remote site by
code and link it.

What is lost is stated rather than implied: upstream also *creates* missing Items on the
ERPNext side, and creates CRM Products for Items that have none. Both are writes into
ERPNext's own models. The unlinked-orphan detection that produces `CRM Product Sync Issue`
rows is kept, because it is about *our* records.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from crm_app.integrations.erpnext import client

logger = logging.getLogger(__name__)

ISSUE_UNLINKED_ORPHAN = "unlinked_orphan"


def reconcile() -> dict:
    """Link CRM Products to remote ERPNext Items by product code.

    Returns the summary shape upstream returns (`reconcile_job.py:39-47`), minus the two
    counters for writes this port does not make.
    """
    from crm_app.models import CRMProduct

    summary = {
        "already_linked": 0,
        "linked_by_exact_code": 0,
        "unlinked_orphans": 0,
        # Present and always zero: upstream creates records on both sides, this port does
        # not. Kept in the shape so the frontend's summary does not gain a KeyError.
        "created_in_crm": 0,
        "created_in_erpnext": 0,
    }

    products = list(CRMProduct._default_manager.all())
    if not products:
        return summary

    remote_codes = _remote_item_codes()
    issues = []

    for product in products:
        code = product.product_code or ""
        if product.erpnext_item_code:
            if remote_codes and product.erpnext_item_code not in remote_codes:
                # It was linked and the Item is gone. That is exactly the case
                # `unlinked_orphan` names.
                issues.append(
                    (product, f"Item {product.erpnext_item_code} no longer exists in ERPNext")
                )
                summary["unlinked_orphans"] += 1
            else:
                summary["already_linked"] += 1
            continue

        if code and code in remote_codes:
            CRMProduct._default_manager.filter(pk=product.pk).update(erpnext_item_code=code)
            summary["linked_by_exact_code"] += 1

    _record_issues(issues)
    return summary


def _remote_item_codes() -> set[str]:
    """Every Item code on the remote site.

    Returns an empty set on failure, and callers treat empty as "unknown" rather than as
    "there are none" — otherwise an unreachable ERPNext would mark every linked product as
    an orphan.
    """
    rows = client.get_list("Item", fields=["item_code"], limit=5000)
    return {row.get("item_code") for row in rows if row.get("item_code")}


def _record_issues(issues: list[tuple]) -> None:
    """`reconcile_job.py:_record_issues` — write the findings onto the settings singleton.

    Idempotent on `(product, kind)`: a reconciliation that runs hourly must not add an
    identical issue row every hour. Upstream appends unconditionally, which is
    `UPSTREAM_BUGS` #31.
    """
    from crm_app.models import CRMProductSyncIssue, ERPNextCRMSettings

    if not issues:
        return

    parent = ERPNextCRMSettings.load()
    existing = set(
        CRMProductSyncIssue._default_manager.filter(
            parenttype="ERPNext CRM Settings", kind=ISSUE_UNLINKED_ORPHAN, dismissed=False
        ).values_list("product", flat=True)
    )

    idx = (
        CRMProductSyncIssue._default_manager.filter(
            parenttype="ERPNext CRM Settings"
        ).count()
        + 1
    )
    for product, detail in issues:
        if str(product.pk) in existing:
            continue
        CRMProductSyncIssue._default_manager.create(
            parenttype="ERPNext CRM Settings",
            parentfield="sync_issues",
            parent=str(parent.pk),
            idx=idx,
            product=str(product.pk),
            kind=ISSUE_UNLINKED_ORPHAN,
            detail=detail,
            detected_on=timezone.now(),
        )
        idx += 1
