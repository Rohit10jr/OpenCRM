# CONFIGURATION — CRM settings, email accounts, saved views, layouts and the list engine

**Status: Ready for milestones 1-6 (addenda: milestone 3 A-30, milestone 4 A-33, milestone 5 A-35, milestone 6 A-37) — rewritten 18 Nov 2026** from the spec check
(`tasks\CONFIGURATION_00_spec_check_verdict.md`, `temp` A-27); spec review A-28. **Approval is staged** (A-27, DECISIONS 30, flagged for the owner): the facts and
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
(`<resource>/list-view/`, S24). As S25 (8) says, a record named exactly like an action
cannot be reached by its document route: an Email Account named `setup`, a Form Script
or Fields Layout named `layout`, `save` or `sidepanel-sections`, any record named `value`
or `search`.

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
  `frappe_platform/models.py:1616-1839` (Country, Currency, Language, System Settings:
  their choices, the three `FieldValue` naming rules, `SystemSettings.LINK_FIELDS`),
  `config/settings/base.py:305-313` (`FRAPPE_SYSDEFAULTS`)
- **Settings:** `crm_app/api/settings.py:70-156`, `api/exchange_rate.py`,
  `crm_app/integrations/http.py`, `management/commands/refresh_exchange_rates.py`,
  `crm_app/models/metadata.py:360-491` (FCRM Settings, dropdown items),
  `frappe_platform/models.py:1390-1557` (Email Account, User Email),
  `frappe_core/mail.py`, `frappe_core/field_security.py`
- **Field metadata, layouts, views, the engine:** `frappe_core/api/doc.py`,
  `crm_app/api/doc.py`, `api/views.py`, `api/view_settings.py`, `api/fields_layout.py`,
  `api/form_load.py`, `api/user_settings.py`, `api/form_script.py`,
  `frappe_core/metadata.py`, `frappe_core/field_meta.py`, `frappe_core/registry.py:94-137`
  (the per-model list hooks), `crm_app/metadata_hooks.py`,
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
| `test_get_data.py` | internal (`tests_support`) | milestone 8, ported onto `test-widgets/list-view/` (§4.8) | none |
| `test_kanban_counts.py`, `test_kanban_defaults.py`, `test_list_definitions.py` | internal | milestone 8: two count properties and a `parse` twin (§4.8) | the count values: ACTIVITIES; the definitions: SALES, ACTIVITIES, CONTACTS |
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
- Both refusals are `PermissionError`, 403; `current_site_info`'s carries the default
  title "Not Permitted" (`backend/frappe_core/exceptions.py:68-70`). A wrong method is
  **405** under PE-1 (the old dispatch answered 403 "Method … does not accept GET");
  `13` 9.11 is a negative block.

### 4.2 Reference data, boot and onboarding (milestone 2)

- **Rules** (`platform_docs.py`): Country and Language are read by everyone and written
  by System Manager (`:458-498`). **Currency** is read by Administrator, System Manager,
  or any of Sales User, Sales Manager, Accounts Manager, Accounts User, Purchase User; a
  caller with none gets an empty list, and a refused read by name is 403; writes are
  System Manager or Administrator (`:504-529`). System Settings is System Manager only,
  **reads included**, and nobody deletes it (`:532-551`).
- **Field lists:** in `backend/` every column of Country, Currency, Language and System
  Settings is readable, filterable and sortable, none sensitive
  (`frappe_platform/models.py:1616-1839`); `backend_v2`'s allowlists default to empty, so
  each resource lists them all. `SystemSettings.LINK_FIELDS` maps `currency` to Currency
  (417 for an unknown one).
- **Link search** (SHARED_ACTIONS' mixin, §7): Language, Currency and Country opt in —
  `languages/search/`, `currencies/search/`, `countries/search/` — because the pickers
  search them (`DashboardSettings.vue:88`, `DefaultsSettings.vue:44` for Currency; the
  Address control for Country; `backend/tests/test_currency.py:27,36-39,60-63`,
  `test_address.py:6`). Language keeps `language_name` (its `SEARCH_FIELD`) readable and
  filterable; `enabled` is filterable on Currency and Language.
- **`get_context_for_dev`**: guest, POST only, exactly eight keys — `sysdefaults` (exactly
  seven keys, all strings, `test_boot.py`), `timezone` `{"system", "user"}` (the caller's
  `time_zone`, else the system zone; a guest gets the system zone twice),
  `translated_messages` `{}`, `translated_doctypes` `[]`, `state_options` `{}`, and
  `is_demo_site`, `demo_data_created`, `is_fc_site` all false (`boot.py:41-73`). It reads
  System Settings server-side, so no permission on that doctype is needed.
- **A missing System Settings row is written again on the next boot** (required:
  `test_system_settings.py` `test_a_missing_row_is_written_again_on_the_next_boot`;
  `boot.py:61`, `frappe_platform/models.py:1806-1826`): from `FRAPPE_SYSDEFAULTS`, with
  `Administrator` as the actor (decision 11); a lost insert race reads the winner's row.
- **`FRAPPE_SYSDEFAULTS`** (`backend/config/settings/base.py:305-313`): seven keys from
  seven `FRAPPE_*` environment names, with defaults. Added to `backend_v2`'s settings;
  the data migration and the re-create both read it.
- **Onboarding** (`onboarding.py:43-85`, `test_onboarding_status.py:64-72`):
  `get_onboarding_status` answers the caller's `User.onboarding_status` as a dict, `{}`
  when unset or unreadable; `update_user_onboarding_status` refuses "appName is required"
  and "steps must be JSON", both 417; `steps` may be a JSON string or a list or dict;
  extra inputs are ignored; it stores `steps` under `<appName>_onboarding_status`, keeps
  other apps' keys, treats an unset status as `{}` (upstream bug 40 not reproduced, as in
  `backend/`), leaves the row's timestamps untouched and answers `null`. A guest gets 401.
- **Rows the application cannot run without** (decision 13): the countries, languages,
  currencies (nine enabled) and the System Settings row are written by a **data migration**
  in `configuration`, as FOUNDATION writes roles and built-in users; not a dev-data step,
  so `DEV_DATA_ALLOWED` does not gate them. The mechanism differs from `backend/`, where
  countries and languages come from the `seed_defaults` command (`setup.py:374-416`) and
  currencies and System Settings from migrations 0017 and 0019. The two data files
  (`country_info.json`, the version-15 copy, and `languages.csv`) are copied into
  `backend_v2/configuration/`, since nothing imports from `backend/`. A Country without
  formats falls back to `dd-mm-yyyy` and `HH:mm:ss`, and its time zones are joined with
  newlines; a Language's `enabled` is the file's column; existing rows are left alone; the
  owner is Administrator, so the migration depends on `accounts`' built-in users.
  Whether the default layouts, quick filters, form scripts and dropdown rows are a
  migration or a seed: milestone 3's dropdown rows by migration (A-30); milestone 6's by `seed_dev_data` steps, the question parked for the owner (DECISIONS 44, section 4.6).

### 4.3 FCRM Settings and exchange rate (milestone 3)

Spec-review addendum: `temp` A-30 (DECISIONS 31-35).

- **Rules:** everyone reads FCRM Settings (the timeline reads it on every screen); the
  manager pair (Sales Manager, System Manager) or Administrator writes it
  (`platform_docs.py:302-315`). Route `crm-settings/`, a singleton: GET, PATCH, `value/`;
  no list route (PE-11). `GET crm-settings/` on a missing row answers 404, as `backend/`
  (`docs/FINDINGS.md:1373-1375`); only internal callers re-create it.
