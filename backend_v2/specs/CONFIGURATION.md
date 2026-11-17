# CONFIGURATION — CRM settings, email accounts, saved views, layouts and the list engine

**Status: Provisional** — the scope is right, the details are guesses. **Rewrite against
`backend_v2/docs/AS_BUILT.md` before building.** Paths are from the repository root.

## 1. Scope

App `configuration`: everything an admin configures, plus the list engine that reads it.
The `PORT_MAP.md` rows under **CONFIGURATION**:

- **Settings:** FCRM Settings (singleton) and its CRM Dropdown Item rows, Email Account;
  `crm.api.settings.create_email_account`, `crm.api.exchange_rate.get_exchange_rate`,
  `crm.api.get_translations` (guest), `crm.demo.api.clear_demo_data`, and the Desk plumbing
  calls `frappe.apps.get_apps`, `frappecloud_billing.current_site_info`,
  `telemetry.pulse.client.boot_config`.
- **Views and layouts — the keystone:** CRM View Settings (integer key), CRM Fields Layout,
  CRM Form Script, CRM Global Settings, and the per-user list settings model;
  `crm.api.doc.get_data` (six screens render from it), the field and filter helpers
  (`get_fields`, `get_filterable_fields`, `get_group_by_fields`, `get_quick_filters`,
  `update_quick_filters`, `sort_options`), `crm.api.views.get_views`, the eight
  `crm_view_settings.*` calls, the three `crm_fields_layout.*` calls,
  `frappe.desk.form.load.getdoctype`, `frappe.model.utils.user_settings.get` and `save`.
- **System and reference data:** System Settings (singleton), Country, Currency and
  Language; the boot values `crm.www.crm.get_context_for_dev` (guest), and the onboarding
  status calls `frappe.onboarding.get_onboarding_status` and
  `update_user_onboarding_status`.
- **The list-view and field-metadata mixins** (REBUILD_PLAN S24), which each resource opts
  in to.

## 2. Depends on

FOUNDATION. It is built **before** the CRM doctypes exist, so the list engine is tested
against the test-only resources. Each CRM app later supplies its own list definition —
default columns and rows, kanban settings, fields that cannot be filtered — through the
convention this unit sets and records in `AS_BUILT.md`.

## 3. Read in `backend/` first

- **Settings:** `crm_app/api/settings.py`, `api/exchange_rate.py`, `api/desk.py`,
  `api/demo.py`, `api/misc.py` (translations); `crm_app/models/metadata.py` (FCRM
  Settings, dropdown items), `frappe_platform/models.py` (Email Account);
  `frappe_core/mail.py` (SMTP validation and its timeout), `frappe_core/secrets.py`
- **Views and the list engine:** `frappe_core/api/doc.py` (`get_data` itself),
  `crm_app/api/doc.py`, `api/views.py`, `api/view_settings.py`, `api/fields_layout.py`,
  `api/form_load.py`, `api/user_settings.py`, `api/form_script.py`;
  `frappe_core/metadata.py`, `frappe_core/field_meta.py`, `crm_app/metadata_hooks.py`;
  `crm_app/data/doctype_meta.json` and `backend/scripts/generate_field_meta.py`, which
  builds it from the upstream DocType JSON
