# TELEPHONY — call logs, agents, Twilio and Exotel

**Status: Provisional, 2026-09-16.** Written before FOUNDATION exists: the scope is right,
the details are guesses. **Rewrite against `backend_v2/docs/AS_BUILT.md` before running.**
Paths are from the repository root.

## 1. Scope

App `telephony`. Both providers stay behind `ENABLE_TWILIO` and `ENABLE_EXOTEL`, off by
default — but logging a call by hand works with neither configured. The `PORT_MAP.md`
rows under **TELEPHONY**:

- **Doctypes:** CRM Call Log, CRM Telephony Agent, CRM Twilio Settings (singleton),
  CRM Exotel Settings (singleton); child table CRM Telephony Phone
- **Method paths (17):** the call-log calls (`get_call_log`,
  `create_lead_from_call_log`); `crm.integrations.api.*` (notes and tasks on a call,
  phone-number lookups, calling medium); Exotel (`make_a_call`, `is_integration_enabled`,
  and the `handle_request` webhook); Twilio (`generate_access_token`, `is_enabled`, and
  the four webhooks `voice`, `twilio_incoming_call_handler`, `update_call_status_info`,
  `update_recording_info`)
- **The list definition** for Call Log

## 2. Depends on

SALES (a call resolves to a lead, deal or contact), ACTIVITIES (notes and tasks on a
call).

## 3. Read in `backend/` first

- `crm_app/models/telephony.py`, `crm_app/api/call_log.py`
- `crm_app/integrations/api.py`, `integrations/call_log.py`, `integrations/phone.py`,
  `integrations/http.py`
- `crm_app/integrations/twilio/`, `crm_app/integrations/exotel/`
- `specs/SECURITY_MODEL.md` — "Integration settings" and the Exotel known gap
- `specs/PHASE_7_INTEGRATIONS.md`, `docs/internal/PROGRESS_PHASE_7.md`
- Tests: `test_twilio.py`, `test_exotel.py`, `test_telephony_shared.py`,
  `test_call_log_endpoints.py`, `test_integration_isolation.py`

## 4. Must not be lost

- **Twilio webhooks verify the signature from the real request** — the absolute URL and
  the header. The first port took them as ordinary parameters, so the check passed in
  tests and **rejected every real webhook**.
- **Exotel compares its webhook token in constant time, and refuses when none is set.**
- **The settings rows are manager-only, reads included.** `api_secret`, `auth_token` and
  `api_token` are hidden and encrypted; `api_key`, `twiml_sid`, `account_sid` and
  `webhook_verify_token` are restricted. `webhook_verify_token` is plaintext at rest — a
  recorded gap, because the settings screen edits it as text.
- **The divergences recorded as upstream bugs #26 (Exotel) and #27 (Twilio) are kept.**
- **`get_recording_url` is deliberately not ported.** It is a server-side fetch of a URL
  from a provider; port it only with upstream's IP pinning and per-hop redirect
  validation, or not at all.
- **Every outbound HTTP call has a timeout** (upstream bugs #15 and #24).
- **No provider SDK is a dependency**, and nothing imports one when the flags are off.
- **`create_lead_from_call_log` answers 404 for a missing call before checking write
  permission**, and ignores standard fields in the lead details.
- **CRM Call Log and CRM Telephony Agent are open to every authenticated user today**,
  with questions still owed (`PARITY_EXCEPTIONS.md`).

## 5. Acceptance

- pytest for each item in section 4, the webhooks with real signed requests.
- The call blocks of `docs/http/06_tasks_notes_calls.http`, which then turns green; the
  telephony blocks of `12_settings_singletons.http`.
- The body diff over the same blocks.

## 6. Open questions

- O3 for CRM Call Log and CRM Telephony Agent.
