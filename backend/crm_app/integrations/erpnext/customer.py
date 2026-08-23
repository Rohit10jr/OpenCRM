"""Creating an ERPNext Customer when a deal reaches the configured status.

Ports `erpnext_crm_settings.py:511-635`'s remote branch, and the `crm_customer_created`
event `PHASE_6_REALTIME.md` §2 named and left unported.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save

from crm_app.integrations.erpnext import client

logger = logging.getLogger(__name__)


def _settings():
    from crm_app.models import ERPNextCRMSettings

    return ERPNextCRMSettings.load()


def should_create_customer(deal) -> bool:
    """`erpnext_crm_settings.py:511-518`.

    Three conditions, all upstream's: the integration is on, the operator asked for it, and
    the deal has reached *the* configured status — not any status, one named one.
    """
    if not client.is_enabled():
        return False

    row = _settings()
    if not row.create_customer_on_status_change:
        return False
    if not row.deal_status_id:
        return False
    return str(deal.status_id or "") == str(row.deal_status_id)


def create_customer_from_deal(deal) -> str | None:
    """`erpnext_crm_settings.py:580-634`, remote branch. Message verbatim.

    Returns the remote Customer name, or None.

    **Failure does not break the deal save.** `PHASE_7_INTEGRATIONS.md` §3: *"an unreachable
    provider must never break lead or deal CRUD."* This runs from a `post_save` signal, so a
    raise here would roll back a status change the user made for reasons of their own.
    Upstream throws — it runs in a `doc_events` hook where the same objection applies, which
    is `UPSTREAM_BUGS` #32.
    """
    from crm_app.models import CRMDeal

    row = _settings()
    payload = {
        "customer_name": getattr(deal, "organization_id", None) or deal.lead_name or str(deal.pk),
        "crm_deal": str(deal.pk),
        "erpnext_company": row.erpnext_company or "",
        "territory": getattr(deal, "territory_id", None) or "",
        "industry": getattr(deal, "industry_id", None) or "",
        "no_of_employees": deal.no_of_employees or "",
        "annual_revenue": deal.annual_revenue or 0,
        "website": deal.website or "",
    }

    try:
        customer_name = client.post_api("erpnext.crm.frappe_crm_api.create_customer", payload)
    except Exception:
        logger.warning(
            "Error while creating customer in ERPNext for CRM Deal: %s", deal.pk, exc_info=True
        )
        return None

    if not customer_name:
        logger.warning(
            "Error while creating customer in ERPNext for CRM Deal: %s", deal.pk
        )
        return None

    # `update()`, not `save()`: this is a signal handler on that same row, and `save()`
    # would recurse into it as well as re-stamping `modified_by`.
    CRMDeal._default_manager.filter(pk=deal.pk).update(erpnext_customer=str(customer_name))
    deal.erpnext_customer = str(customer_name)

    from crm_app import realtime

    # `erpnext_crm_settings.py:632` — broadcast, no payload. `Deal.vue:500` refetches.
    realtime.publish("crm_customer_created")
    return str(customer_name)


def on_deal_saved(sender, instance, created, **kwargs):
    if created:
        return
    if instance.erpnext_customer:
        return
    if not should_create_customer(instance):
        return
    create_customer_from_deal(instance)


def connect_signals() -> None:
    from crm_app.models import CRMDeal

    post_save.connect(on_deal_saved, sender=CRMDeal, dispatch_uid="crm.erpnext.deal")
