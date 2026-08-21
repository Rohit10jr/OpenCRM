"""The ERPNext endpoints.

Ports the whitelisted methods of `erpnext_crm_settings.py`. Every `frappe.throw` message is
preserved verbatim; they are shown in dialogs.

Paths keep upstream's long dotted form —
`crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.*` — because that is what the
frontend calls (`ERPNextSettings.vue`), and `PORT_PLAN.md` §3 makes the wire protocol a
fixed contract.
"""

from __future__ import annotations

import logging

from crm_app.integrations.erpnext import client
from frappe_core import permissions, registry
from frappe_core.exceptions import throw
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

logger = logging.getLogger(__name__)

_PREFIX = "crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings"

#: `erpnext_crm_settings.py:610` and `:622` — a message the operator sees, kept verbatim.
SAME_SITE_UNSUPPORTED = (
    "ERPNext must be configured as a separate site. This deployment integrates with "
    "ERPNext over its API and cannot host ERPNext itself."
)


def settings():
    from crm_app.models import ERPNextCRMSettings

    return ERPNextCRMSettings.load()


def _enabled_settings():
    """`erpnext_crm_settings.py:24-28`, message verbatim."""
    row = settings()
    if not client.is_enabled():
        throw("ERPNext is not integrated with the CRM")
    return row


def _require_same_site_unsupported(row) -> None:
    """The one branch this port refuses rather than reproduces.

    Upstream's same-site mode reaches directly into ERPNext's models and mutates their
    schema. See the package docstring: that is out of scope by the standing decision, and
    refusing loudly is better than a code path that appears to work and writes nothing.
    """
    if not row.is_erpnext_in_different_site:
        throw(SAME_SITE_UNSUPPORTED, title="Unsupported Configuration")


def _may_read_products() -> bool:
    """`erpnext_crm_settings.py:229-230` — `frappe.has_permission("CRM Product", "read")`."""
    from crm_app.models import CRMProduct

    return permissions.check_object_permission(CRMProduct(), "read", get_current_user())


@whitelist(f"{_PREFIX}.is_erpnext_installed")
def is_erpnext_installed():
    """`erpnext_crm_settings.py:214-216`.

    Upstream asks whether the `erpnext` app is installed **in this site**. It never can be
    here, so this is always False — which is the honest answer and is what makes the
    frontend show the "different site" configuration rather than the same-site one.
    """
    return False


@whitelist(f"{_PREFIX}.get_external_companies")
def get_external_companies():
    """`erpnext_crm_settings.py:207-212`."""
    if not client.is_configured():
        return []
    return client.get_list("Company", fields=["company_name"])


@whitelist(f"{_PREFIX}.get_customer_link")
def get_customer_link(crm_deal: str):
    """`erpnext_crm_settings.py:347-371`.

    Returns a URL into the remote site's desk, or `""`. Upstream logs and throws on a
    remote failure; `client.get_list` returns `[]` instead, so a network blip degrades to
    "no link yet" rather than an error dialog on a deal page — which is what
    `PHASE_7_INTEGRATIONS.md` §3's "failures degrade gracefully" asks for.
    """
    from crm_app.models import CRMDeal

    row = _enabled_settings()
    _require_same_site_unsupported(row)

    deal = CRMDeal._default_manager.filter(pk=crm_deal).first()
    if deal is None:
        return ""
    if not permissions.check_object_permission(deal, "read", get_current_user()):
        throw("Not permitted", title="Not Permitted")

    remote = client.get_list("Customer", filters={"crm_deal": crm_deal})
    customer = (remote[0].get("name") if remote else None) or deal.erpnext_customer
    if not customer:
        return ""
    return f"{client.site_url(row)}/app/customer/{customer}"


@whitelist(f"{_PREFIX}.get_quotation_url")
def get_quotation_url(crm_deal: str, organization: str | None = None):
    """`erpnext_crm_settings.py:374-407`.

    Builds a pre-filled "new Quotation" URL on the remote site. The prospect is created
    there first, because the URL names it as `party_name`.
    """
    from urllib.parse import quote

    from crm_app.models import CRMDeal

    row = _enabled_settings()
    _require_same_site_unsupported(row)

    deal = CRMDeal._default_manager.filter(pk=crm_deal).first()
    if deal is None:
        throw(f"CRM Deal {crm_deal} not found")
    if not permissions.check_object_permission(deal, "read", get_current_user()):
        throw("Not permitted", title="Not Permitted")

    prospect = create_prospect_in_remote_site(deal, row)

    params = {
        "quotation_to": "Prospect",
        "crm_deal": crm_deal,
        "party_name": prospect,
        "company": row.erpnext_company,
        "contact_person": _primary_contact(deal),
    }
    query = "&".join(
        f"{key}={quote(str(value))}" for key, value in params.items() if value is not None
    )
    return f"{client.site_url(row)}/app/quotation/new?{query}"


