# CONFIGURATION — CRM settings, email accounts, saved views, layouts and the list engine

**Status: Provisional — rewritten 18 Nov 2026** from the spec check
(`tasks\CONFIGURATION_00_spec_check_verdict.md`, `temp` A-27), waiting for its spec
review. **Approval is staged** (A-27, DECISIONS 30, flagged for the owner): the facts and
the route map below cover the whole unit, but the spec review approves **milestones 1
and 2 only**; each later milestone needs the decisions marked "open" in §6 settled and a
short spec-review addendum before its first brief. Paths are from the repository root;
`backend/` is read at `main` `8f5ff1b`.

## 1. Scope

App `configuration`: everything an admin configures, plus the list engine that reads it.
Every row is in `PORT_MAP.md` under CONFIGURATION, with its New route.

**Doctypes (12):** FCRM Settings (singleton) and its child CRM Dropdown Item; Email
Account and its child User Email (moved here from ACCOUNTS); CRM View Settings (integer
key); CRM Fields Layout; CRM Form Script; CRM Global Settings; System Settings
(singleton); Country; Currency; Language. Plus the unrouted per-user list-settings model
(`frappe_platform.UserSettings`, not a doctype).

**Method paths (32):** the five Desk calls (`frappe.apps.get_apps`,
`frappecloud_billing.current_site_info`, `telemetry.pulse.client.boot_config`,
`crm.demo.api.clear_demo_data`, `crm.api.get_translations`); boot and onboarding
(`crm.www.crm.get_context_for_dev`, `frappe.onboarding.get_onboarding_status`,
`update_user_onboarding_status`); settings (`crm.api.settings.create_email_account`,
`crm.api.exchange_rate.get_exchange_rate`); field metadata (`crm.api.doc.get_fields`,
`get_filterable_fields`, `get_group_by_fields`, `sort_options`,
`frappe.desk.form.load.getdoctype`, `frappe.model.utils.user_settings.get`/`save`);
layouts and quick filters (the three `crm_fields_layout.*` calls, `get_quick_filters`,
`update_quick_filters`); saved views (`crm.api.views.get_views` and the eight
`crm_view_settings.*` calls); the list engine (`crm.api.doc.get_data`, in
`backend/frappe_core/api/doc.py`, not `crm_app/api/doc.py`).

**Routes** (`PORT_MAP.md`, REBUILD_PLAN S25 and `REBUILD_PLAN.md:174-176`): field
metadata, saved views and `getdoctype` keep `doctype` as an input; everything else has a
per-resource or per-purpose route. The list engine is a mixin each resource opts in to
(`<resource>/list-view/`, S24).

## 2. Depends on