- **System and reference data:** `crm_app/api/boot.py`, `api/onboarding.py`,
  `frappe_platform/reference_data.py`, `crm_app/data/country_info.json` (the version-15
  copy, not `develop`'s — finding 90), `crm_app/data/languages.csv`
- **Rules:** `crm_app/permissions/metadata_docs.py`, `permissions/platform_docs.py`
- `specs/SECURITY_MODEL.md` — sections `Email Account` and "Integration settings";
  `PORT_PLAN.md` section 4, trap 2 — views and layouts are runtime data, not code
- Tests to read and write again: `test_email_account_access.py`,
  `test_settings_access.py`, `test_mail_validation.py`, `test_get_data.py`,
  `test_list_definitions.py`, `test_kanban_counts.py`, `test_onboarding_status.py`
- **Tests to port** (REBUILD_PLAN S14): `test_desk_plumbing.py`, `test_form_load.py`,
  `test_phase4_metadata.py`, `test_boot.py`, `test_currency.py`, `test_language.py`,
  `test_system_settings.py`, and this unit's routes in `test_phase3_endpoints.py`. The
  spec check confirms the list.

## 4. Must not be lost

**Settings**

- **FCRM Settings:** every user reads it — the timeline reads it on every screen — and
  only managers write it. **`access_key` is restricted to managers** (upstream bug #20:
  upstream hands an exchange-rate credential to every user).
- **Email Account:** everyone may read the record, because the Profile screen's "send
  from" picker lists accounts for every user (a deliberate divergence, upstream bug #17).
  System Manager and Sales Manager create, write and delete. `password` and `api_secret`
  are **hidden and encrypted**; the server, port, login, domain, key and signature fields
  are **restricted to managers**. Hiding the password alone once let it be recovered
  through a filter; hiding it without a write rule once let anyone repoint the server.
- **Validating a mail server times out after 10 seconds** (upstream bug #15: upstream
  hangs the save).
- **`get_apps` is role-gated. `current_site_info` answers `{}`** — this can never be a
  Frappe Cloud site. **`boot_config`** reports telemetry enabled only when both PostHog
  settings are present. **`clear_demo_data`** checks the role, then returns early.

**Views and the list engine**

- **`get_data`'s response shape**, and every key in it even when its value is empty.
- **It reads through the resource's own queryset and field rules** — one of the doors in
  the root `CLAUDE.md`, rebuild hard rule 6.
- **Kanban counts do not leak** rows the caller cannot read.
- **A public view is readable by everyone and deletable only by its owner.** The list rule
  and the object rule differ here on purpose.
- **A kanban column per user is built from every user**, as upstream builds it without a
  permission check; that is why `User` reads stay open.
- **`getdoctype` puts `docs` and `user_settings` beside `message`.** frappe-ui returns the
  whole body when `docs` is present.
- **The field metadata file is generated, and a test fails if it goes stale.**

## 5. Acceptance

- pytest: every test in the port list passing with its expected answers unchanged; new
  tests for each item in section 4 no old test covers; the list engine on test-only
  resources; each saved-view permission shown failing without its rule.
- The settings blocks of `docs/http/12_settings_singletons.http` (its integration blocks
  wait on INTEGRATIONS), the settings and plumbing blocks of `13_bulk_and_misc.http`, and
  the blocks of `07_views_and_metadata.http` this unit owns — the file turns green once
  ACTIVITIES exists.
- The body comparison over the same blocks.

## 6. Open questions

None. Where a CRM app declares its list definition is settled with FOUNDATION's
questions (FOUNDATION section 6).

## 7. Carried from SHARED_ACTIONS

Opt the resources below in to the `core/mixins/` actions (AS_BUILT §2, "Opting a
resource in to a shared action"), write each generated route's row in `PORT_MAP.md`,
and port the real-doctype cases SHARED_ACTIONS left (its §3 table). Their generic
mechanism is tested on `tests_support`; the cases below prove it on real records.

- **List export's column labels and fieldtypes.** `core/mixins/export.py:field_info`
  uses field names and `Data` as a marked placeholder: `backend_v2` has no source
  for the old DocType labels (`backend/crm_app/api/reportview.py:field_info` reads
  `frappe_core.field_meta`). The field metadata this unit builds must replace it, and
  Duration formatting then activates. No resource should opt in to export before.
- `test_bulk_edit_fields.py` (`crm.api.doc.get_fields`) is this unit's, not
  SHARED_ACTIONS'.
- Email Account opts in to rename (`EmailEdit.vue:191-196`; moved here from
  INTEGRATIONS by the milestone-2 review, A-12): its `PORT_MAP.md` row, an allowed
  and a write-denied rename case on real Email Accounts.
- Language keeps `language_name` (its `SEARCH_FIELD`) in its readable and filterable
  fields: link search drops a `SEARCH_FIELD` that is hidden or outside the
  allowlists (A-12).

## 8. Carried from ACCOUNTS

Moved here by ACCOUNTS' spec rewrite (`temp` A-21 D-D, 18 Nov 2026; flagged for the owner).

- **User Email**, with Email Account: the child model (`backend/frappe_platform/models.py:1491-1554`),
  the Email Account `post_save` hook that fills it, `User.PRIVILEGED_WRITE_FIELDS =
  ("user_emails",)` (System Manager only, old `:248-249`) and `test_user_emails.py`. Until
  then a User document returns `user_emails: []` and drops an incoming `user_emails`;
  make it return the rows (`backend/frappe_core/children.py:38-51`,
  `serializers.py:125-129`) and accept the privileged write.
- **`get_user_signature`'s fallback**: with no `email_signature`, the default outgoing
  Email Account's signature when `add_signature` is set (`backend/crm_app/api/misc.py:62-67`).
- **The outgoing-account lookup**: add the Email Account steps of
  `backend/crm_app/communication.py:find_outgoing_account` (`:400-440`) to the carrier
  ACCOUNTS built in `core`, tried **before** the settings-configured account, in the old
  order.
- **`User.default_list_data`** (the User list view, old `:309-318`), with the other list
  views.
- `test_language.py:65` and `test_onboarding_status.py` write `User` through ACCOUNTS'
  `/api/v1/users/<name>/` route.