- **Fields:** all 16 are built now, with the old defaults and choices
  (`backend/crm_app/models/metadata.py:316-353`, choices `:27-58`); only the behaviour
  that reads each waits for its unit. Every column readable, filterable and sortable.

  | Field | Type, default |
  |---|---|
  | `brand_name` | text, `""` |
  | `brand_logo`, `favicon` | text (500), `""`; `ATTACH_FIELDS` (attach-on-save is ACTIVITIES') |
  | `enable_forecasting`, `enable_sales_hierarchy` | bool, false |
  | `currency` | text, `""`; a validated text link to Currency (417 for an unknown one), as on System Settings |
  | `service_provider` | `frankfurter.app`, `fawazahmed-exchange-api`, `exchangerate.host`, `exchangerate-api`; default `frankfurter.app` |
  | `access_key` | text (280), `""`; `RESTRICTED_FIELDS` |
  | `auto_update_expected_deal_value`, `update_timestamp_on_new_communication` | bool, true |
  | `auto_mark_replied_on_response`, `auto_reopen_on_new_communication`, `persona_captured` | bool, false |
  | `crm_timeline_timestamp_format` | `Relative` / `Exact`, default `Relative` |
  | `crm_timeline_sort_order` | `Oldest First` / `Newest First`, default `Oldest First` |
  | `dropdown_items` | CRM Dropdown Item rows, inline |

- **`access_key`** is restricted to the manager pair and Administrator (upstream bug #20):
  for anyone else it is absent from the body (`test_settings_access.py:160`) and
  `value/?field=access_key` answers 403. `backend/` stores it as plain restricted text;
  the credential guard (`tests/guards/test_model_fields.py`, a FOUNDATION file) gets
  `"access_key"` in `CREDENTIAL_HINTS`, `("configuration.FCRMSettings", "access_key")` in
  `test_known_credentials_remain_covered`, and a `REVIEWED_RESTRICTED_ONLY` entry saying
  managers read it back (`DashboardSettings.vue:157`) (decision 15).
- **No save hooks:** none of upstream's `validate`, `setup_forecasting`,
  `make_currency_read_only`, `restore_*` or `after_migrate` is built, as in `backend/`
  (`metadata.py:317-379`; `docs/FINDINGS.md:1371-1373`). A manager may empty the dropdown
  table.
- **CRM Dropdown Item:** read and written inline only, replaced wholesale on a parent
  write (`backend/frappe_core/children.py:221-250`); no route; its writers are the
  parent's. `CHILD_FIELDS`: the standard stamps, `parent_settings`, `parentfield`,
  `parenttype`, `name1`, `label`, `type`, `route`, `icon`, `hidden`, `is_standard`,
  `open_in_new_window`. `is_standard` and `name1` mark a standard row and stay writable
  by a manager, as in `backend/` (upstream marks them read-only). Row names change on
  every save in both backends, so the body comparison ignores child `name`s.
- **The row and its six standard items** (decision 13; A-30 question 2): the data
  migration writes the FCRM Settings row with the six standard items of `crm/hooks.py:314-357`,
  as Administrator, each row named with `core.naming`'s hash, `idx` 1-6, and leaves an
  existing row alone. `load_or_create(user)` takes the caller as actor and adds the
  standard items **only when it creates the row** (`backend/`'s `if created`,
  `metadata.py:369-376`), never on a row that exists. `add_standard_dropdown_items(settings,
  *, user, force=False)` was ported whole, force branch included; §10.3 deletes the force
  branch (the old backend's `setup.py:508-515`, not upstream's; not carried).
- **The outbound HTTP helper** (decision 5): `backend/crm_app/integrations/http.py` ported
  whole as `core/http.py`. The exchange-rate call uses `timeout=5, attempts=1`
  (`exchange_rate.py:123-126`), so the retry and redact code is tested by patching the
  session. The reason for retrying POST (`integrations/http.py:20-25`) concerns telephony
  and is a note for INTEGRATIONS' callers.
- **`get_exchange_rate`** (`backend/crm_app/api/exchange_rate.py`): the same currency, an
  empty or missing currency, or `ENABLE_EXCHANGE_RATE_API` off answers `1`; the cache key
  is `exchange_rate_<from>_<to>_<date>`, "latest" keyed by today, kept 24 hours; a failure
  is never cached; a five-second timeout, no retry; the free providers fall back to each
  other, the paid ones do not. All four error sentences are 417 (`:157-165`, `:189-214`);
  the manager wording fires only when the provider is `fawazahmed-exchange-api` and both
  free providers fail (`:108-114`, `:198-209`), "manager" meaning System Manager, Sales
  Manager or Administrator (`:217-226`). `ENABLE_EXCHANGE_RATE_API` is on in base, off
  in the test settings, and listed in `.env.example`; tests patch `_get`. No
  `frontend/src` file calls it; its callers are the deal and organization saves and
  `refresh_exchange_rates` (SALES).
  - PE-10 (approved by the owner, 20 Nov 2026): `get_exchange_rate` accepts `date` only
    as `latest` or an ISO date (ASCII digits, a real date) and a currency only as 2 to 5
    ASCII letters or digits (either case, used as given); the old backend passes them
    through.
  - PE-12: a missing `from_currency` or `to_currency` answers `1`, as an empty one does
    (`:56`); a transport error or malformed JSON from a paid provider falls through to
    the generic 417 (`:168-186`); a provider's answer counts only as a positive number.
- **Tests:** `test_settings_access.py:126-175` (`:177-190` is INTEGRATIONS'); fixtures
  that create the row (`test_settings_access.py:60-65`, `test_dropdown_items.py:71,81`,
  `test_singleton_names.py:29,37,56`) update the migrated row instead;
  `test_dropdown_items.py:79-89` (two cases about the old data-fix migration) become "the
  migration writes the row with six items and leaves an existing row alone";
  `test_loading_the_settings_for_the_first_time_seeds_them` deletes the row first;
  `test_singleton_names.py:21-50` and `test_phase7_review_fixes.py:114-125` are ported
  here. `refresh_exchange_rates` and `test_exchange_rate.py:176` go to SALES;
  `test_seed_defaults.py`'s dropdown cases wait for milestone 6. `value/?field=dropdown_items`
  answers 417 (a child table is not a readable column).
- **`.http`:** `12` 1.3 maps to 1.2's check on `GET crm-settings/`; 1.4 is covered by
  1.11 (`value/?field=access_key`, 403); 1.5 and `test_settings_access.py`'s
  `test_the_key_cannot_be_probed_by_filtering` retire under PE-11 (no list route).

### 4.4 Email Account and User Email (milestone 4)

Spec-review addendum: `temp` A-33 (DECISIONS 36-39). Old model and link:
`backend/frappe_platform/models.py:1390-1557`.

- **Rules:** System Manager or Administrator lists, reads, creates, writes, renames and
  deletes an Email Account, and calls `setup/`; anyone else gets an empty list and 403
  (PE-27, owner, 20 Nov 2026). The old backend lets everyone read and the manager pair
  write (`platform_docs.py:158-186`). Route `email-accounts/` (list, POST, `<name>/` GET, PATCH,
  DELETE, rename) and `email-accounts/setup/` (`create_email_account`, an
  `@action(detail=False)`; GET is 405 under PE-1). Naming
  `FieldValue("email_account_name")`; default sort `-modified` (the account lookup and
  the signature take `.first()`).
- **Fields** (types, lengths and defaults as the old model): `password` and `api_secret`
  are `EncryptedCharField(max_length=280)` (parity; an encrypted secret longer than about
  143 bytes does not fit) and `SENSITIVE_FIELDS`: absent for everyone, Administrator
  included, in the document and in `fields=["*"]`; 417 when named in `fields` or in
  `value/`'s `fieldname` (`value/` goes through the list query, as the old
  `get_value`, `crm_app/api/client.py:243`), 400 when filtered on. The eleven restricted fields (`smtp_server`,
  `smtp_port`, `email_server`, `incoming_port`, `login_id`, `domain`, `api_key`,
  `frappe_mail_site`, `signature`, `no_smtp_authentication`, `awaiting_password`) are
  present for Administrator and the manager pair and, for anyone else, absent (417 / 400
  the same way). Nothing is masked or `null`. `email_id` is in `EMAIL_FIELDS`.
  `api_key` gets its reviewed guard entry (decision 15). The model cannot be
  `Access.open`.
- **Through the resource** (decision 4, parity): `POST email-accounts/` is served for the
  manager pair; a create or PATCH is saved **without** validation, service defaults or
  the name check, as in `backend/`. **PE-30** (owner, 20 Nov 2026, DECISIONS 37): a
  non-empty `password` or `api_secret` sent on create or PATCH is stored, encrypted, as
  upstream (`EmailEdit.vue:104-118` sends `password` with every save); null or "" leaves
  the stored value. `backend/` discards both (`frappe_core/serializers.py:253-257`).
- **Rename** sets `email_account_name` to the new name, as upstream
  (`frappe/model/rename_doc.py:319,323-328`): **PE-31** (owner, 20 Nov 2026, DECISIONS
  38). `backend/` keeps the old value (`frappe_core/rename.py:41-45`).
- **`create_email_account`** (`backend/crm_app/api/settings.py`), checks in this order:
  1. the role check: manager pair or Administrator, else 403 "Not permitted" (`:96`;
     `crm_app/api/user.py:28-34`);
  2. `data` must be an object, else 417 "Invalid data" (`:98-100`);
  3. an unknown `service` answers the **string** "Service not supported", 200
     (`:102-106`);
  4. "Email account name is required" (`:133-134`);
  5. the encryption key (`core/secrets.py`'s `ensure_key()` when `password` or
     `api_secret` is non-empty): 417, no row, no connection (`:140-141`,
     `test_email_account_setup.py:36-43`);
  6. mail validation (`:148-153`);
  7. the insert (`:155`); a duplicate name fails here, after validation, as 409
     `DuplicateEntryError`.
  Frappe Mail takes `api_key`, `api_secret`, `frappe_mail_site`, the others `password`;
  `append_to` is always CRM Lead; every service fixes the hosts and the payload cannot
  set the escape hatches. Booleans are `bool(value)`, so `"0"` is true (parity). Answers
  the account's name.
- **Validation** (`backend/frappe_core/mail.py:179-226`), in `core/mail.py` with
  `smtp_settings`, `check_smtp`, `check_imap` (decision 7): `awaiting_password` returns
  without checking; with no password and a server other than `127.0.0.1`/`localhost` it
  refuses "Password is required or select Awaiting Password" when incoming is on, or
  outgoing is on without `no_smtp_authentication`, and otherwise returns **without
  connecting**; then SMTP when outgoing, IMAP when incoming and `use_imap` (always
  `IMAP4_SSL` on 993, login `email_id`, host `email_server` else `smtp_server`).
  `SMTPAuthenticationError` and any `imaplib.IMAP4.error`: "Failed to create email
  account: invalid credentials"; `SMTPException`, `socket.timeout`, `gaierror`,
  `OSError`: "Could not connect to the mail server: {0}"; anything else: its text; all
  417. "SMTP Server is required", "Email Server is required". Ten seconds per
  connection (`MAIL_CONNECT_TIMEOUT`, upstream bug #15). A Frappe Mail account with
  either direction on is always refused (its service config has no password and no
  server; the UI hides it); this is intended, not a bug to fix.
- **How `core` reaches a saved account** (decision 7): `configuration/mail.py` exposes
  `saved_outgoing_account(sender=None, reference_doctype=None)` (steps 1-3 of
  `backend/crm_app/communication.py:400-440`, newest by `-modified`) and
  `default_signature()`. `core.mail` reaches them through the setting
  `MAIL_ACCOUNT_PROVIDER = "configuration.mail"` (a module path resolved with
  `import_module`), with a system check that fails when the path does not resolve, so a
  typo never falls back quietly to the config account. `core.mail` wraps both as
  `find_outgoing_account(sender=None, reference_doctype=None)` (saved account, else the
  config account) and `default_signature()`. An empty setting means the config account
  only and no signature fallback.
- **`open_backend`** gets its saved-account branch (old `communication.py:617-631`): a
  saved account sends through `EmailBackend(**smtp_settings(account, <its password>),
  timeout=MAIL_CONNECT_TIMEOUT)`, "what was checked is what sends"; the config account
  keeps Django's own connection. `ConfigAccount` stays (section 8's replacement is
  withdrawn).
- **The signature fallback** (`backend/crm_app/api/misc.py:62-67`): the Email Account
  with `default_outgoing=True, add_signature=True`, newest by `-modified`; it does not
  require `enable_outgoing`; an empty signature on that row answers `None`.
  `accounts.services.user_signature` calls `core.mail.default_signature()`.
- **Several default accounts can coexist** (upstream un-defaults the others; `backend/`
  does not): parity; the newest wins.
- **User Email** (old `models.py:1495-1557`): a child table of User (`user_emails`),
  `IS_CHILD_TABLE`, `CHILD_FIELDS` the standard stamps, `parent_user`, `parentfield`,
  `parenttype`, `email_account`, `email_id`, `awaiting_password`, `enable_outgoing`,
  `used_oauth`; FK to `accounts.User` with `related_name="user_emails"`; `email_account`
  CASCADE; `FETCH_FROM` as old `:1505-1509`. `EmailAccount.save()` calls
  `link_to_user()` after `super().save()`, a direct call, not a signal: `email_id`
  trimmed, matched against `User.email` or `User.pk` case-insensitively; it updates the
  user's existing row or appends one with `idx = count + 1`; an empty `email_id` does
  nothing; a changed `email_id` leaves the previous user's row; a rename keeps the rows;
  a delete removes them; a queryset `.update()` does not link.
- **What `accounts` changes** (decision 8, one commit per file's concern):
  `accounts/models.py` gains `PRIVILEGED_WRITE_FIELDS = ("user_emails",)` and
  `PRIVILEGED_WRITE_ROLES = ("System Manager",)`; `accounts/serializers.py:73-86` drops
  `user_emails` from `EMPTY_CHILD_KEYS`, declares the child table and adds it to
  `Meta.fields`; `accounts/services.py:157-164` takes the signature fallback through
  `core.mail.default_signature()`; `tests/test_user_access.py:166`
  (`test_user_emails_is_an_empty_list_until_configuration`) is rewritten.
- **Closed to a non-manager, each tested:** create, PATCH, DELETE: 403
  (`platform_docs.py:174-186`); rename: 417 "You need write permission on Email Account
  X to rename" (`client.py:490-491`); `setup/`: 403; `user_emails` on their own User:
  dropped with 200 while the rest of the save applies (`test_user_emails.py:57-63`).
- **The list the frontend reads:** `fields=["*"]` filtered `email_id not like %example%`
  (`EmailAccountList.vue:66-72`), and the Profile picker's `name`, `email_id` filtered on
  `enable_outgoing` (`UserEmailSettings.vue:138-143`).
- **Tests:** `test_email_account_access.py` whole except `:206` (the legacy-rows
  migration; `:183` is kept); `test_mail_validation.py` (its two endpoint cases moved to
  the new validation path); `test_email_account_setup.py`; `test_user_emails.py`;
  `test_phase5_async.py:377`. New: the signature fallback, `open_backend`'s branch (a
  saved account does not use the settings connection), the 409, the role 403, rename
  refused, rename keeping the naming field, the provider system check. No seeded Email
  Account in dev data.

### 4.5 Field metadata (milestone 5)

Spec-review addendum: `temp` A-35 (DECISIONS 41-43). These routes keep `doctype` as an
input (`REBUILD_PLAN.md:173-176`), beside S24's "from mixins" wording; this is settled.
Caching: the process-lifetime memo of the metadata file only.

- **Who may call:** all seven calls (`getdoctype`, `user_settings` get and save,
  `get_fields`, `sort_options`, `get_filterable_fields`, `get_group_by_fields`) are for
  any signed-in caller, with no role or per-doctype check, as `backend/`
  (`form_load.py:23-26`; `07` 9.15). The three narrowings below are the only ones.
- **The metadata file** (decision 41): the whole 39-doctype `doctype_meta.json` is copied
  to `backend_v2/configuration/data/`; entries for doctypes with no v2 model yet are
  inert data. The generator is ported to `backend_v2/scripts/generate_field_meta.py`,
  reading `CRM_UPSTREAM_DIR` (its hard-coded owner path is the fallback only). The
  staleness test is ported and runs in CI: `.github/workflows/backend_v2.yml` gets the
  same pinned `frappe/crm` checkout (`48cb3ccce…`) and `CRM_UPSTREAM_DIR` as
  `backend.yml:80,93-97`, and a `backend_v2/tests` helper resolves the path as
  `backend/tests/upstream_source.py:21-28`. A guard: every value field the file lists for
  a served doctype is a model column or explicitly excused.
- **What "doctype exists" means** (decision 42): a model declares `DOCTYPE`
  (`core.doctypes.declared_doctypes`) and is served (`core.resources.routed_rule_map`; a
  singleton counts) or is a child in a served serializer's `CHILD_TABLES`. No registry:
  these are the existing derived lookups.
  - **A withheld doctype** (Version now; ToDo and Data Import Log when built): 404
    "DocType X not found" on every call that validates a doctype. **PE-14** (proposed,
    flagged): `backend/` answers them, checking only that the doctype is registered
    (`form_load.py:177`, `crm_app/api/doc.py:90,346`, `frappe_core/metadata.py:117,154`).
  - **A child table:** `getdoctype` answers (`Grid.vue:545`, `stores/meta.js:9-17`, the
    Home Actions grid; `docs/http/07` 9.2, 9.3), and so will milestone 6's layout calls;
    `get_fields`, `sort_options`, `get_filterable_fields` and `get_group_by_fields` answer
    404 (no screen calls them for a child). **PE-15** (proposed, flagged), against
    `API_CONTRACT.md:209`, which says 404 for every child table; the contract is not
    edited here, the line is flagged to the owner.
  - **`user_settings` never validates the doctype**, as `backend/`: parity.
  - **A doctype in the file with no model yet:** 404, as `backend/` answers an
    unregistered doctype.
  - `with_parent`: only a parent that exists, else the child's own bundle
    (`form_load.py:189-190`); unbuilt children are left out of a bundle; the parent scan
    covers existing doctypes only.
- **Field names a caller may not read** (decision 43, **PE-16**, proposed, flagged):
  metadata answers list only the fields the caller may read; the old backend lists every
  field name. Every answer (`getdoctype`'s fields, `get_fields`,
  `get_filterable_fields`, `get_group_by_fields`, `sort_options`, later `get_data`'s
  `fields` block) leaves out `core.field_access.hidden_from(model, user)`. Each remaining
  field keeps its original `idx` (gaps are fine); a copy is filtered, never the file memo.
- **The four helpers, each ported verbatim:**
  - `sort_options` (`backend/crm_app/api/doc.py:82-101`): the model's concrete fields,
    labels from `verbose_name`, entries `label`, `value`, `fieldname`; the five standard
    fields are appended (`:38-44`), so `name`, `creation`, `modified`, `modified_by`,
    `owner` appear twice. The duplicates are reproduced.
  - `get_filterable_fields` (`backend/frappe_core/metadata.py:111-144`): the nine
    standard fields first (`:60-75`), then the metadata value fields of the 16 allowed
    types; drops `name`, duplicates and `get_non_filterable_fields()`; the label falls
    back to the fieldname; `options` always present.
  - `get_group_by_fields` (`:147-172`): the doctype's fields first, then the eight
    standard fields without duplicates (`:77-89`); entries `{fieldname, label}`.
  - `get_fields` (`crm_app/api/doc.py:329-355`): rows through `docfield()` (adds
    `options`, `description`, `default` as None and six flags as 0, `:309-326`); drops
    fieldless rows, and the no-value types and `Read Only` unless `allow_all_fieldtypes`
    is `1` or `true`.
  - `getdoctype` (`form_load.py`): the raw rows plus `idx`, **without** `docfield()`'s
    defaults; `istable`/`issingle` from the model when there is no file entry (`:79-84`);
    `message` null with `docs`, `user_settings` and the conditional `parent_dt`
    (`:192-196`); `cached_timestamp` ignored; the parent lookup is deterministic over
    sorted doctypes (`:109-141`); nine DocType properties defaulted (`:55-65`).
  - No intersection with the resource's `filterable_fields` / `sortable_fields` beyond
    PE-16; a guard test checks that every name a helper offers is accepted by the served
    list route.
  - `get_non_filterable_fields` is a model staticmethod, adopted unchanged by milestone 8.
- **The model fallback** (old `field_meta.py:124-180`) reads v2's declarations:
  `TEXT_LINK_FIELDS` (tuple values), `DYNAMIC_LINK_FIELDS` (pairs) and `ATTACH_FIELDS`.
  System Settings' `currency` answers `Link` / `Currency` (`test_system_settings.py:70`).
  Table rows for a model's child tables come only from `TABLE_FIELD_LABELS`, as the old
  fallback (`field_meta.py:181-195`): never synthesised from `CHILD_TABLES`. The old User
  has none, so `getdoctype` on User has no Table row for `user_emails`. The old Contact
  has one (`email_ids`, `phone_nos`); its reading is not built here and is carried to
  CONTACTS' spec, since no backend_v2 model declares it yet.
- **`user_settings`** (`backend/crm_app/api/user_settings.py`): keyed on (user, doctype),
  unique, cascading with the User; no `user` input, so nobody reads or writes another's.
  A dict or a JSON string; `""` and None mean `{}`; valid JSON that is not an object
  becomes `{}`; a top-level merge; `save` answers the incoming value; `get` answers the
  stored **string**, `"{}"` when none (`:113-121`). Two probable 500s in `backend/`
  become 417 with a fixed sentence, recorded with PE-12's kind (replacing a crash): a
  string that is not JSON, and a `doctype` longer than 140 characters. The model is a
  plain `models.Model` with no `DOCTYPE`, so it needs no withheld entry (decision 12).
- **The export provider** (old `backend/crm_app/api/reportview.py:39-47,59-84`): `name`
  is labelled `ID`, type `Data`; a metadata field gives its label (or the fieldname) and
  fieldtype (or `Data`); anything else uses the standard labels and types.
  `core/mixins/export.py:96-102` calls `provider(fields)` with no doctype, so
  `configuration` exposes a factory, `export_field_info_for(model)`, that a resource's
  ViewSet assigns; `core` never imports `configuration`. No CONFIGURATION resource opts
  in; the waiting resources are SALES', CONTACTS' and ACTIVITIES'. None of this unit's
  doctypes has a Duration, Text Editor, Long Text or Rating field, so the reader accepts
  a `tests_support` metadata overlay and those types are tested through it.
- **What can be gated now:**
  - `.http`: `07` 1.6 and 9.6 (unknown doctype, 404), 9.7, 9.9, 9.11, 9.13
    (`user_settings`); not 9.12 and 9.14 (CRM Holiday List, a later unit), nor 1.1-1.5,
    9.1-9.5, 9.8, 9.10, 9.15 (SALES, CONTACTS). The REST rows of `07` for the `meta/` and
    `user-settings/` routes are written in PORT_MAP.
  - pytest: `test_form_load.py:292`, `:316`, `:431`, `:333`, `:341`, `:354`, `:409`;
    `test_bulk_edit_fields.py:61`; from `test_phase4_metadata.py:37-186` (internal,
    rewritten) the platform-fallback case on User (`:82`), the allowlist constants
    (`:94`, `:103`), the non-filterable case on a test model (`:152`);
    `test_system_settings.py:51`. In-unit twins of the Deal and Contacts `getdoctype`
    cases on FCRM Settings and CRM Dropdown Item (the Home Actions grid:
    `HomeActions.vue:26-31`, `Grid.vue:545-546`, `GridFieldsEditorModal.vue:193`); the
    Deal versions are SALES'.

### 4.6 Layouts, form scripts, quick filters (milestone 6)

Spec-review addendum: `temp` A-37 (DECISIONS 44-47).

- **Who may do what:**

  | Doctype or call | Read | Create, write, delete |
  |---|---|---|
  | CRM Fields Layout (resource) | everyone | Administrator or the manager pair (`metadata_docs.py:126-132`) |
  | CRM Form Script (resource) | everyone | System Manager or Administrator (**PE-17**) |
  | CRM Global Settings (resource) | everyone | everyone: `Access.open(reason=…)`, as upstream's role table (`test_route_surface.py:77-80`) |
  | `get_fields_layout`, `get_sidepanel_sections`, `get_quick_filters`, `update_quick_filters` | any signed-in caller | — |
  | `save_fields_layout` | — | System Manager or Sales Manager, else 403 "Not permitted to modify fields layout" (`fields_layout.py:256`); roles only, as `backend/` (the resource also passes the literal Administrator) |

  `update_quick_filters` has no role check, as `backend/` and upstream (the UI offers it to
  managers only, `ViewControls.vue:229`).
- **Doctype validation (PE-14, PE-15, PE-16 extended):** all five calls take the model
  through `model_or_404`: `get_fields_layout` and `save_fields_layout` with
  `child_allowed=True` (the grid row editor sends `{doctype: <child>, type: "Grid Row"}`:
  `GridRowModal.vue:70-78`, `GridRowFieldsModal.vue:68-82,114-121`);
  `get_sidepanel_sections`, `get_quick_filters`, `update_quick_filters` with
  `child_allowed=False`. An unknown, unbuilt or withheld doctype is 404 "DocType X not
  found" (in `backend/` the three layout calls validate nothing; an unknown doctype gets
  an empty first tab, `fields_layout.py:120-135`). Fields the caller may not read are
  left out of every answer, the Required Fields section and the default layout included.
  The saved-view calls of milestone 7 check no doctype, as `backend/` (§4.7); the
  difference is on purpose.
- **Field lists hold fieldnames (PE-18):** `save_fields_layout` and the resource's create
  and PATCH refuse a layout whose `fields` lists hold anything but strings (417);
  `get_fields_layout` and `get_sidepanel_sections` leave such an entry out on read. A
  `layout` that is not valid JSON is 417 on save (PE-12c; `backend/` stores it).
- **`get_fields_layout`** (`fields_layout.py:111-186`): a list of tabs; a sections-only
  layout is wrapped as `first_tab`; never an empty list. Without a row, the default
  layout is the metadata file's rows in declaration order (`:60-109`): a tab opens unless
  the first row is a Tab Break, then a new tab, section or column opens at each break,
  with four-character random ids. The "Required Fields" type has no default fallback and
  appends a section with keys `label`, `name`, `opened`, `hideLabel`, `columns`
  (`:139-186`). Unknown fieldnames are dropped (upstream keeps them); `parent_doctype` is
  accepted and ignored.
- **`get_sidepanel_sections`** (`:189-235`): the sections, each field expanded by
  `get_field_obj` (`:191-210`): the placeholder is "Select {label}..." for Link and Select
  fields, "Add {label}..." otherwise; Select options become `{label, value}` with no blank
  entry; a read-only field gets a tooltip. `[]` with no row.
- **`save_fields_layout`** (`:240-260`): answers the stored string (a list input is
  JSON-dumped); `type` is stored as given (parity).
- **CRM Form Script:** the resource only, no save hooks; upstream's lock on standard
  scripts (`crm_form_script.py:24-38`) and `set_only_once` on `view` are not ported, as
  `backend/`. **`get_form_script` is not a route**: an internal helper in
  `configuration`, built now, answering a bare string for one script, a list for several,
  `None` for none (`form_script.py:17-34`); `get_data` uses it at milestone 8. The
  resource's default order decides the order scripts run in (`script.js:114-123,156-171`):
  match `backend/`'s.
- **Quick filters** (`crm_app/api/doc.py:126-234`): a JSON list on the CRM Global Settings
  row for `(dt, "Quick Filters")`. Several such rows can exist (Hash names, no unique
  constraint); the first by name wins. Without a row, the fallback table only (no model
  defines the old per-model hook, so it is not ported; §4.8), named apart from `field_helpers.STANDARD_FILTER_FIELDS`;
  the table covers ten doctypes of six units. Entries are built from the model's
  concrete fields and `verbose_name`, not from the metadata file: `{label, fieldname,
  fieldtype, options}`; `converted` dropped for CRM Lead; a blank first option only when a
  Select has none (`:190-192`); `cached` ignored. A `json` stored as a string is parsed
  (`:171-172`), and one that does not parse to a list counts as no entries. A `json` entry that is not a string is
  skipped on read (PE-12c; in `backend/` it fails the call for every later caller,
  `:173-177`). Stored names are matched against model fields, never used in a query as
  they are. `update_quick_filters` answers `None`; `old_filters` is ignored (Property
  Setter is not ported, `:210-234`).
- **Allowlists:** every column of the three resources readable, filterable and sortable,
  listed explicitly, as `backend/`. The resource does not check `dt` against existing
  doctypes, as `backend/` (the default rows name doctypes not built yet).
- **The default rows:** written by data migration, and put back by the
  `restore_defaults` command (§10, which replaces the `seed_dev_data` steps milestone 6
  built). As built in milestone 6, `write_default_layouts`, `write_quick_filters` and
  `sync_standard_form_scripts` were `seed_dev_data` steps; §10.8 retires them.
- **Gating:** in-unit twins on FCRM Settings and CRM Dropdown Item (Grid Row);
  `get_quick_filters` on CRM Fields Layout falls back to `dt` and `type` with a blank
  Select option. The CRM Lead, CRM Deal and CRM Task cases wait for SALES and ACTIVITIES.
  Tests also: `test_phase3_endpoints.py:1054`, `:1106-1115`, `:160`, `:214-217`;
  `test_crm_behaviour.py:270` (the five layout types); `test_permissions.py:778`;
  `test_route_surface.py:77`; `test_phase4_metadata.py:880` rewritten for PE-17.
  `test_phase4_metadata.py:317-339` is milestone 8's. `test_seed_defaults.py:131-147` is
  ported against the data file; `:105`, `:176` and `:162` (the methods the seeded scripts
  call are served) wait for SALES. `.http` `07` 2.5, 6.7, 8.5 and 8.6 read or delete
  rows that 2.3 and 6.5 write on CRM Task, so they wait.

### 4.7 Saved views (milestone 7)

Spec-review addendum: `temp` A-39 (DECISIONS 49-52). CRM View Settings, its eight calls
(`backend/crm_app/api/view_settings.py`) and `get_views` (`crm_app/api/views.py`). In
this section "the read rule" and "the write rule" are the resource's.

- **The resource's rules** (`backend/crm_app/permissions/metadata_docs.py:61-91`):
  - **Read rule:** the caller's own views, ownerless views and public views;
    Administrator and System Manager read every view (`:64-65`, `:76-77`).
  - **Write rule** (write and delete): the owner; Sales Manager on a public view;
    Administrator and System Manager. The same rule as `check_permission`
    (`view_settings.py:37-48`, message "Not permitted").
  - **Create:** everyone (`:84-85`); the created view belongs to the caller: the create
    stamps `user` = caller explicitly, since `DocumentSerializer.save`'s `user` keyword is
    the actor (`core/serializers.py:137-143`), not the field (PE-19).
  - **Read-only on the resource, for everyone (PE-19):** `user`, `public`, `is_standard`,
    `is_default`. Only the `public` call keeps "a public view has no owner and is not
    pinned", and only the default calls keep one default per user. `pinned` stays
    writable under the write rule (the rule `pin` uses). The frontend never writes this
    doctype through the resource (`ViewControls.vue:984-1290`, `ViewModal.vue:121-130`);
    create, PATCH and DELETE stay, for the `.http` cleanup.
  - **Allowlists:** every column readable, filterable and sortable, listed explicitly, as
    `backend/`. No bulk delete. `backend/`'s migration `0011_kanban_fields_reset` is not
    ported.
  - **A JSON column written through the resource** (`filters`, `columns`, `rows`,
    `kanban_columns`, `kanban_fields`) that is not valid JSON is 417 (PE-12d).
    `route_name` and `type` are not checked (parity).
- **The calls:**

  | Call | Rule | What it does |
  |---|---|---|
  | `create` (`:150-167`) | none, as `backend/` | `user` = caller; never sets `public`, `pinned`, `is_standard`, `is_default`. Merges the doctype's default rows; fills `columns` (or, for a kanban, `kanban_columns`) from the default columns when empty. Answers the document. No `doctype` is 417 (PE-12d) |
  | `update` (`:170-187`) | 404 "CRM View Settings X not found", then the write rule | changes `label` (an empty label keeps the old one), `type`, `icon`, `route_name`, `load_default_columns` and the eight query and JSON fields (`_apply`, `:120-135`: a field left out is reset to its blank, as `backend/`); never `dt`, `user`, `public`, `pinned`, `is_standard`, `is_default`. Answers the document |
  | `delete` (`:193-201`) | the write rule | a missing view answers 200, `null`, and does nothing |
  | `public` (`:204-229`) | Administrator or Sales Manager, else 403 "Not permitted" (System Manager excluded, parity); then 404 for a missing view; then the read rule, 403 "Not permitted" (PE-20) | publishing clears `user` and unpins; unpublishing gives the view to the caller. Answers `null` |
  | `pin` (`:232-243`) | 404, then the write rule | sets `pinned`; a Sales Manager pinning a public view pins it for everyone (parity, pinned by a test). Answers `null` |
  | `set_as_default` (`:246-270`) | with a `name`: 404 for a missing view, then 403 "Not permitted" unless the view's `user` is the caller (PE-21); without one: as the standard-view call | marks the view default, then clears `is_default` on the caller's other views. Answers `null` |
  | `create_or_update_standard_view` (`:273-315`) | none: it acts on the caller's own row | the caller's own newest `{dt, type, is_standard, user}` row, created when missing with the label "List", "Group By" or "Kanban"; defaults `column_field` "status", `order_by` "modified desc", `group_by_field` "owner"; sets `is_default` from the payload **without** clearing the caller's other defaults (parity, pinned by a test). Answers the document. No `doctype` is 417 (PE-12d) |
  | `fetch_and_update_kanban_columns` (`:318-347`) | the read rule on the named view; it **saves** only when the caller also passes the write rule, and otherwise computes and answers without saving (PE-21) | answers the `kanban_columns` JSON **string**; `null` for a missing view or one that is not a kanban. A column that has appeared since the view was saved is appended with `delete: True` |
  | `get_views` (`crm_app/api/views.py:12-36`) | the read rule, then `user IS NULL OR user = caller` (Administrator and System Manager too) | then `dt = doctype` when `doctype` is truthy (the store sends `''`, `stores/views.js:5-8,19`, which answers every doctype's views); no `doctype` at all is 417 "DocType is required" (PE-12d); ordered `-modified`, which decides which default the store picks. Keys as `backend/`'s `.values()` gives them (`user_id`, `owner_id`, `modified_by_id`; no frontend code reads them); the JSON columns as strings (`wire_json_text`) |

  A `name` that is not an integer is a missing view on every call that takes one, as
  `backend/`'s `by_name` makes it (`frappe_core/query.py:32-44`): `delete` and
  `fetch_and_update_kanban_columns` answer `null`, the others 404. `update` and
  `set_as_default` look the name up with `filter(pk=…)` and raise in `backend/`; in
  `backend_v2` they use `by_name` too and answer 404 (PE-12d). `name` stays an
  **integer** in `get_views` and in every answer: PE-21 rests on the screen never
  sending a saved view's integer name to `set_as_default` (`ViewControls.vue:1112-1116`,
  `:1141-1146`, `:1225-1233`), and a test pins it.
- **`value` on `pin` and `public`** is `bool(value)` on the raw payload
  (`view_settings.py:223,242`; `frappe_core/whitelist.py` coerces nothing): a JSON body's
  `true`/`false`/`1`/`0` give what they say; a body string, `"0"` and `"false"`
  included, is true; a query-string value is parsed as JSON first
  (`frappe_core/method_views.py:77-91`), so `?value=0` and `?value=false` are false.
  `backend_v2` matches this.
- **`get_views`' HTTP method:** `GET /api/v1/views/` as `PORT_MAP.md:201`. The frontend
  sends it as POST (frappe-ui `frappeRequest.ts:141` defaults to POST and
  `stores/views.js:17-22` names no method); as for the `meta/` calls, the `.http`
  generator rewrites the method and the frontend changes at S22.
- **No doctype check** on any view call or on `get_views`, as `backend/`: `dt` is stored
  text, and an unknown doctype gets no default rows or columns (`view_settings.py:67,84`).
  This differs from milestone 6's calls on purpose (§4.6).
- **The seam to milestone 8:** `create`, `update` and the standard-view call merge the
  doctype's default rows and columns (`view_settings.py:65-106,138-143`). Milestone 7
  builds `list_definition_for(dt)` as FOUNDATION Q6 decided (`specs/FOUNDATION.md:349`):
  for a served doctype that is not a child, the ViewSet's `list_view_class`
  found through `routed_rule_map()`, else the fallback (the Name and Last Modified
  columns, rows `["name"]`, `registry.py:94-114`); for an unknown, child or withheld
  doctype, nothing. At milestone 7 no ViewSet names a class, so every served doctype
  answers the fallback. The saved-view calls' kanban column lookup reads the metadata
  file (`view_settings.py:87-103`): a Link column's values through the target's list
  rule, ordered by `modified`, and nothing when no resource serves the target (the
  routed rule map, not `rules_for`'s `ROW_RULES` fallback); a Select's options. A
  `column_field` the caller may not read gives no columns (PE-16). The tests use CRM
  Fields Layout's `type` (a Select), a Link to User, and Version (withheld).
- **Crashes become errors (PE-12d):** besides the cases above, a view that is not an
  object, `rows` or `columns` that is not a list, a row that is not a fieldname, a
  `doctype` or `type` that is not text, and `create` with no `label` are 417 with a fixed
  sentence; in the kanban refresh a stored `kanban_columns` that is not a list counts as
  none and an entry that is not an object is skipped. A value longer than its column
  stays as `backend/` (not in the PE).
- **Version history:** no `TRACKED_FIELDS` on CRM View Settings, as `backend/` pins on
  purpose (`backend/tests/test_version_retention.py:97-107`, `crm_app/tasks.py:75-85`);
  that test is ported as a guard (decision 14). `clear_old_versions` already prunes its
  versions (`backend_v2/core/tasks.py`).
- **Gating.** Now: `test_phase4_metadata.py:213`, `:236`, `:573`, `:584`, `:599`
  (rewritten for PE-20), `:616`, `:626`, `:640`, `:654` (twinned on a Link to User),
  `:681`, `:689`, `:699`, `:778`, `:792`, `:804`, `:817`; `test_version_retention.py:97`
  (a guard); `:551` (the calls are registered) is covered by
  `tests/guards/test_route_map.py`, and `test_permissions.py:777` (the doctype has a row
  rule) by `tests/guards/test_resource_access.py`; new tests for PE-19, PE-20, PE-21 and
  PE-12d, the resource create's `user`, the integer `name`, and the two parity facts
  above. `.http` `07`: 0.4-0.11, 3.1-3.3, 3.5-3.20, 4.1-4.5, 4.9, 8.1-8.3, 8.8 run;
  3.1's and 4.4's checks of CRM Lead's default columns move to 3.1a and 4.4a, which wait
  for SALES. Waiting for SALES or milestone 8: `test_phase4_metadata.py:562`, `:223`,
  `:900-940`; `.http` 3.1a, 3.4, 4.4a, 4.6-4.8, 8.4; `test_kanban_defaults.py`,
  `test_kanban_counts.py`.

### 4.8 The list engine (milestone 8)

Spec-review addendum: `temp` A-40 (DECISIONS 53-55). Milestone 7 is built first: the
`views` key, the saved standard view and `load_default_columns` all read CRM View
Settings. Paths in this section are `backend/frappe_core/api/doc.py` unless named.

- **The route.** `get_data` is `GET` and `POST /api/v1/<resource>/list-view/`, a mixin a
  resource opts in to (`PORT_MAP.md:191`, S24); `doctype` leaves the input. It is served
  only where a resource opts in: a child table, a withheld doctype and a settings record
  have no list-view route, and the URL answers the generic 404 (**PE-22**; the old
  backend answers `get_data` for any registered doctype, `:229`). A guard checks that no
  child or singleton ViewSet opts in or names a definition (a withheld doctype has no
  ViewSet). On a resource that opts in, a record named `list-view` cannot be reached by
  its document route (S25 (8)). It reads through the resource's own queryset and field
  rules (root `CLAUDE.md` rule 11).
- **The list-view convention** (FOUNDATION Q6, `specs/FOUNDATION.md:349`): a class in
  each app's `list_views.py`, named by the ViewSet's `list_view_class`.
  `configuration/list_views.py` holds the base `ListView`: `columns`, `rows`,
  `kanban_settings`, `hidden_fields` and `parse(data)`, the old hooks
  `default_list_data`, `default_kanban_settings`, `get_hidden_fields` and
  `parse_list_data` (`frappe_core/registry.py:94-137`, `:145-155`; only CRM Lead has
  hidden fields). The base answers the fallback: the Name and Last Modified columns and
  rows `["name"]` (`:38-44`, `registry.py:94-114`). `list_definition_for(dt)` takes
  `served_model(dt)`, refuses a child, then reads `routed_rule_map()[model]
  .list_view_class` (`core/resources.py:57-61`), else the base; an unknown, child or
  withheld doctype gets nothing (PE-14, PE-15). `get_non_filterable_fields` stays a
  model staticmethod, as milestone 5 built it. `get_standard_filter_fields` is defined
  by no model and is not ported. Definitions now: `tests_support` (Widget, and a second
  resource without one) and `UserListView` (old `frappe_platform/models.py:309-318`;
  the definition only, with no `list-view/` route on User, since no screen lists
  users). No CONFIGURATION doctype has one. Lead and Deal come with SALES; Task, Note
  and Call Log with ACTIVITIES; Contact and Organization with CONTACTS.
- **`get_data`, in order** (`:211-372`):
  1. **Inputs** (`:211-240`): `filters` through `_as_filters` (`:70-88`: a dict or a
     list of conditions; anything else is 417 "Unsupported filters value of type X");
     `rows`, `columns`, `kanban_fields` and `kanban_columns` through `_as_list`
     (`:58-62`: a single value becomes a one-item list); `view` through `_as_dict`. From
     `view`: `custom_view_name`, `view_type`, `group_by_field`.
  2. **`@me` and `default_filters`** (`:242-247`, `:91-111`): `@me` resolved in either
     filter shape; a dict `default_filters` overrides a dict `filters` key by key, and
     otherwise the conditions are appended.
  3. **List and group-by** (`:256-317`, when `view_type` is not `kanban`). Sent
     `columns` or `rows` make a custom view (`is_default` false); a missing one takes
     the fallback. Without a custom view, the caller's own saved standard view
     (`crm_app/metadata_hooks.py:27-51`: `{dt, type: view_type or "list", is_standard,
     user}`, newest by `modified`, ignored when both its lists are empty) gives
     `columns` and `rows`, and `is_default` is false. Otherwise the definition's
     `columns` and `rows`, each falling back when empty. The dead clause
     `is_default and has_default_list_data` (`:275`) is ported as it is. Then every
     column's `key` is added to `rows`; a `_liked_by` column 10rem wide becomes 50px;
     a column flagged `hidden`, or whose key is a definition hidden field, is dropped
     (iterating a copy, `:285-303`). `group_by_field` is added to `rows`. The query runs
     with `page_length` through `coerce_page_length`, then the definition's `parse`
     (the list branch only).
  4. **Kanban** (`:319-331`, `:405-528`): `rows` default to the definition's rows.
     Without `kanban_columns` and with a `column_field`, the columns come from the
     **model** (`:426-450`): a forward foreign key gives the target's rows through the
     target's list rule, ordered by `modified` (else `pk`), and **a target no resource
     serves gives no columns** (the routed rule map, as milestone 7's lookup after A-43;
     PE-22: the old backend builds the column list whether or not the link target is
     served); a field with choices gives its choices. A `column_field` the model lacks
     gives an empty board without sent columns and "Unknown field 'x' for this document
     type" with them, as `backend/`; one it has but the caller may not filter on is
     "Cannot filter on 'x'". `title_field` defaults to the
     definition's (else `name`) and joins `rows`; `kanban_fields` default to the
     definition's (a JSON string parsed), else `["name"]`, and join `rows`. Only an
     equality filter on `column_field` pre-selects a column (`:468-482`): every other
     column, and a column flagged `delete`, is answered empty; any other operator on
     the column field stays and is AND-ed. Each column: its own `page_length`
     (default 20; 0 means no limit, parity), a manual `order` fetched as the named cards
     first, newest `creation` first, then the rest (`:531-561`) and re-sorted by
     `order`; `all_count` through the caller's rules and `count` the cards answered;
     the four badge counts per card (below). Answers `data` as
     `[{column, fields, data}]`; in kanban, `row_count` is the number of columns and
     `columns` is echoed unprocessed (parity).
  5. **`fields`** (`:333-341`): every concrete model field as `{label, fieldtype,
     fieldname, options}` with `backend/`'s types (`:114-134`,
     `frappe_core/metadata.py:175-201`: never `Select`; `options` only for a link).
     Milestone 5's `configuration/field_meta.py:128-134` answers `Select` and is not
     reused. The seven standard fields (`:47-55`) join `rows` and, when missing,
     `fields`; PE-16 is applied **after** they are added, so a hidden one is not
     re-added.
  6. **`is_default`** (`:343-348`): when not default and a `custom_view_name` is sent,
     the named view's `load_default_columns`, read under milestone 7's read rule: a view
     the caller may not read, or a name that is not an integer, counts as no view
     (PE-21's "Where", PE-12e).
  7. **Group-by options** (`:350-351`, `:601-630`): for `view_type` `group_by`,
     `group_by_field` becomes `{label, fieldname, fieldtype, options}`: a Select's
     options, or else the page's own distinct non-empty values, plus `""` when a row is
     empty, all sorted together (so `""` first), descending only when `order_by` sorts
     that field `desc`. A
     field not in `fields` is answered as the plain name.
  8. **The answer** (`:353-372`): `data`, `columns`, `rows`, `fields`, `column_field`,
     `title_field`, `kanban_columns`, `kanban_fields`, `group_by_field`, `page_length`
     and `page_length_count` (both echoed raw, parity), `is_default`, `views`
     (milestone 7's `get_views`), `total_count` through the caller's rules,
     `row_count`, `form_script` and `list_script` (`get_form_script`, milestone 6),
     `view_type`. Every key present, even when empty.
- **Which allowlist checks which input** (root rule 10; DECISIONS 53). Readable:
  `rows`, the column keys, `title_field`, `kanban_fields`, `group_by_field`.
  Filterable: `filters`, `default_filters`, and `column_field`, checked **before** any
  column is built. Sortable: `order_by`. The engine's own fixed clauses (`creation desc`
  and the `name in` / `not in` pair of a manual kanban order, `:540-557`) are not
  checked against the caller's lists. Row keys the model lacks are named together in
  the old `_selectable`'s 417 ("Unknown field 'x' for Foundation Widget", "Unknown
  fields 'a', 'b' for …", `:375-402`; a number or null in `rows` too); a known field the
  caller may not read, filter or sort is refused with `core`'s existing texts ("Field
  'x' is not readable", for a group-by field too; "Cannot filter on 'x'"; "Cannot order
  by 'x'"). A manual card order's names are read as the key field holds them; one the
  key cannot hold (a word on an integer key, an object, null) names no card, as the old
  filter builder coerced them. The engine adds names the caller never typed
  (`group_by_field` to `rows` in the list and group-by views; the screen always sends
  `owner`; the seven standard fields), so a guard checks that every resource that opts in has the
  seven standard fields readable, and that every definition and kanban default names
  only readable fields and no restricted one. Group-by here checks the **readable** list, unlike
  `core.query.resolve_group_by` (sortable) and milestone 5's guard (filterable); the
  difference is recorded, not unified now.
- **Standard entries a model lacks** (on User: `owner`, `modified_by`, the
  `_`-prefixed fields; `tests/guards/test_field_helper_names.py`): offered by the
  metadata helpers, as `backend/`, and refused by the engine, as `backend/` refuses
  them (a filter: 400 "Unknown field 'owner' for this document type",
  `frappe_core/filters.py:468-470`; a sort: 417 "Cannot order by unknown field
  'owner'"; a group-by: 417 from `_selectable`, `:375-402`). Only User lacks them.
- **Badge counts** (`:564-598`): `_email_count` (Communication and Automated Message
  together), `_comment_count`, `_task_count`, `_note_count` per card, counts of related
  rows, **not** filtered by the caller's rules, as `backend/`; only the cards were
  filtered first. They come from a provider setting with a system check, like
  `MAIL_ACCOUNT_PROVIDER`: `counts_for(doctype, names) -> {name: {the four keys}}`,
  batched (one grouped query per kind per column). The default answers 0 for all four
  (the screen hides 0 and a missing key alike, `Deals.vue:179`); ACTIVITIES' check
  fails when its app is installed and the setting does not point at it. `core` never
  imports `activities`.
- **Crashes become 417 (PE-12e):** a `columns` or `kanban_columns` entry that is not an
  object; a `rows` or `kanban_fields` entry that is not a string; a column's `order`
  that is not a list. A `custom_view_name` that is not an integer counts as no view.
- **No cap on sent columns** (PE-23 withdrawn by the owner, 20 Nov 2026): any number of
  `kanban_columns` is taken, as `backend/`. A column's `page_length` of 0 still means no
  limit, and `page_length=0` every row (parity).
- **Gating.** Ported now onto `test-widgets/list-view/`: all of `test_get_data.py`
  (`:301` with a real view row; `:322`, `:345` with `hidden_fields`; `:284` with the
  second resource; `:442`, `:448` become 401 and the route's 404). Twins now:
  `test_phase4_metadata.py:251-339` and `:900-940` on Widget; `:347` with Widget's
  owner field; `:362` once a field with choices is added to `tests_support`; `:403`,
  `:422`; from `test_kanban_counts.py`, "an invisible row gets no counts" and
  "`all_count` is ruled". Waiting: `:374` and the count values (ACTIVITIES);
  `test_kanban_defaults.py:23`, `:36` (SALES, ACTIVITIES; `:53` is dropped with
  migration 0011); all of `test_list_definitions.py` but a `parse` twin. `.http`: no
  `get_data` block can run (each names Lead, Deal, Task or Organization); `07` 5.8 runs
  as a negative case with the generic 404 body.

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
  | `07_views_and_metadata` | the resource-only blocks 0.12-0.15, 2.5, 6.7, 7.1-7.3, 7.5, 8.5-8.8, 9.12-9.14; the view blocks §4.7 names (7); 5.8 as a negative case, the generic 404 body (8) | 5-8 | every other block, every `get_data` block among them: SALES, ACTIVITIES, CONTACTS |

  `12` 1.14 and 1.15 (a second POST, a DELETE on the singleton, 403 in `backend/`) answer
  405 under the singleton route (PE-1); so does `test_system_settings.py`
  `test_nobody_deletes_it` (403 from `frappe.client.delete` in `backend/`). Two more cases
  wait for later milestones: `test_system_settings.py`
  `test_the_defaults_page_loads_the_row_and_its_options` (`getdoctype`, milestone 5) and
  `test_currency.py` `test_the_dashboard_currency_can_be_chosen` (FCRM Settings,
  milestone 3). Two more `test_currency.py` cases wait for other units:
  `test_a_currency_that_names_nothing_is_refused` (an organization, SALES; its System
  Settings half is ported) and `test_the_dashboard_shows_the_currencys_symbol`
  (DASHBOARD). `test_boot.py` `test_the_guard_sees_the_prefixed_call` checked the old
  backend's frontend-path guard; its intent is ported as a check that the old path
  `main.js` calls has a built route-map row for `POST /api/v1/boot/`. `13` 5.3 expects `1` for EUR to USD, true only
  with `ENABLE_EXCHANGE_RATE_API` off. No `.http` block covers Email Account, System
  Settings, Country, Currency, Language or the onboarding status: pytest is their gate.
- The body comparison over the same blocks.

## 6. Decisions

| # | Decision | Status |
|---|---|---|
| 1 | Route names and methods | decided (A-27): §1 and `PORT_MAP.md`, checked at the spec review |
| 11 | The actor for the guest boot call | decided: the row comes from the data migration; `Administrator` if a create is ever needed |
| 12 | `UserSettings` | decided: a plain model, unrouted; a `core.withheld` entry only if the guard asks |
| 13 | Migration or seed for reference rows and the two settings rows | decided: a data migration (§4.2), not dev data. The owner changed S20 on 20 Nov 2026: every default row is written by data migration and put back by `restore_defaults` (§10) |
| 8 | Who edits `accounts` for §8 | decided: this unit, in milestone 4, one commit per file's concern |
| 15 | Guard exceptions for `access_key`, `api_key` | decided: written, reviewed entries at the milestone that builds each (3, 4) |
| 5 | The outbound HTTP helper before INTEGRATIONS | decided (A-30, DECISIONS 31): `backend/crm_app/integrations/http.py` ported whole as `core/http.py` (§4.3) |
| 4 | `POST /api/v1/email-accounts/` served? A PATCH re-validates? | decided (A-33, DECISIONS 36): parity, served (for System Manager or Administrator since PE-27), no re-validation (section 4.4); the owner then decided the sent password is stored (PE-30, DECISIONS 37) and a rename updates the naming field (PE-31, DECISIONS 38) |
| 7 | Where mail validation lives; how `core/mail.py` reaches an Email Account | decided (A-33, DECISIONS 39): the validators in `core/mail.py`; saved accounts through `MAIL_ACCOUNT_PROVIDER = "configuration.mail"`, with a system check (section 4.4) |
| 2, 9 | What "doctype exists" means; what a child table and a withheld doctype answer, per call; copying or regenerating `doctype_meta.json` and where its generator lives | decided (A-35, DECISIONS 41, 42): the file copied and its generator and staleness test ported, wired into CI; a doctype exists when declared and served or a served child; withheld 404 everywhere (PE-14); a child answers `getdoctype` and the layout calls only (PE-15) (section 4.5) |
| 10 | Sensitive column names in field metadata | decided (A-35, DECISIONS 43): every metadata answer leaves out the fields the caller may not read, sensitive and restricted (PE-16) |
| 3 | The saved-view rules (§4.7) | decided (A-39, DECISIONS 49-52): `user`, `public`, `is_standard`, `is_default` read-only on the resource (PE-19); `public` also applies the read rule (PE-20); `set_as_default` with a name on the caller's own view, `fetch_and_update_kanban_columns` under the read rule, saving under the write rule (PE-21); crashes become errors (PE-12d); the rest parity |
| 14 | `TRACKED_FIELDS` on CRM View Settings | decided (A-39): none, as `backend/`; its test ported as a guard |
| 6 | Kanban badge counts before ACTIVITIES | decided (A-40): a batched provider setting with a system check, answering 0 until ACTIVITIES (§4.8) |
| — | `get_data` on a withheld or child doctype | decided (A-40): no list-view route, so the generic 404 (PE-22) |
| — | The standard filter, group-by and sort entries a model lacks (on User: `owner`, `modified_by`, the `_`-prefixed fields; `tests/guards/test_field_helper_names.py`) | decided (A-40): parity, offered by the helpers and refused by the engine, as `backend/` (§4.8) |
| — | The list-view convention | decided by FOUNDATION Q6 (`specs/FOUNDATION.md:349`): `list_view_class` on the ViewSet, a class in each app's `list_views.py` (§4.8) |

Departures from `backend/` in any of these are flagged for the owner and recorded in
`PARITY_EXCEPTIONS.md` before they are built. `API_CONTRACT.md:209` (404 for a child table)
conflicts with `docs/http/07` 9.2, 9.3 (200 for `getdoctype` on `CRM Contacts`) and
`Grid.vue:545` and `stores/meta.js:9-17`: reported to the owner, not edited here (PE-15).

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
- **The outgoing-account lookup**: the saved Email Account steps of
  `find_outgoing_account` (`backend/crm_app/communication.py:400-440`) are tried **before**
  the settings-configured account, through `MAIL_ACCOUNT_PROVIDER` (section 4.4).
  `ConfigAccount` stays: the earlier plan to replace it with an unsaved `EmailAccount` is
  withdrawn (A-33), since `core` cannot build a `configuration` model. Steps 1 and 2 are
  reachable only from `email.make` (ACTIVITIES). Port `test_phase5_async.py:377` here;
  `test_mail_config_account.py:262` is ACTIVITIES'.
- **`User.default_list_data`** (the User list view, old `:309-318`) — milestone 8.
- `test_language.py:65` writes `User` through ACCOUNTS' `/api/v1/users/<name>/` route;
  `test_onboarding_status.py` calls the two onboarding paths (milestone 2).
- `docs/http/09_users_and_invitations.http` 6.5 (`get_translations`) waits on this unit
  (milestone 1).

## 9. Milestones, smallest first

| # | Holds | Gate alone today? |
|---|---|---|
| **1. Desk plumbing** | `get_apps`, `current_site_info`, `boot_config`, `clear_demo_data`, `get_translations`; no model; the two `POSTHOG_*` settings | yes |
| **2. Reference data and boot** | Country, Currency, Language, System Settings and their data migration; `FRAPPE_SYSDEFAULTS`; `get_context_for_dev` (re-creating a missing System Settings row); both onboarding calls; link search on Language, Currency and Country | yes |
| **3. FCRM Settings** | FCRM Settings (16 fields), CRM Dropdown Item and its standard rows, `core/http.py`, `get_exchange_rate`, `ENABLE_EXCHANGE_RATE_API`; PE-10 to PE-12 | yes (A-30) |
| **4. Email Account** | Email Account, User Email, `create_email_account` (`setup/`), validation in `core/mail.py`, `MAIL_ACCOUNT_PROVIDER`, `open_backend`'s saved-account branch, the signature fallback, rename, section 8 | yes (A-33); pytest only |
| **5. Field metadata** | the metadata file, its generator and CI check; "doctype exists"; `getdoctype`; `user_settings`; the four field helpers; export's provider factory; PE-14 to PE-16 | yes (A-35), on this unit's own doctypes and `tests_support` |
| **6. Layouts, scripts, quick filters** | CRM Fields Layout and its three calls, CRM Form Script and the internal `get_form_script`, CRM Global Settings, the two quick-filter calls, the default rows as `seed_dev_data` steps; PE-12c, PE-17, PE-18 | yes (A-37); content cases on Lead, Deal and Task wait |
| 7. Saved views | CRM View Settings, the eight calls, `get_views` | rules yes; default columns need a list definition |
| 8. List engine | `get_data` as the list-view mixin, the base `ListView` and `list_view_class`, `UserListView`, the badge-count provider; PE-12e, PE-22, PE-23. After milestone 7, whose views it reads | on `tests_support` and `User` only; the real gate is SALES and ACTIVITIES |

## 10. Default rows by migration, and the restore command (addendum, 21 Nov 2026)

Owner's change to REBUILD_PLAN S20 (`temp` A-48 group 4); spec-checked and reviewed
(`temp` A-57, A-58), approved (`temp` A-59). It replaces §4.6 "The default rows", §4.3's
operator command, and decision 13's parked part, and CONTACTS' seeding of industries,
salutations and genders (`specs/CONTACTS.md` §4 "Reference rows", decision H). No route
serves the restore (§10.4).

**Built:** steps 1 and 2 (§10.8) on `rebuild/owner-review-4-defaults` (22 Nov 2026).
The migration is `configuration/0012_default_rows`, not 0011 as first written: 0011
is the Email Account secret width (temp A-75). Step 3, `restore_defaults`, is built
too (`configuration/restore.py`, `contacts/restore.py`, `core/defaults.py`,
`core/management/commands/restore_defaults.py`; PE-33).

### 10.1 What moves

| Rows | Today | After |
|---|---|---|
| the 14 default field layouts | `seed_dev_data` step `fields_layouts` (`configuration/dev_data.py:50`) | data migration `configuration/0012_default_rows` |
| the 6 quick filters | step `quick_filters` (`:80`) | same migration |
| the 3 standard form scripts (product details for CRM Lead and CRM Deal; forecasting) | step `form_scripts` (`:119`) | same migration |
| the 51 industries | step `industries` (`contacts/dev_data.py`) | data migration `contacts/0004_industries` |
| salutations, genders | migration `contacts/0002`; the step `reference_rows` re-adds missing ones | migration unchanged; the step is retired (restore covers it, §10.3) |
| countries, currencies, languages; the System Settings and FCRM Settings rows; the six dropdown items | migrations `configuration/0002`, `0004`, `0006` | unchanged |

`core.dev_data.STEPS` then holds the `users` step only. Later units (statuses, lead
sources, lost reasons) write theirs by migration from the start and add a restore writer
(§10.3). The manager dashboard belongs to DASHBOARD, which builds its migration and its
force rule (§10.3) when it exists.

### 10.2 How a migration writes them

**Shared data, frozen code.** A migration imports only data constants:
- `configuration/data/default_rows.json` (the layouts, the quick filters, the
  product-details script body, the forecasting script);
- `contacts/reference_rows.py` (`INDUSTRIES`).

The precedent for reading a data file is `configuration/migrations/0004_reference_rows.py`
(`DATA / "country_info.json"`); `contacts/0002` imports `reference_rows`. The writer code
is inside each migration, never imported, so a later change to live code cannot break an
old migration on a fresh install. The live writers (`row.save(user=…)`) need
`BaseDocument.save` (`core/models.py:181-206`), which a historical model lacks.

**Columns each migration sets**, through `_default_manager.create` on historical models
(`apps.get_model`), as `contacts/migrations/0002_salutations_and_genders.py:17-31` does.
Common to all: `owner_id="Administrator"`, `modified_by_id="Administrator"`,
`creation = modified = now + offset µs` (one offset per row, in file order), `idx=0`,
`docstatus=0`; `_assign`, `_liked_by`, `_comments` and `_user_tags` keep their model
defaults (`[]`, `[]`, `[]`, `""`).

| Kind | `name` | Other columns | Skipped when |
|---|---|---|---|
| CRM Fields Layout (14) | `f"{dt}-{type}"` (its `Format` rule, `configuration/models.py:632`) | `dt`, `type`, `layout` from each `layouts[]` entry, the layout as the stored JSON text exactly as in the file | a row with that name exists |
| CRM Global Settings, quick filters (6) | `secrets.token_hex(5)`, as `configuration/0006` names dropdown items (`Hash()`, `models.py:682`) | `dt` = the key of `quick_filters`; `type="Quick Filters"` (`models.py:685`); `json` = the list, in file order | a row with that `(dt, type)` exists |
| CRM Form Script, product details (2) | `f"Product Details Script for {dt}"` (`Prompt()`; `dev_data.py:43-44`) | `dt` = `"CRM Lead"` / `"CRM Deal"`; `view="Form"`; `enabled=True`; `is_standard=True` (the model defaults are False, `models.py:660-661`); `script = "class " + dt.replace(" ", "") + " {" + product_details_script_body`, the composition of `dev_data.py:38-40` copied into the migration | a row with that name exists |
| CRM Form Script, forecasting (1) | `"Forecasting Script"` | `dt="CRM Deal"`; `view="Form"`; `enabled=True`; `is_standard=True`; `script` = `forecasting_script` from the file | a row with that name exists |
| CRM Industry (51) | the value | `industry` = the value | a row with that name exists |

It never updates a row. Dependencies:
- `configuration/0012_default_rows` → `configuration/0010_crmviewsettings` and
  `accounts/0002_seed_roles_and_users`;
- `contacts/0004_industries` → `contacts/0003_dynamic_link_address` and
  `accounts/0002_seed_roles_and_users`.

Reverse: `RunPython.noop`, as the existing data migrations.

**A changed default reaches an existing install by a new migration** that updates only
the rows still equal to the old value:
- **the old value is a literal frozen in that migration**, because the shared file
  already holds the new one;
- **the comparison is exact:**
  - a layout's `layout` text, byte for byte (whitespace counts);
  - a quick filter's `json` list, element by element, in order;
  - a script's `script` text, byte for byte;
  - for each, only the column that changed is compared and written;
- a row an administrator changed differs from the old value, and is left alone;
- on a fresh install the migration finds the new value already written by 0012 and does
  nothing.

There is no `post_migrate` re-sync. Upstream re-runs `add_default_scripts` on every
migrate (`crm/hooks.py:302-307`); v2 ships a migration when the standard script changes.

**`DevDataRecord` tidy-up:** `core/0004_retire_default_row_steps`, which depends on
`core/0003_dev_data_record`, deletes the records with `step` in `fields_layouts`,
`quick_filters`, `form_scripts`, `industries`. It is tidy-up, not safety:
`clear_dev_data` reads only the steps in `core.dev_data.STEPS`. Reverse: noop.

### 10.3 The restore command

`manage.py restore_defaults [--force]`, in `core/management/commands/`, not gated by
`DEV_DATA_ALLOWED`. It is upstream's `FCRMSettings.restore_defaults(force)` →
`after_install(force)` (`crm/fcrm/doctype/fcrm_settings/fcrm_settings.py:46-48`,
`crm/install.py:17-35`). It runs as Administrator, in one transaction.

**Where the writers live (live models, `save(user=…)`):**
- `configuration/restore.py`: layouts, quick filters, form scripts, countries,
  currencies, languages, the System Settings row, and the FCRM Settings row with its
  dropdown items;
- `contacts/restore.py`: salutations, genders, industries;
- `core/defaults.py`: `RESTORERS`, the ordered list the command runs, as
  `core/dev_data.py` lists `STEPS`.

The country, currency and language logic exists only inside
`configuration/migrations/0004_reference_rows.py`; it is copied into
`configuration/restore.py` for live models, and the migration keeps its own copy. The
same goes for the two settings rows (`0002`, `0006`).

**Deleted:**
- `configuration/dev_data.py` and `contacts/dev_data.py` whole — the step functions,
  the recording calls (`configuration/dev_data.py:65,89,115`, `contacts/dev_data.py:34`),
  the force branch's `recorded` logic (`:54,67`) and every `clear_*` function. Their
  constants and helpers (`DATA_FILE`, `default_rows()`, `product_details_script`,
  `product_script_name`) move to `configuration/restore.py`;
- the four retired lines of `core/dev_data.py` `STEPS`;
- `seed_dev_data --force`: with only the users step, which ignores it
  (`accounts/dev_data.py`), it does nothing. Dropped; `restore_defaults --force` is the
  forced path.

**Plain:** each writer adds what is missing, by its key, and changes nothing that exists:
- layouts, form scripts and industries by name;
- quick filters by `(dt, type)`;
- salutations, genders, countries, currencies and languages by name;
- the System Settings and FCRM Settings rows when missing;
- the dropdown items only when the FCRM Settings row has none (`install.py:530-542`).

Quick filters keep the key `(dt, type)`, not upstream's `dt` alone (`install.py:521`).
CRM Global Settings has a `type` column here, and quick filters are one type of several
(`CRMGlobalSettings.first_row(dt, type)`).

The one exception (owner, 21 Nov 2026): plain restore re-syncs the two standard
product-details scripts the app ships when their text drifted, and nothing else.
Upstream overwrites them (`crm_products.py:95-98`), and S20 names this exception.

Salutations, genders, countries, currencies and languages are the port's own: upstream's
`after_install` writes none of them; the old backend's seed does
(`backend/crm_app/setup.py:557-561`).

**`--force`**, in upstream's way:
- **the 14 default layouts are deleted and inserted again** (`install.py:226-263`). The
  row's history goes with it, and the new row is owned by Administrator, the command's
  actor;
- the manager dashboard is DASHBOARD's: upstream saves it in place under force
  (`crm_dashboard.py:28-32`; name, owner and creation survive). DASHBOARD adds that
  writer.

Nothing else is forced. Upstream's `add_standard_dropdown_items` has no force; the forced
branch is the old backend's (`backend/crm_app/setup.py:508-515`) and is not carried. It
is deleted with the retired steps (§10.8 step 2): the `force` parameter and its branch in
`configuration/models.py:394`, and its test (`tests/test_dropdown_items.py:134`). The
one other caller, `load_or_create` (`models.py:293`), never passes `force`.

**Never touched:** any row that is not a default (a layout, script or filter an
administrator created under another name or key), and any business record.

**Output and exit code**, as the old `seed_defaults`
(`backend/crm_app/management/commands/seed_defaults.py:35-37`):
- one line `key: count` per writer, in `RESTORERS` order, where count is the rows added
  plus the rows rewritten. Keys: `fields_layouts`, `quick_filters`, `form_scripts`,
  `countries`, `currencies`, `languages`, `system_settings`, `fcrm_settings`,
  `dropdown_items`, `salutations`, `genders`, `industries`;
- then `N row(s) written`;
- exit code 0. Any error rolls the transaction back and exits non-zero, as a
  `CommandError`.

### 10.4 A settings route: not served

Not served; the command is the way, as in the old backend (owner, 21 Nov 2026; S20,
`REBUILD_PLAN.md:68`, says the same). The facts:
- upstream offers it as a Desk button on FCRM Settings (`run_doc_method`,
  `frappe/handler.py:339`); `backend_v2` offers the command only, run by an operator;
- the button is in the Desk form only (`crm/fcrm/doctype/fcrm_settings/fcrm_settings.js:16-46`);
  no file under `frontend/src` calls it (the field is listed in the old backend's
  `backend/crm_app/data/doctype_meta.json:3159`);
- the old backend has no HTTP route, only the `seed_defaults` command.


### 10.5 Differences to record

- **On upgrade, a default an administrator deleted comes back once.** The migration
  cannot tell such a database from one the seed never filled. Upstream re-creates only
  the scripts on migrate.
- **A renamed default layout is added again, and takes over.** Defaults are keyed by
  their shipped name, so a renamed `CRM Lead-Quick Entry` counts as missing on the
  migration and on every restore; the re-added default has the same `(dt, type)`, and
  `CRMFieldsLayout.row_for` (`configuration/models.py:607-610`, the first by name) then
  returns it rather than the administrator's renamed row. Upstream keys by name too and
  behaves much the same. Recorded, no remedy (PE-33).
- **The standard dropdown items are added only when the row has none**, as upstream.
  The old backend's `seed_defaults --force` also restored them by `name1`, its remedy for
  upstream bug 47 (`UPSTREAM_BUGS.md`); that branch is not carried (A-59), so an
  administrator who changes a standard item gets it back only by emptying the menu and
  running `restore_defaults` (PE-33).

### 10.6 Tests

**Rule for transactional tests.** A transactional test flushes the database, and with it
every migration-written row. `conftest.py:17-39` re-creates only Administrator and
Guest. A transactional test that needs a default row re-creates it through a fixture.
The five transactional tests today — `core/tests/test_tree.py:231,262`,
`tests/test_hierarchy_concurrency.py:45,74`, `tests/test_walk_auth_flow.py:12` — read no
default row (no layout, quick filter, script, industry or reference row in them or in
`scripts/walk_auth_flow.py`), so they need no fixture. They pass after a flush only
because pytest-django runs transactional tests last.

**Rewritten whole:**
- `tests/test_configuration_dev_data.py` becomes `tests/test_configuration_defaults.py`:
  - the data-file tests (`:19`, `:29`) stay as they are;
  - every step test (`:34-160`) is replaced by the restore tests below.
- `tests/test_contacts_dev_data.py` becomes `tests/test_contacts_defaults.py`, with
  each test replaced:

| Today | Replaced by |
|---|---|
| `:18` the migration wrote the lists, the step adds none | restore adds 0 salutations, genders, industries on a migrated database |
| `:22` a deleted salutation is put back by the step | restore puts a deleted salutation back |
| `:28` 51 industries written once | the migration wrote the 51 (`set == INDUSTRIES`); restore after deleting one adds 1, a second run 0 |
| `:35-45` clear removes seeded industries, keeps a reference row | `clear_dev_data` leaves every industry, salutation and gender, an administrator's `Handmade` industry included |
| `:48-51` `STEPS[4:]` | `STEPS` keys are `["users"]` |
| `:54-67` `seed_dev_data` puts a deleted salutation back | `restore_defaults` puts it back; `seed_dev_data` does not; `clear_dev_data` keeps it |

**Changed, one by one:**

| Test | Today | After |
|---|---|---|
| `tests/test_configuration_dev_data.py:36-38` | `STEPS[:4]` are users and the three CONFIGURATION steps | (in the new file) `STEPS` keys are `["users"]` |
| `:40-47` layouts written once and recorded | — | the migration wrote 14, named `{dt}-{type}`; restore adds 0; after deleting one adds 1 and records nothing |
| `:49-55` an existing layout is left alone, off the record | — | plain restore leaves an edited default layout edited |
| `:57-67` force rewrites a layout, keeps the record | — | `--force` rewrites an edited default layout, owned by Administrator; an administrator's own layout under another name survives |
| `:70-77` quick filters skip a doctype with a row | — | restore skips a `(dt, "Quick Filters")` that has a row; deleting one default brings back that one |
| `:79-99` form scripts written once | — | the migration wrote the 3 with `enabled`, `is_standard`, `view="Form"` and the composed text; restore adds 0 |
| `:101-107` quick filter rows match the data file | — | the migration's 6 rows match the file, `type="Quick Filters"` |
| `:109-123` a second seed keeps one record per row | — | dropped: nothing is recorded |
| `:125-140` a row deleted and seeded again is still cleared | — | dropped: `clear_dev_data` never removes a default; one test asserts that for all four kinds |
| `:142-154` a drifted product script gets its text back | — | plain restore re-syncs it; the forecasting script's drift is kept |
| `:156-160` clear removes only the scripts the seed created (creates `Forecasting Script`) | — | dropped with the clear functions |
| `tests/test_layout_resources.py:143-147` POSTs `CRM Lead-Quick Entry` | now a default: 409 | POSTs a pair with no default (`dt="CRM Task", type="Side Panel"`; `CRM Task-Quick Entry` is itself one of the 14 defaults), same assertions with the name `CRM Task-Side Panel` |
| `:151`, `:169` create `CRM Lead-Side Panel` | now a default | `dt="CRM Task"`, `type="Side Panel"`; same assertions |
| `:165` no layout exists | the 14 exist | `CRMFieldsLayout.objects.count() == 14` (nothing was added) |
| `:187`, `:200` `get_form_script("CRM Lead") is None` | the standard script exists | `make_script(..., dt="CRM Task")` and `get_form_script("CRM Task")`; CRM Task has no standard script; the assertions are kept |
| `:206` `CRMGlobalSettings.objects.get()` | six rows | `CRMGlobalSettings.objects.get(dt="CRM Lead", type="Quick Filters", json=["status"])` — the POSTed row; the defaults' CRM Lead row has another list |
| `tests/test_fields_layout_calls.py:260` | no layout exists | `count() == 14` |
| `tests/test_quick_filters.py:94` | `count() == 1` | `count() == 7`: the six defaults and the one row for CRM Fields Layout |
| `test_quick_filters.py:153` | none exists | `count() == 6` |
| `tests/test_dev_data_commands.py:83-85` | `77 row(s) created` | `3 row(s) created`, the users step alone; the comment goes |
| `:162-164` | `77 row(s) removed` | `3 row(s) removed` |

**New:**
- **The migrations write what §10.2 says.** In a plain `db` test: delete the rows, call
  each migration's function with `loader.project_state(...).apps` at that migration,
  and assert every column of §10.2's table on the rows it wrote. This fails if the
  function needs `save(user=…)` or a live helper. No reverse-then-forward test: with a
  noop reverse, the forward pass skips every row and proves nothing.
- **The `DevDataRecord` tidy-up.** Records for the four steps and one for `users`; call
  `core/0004`'s function; only the `users` record is left.
- **An upgrade from a database the old seed filled.** Rows plus their `DevDataRecord`
  rows, as the old steps wrote them; run the three functions; the rows are unchanged,
  the four steps' records are gone, and `clear_dev_data` leaves every row.
- **Restore plain:**
  - a deleted default comes back, for each kind;
  - an edited default stays edited (the two standard product scripts excepted);
  - an administrator's own row is untouched;
  - a second run writes 0;
  - a missing FCRM Settings row comes back with its six items;
  - the output lines and the total match §10.3.
- **Restore `--force`:**
  - an edited default layout is rewritten, owned by Administrator;
  - an edited quick filter is untouched;
  - an administrator's own layout under another name survives.
- **The command runs with `DEV_DATA_ALLOWED` unset.**
- **A failing writer** (forced) rolls everything back and exits non-zero.
- The dashboard under force: DASHBOARD's.

### 10.7 Notes to record

- A force restore while a user saves the same default layout can fail for that user,
  because the row is deleted under them. Recorded; no remedy.
- `clear_dev_data` fails, and rolls back, if a seeded user edited a default row
  (`owner` / `modified_by` are PROTECT). That is older than this change and likelier
  after it. Carried to the owner's dev-data discussion by the supervisor.

### 10.8 Order of building

1. **The migrations, with their tests:** `configuration/0012_default_rows`,
   `contacts/0004_industries`, `core/0004_retire_default_row_steps`.
2. **Retire the dev-data steps and fix the tests they break:** the steps and
   `dev_data.py` modules are deleted, `seed_dev_data --force` is dropped, the forced
   dropdown branch and its test are deleted, and the §10.6 rewrites and changes are made.
3. **The restore command:** `configuration/restore.py`, `contacts/restore.py`,
   `core/defaults.py`, the command, and their tests.