FOUNDATION, SHARED_ACTIONS (rename, link search, export's field-info hook), ACCOUNTS
(roles, `User`, `user_emails`, the signature, `core/mail.py`'s carrier). Pieces of later
units this unit's engine reads (spec check finding 7):

- **Kanban badge counts** read Communication, Comment, CRM Task, FCRM Note
  (`backend/frappe_core/api/doc.py:564-598`): ACTIVITIES' models.
- **`get_exchange_rate`** sends through `crm_app/integrations/http.py`: an outbound HTTP
  helper `backend_v2` does not have yet (decision 5).
- **`doctype_meta.json`** holds 39 doctypes, 33 of them other units'; the old backend
  decides "doctype exists" from its registry (decision 2).
- **The default layouts, quick filters and form scripts** `backend/crm_app/setup.py`
  seeds name Lead, Deal, Contact, Organization, Task.

So milestones 1-4 gate on what exists; 5-8 gate on `tests_support`, `User` and this
unit's own doctypes, and their real gate is SALES and ACTIVITIES (§9).

## 3. Read in `backend/` first

- **Desk:** `crm_app/api/desk.py:41-185` (without `get_timezones`), `api/demo.py`,
  `api/misc.py:31-39`
- **Boot, onboarding, reference data:** `crm_app/api/boot.py`, `api/onboarding.py:43-85`,
  `frappe_platform/reference_data.py`, `crm_app/data/country_info.json` (the version-15
  copy), `crm_app/data/languages.csv`, `crm_app/setup.py` (`:374`, `:397`), migrations
  `frappe_platform` 0017 (currencies) and 0019 (System Settings),
  `frappe_platform/models.py:1667` (Language), `:1806-1839` (System Settings)
- **Settings:** `crm_app/api/settings.py:70-156`, `api/exchange_rate.py`,
  `crm_app/integrations/http.py`, `management/commands/refresh_exchange_rates.py`,
  `crm_app/models/metadata.py:360-491` (FCRM Settings, dropdown items),
  `frappe_platform/models.py:1440-1554` (Email Account, User Email),
  `frappe_core/mail.py`, `frappe_core/field_security.py`
- **Field metadata, layouts, views, the engine:** `frappe_core/api/doc.py`,
  `crm_app/api/doc.py`, `api/views.py`, `api/view_settings.py`, `api/fields_layout.py`,
  `api/form_load.py`, `api/user_settings.py`, `api/form_script.py`,
  `frappe_core/metadata.py`, `frappe_core/field_meta.py`, `frappe_core/registry.py:85-137`
  (the six per-model list hooks), `crm_app/metadata_hooks.py`,
  `crm_app/data/doctype_meta.json`, `backend/scripts/generate_field_meta.py`
- **Mail carrier:** `crm_app/communication.py:350-442`, `:589`
- **Rules:** `crm_app/permissions/metadata_docs.py`, `permissions/platform_docs.py`
- `specs/SECURITY_MODEL.md` (`Email Account`, "Integration settings")

### Tests (REBUILD_PLAN S14)

| File | Kind | Here | Later-unit dependency |
|---|---|---|---|
| `test_desk_plumbing.py` | API | all but `:108`, `:125` (ACCOUNTS, done) — milestone 1 | none |
| `test_boot.py` | API | milestone 2; `:110` imports a source scan from `test_phase3_endpoints` | none |
| `test_system_settings.py`, `test_language.py`, `test_onboarding_status.py` | API | milestone 2 | none (User through ACCOUNTS) |
| `test_currency.py` | API + internal | milestone 2, without the organization and dashboard cases | CONTACTS, DASHBOARD |
| `test_dropdown_items.py` | internal + 1 API | milestone 3 | none |
| `test_settings_access.py` | API | `:129-185` (FCRM Settings) — milestone 3; the rest INTEGRATIONS | none |
| `test_exchange_rate.py` | internal | the provider cases — milestone 3 | the deal, organization, dashboard cases: SALES, CONTACTS, DASHBOARD |
| `test_email_account_access.py`, `test_email_account_setup.py`, `test_mail_validation.py`, `test_user_emails.py`, `test_phase5_async.py:377` | API / internal | milestone 4 | none |
| `test_bulk_edit_fields.py`, `test_form_load.py` | API | milestone 5 | name CRM Task, Deal, Contacts, Call Log as data |
| `test_phase4_metadata.py` | mixed, 63 tests | the metadata cases `:37-186` (5), layouts `:446-536`, `:832-890` (6), views `:213-236`, `:551-699`, `:778-817` (7), the rest (8) | most name CRM Lead: SALES |
| `test_phase3_endpoints.py:1078-1106` | API | quick filters — milestone 6 | name CRM Lead and Task |
| `test_get_data.py` | internal (`tests_support`) | milestone 8, rewritten | none |
| `test_kanban_counts.py`, `test_kanban_defaults.py`, `test_list_definitions.py` | internal | the engine half — milestone 8 | the definitions: SALES, ACTIVITIES |
| `test_seed_defaults.py` | internal | this unit's seeds, per milestone | Lead/Deal statuses, industries, sources |
| `test_mail_config_account.py:262` | API | **not here**: posts `email.make` on a lead — ACTIVITIES (a unit test of the lookup steps stays here) | SALES, ACTIVITIES |

## 4. Must not be lost

### 4.1 Desk plumbing (milestone 1)

- **`get_apps`**: `[{"name": "crm", "logo": "/assets/crm/images/logo.svg", "title":
  "CRM", "route": "/crm"}]` for Administrator or any of System Manager, Sales Manager,
  Sales User; **`[]`, not 403**, for anyone else (`desk.py:24-75`).
- **`current_site_info`**: Administrator or System Manager, else 403 "Not permitted";
  answers `{}` (`desk.py:127-158`).
- **`boot_config`**: `{"enabled": true}` only when both `POSTHOG_PROJECT_ID` and
  `POSTHOG_HOST` are set, else `{"enabled": false}` (`desk.py:161-185`); any authenticated
  caller.
- **`clear_demo_data`**: POST only; Administrator, Sales Manager or System Manager, else
  the refusal "This action is only allowed for <strong>Sales Manager</strong>,
  <strong>System Manager</strong>", title "Not Permitted"; then returns early with nothing
  cleared (`demo.py:55-63`).
- **`get_translations`**: guest; answers `{}` (`misc.py:31-39`).

### 4.2 Reference data, boot and onboarding (milestone 2)

- **Rules** (`platform_docs.py`): Country and Language are read by everyone and written
  by System Manager (`:458-498`); Currency is read only by the five listed roles, so a
  caller with none gets an empty list (`:504-529`); System Settings is System Manager
  only, **reads included**, and nobody deletes it (`:532-551`).
- **Language** keeps `language_name`, its `SEARCH_FIELD`, readable and filterable (link
  search, §7).
- **`get_context_for_dev`**: guest, POST only, exactly eight keys — `sysdefaults` (always
  a dict with `date_format`), `timezone` `{"system", "user"}` (the caller's `time_zone`,
  else the system zone; a guest gets the system zone twice), `translated_messages` `{}`,
  `translated_doctypes` `[]`, `state_options` `{}`, and `is_demo_site`,
  `demo_data_created`, `is_fc_site` all false (`boot.py:41-73`). It reads System
  Settings server-side, so no permission on that doctype is needed.
- **Onboarding** (`onboarding.py:43-85`): `get_onboarding_status` answers the caller's
  `User.onboarding_status` as a dict, `{}` when unset or unreadable;
  `update_user_onboarding_status` refuses "appName is required" and "steps must be JSON",
  stores `steps` under `<appName>_onboarding_status`, keeps other apps' keys, treats an
  unset status as `{}` (upstream bug 40 not reproduced, as in `backend/`) and leaves the
  row's timestamps untouched.
- **Rows the application cannot run without** (decision 13): the countries, languages,
  currencies (nine enabled) and the System Settings row are written by a data migration
  in `configuration`, as FOUNDATION writes roles and built-in users and as `backend/`
  does (`crm_app/setup.py:374`, `:397`; migrations 0017, 0019), **not** by a dev-data step:
  `DEV_DATA_ALLOWED` does not gate them. The guest boot call therefore only reads the row;
  if it ever must create it, the actor is `Administrator` (decision 11).

### 4.3 FCRM Settings and exchange rate (milestone 3)

- Everyone reads FCRM Settings (the timeline reads it on every screen); the manager pair
  writes it (`platform_docs.py:302-315`). `access_key` is restricted to managers (upstream
  bug #20). `backend/` stores it as plain restricted text, so the credential guard
  (`tests/guards/test_model_fields.py`) gets a written, reviewed exception for it
  (decision 15).
- CRM Dropdown Item: the standard rows come from `FCRMSettings.load` and the setup data;
  `seed --force` restores them (`metadata.py:448-491`).
- **`get_exchange_rate`**: the same currency, or `ENABLE_EXCHANGE_RATE_API` off, answers
  `1`; cache key `exchange_rate_<from>_<to>_<date>` for a day, "latest" keyed by today;
  a five-second timeout, no retry; free providers fall back to each other, paid ones do
  not; four error sentences (`exchange_rate.py:160-166`, `:200-222`), one worded
  differently for managers. No `frontend/src` file calls it; its callers are the deal and
  organization saves and `refresh_exchange_rates`.

### 4.4 Email Account and User Email (milestone 4)

- Everyone reads an Email Account (the Profile picker lists them; upstream bug #17); the
  manager pair creates, writes and deletes (`platform_docs.py:158-186`). `password` and
  `api_secret` are sensitive and encrypted — in `backend_v2` with
  `core.fields.EncryptedCharField`/`EncryptedTextField` and `SENSITIVE_FIELDS`
  (AS_BUILT §2), so the model cannot be `Access.open`. The eleven restricted fields:
  `smtp_server`, `smtp_port`, `email_server`, `incoming_port`, `login_id`, `domain`,
  `api_key`, `frappe_mail_site`, `signature`, `no_smtp_authentication`,
  `awaiting_password` (`frappe_platform/models.py:1465-1477`). `api_key` gets the same
  reviewed guard exception as `access_key`.
- **`create_email_account`** (`settings.py:70-156`): one `data` object (anything else
  refuses "Invalid data"); "Email account name is required"; an unknown `service`
  **answers the string** "Service not supported" (200); Frappe Mail takes `api_key`,
  `api_secret`, `frappe_mail_site`, the others `password`; `append_to` is always CRM Lead;
  the account is validated before it is saved (`validate_email_account`, the only caller,
  `:149`), a rejected one leaves no row, any non-API exception from the mail library is a
  417 with its text; answers the account's name.
- **Validation** (`frappe_core/mail.py`): "Password is required or select Awaiting
  Password", "SMTP Server is required", "Email Server is required", "Failed to create
  email account: invalid credentials", "Could not connect to the mail server: <exc>";
  the three escape hatches at `:179-226`; a 10-second timeout (`MAIL_CONNECT_TIMEOUT`,
  upstream bug #15).
- **Through the resource** (`EmailEdit.vue:200-207` uses `set_value`): a manager's create
  or write is saved **without** that validation, service defaults or the name check, as
  in `backend/`; and a `password` sent on update is **ignored** (200), because the field
  is excluded from the serializer (`frappe_core/serializers.py:254`). Decision 4 settles
  whether `POST /api/v1/email-accounts/` is served at all.
- The frontend reads the list with `fields=["*"]` filtered `email_id not like %example%`
  (`EmailAccountList.vue:66-72`), and the Profile picker `name`, `email_id` filtered on
  `enable_outgoing` (`UserEmailSettings.vue:138-143`).
- §8: User Email, the signature fallback, the carrier's saved-account steps.

### 4.5 Field metadata (milestone 5)

- **`getdoctype`** (`form_load.py:151-196`): `message` is `null`, with `docs` and
  `user_settings` beside it (frappe-ui returns the whole body when `docs` is present);
  `parent_dt` only when a parent is found; `with_parent` on a child table answers the
  parent's bundle; `cached_timestamp` accepted and ignored; each field gets `idx`; nine
  DocType properties defaulted (`:55-65`); `user_settings` is the row of
  `parent_dt or doctype`.
- **`user_settings`** (`user_settings.py`): `save` answers the **incoming** dict, merges at
  the top level only, does not validate the doctype; a non-JSON string raises. The model
  stays unrouted (decision 12): a plain model, with a `core.withheld` entry only if the
  served-or-withheld guard asks for one.
- The field metadata file is generated, and a test fails if it goes stale (it skips when
  the upstream checkout is absent, `test_phase4_metadata.py:37`).
- **Export's field-info provider** (§7) is filled from this metadata.
- `sort_options`, `get_data`'s `fields` block and the model fallback list every concrete
  column name in `backend/`, sensitive ones included (decision 10).

### 4.6 Layouts, form scripts, quick filters (milestone 6)

- `save_fields_layout` checks roles only (`fields_layout.py:256`); the resource rule also
  passes the literal Administrator (`metadata_docs.py:132`).
- `get_form_script` answers a bare string for one script, a list for several, `None` for
  none (`form_script.py:17-34`); the frontend also lists them through the resource
  (`data/script.js:38-42`).
- Quick filters are a JSON list on the CRM Global Settings row for `(dt, "Quick
  Filters")`; without a row the fallback is the `STANDARD_FILTER_FIELDS` table
  (`crm_app/api/doc.py:126-137`, ten doctypes of five units); `converted` is dropped for
  CRM Lead; a Select gets a blank first option. `update_quick_filters` has no role check,
  as CRM Global Settings is reviewed-open.

### 4.7 Saved views (milestone 7)

Who may do what (spec check findings 2, 3; detail for the owner in `temp\`):

| Call or route | `backend/` |
|---|---|
| Resource read | own, ownerless or public views |
| Resource create | everyone (`metadata_docs.py:84-85`) |
| Resource write / delete | own; a public view: Sales Manager; System Manager or Administrator (`metadata_docs.py:86-91`) |
| `public` | Administrator or Sales Manager only, System Manager excluded; clears `user` (`view_settings.py:205-229`) |
| `delete` | as the resource rule for a public view (`view_settings.py:37-48`) |
| `set_as_default` | no permission check, as upstream (`view_settings.py:249-270`) |
| `fetch_and_update_kanban_columns` | no permission check, as upstream; a missing name answers `None` (`view_settings.py:322`) |

A public view has no owner. Whether `backend_v2` matches every row or narrows the
resource side is decision 3. `clear_old_versions` already prunes CRM View Settings
versions (`backend_v2/core/tasks.py`); whether the model declares `TRACKED_FIELDS` follows
what `backend/` tracks, decided at milestone 7 (decision 14).

### 4.8 The list engine (milestone 8)

- `get_data`'s response shape, every key present even when empty.
- It reads through the resource's own queryset and field rules (root `CLAUDE.md` rule
  11). In `backend/` it resolves any registered doctype (`frappe_core/api/doc.py:229`);
  `backend_v2` serves it per resource (decision 9 and §6).
- `all_count` and `count` go through the caller's rules (`doc.py:506-515`); the four badge
  counts are deliberately **not** permission-filtered (`:564-598`) and are safe only
  because the rows they count for were filtered first.
- A kanban column list for a Link field is built through the **target's list rule**
  (`doc.py:432-448`, `view_settings.py:86-98`; `core.resources.rules_for(model)` in
  `backend_v2`): for `User`, Administrator and Guest are left out for everyone but
  Administrator.
- A list definition supplies six things (`registry.py:85-137`): `default_list_data`,
  `default_kanban_settings`, `get_non_filterable_fields`, `parse_list_data`,
  `get_hidden_fields`, `get_standard_filter_fields`. `User.default_list_data` is here (§8).

## 5. Acceptance

- pytest: §3's table with expected answers unchanged; new tests for each §4 item no old
  test covers, each shown failing without its protection.
- `.http` blocks (finding 13 of the spec check; none pass today):

  | File | This unit's | Milestone | Wait for |
  |---|---|---|---|
  | `13_bulk_and_misc` | 9.1, 9.2, 9.4-9.8 | 1 | — |
  | `09_users_and_invitations` | 6.5 (`get_translations`) | 1 | — |
  | `13_bulk_and_misc` | 9.9-9.11 | 2 | — |
  | `12_settings_singletons` | 0.10, 1.1-1.12, 1.14-1.16 | 3 | 1.13 (CRM Lead: SALES); sections 2-4 INTEGRATIONS |
  | `13_bulk_and_misc` | 5.2, 5.3 (exchange rate) | 3 | — |
  | `07_views_and_metadata` | the resource-only blocks 0.12-0.15, 2.5, 6.7, 7.1-7.3, 7.5, 8.5-8.8, 9.12-9.14 | 5-8 | every other block: SALES, ACTIVITIES, CONTACTS |

  `12` 1.14 and 1.15 (a second POST, a DELETE on the singleton, 403 in `backend/`) answer
  405 under the singleton route (PE-1). `13` 5.3 expects `1` for EUR to USD, true only
  with `ENABLE_EXCHANGE_RATE_API` off. No `.http` block covers Email Account, System
  Settings, Country, Currency, Language or the onboarding status: pytest is their gate.
- The body comparison over the same blocks.

## 6. Decisions

| # | Decision | Status |
|---|---|---|
| 1 | Route names and methods | decided (A-27): §1 and `PORT_MAP.md`, checked at the spec review |
| 11 | The actor for the guest boot call | decided: the row comes from the data migration; `Administrator` if a create is ever needed |
| 12 | `UserSettings` | decided: a plain model, unrouted; a `core.withheld` entry only if the guard asks |
| 13 | Migration or seed for reference rows and the two settings rows | decided: a data migration (§4.2), not dev data |
| 8 | Who edits `accounts` for §8 | decided: this unit, in milestone 4, one commit per file's concern |
| 15 | Guard exceptions for `access_key`, `api_key` | decided: written, reviewed entries at the milestone that builds each (3, 4) |
| 5 | The outbound HTTP helper before INTEGRATIONS | **open — before milestone 3** [supervisor's default: a minimal helper in `core`, carried to INTEGRATIONS] |
| 4 | `POST /api/v1/email-accounts/` served? A PATCH re-validates? | **open — before milestone 4** [default: parity — served, no re-validation, a new password ignored; ask first] |
| 7 | Where mail validation lives; how `core/mail.py` reaches an Email Account | **open — before milestone 4** [default: a provider hook in `core`, as export's] |
| 2, 9 | What "doctype exists" means; what a child table and a withheld doctype answer, per call; copying or regenerating `doctype_meta.json` and where its generator lives | **open — before milestone 5** [default: 404 for a withheld doctype (`API_CONTRACT.md:209`); child tables only where a screen needs them — `getdoctype`, the layout calls, `get_fields`, `user_settings`] |
| 10 | Sensitive column names in field metadata | **open — before milestone 5** [default: left out] |
| 3 | The saved-view rules (§4.7) | **open — before milestone 7** [default: the resource applies the same role rule as the dedicated call; the unchecked calls get the object rule; proposed parity exceptions] |
| 14 | `TRACKED_FIELDS` on CRM View Settings | **open — at milestone 7**, following what `backend/` tracks |
| 6 | Kanban badge counts before ACTIVITIES | **open — before milestone 8** |
| — | `get_data` on a withheld or child doctype | **open — before milestone 8** [default: refused, as the contract says] |

Departures from `backend/` in any of these are flagged for the owner and recorded in
`PARITY_EXCEPTIONS.md` before they are built. `API_CONTRACT.md:209` (404 for a child table)
conflicts with `docs/http/07` 9.2, 9.3 (200 for `getdoctype` on `CRM Contacts`) and
`GridRowFieldsModal.vue:77`: reported to the owner, not edited here.

## 7. Carried from SHARED_ACTIONS

Opt the resources below in to the `core/mixins/` actions (AS_BUILT §2), write each
generated route's row in `PORT_MAP.md`, and port the real-doctype cases SHARED_ACTIONS
left (its §3 table).

- **List export's column labels and fieldtypes** (milestone 5): `core/mixins/export.py`
  uses field names and `Data` as a marked placeholder (`core.E002` refuses it in
  production); this unit's field metadata replaces it, and Duration formatting activates.
  No resource opts in to export before.
- `test_bulk_edit_fields.py` (`crm.api.doc.get_fields`) is this unit's (milestone 5).
- Email Account opts in to rename (`EmailEdit.vue:191-196`; milestone 4): an allowed and a
  write-denied case on real Email Accounts.
- Language keeps `language_name` readable and filterable (milestone 2).

## 8. Carried from ACCOUNTS (milestone 4 unless named)

Moved here by ACCOUNTS' spec rewrite (`temp` A-21 D-D; flagged for the owner).

- **User Email**, with Email Account: the child model
  (`backend/frappe_platform/models.py:1491-1554`), the Email Account `post_save` hook that
  fills it, `User.PRIVILEGED_WRITE_FIELDS = ("user_emails",)` (System Manager only, old
  `:248-249`) and `test_user_emails.py`. `backend_v2/accounts/serializers.py`
  (`EMPTY_CHILD_KEYS`) then loses `user_emails`, returns the rows and accepts the
  privileged write — an edit in `accounts` (decision 8).
- **`get_user_signature`'s fallback**: with no `email_signature`, the default outgoing
  Email Account's signature when `add_signature` is set (`backend/crm_app/api/misc.py:62-67`;
  `backend_v2/accounts/services.py`).
- **The outgoing-account lookup**: add the Email Account steps of
  `find_outgoing_account` (`backend/crm_app/communication.py:400-440`) to `core/mail.py`,
  tried **before** the settings-configured account, and replace its `ConfigAccount` with
  the unsaved `EmailAccount` the old backend builds (`:372-398`). Steps 1 and 2 are
  reachable only from `email.make` (ACTIVITIES). Port `test_phase5_async.py:377` here;
  `test_mail_config_account.py:262` is ACTIVITIES'.
- **`User.default_list_data`** (the User list view, old `:309-318`) — milestone 8.
- `test_language.py:65` and `test_onboarding_status.py` write `User` through ACCOUNTS'
  `/api/v1/users/<name>/` route (milestone 2).
- `docs/http/09_users_and_invitations.http` 6.5 (`get_translations`) waits on this unit
  (milestone 1).

## 9. Milestones, smallest first

| # | Holds | Gate alone today? |
|---|---|---|
| **1. Desk plumbing** | `get_apps`, `current_site_info`, `boot_config`, `clear_demo_data`, `get_translations`; no model; the two `POSTHOG_*` settings | yes |
| **2. Reference data and boot** | Country, Currency, Language, System Settings and their data migration; `get_context_for_dev`; both onboarding calls; Language link search | yes |
| 3. FCRM Settings | FCRM Settings, CRM Dropdown Item, `get_exchange_rate`, `ENABLE_EXCHANGE_RATE_API` | once decision 5 is taken |
| 4. Email Account | Email Account, User Email, `create_email_account`, validation, rename, §8 | once decisions 4, 7 are taken; pytest only |
| 5. Field metadata | the metadata file and generator, the four field helpers, `getdoctype`, `user_settings`, export's provider | on this unit's own doctypes and `tests_support` |
| 6. Layouts, scripts, quick filters | CRM Fields Layout and its three calls, CRM Form Script, CRM Global Settings, the quick-filter calls, default seeds | partly; content cases name Lead or Task |
| 7. Saved views | CRM View Settings, the eight calls, `get_views` | rules yes; default columns need a list definition |
| 8. List engine | `get_data` as the list-view mixin, the list-definition convention, `User.default_list_data` | on `tests_support` and `User` only; the real gate is SALES and ACTIVITIES |
