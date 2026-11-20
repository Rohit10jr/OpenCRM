# CONFIGURATION — CRM settings, email accounts, saved views, layouts and the list engine

**Status: Ready for milestones 1-5 (addenda: milestone 3 A-30, milestone 4 A-33, milestone 5 A-35) — rewritten 18 Nov 2026** from the spec check
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
  migration or a seed is **open — before milestones 3 and 6**.

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
  *, user, force=False)` is ported whole, force branch included; the operator command
  that calls it with `force` (`seed_defaults --force`, `setup.py:508-515`) is milestone 6's.
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
  - PE-10 (proposed): `get_exchange_rate` accepts `date` only as `latest` or an ISO date
    (ASCII digits, a real date) and currencies only as three-letter codes (ASCII
    letters, either case, used as given); the old backend passes them through.
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

- **Rules:** everyone reads an Email Account (the Profile picker lists them; upstream bug
  #17); the manager pair or Administrator creates, writes and deletes
  (`platform_docs.py:158-186`). Route `email-accounts/` (list, POST, `<name>/` GET, PATCH,
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
  the name check, as in `backend/`; a `password` or `api_secret` sent on update is
  ignored with 200 (`frappe_core/serializers.py:253-257`). **Known difference from
  upstream, parked for the owner (DECISIONS 37):** `EmailEdit.vue:104-118` sends
  `password` with every save and upstream stores it; here, as in `backend/`, it is
  discarded.
- **Rename** keeps `email_account_name` at the old value, as `backend/`
  (`frappe_core/rename.py:41-45`; `backend_v2/core/rename.py:14-20`). Upstream updates
  the naming field (`frappe/model/rename_doc.py:319,323-328`). Parked for the owner
  (DECISIONS 38); a test pins today's behaviour.
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
| `public` | Administrator or Sales Manager only, System Manager excluded, on any user's view, without the object rule; clears `user` (`view_settings.py:205-229`) |
| `delete` | as the resource rule for a public view (`view_settings.py:37-48`) |
| `create`, `update`, `pin` | as `backend/`'s `view_settings.py` decides each, read at milestone 7 |
| `set_as_default` | no permission check, as upstream; `name` is optional (`view_settings.py:249-270`), so the route is a collection action with `name` in the body |
| `fetch_and_update_kanban_columns` | no permission check, as upstream; a missing name answers `None` (`view_settings.py:322`) |

A public view has no owner. Whether `backend_v2` matches every row or narrows the
resource side is decision 3. `clear_old_versions` already prunes CRM View Settings
versions (`backend_v2/core/tasks.py`); whether the model declares `TRACKED_FIELDS` follows
what `backend/` tracks, decided at milestone 7 (decision 14).

### 4.8 The list engine (milestone 8)

- `get_data`'s response shape, every key present even when empty.
- It reads through the resource's own queryset and field rules (root `CLAUDE.md` rule
  11). In `backend/` it resolves any registered doctype (`frappe_core/api/doc.py:229`);
  `backend_v2` serves it per resource (§6, the last row).
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
| 13 | Migration or seed for reference rows and the two settings rows | decided: a data migration (§4.2), not dev data |
| 8 | Who edits `accounts` for §8 | decided: this unit, in milestone 4, one commit per file's concern |
| 15 | Guard exceptions for `access_key`, `api_key` | decided: written, reviewed entries at the milestone that builds each (3, 4) |
| 5 | The outbound HTTP helper before INTEGRATIONS | decided (A-30, DECISIONS 31): `backend/crm_app/integrations/http.py` ported whole as `core/http.py` (§4.3) |
| 4 | `POST /api/v1/email-accounts/` served? A PATCH re-validates? | decided (A-33, DECISIONS 36): parity, served for the manager pair, no re-validation, a sent password ignored (section 4.4); the discarded password and the stale naming field after a rename are parked for the owner (DECISIONS 37, 38) |
| 7 | Where mail validation lives; how `core/mail.py` reaches an Email Account | decided (A-33, DECISIONS 39): the validators in `core/mail.py`; saved accounts through `MAIL_ACCOUNT_PROVIDER = "configuration.mail"`, with a system check (section 4.4) |
| 2, 9 | What "doctype exists" means; what a child table and a withheld doctype answer, per call; copying or regenerating `doctype_meta.json` and where its generator lives | decided (A-35, DECISIONS 41, 42): the file copied and its generator and staleness test ported, wired into CI; a doctype exists when declared and served or a served child; withheld 404 everywhere (PE-14); a child answers `getdoctype` and the layout calls only (PE-15) (section 4.5) |
| 10 | Sensitive column names in field metadata | decided (A-35, DECISIONS 43): every metadata answer leaves out the fields the caller may not read, sensitive and restricted (PE-16) |
| 3 | The saved-view rules (§4.7) | **open — before milestone 7** [default: the resource applies the same role rule as the dedicated call; the unchecked calls get the object rule; proposed parity exceptions] |
| 14 | `TRACKED_FIELDS` on CRM View Settings | **open — at milestone 7**, following what `backend/` tracks |
| 6 | Kanban badge counts before ACTIVITIES | **open — before milestone 8** |
| — | `get_data` on a withheld or child doctype | **open — before milestone 8** [default: refused, as the contract says] |
| — | The standard filter, group-by and sort entries a model lacks (on User: `owner`, `modified_by`, the `_`-prefixed fields; `tests/guards/test_field_helper_names.py`) | **open — before milestone 8**, where the User list view is built [today: offered, as `backend/`; the alternative is a parity exception dropping them] |

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
| 6. Layouts, scripts, quick filters | CRM Fields Layout and its three calls, CRM Form Script, CRM Global Settings, the quick-filter calls, default seeds, and the operator command that restores standard rows (`seed_defaults --force`, which calls `add_standard_dropdown_items(force=True)`) | partly; content cases name Lead or Task |
| 7. Saved views | CRM View Settings, the eight calls, `get_views` | rules yes; default columns need a list definition |
| 8. List engine | `get_data` as the list-view mixin, the list-definition convention, `User.default_list_data` | on `tests_support` and `User` only; the real gate is SALES and ACTIVITIES |