def _primary_contact(deal) -> str | None:
    """`erpnext_crm_settings.py:466-472`."""
    from crm_app.models import CRMContacts

    return (
        CRMContacts._default_manager.filter(parent_deal=deal, is_primary=True)
        .values_list("contact_id", flat=True)
        .first()
    )


def create_prospect_in_remote_site(deal, row):
    """`erpnext_crm_settings.py:410-441`, message verbatim."""
    payload = {
        "organization": getattr(deal, "organization_id", None) or "",
        "lead_name": deal.lead_name or "",
        "no_of_employees": deal.no_of_employees or "",
        "deal_owner": deal.deal_owner_id or "",
        "crm_deal": str(deal.pk),
        "territory": getattr(deal, "territory_id", None) or "",
        "industry": getattr(deal, "industry_id", None) or "",
        "website": deal.website or "",
        "annual_revenue": deal.annual_revenue or 0,
        "erpnext_company": row.erpnext_company or "",
    }
    try:
        return client.post_api(
            "erpnext.crm.frappe_crm_api.create_prospect_against_crm_deal", payload
        )
    except Exception:
        logger.warning("erpnext: prospect creation failed for deal %s", deal.pk, exc_info=True)
        throw("Error while creating prospect in ERPNext, check error log for more details")


@whitelist(f"{_PREFIX}.prefill_quotation_items")
def prefill_quotation_items(crm_deal: str):
    """`erpnext_crm_settings.py:446-464`.

    Purely local — it reads the deal's own product rows and maps them onto ERPNext item
    codes. A product with no `erpnext_item_code` is skipped, which is upstream's behaviour
    and means an unsynced product silently does not reach the quotation.
    """
    from crm_app.models import CRMDeal, CRMProduct, CRMProducts

    deal = CRMDeal._default_manager.filter(pk=crm_deal).first()
    if deal is None:
        return []
    if not permissions.check_object_permission(deal, "read", get_current_user()):
        throw("Not permitted", title="Not Permitted")

    codes = dict(
        CRMProduct._default_manager.exclude(erpnext_item_code="").values_list(
            "pk", "erpnext_item_code"
        )
    )

    items = []
    for row in CRMProducts._default_manager.filter(
        parenttype="CRM Deal", parent=str(deal.pk)
    ).order_by("idx"):
        item_code = codes.get(row.product_code_id if hasattr(row, "product_code_id") else None)
        if not item_code:
            continue
        items.append(
            {
                "item_code": item_code,
                "qty": row.qty or 1,
                "price_list_rate": row.rate or 0,
                "discount_percentage": row.discount_percentage or 0,
            }
        )
    return items


# ---------------------------------------------------------------------------
# Sync issues
# ---------------------------------------------------------------------------


@whitelist(f"{_PREFIX}.get_open_sync_issues")
def get_open_sync_issues():
    """`erpnext_crm_settings.py:228-243`."""
    from crm_app.models import CRMProductSyncIssue

    if not _may_read_products():
        return []

    return [
        {
            "name": issue.pk,
            "product": issue.product,
            "kind": issue.kind,
            "detail": issue.detail,
            "detected_on": issue.detected_on,
        }
        for issue in CRMProductSyncIssue._default_manager.filter(
            parenttype="ERPNext CRM Settings", dismissed=False
        ).order_by("idx")
    ]


@whitelist(f"{_PREFIX}.dismiss_sync_issue")
def dismiss_sync_issue(issue_name: str):
    """`erpnext_crm_settings.py:246-255`."""
    from crm_app.models import CRMProductSyncIssue

    updated = CRMProductSyncIssue._default_manager.filter(pk=issue_name).update(dismissed=True)
    return bool(updated)


@whitelist(f"{_PREFIX}.get_product_sync_status")
def get_product_sync_status():
    """`erpnext_crm_settings.py:257-266`."""
    from crm_app.models import CRMProduct

    if not _may_read_products():
        return {}

    row = settings()
    products = CRMProduct._default_manager.all()
    return {
        "products": {
            "count": products.count(),
            "rows": list(
                products.order_by("-modified").values(
                    "name", "product_code", "product_name", "erpnext_item_code"
                )[:20]
            ),
        },
        # The remote item list is not fetched here: upstream reads a local `Item` table,
        # which this port does not have. Empty rather than a fabricated count.
        "items": {"count": 0, "rows": []},
        "failed": get_open_sync_issues(),
        "unsynced": {
            "items": 0,
            "products": products.filter(erpnext_item_code="").count(),
            "sync_products": bool(row.sync_products),
        },
    }


@whitelist(f"{_PREFIX}.run_product_sync")
def run_product_sync():
    """`erpnext_crm_settings.py:218-225`.

    Upstream refuses unless ERPNext is on the **same** site, because its reconciliation
    reads the local `Item` table. Here it is the other way round: the remote path is the
    only one, so the guard is inverted and says why.
    """
    from crm_app.tasks import run_product_reconciliation

    row = _enabled_settings()
    _require_same_site_unsupported(row)

    run_product_reconciliation.delay(user=get_current_user())
    return True
