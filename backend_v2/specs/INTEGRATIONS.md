# INTEGRATIONS — Twilio, Exotel, ERPNext, Facebook lead sync, WhatsApp

**Status: Provisional** — the scope is right, the details are guesses. **Rewrite against
`backend_v2/docs/AS_BUILT.md` before building.** Paths are from the repository root.

## 1. Scope

App `integrations`: every outside service. Each stays behind its flag — `ENABLE_TWILIO`,
`ENABLE_EXOTEL`, `ENABLE_ERPNEXT`, `ENABLE_FACEBOOK_LEAD_SYNC`, `ENABLE_WHATSAPP` — **off by
default**, which is why this unit comes last. The `PORT_MAP.md` rows under
**INTEGRATIONS**:

- **Telephony providers:** CRM Twilio Settings and CRM Exotel Settings (singletons), CRM
  Telephony Agent and its CRM Telephony Phone rows; Exotel (`make_a_call`,
  `is_integration_enabled`, the `handle_request` webhook), Twilio (`generate_access_token`,
  `is_enabled`, the webhooks `voice`, `twilio_incoming_call_handler`,
  `update_call_status_info`, `update_recording_info`), and
  `crm.integrations.api.is_call_integration_enabled` / `set_default_calling_medium`
- **ERPNext:** ERPNext CRM Settings (singleton) and its CRM Product Sync Issue rows; the nine
  `erpnext_crm_settings.*` calls
- **Facebook lead sync:** Facebook Page, Facebook Lead Form and its questions, Lead Sync
  Source, Failed Lead Sync Log; the four scheduled sync jobs (every five minutes, hourly,
  daily, monthly), each a no-op behind its flag (`backend/config/celery.py`)
- **WhatsApp:** WhatsApp Message; the six `crm.api.whatsapp.*` calls

The call logs themselves are in ACTIVITIES: logging a call works without any provider.

**WhatsApp is ported for parity, behind its flag.** Whether the business will use it is
an open question for the owner; it does not block this unit.

## 2. Depends on

SALES (synced leads, quoted deals), ACTIVITIES (call logs, and WhatsApp messages on the
timeline).

## 3. Read in `backend/` first

- `crm_app/models/telephony.py` (agents and provider settings),
  `crm_app/models/erpnext_integration.py`, `models/lead_syncing.py`, `models/whatsapp.py`
- `crm_app/integrations/twilio/`, `integrations/exotel/`, the provider parts of
  `integrations/api.py`, `integrations/erpnext/`, `integrations/facebook/`,
  `integrations/whatsapp/`, `integrations/http.py`
- `crm_app/permissions/attachments.py` (WhatsApp Message)
- `specs/SECURITY_MODEL.md` — "Integration settings", the Exotel known gap, and "Phase 7 —
  the integration doctypes"
- `docs/history/PHASE_7_INTEGRATIONS.md`, `docs/history/PROGRESS_PHASE_7.md`
- `UPSTREAM_BUGS.md` #26–#33
- Tests to read and write again: `test_twilio.py`, `test_exotel.py`, `test_erpnext.py`,
  `test_facebook_lead_sync.py`, `test_whatsapp.py`, `test_integration_isolation.py`,
  `test_phase7_review_fixes.py`
- **Tests to port** (REBUILD_PLAN S14): this unit's routes in `test_phase3_endpoints.py`;
  the integration tests above call internals, not the test client. The spec check
  confirms the list.

## 4. Must not be lost

**Telephony providers**

- **Twilio webhooks verify the signature from the real request** — the absolute URL and
  the header. The first port took them as ordinary parameters, so the check passed in
  tests and **rejected every real webhook**.
- **Exotel compares its webhook token in constant time, and refuses when none is set.**
- **The provider settings are manager-only, reads included.** `api_secret`, `auth_token`
  and `api_token` are hidden and encrypted; `api_key`, `twiml_sid`, `account_sid` and
  `webhook_verify_token` are restricted. `webhook_verify_token` is plaintext at rest — a
  recorded gap, because the settings screen edits it as text.
- **`get_recording_url` is deliberately not ported.** It is a server-side fetch of a URL
  from a provider; port it only with upstream's IP pinning and per-hop redirect
  validation, or not at all.
- **CRM Telephony Agent is open to every CRM role**, reviewed and kept as upstream's role
  table grants (REBUILD_PLAN S21).
- **Moving a webhook to its new route also means updating the provider's console.**

**ERPNext, Facebook, WhatsApp**

- **Every configuration doctype is manager-only, reads included.** They back
  administration screens.
- **Credentials are hidden and encrypted:** ERPNext's `api_secret`, Lead Sync Source's and
  Facebook Page's `access_token` — the page token is plain text upstream (bug #28).
  ERPNext's `api_key` and site URL are restricted.
- **Failed Lead Sync Log holds a real person's details** from a lead that failed to
  import, with no CRM record to protect it. It stays manager-only.
- **Facebook Lead Form is ruled even though it holds no secret**, so the feature's four
  doctypes read as one decision.
- **WhatsApp Message defers to the record it belongs to**, like Comment, with the
  destination re-check on update.

**All of them**

- **Every outbound call has a timeout** (upstream bugs #15 and #24); **no provider SDK is
  a dependency**; nothing imports one with the flags off.
- **Each divergence in upstream bugs #26–#33 is kept as recorded.**

## 5. Acceptance

- pytest: the ported tests passing with their expected answers unchanged, and new tests
  for each item in section 4 — the webhooks with real signed requests, external APIs
  faked at the HTTP boundary.
- `docs/http/12_settings_singletons.http` in full.
- The body comparison over the same blocks.

## 6. Open questions

None yet.
