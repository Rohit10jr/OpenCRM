"""ERPNext — behind `ENABLE_ERPNEXT`.

Ports `crm/fcrm/doctype/erpnext_crm_settings/` and `crm/integrations/erpnext/`.

## Only the remote path is in scope, and that follows from the standing decision

`RUNBOOK_PHASE_7.md`: *"ERPNext is an API client. You are integrating with a live ERPNext
instance over HTTP. You are **not** reimplementing ERPNext's models — that is explicitly out
of scope. If the work seems to require porting `Item` or `Sales Order`, you have taken a
wrong turn; log it and reduce scope."*

Upstream supports two modes, and the flag `is_erpnext_in_different_site` selects between
them:

* **Different site** — talk to ERPNext over its REST API. *This is what is ported.*
* **Same site** — ERPNext is installed as another app in the same Frappe bench, so upstream
  reaches directly into `Item`, `Quotation`, `Sales Order`, `Customer`, `Territory` and
  `Industry Type`, and mutates their schema through `Custom Field`, `Property Setter` and
  role grants.

The same-site mode is not a thing this port can have: it presupposes ERPNext's models and
Frappe's runtime-schema machinery in this process, which is exactly what the decision rules
out. So `is_erpnext_in_different_site` defaults to True here and the same-site branches are
**not ported** — they refuse with a message naming the reason rather than silently doing
nothing. What that costs is listed in the progress file.

That single fact removes roughly two-thirds of `erpnext_crm_settings.py`'s 690 lines from
scope, and it removes them for a reason rather than for time.

## What is ported

* the settings singleton and its child `CRM Product Sync Issue`
* the API client (`client.py`) — token auth, timeout, retry, through
  `crm_app.integrations.http`
* the endpoints that make sense over an API: company list, customer link, quotation URL,
  quotation item prefill, the sync-issue endpoints
* customer creation when a deal reaches the configured status, and the
  `crm_customer_created` event phase 6 named
* `_reconcile_products`, the seam phase 5 left — which finally gives
  `crm_product_sync_complete` a live caller (`KNOWN_ISSUES.md` §5 notes it had none)
"""
