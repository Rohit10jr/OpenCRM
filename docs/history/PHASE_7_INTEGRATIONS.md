# Phase 7 — Integrations

> **BUILT** — phase 7 landed on `phase-7-integrations`, 1574 tests passing, reviewed twice
> at tier 1. See `docs/internal/PROGRESS_PHASE_7.md`.
>
> **Two scope reductions are recorded there and are deliberate**, not omissions: ERPNext's
> *same-site* mode is not ported (it presupposes ERPNext's models in this process, which the
> standing decision rules out), and `get_recording_url` — the SSRF-safe recording proxy — is
> left for its own change. Port it **with** upstream's IP pinning and per-hop redirect
> validation, or not at all.

**Fan out — the four integrations are fully independent.**

~2,300 LOC of external-service glue. This is the single largest chunk of *deferrable*
work in the port, and none of it is needed for a working CRM.

---

## 1. Scope

| Integration | Source | LOC | Notes |
|---|---|---|---|
| **ERPNext** | `integrations/erpnext/`, `erpnext_crm_settings.py` | ~1,300 | Largest. 12 endpoints, 690 LOC controller |
| **Twilio** | `integrations/twilio/`, `crm_twilio_settings` | ~250 | Voice, webhooks |
| **Exotel** | `integrations/exotel/`, `crm_exotel_settings` | ~200 | Voice, webhooks |
| **Facebook lead sync** | `lead_syncing/`, `facebook_*` doctypes | ~550 | Six scheduled jobs |
| **WhatsApp** | `api/whatsapp.py` (6 endpoints) | ~200 | Needs the separate `frappe_whatsapp` app |

---

## 2. Per-integration notes

### ERPNext
Bidirectional sync of Customer, Item, Sales Order, Quotation. Hooks into **ERPNext's
own doctypes** (`Item`, `Sales Order`, `User Permission`, `DocShare`) via `doc_events`
— meaning it assumes a live ERPNext site on the other end.

Decide first: are you integrating with a **real ERPNext instance** (then this is an
API client) or reimplementing ERPNext models too (then it is out of scope entirely)?
Almost certainly the former. Also emits `crm_customer_created` (phase 6).

### Twilio / Exotel
Both follow the same shape: settings singleton, outbound call API, inbound webhook,
call-log write into `crm_call_log`, realtime push. Port the shared call-log path once;
keep the provider adapters separate.

Webhooks need **public endpoints with signature verification**. Do not skip signature
verification because it is inconvenient in dev — use ngrok or the provider's test mode.

### Facebook lead sync
`lead_sync_source` polls Facebook Lead Ads on six schedules (phase 5 §1) and writes
`crm_lead` rows, logging failures to `failed_lead_sync_log`. Needs Meta app
credentials and long-lived page tokens; token refresh is its own failure mode. Retry
and dedupe are essential — re-syncing must not create duplicate leads.

### WhatsApp
Depends on `frappe_whatsapp`, a **separate Frappe app not in this repo**. You are
reimplementing its message model too, not just calling it. Scope accordingly, or drop.

---

## 3. Rules

- Every integration behind its own flag, **off by default**
- The CRM must be fully functional with all four disabled — no import-time coupling
- Never commit credentials; settings singletons hold encrypted fields
- Every outbound call gets a timeout and a retry policy
- Failures degrade gracefully — an unreachable provider must never break lead or deal CRUD
- Webhooks: verify signatures, dedupe by provider message ID, respond fast and process async

---

## 4. Acceptance criteria

- [ ] All flags off → full test suite passes, no integration code imported
- [ ] Each integration enables independently
- [ ] Webhook signatures verified; unsigned requests rejected
- [ ] Credentials encrypted at rest, absent from logs
- [ ] Provider outage does not break core CRUD
- [ ] Lead sync is idempotent — re-running creates no duplicates
- [ ] Call logs land in `crm_call_log` identically for both providers
