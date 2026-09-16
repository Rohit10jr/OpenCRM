# INTEGRATIONS — ERPNext, Facebook lead sync, WhatsApp

**Status: Provisional, 2026-09-16.** Written before FOUNDATION exists: the scope is right,
the details are guesses. **Rewrite against `backend_v2/docs/AS_BUILT.md` before running.**
Paths are from the repository root.

## 1. Scope

App `integrations`. Every integration stays behind its flag — `ENABLE_ERPNEXT`,
`ENABLE_FACEBOOK_LEAD_SYNC`, `ENABLE_WHATSAPP` — **off by default**, which is why this
unit comes last. The `PORT_MAP.md` rows under **INTEGRATIONS**:

- **Doctypes:** ERPNext CRM Settings (singleton), Facebook Page, Facebook Lead Form,
  Lead Sync Source, Failed Lead Sync Log, WhatsApp Message; child tables CRM Product Sync
  Issue, Facebook Lead Form Question
- **Method paths (15):** the nine `erpnext_crm_settings.*` calls and the six
  `crm.api.whatsapp.*` calls
- **Scheduled work:** the four lead-sync jobs (every five minutes, hourly, daily,
  monthly), each a no-op behind its flag (`backend/config/celery.py`)

## 2. Depends on

SALES (synced leads, quoted deals), ACTIVITIES (WhatsApp messages sit on the timeline),
TELEPHONY (the shared phone-number resolution).

## 3. Read in `backend/` first

- `crm_app/models/erpnext_integration.py`, `models/lead_syncing.py`, `models/whatsapp.py`
- `crm_app/integrations/erpnext/`, `integrations/facebook/`, `integrations/whatsapp/`,
  `integrations/http.py`
- `crm_app/permissions/attachments.py` (WhatsApp Message)
- `specs/SECURITY_MODEL.md` — "Phase 7 — the integration doctypes"
- `specs/PHASE_7_INTEGRATIONS.md`, `docs/internal/PROGRESS_PHASE_7.md`
- `docs/UPSTREAM_BUGS_PHASE_3-6.md` #28–#33
- Tests: `test_erpnext.py`, `test_facebook_lead_sync.py`, `test_whatsapp.py`,
  `test_integration_isolation.py`, `test_phase7_review_fixes.py`

## 4. Must not be lost

- **Every configuration doctype is manager-only, reads included.** They back
  administration screens.
- **Credentials are hidden and encrypted:** ERPNext's `api_secret`, Lead Sync Source's and
  Facebook Page's `access_token` — the page token is plain text upstream (bug #28).
  ERPNext's `api_key` and site URL are restricted.
- **Failed Lead Sync Log holds a real person's details** from a lead that failed to
  import, with no CRM document to protect it. It stays manager-only.
- **Facebook Lead Form is ruled even though it holds no secret**, so the feature's four
  doctypes read as one decision.
- **WhatsApp Message defers to the document it belongs to**, like Comment, with the
  destination re-check on update.
- **Every outbound call has a timeout; no provider SDK is a dependency; nothing imports
  one with the flags off.**
- **Each divergence in upstream bugs #28–#33 is kept as recorded.**

## 5. Acceptance

- pytest for each item in section 4; external APIs faked at the HTTP boundary.
- The integration blocks of `docs/http/12_settings_singletons.http`, which then turns
  green.
- The body diff over the same blocks.

## 6. Open questions

None yet.
