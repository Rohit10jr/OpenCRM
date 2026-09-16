# SETTINGS — CRM settings, email accounts, and the Desk plumbing calls

**Status: Provisional, 2026-09-16.** Written before FOUNDATION exists: the scope is right,
the details are guesses. **Rewrite against `backend_v2/docs/AS_BUILT.md` before running.**
Paths are from the repository root.

## 1. Scope

App `crm_settings`. The `PORT_MAP.md` rows under **SETTINGS**:

- **Doctypes:** FCRM Settings (singleton), Email Account, CRM Dropdown Item (child of FCRM
  Settings)
- **Method paths (7):** `crm.api.settings.create_email_account`,
  `crm.api.exchange_rate.get_exchange_rate`, `crm.api.get_translations` (guest),
  `crm.demo.api.clear_demo_data`, and the Desk plumbing calls `frappe.apps.get_apps`,
  `frappecloud_billing.current_site_info`, `telemetry.pulse.client.boot_config`

## 2. Depends on

FOUNDATION.

## 3. Read in `backend/` first

- `crm_app/api/settings.py`, `api/exchange_rate.py`, `api/desk.py`, `api/demo.py`,
  `api/misc.py` (translations)
- `crm_app/models/metadata.py` (FCRM Settings, dropdown items),
  `frappe_platform/models.py` (Email Account), `crm_app/permissions/metadata_docs.py`,
  `permissions/platform_docs.py`
- `frappe_core/mail.py` — SMTP validation with its timeout; `frappe_core/secrets.py`
- `specs/SECURITY_MODEL.md` — sections `Email Account` and "Integration settings"
- Tests: `test_email_account_access.py`, `test_settings_access.py`,
  `test_mail_validation.py`, `test_desk_plumbing.py`

## 4. Must not be lost

- **FCRM Settings:** every user reads it — the timeline reads it on every screen — and
  only managers write it. **`access_key` is restricted to managers** (upstream bug #20:
  upstream hands an exchange-rate credential to every user).
- **Email Account:** everyone may read the record, because the Profile screen's "send
  from" picker lists accounts for every user (a deliberate divergence, upstream bug #17).
  System Manager and Sales Manager create, write and delete. `password` and `api_secret`
  are **hidden and encrypted**; the server, port, login, domain, key and signature
  fields are **restricted to managers**. Hiding the password alone once let it be
  recovered through a filter; hiding it without a write rule once let anyone repoint the
  server it belonged to.
- **Validating a mail server times out after 10 seconds** (upstream bug #15: upstream
  hangs the save).
- **`get_apps` is role-gated. `current_site_info` answers `{}`** — this can never be a
  Frappe Cloud site. **`boot_config`** reports telemetry enabled only when both PostHog
  settings are present. **`clear_demo_data`** checks the role, then returns early:
  demo seeding was never ported.

## 5. Acceptance

- pytest for each item in section 4.
- `docs/http/12_settings_singletons.http` (its telephony and integration blocks excepted
  until those units exist), and the settings and plumbing blocks of `13_bulk_and_misc.http`.
- The body diff over the same blocks.

## 6. Open questions

None yet.
