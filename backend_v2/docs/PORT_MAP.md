# Port map — every old endpoint and doctype, and where it goes

**Seeded on 2026-09-16** from `docs/ROUTES.md` (123 method paths, 58 doctypes) and the
`docs/http/*.http` files, by a one-off script. **Refreshed on 2026-11-12** against
`docs/ROUTES.md` at `main` `8f5ff1b` (134 method paths, 71 doctypes): the 24 rows `main`
added since are placed in units, and protections and declared fields changed since are
updated. **Maintained by hand from here on**: when a row moves, edit the row. Do not
regenerate it; that would erase the Status column.

This file is the **one home of per-row status**. Unit status lives in
`backend_v2/specs/README.md` and nowhere else.

**The rows are the old paths.** `backend_v2` serves REST routes under `/api/v1/` instead
(REBUILD_PLAN S6), each answering like the old path it replaces. **The route map** is
the **New route** column, giving each row its method, REST path and any reshaped input
(REBUILD_PLAN S7, S8), following the naming rules in REBUILD_PLAN S25. It is written a
unit at a time, before the unit's spec check: a method-path table without the column
belongs to a unit whose routes are not written yet, and its **New app** and **Unit**
columns say where the code will live.

**Paths are from the repository root.** The **Old source** column is the exception: it
is relative to `backend/`, and names the **function** (`crm_app/api/contact.py:create_new`),
not a line — line numbers drifted with every fix to `backend/`. A brief names the `main`
commit its reference was read at.

## How to use it

- **Building a unit:** your scope is every row under your unit's heading. **Old source**
  is the file to read in `backend/` (read-only) before writing the new code.
- **Carrying protections over:** **Old protection** and **Declared fields** are what the
  old backend enforces today. A doctype row is not `built` until each one is enforced in
  `backend_v2/`, or `backend_v2/docs/PARITY_EXCEPTIONS.md` has an entry saying why not.
  Declared fields: `S` sensitive (never on the wire, not selectable, not filterable),
  `E` encrypted at rest, `R` restricted to managers, `RO` readable but never writable.
- **Status values:** `—` not started · `built` code and its pytest tests are in place ·
  `parity` its `.http` blocks pass against `backend_v2` · `exception` differs on purpose,
  see `PARITY_EXCEPTIONS.md`.

---

## Routes that are not a dotted path or a doctype

| Route | New app | Unit | Status |
|---|---|---|---|
| `/api/resource/<DocType>` — list, create. Not served by `backend_v2`: replaced by each resource's collection route | each resource's app | each resource's unit | — |
| `/api/resource/<DocType>/<name>` — read, update, delete. Not served by `backend_v2`: replaced by each resource's document route | each resource's app | each resource's unit | — |
| `ws/realtime?token=<access>` — WebSocket | notifications | NOTIFICATIONS | — |
| `/admin/` — Django admin, not part of the contract | config | FOUNDATION | — |

## Models that are not doctypes

| Old model | What it is | New app | Unit | Status |
|---|---|---|---|---|
| `frappe_core.NamingSeriesCounter` | One counter row per resolved naming-series prefix | core | FOUNDATION | — |
| `frappe_platform.UserSettings` | Per-user list-view state behind `frappe.model.utils.user_settings.*` | configuration | CONFIGURATION | — |
| SimpleJWT `token_blacklist` tables | Rotated and logged-out refresh tokens | accounts | FOUNDATION | — |

---

## Which unit turns each `.http` file green

The files named here are the old ones in `docs/http/`; `backend_v2` runs their REST copies
in `backend_v2/http/`, generated from the route map (REBUILD_PLAN S9). A file can only pass in full once every unit it
touches is built. Touched units are found by scanning each file for method paths,
resource doctypes and `doctype` parameters, so treat this as a guide: a block can depend
on seed data from a unit the scan cannot see.

| File | Units it touches | Green once this unit is built |
|---|---|---|
| `00_walkthrough.http` | FOUNDATION, ACCOUNTS, CONFIGURATION, CONTACTS, SALES, ACTIVITIES | ACTIVITIES |
| `01_auth.http` | FOUNDATION, ACCOUNTS | ACCOUNTS |
| `02_resource_grammar.http` | FOUNDATION, CONTACTS, SALES | SALES |
| `03_leads.http` | FOUNDATION, CONFIGURATION, CONTACTS, SALES, ACTIVITIES | ACTIVITIES |
| `04_deals.http` | FOUNDATION, CONFIGURATION, SHARED_ACTIONS, CONTACTS, SALES | SALES |
| `05_contacts_organizations.http` | FOUNDATION, SHARED_ACTIONS, CONTACTS, SALES | SALES |
| `06_tasks_notes_calls.http` | FOUNDATION, CONFIGURATION, SHARED_ACTIONS, CONTACTS, SALES, ACTIVITIES | ACTIVITIES |
| `07_views_and_metadata.http` | FOUNDATION, CONFIGURATION, CONTACTS, SLA, SALES, ACTIVITIES | ACTIVITIES |
| `08_activities_comments_notifications.http` | FOUNDATION, NOTIFICATIONS, SALES, ACTIVITIES | ACTIVITIES |
| `09_users_and_invitations.http` | FOUNDATION, ACCOUNTS, CONFIGURATION, SALES, ACTIVITIES | ACTIVITIES |
| `10_dashboard.http` | FOUNDATION, DASHBOARD | DASHBOARD |
| `11_permissions_matrix.http` | FOUNDATION, ACCOUNTS, CONFIGURATION, SHARED_ACTIONS, SALES, ACTIVITIES, DASHBOARD | DASHBOARD |
| `12_settings_singletons.http` | FOUNDATION, CONFIGURATION, SALES, INTEGRATIONS | INTEGRATIONS |
| `13_bulk_and_misc.http` | FOUNDATION, ACCOUNTS, CONFIGURATION, SHARED_ACTIONS, CONTACTS, NOTIFICATIONS, SALES, ACTIVITIES | ACTIVITIES |
| `99_lockout.http` | FOUNDATION, ACCOUNTS | ACCOUNTS |

---

## FOUNDATION

### Doctypes (2)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| User | main | default | ruled: list rule, object rule | S: `groups`, `user_permissions`, `is_superuser`, `is_staff`, `reset_password_key`, `last_reset_password_key_generated_on`, `token_version`; RO: `enabled`, `user_type` | `frappe_platform.User` | accounts | — |
| Version | withheld | `Hash(10)` | withheld — `specs/UNROUTED_DOCTYPES.md` |  | `frappe_core.Version` | core | — |

### Method paths (12)

The eight `frappe.client.*` rows are the generic document calls. In `backend_v2` they
become the base ViewSet's CRUD, which every resource inherits, so their new routes are
each resource's own collection and document routes. FOUNDATION builds the base; each unit
proves it on its own resources, and writes their **New route** in its own rows.

The four auth routes serve one method each (REBUILD_PLAN S25 (6)). Inputs keep their
names: `usr`/`pwd` with the aliases `username`/`email`/`password`, and `refresh` with
the alias `refresh_token`, all in the body. The old paths also answered a second verb
(`logout` GET, `get_logged_user` POST); the new routes do not serve it.

| Dotted path | Verbs | Access | Old source | New route | New app | Status |
|---|---|---|---|---|---|---|
| `frappe.auth.get_logged_user` | GET/POST | auth | `frappe_core/api/auth.py:get_logged_user` | `GET /api/v1/auth/me/` | accounts | built |
| `frappe.client.delete` | DELETE/POST | auth | `crm_app/api/client.py:client_delete` | each resource's, in its unit | core | — |
| `frappe.client.get_doc_permissions` | GET/POST | auth | `crm_app/api/client.py:client_get_doc_permissions` | each resource's, in its unit | core | — |
| `frappe.client.get_list` | GET/POST | auth | `crm_app/api/client.py:client_get_list` | each resource's, in its unit | core | — |
| `frappe.client.get_single_value` | GET/POST | auth | `crm_app/api/client.py:client_get_single_value` | each resource's, in its unit | core | — |
| `frappe.client.get_value` | GET/POST | auth | `crm_app/api/client.py:client_get_value` | each resource's, in its unit | core | — |
| `frappe.client.get` | GET/POST | auth | `crm_app/api/client.py:client_get` | by `name`: each resource's, in its unit. By `filters`: **not served: no caller** (PE-3) | core | — |
| `frappe.client.insert` | POST | auth | `crm_app/api/client.py:client_insert` | each resource's, in its unit | core | — |
| `frappe.client.set_value` | POST/PUT | auth | `crm_app/api/client.py:client_set_value` | each resource's, in its unit | core | — |
| `login` | POST | guest | `frappe_core/api/auth.py:login` | `POST /api/v1/auth/login/` | accounts | built |
| `logout` | POST/GET | auth | `frappe_core/api/auth.py:logout` | `POST /api/v1/auth/logout/` | accounts | built |
| `token/refresh` | POST | guest | `frappe_core/api/auth.py:refresh_token` | `POST /api/v1/auth/token/refresh/` | accounts | built |

## ACCOUNTS

### Doctypes (3)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| CRM Invitation | main | `Hash(10)` | ruled: list rule, object rule | S: `key` | `crm_app.CRMInvitation` | accounts | — |
| CRM Sales Hierarchy | main | `Hash(10)` | ruled: list rule, object rule |  | `crm_app.CRMSalesHierarchy` | accounts | — |
| User Email | child | `Hash(10)` | n/a |  | `frappe_platform.UserEmail` | accounts | — |

### Method paths (13)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.accept_invitation` | GET/POST | guest | `crm_app/api/auth_pages.py:accept_invitation` | accounts | — |
| `crm.api.auth.oauth_providers` | GET/POST | guest | `crm_app/api/auth.py:oauth_providers` | accounts | — |
| `crm.api.get_user_signature` | GET/POST | auth | `crm_app/api/misc.py:get_user_signature` | accounts | — |
| `crm.api.invite_by_email` | GET/POST | auth | `crm_app/api/misc.py:invite_by_email` | accounts | — |
| `crm.api.session.get_user_info` | GET/POST | auth | `crm_app/api/session.py:get_user_info` | accounts | — |
| `crm.api.session.get_users` | GET/POST | auth | `crm_app/api/session.py:get_users` | accounts | — |
| `crm.api.user.add_existing_users` | GET/POST | auth | `crm_app/api/user.py:add_existing_users` | accounts | — |
| `crm.api.user.change_password` | GET/POST | auth | `crm_app/api/user.py:change_password` | accounts | — |
| `crm.api.user.remove_crm_roles_from_user` | GET/POST | auth | `crm_app/api/user.py:remove_crm_roles_from_user` | accounts | — |
| `crm.api.user.update_user_role` | GET/POST | auth | `crm_app/api/user.py:update_user_role` | accounts | — |
| `frappe.core.doctype.user.user.get_timezones` | GET/POST | auth | `crm_app/api/desk.py:get_timezones` | accounts | — |
| `frappe.core.doctype.user.user.reset_password` | POST | guest | `crm_app/api/auth_pages.py:reset_password` | accounts | — |
| `frappe.core.doctype.user.user.update_password` | POST | guest | `crm_app/api/auth_pages.py:update_password` | accounts | — |

## CONFIGURATION

### Doctypes (11)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| CRM Fields Layout | main | `Format('{dt}-{type}')` | ruled: list rule, object rule |  | `crm_app.CRMFieldsLayout` | configuration | — |
| CRM Form Script | main | `Prompt()` | ruled: list rule, object rule |  | `crm_app.CRMFormScript` | configuration | — |
| CRM Global Settings | main | `Hash(10)` | reviewed-open — no secrets: holds only `dt`, `type` and a JSON blob. Upstream grants all three roles full CRUD (`crm_global_settings.json`), deliberately. Reproduced. |  | `crm_app.CRMGlobalSettings` | configuration | — |
| CRM View Settings | main | `AutoIncrement()` | ruled: list rule, object rule |  | `crm_app.CRMViewSettings` | configuration | — |
| Country | main | `FieldValue('country_name')` | ruled: list rule, object rule |  | `frappe_platform.Country` | configuration | — |
| Currency | main | `FieldValue('currency_name')` | ruled: list rule, object rule |  | `frappe_platform.Currency` | configuration | — |
| Email Account | main | `FieldValue('email_account_name')` | ruled: list rule, object rule | S: `password`, `api_secret`; E: `password`, `api_secret`; R: `smtp_server`, `smtp_port`, `email_server`, `incoming_port`, `login_id`, `domain`, `api_key`, `frappe_mail_site`, `signature`, `no_smtp_authentication`, `awaiting_password` | `frappe_platform.EmailAccount` | configuration | — |
| FCRM Settings | single | default | ruled: list rule, object rule | R: `access_key` | `crm_app.FCRMSettings` | configuration | — |
| Language | main | `FieldValue('language_code')` | ruled: list rule, object rule |  | `frappe_platform.Language` | configuration | — |
| System Settings | single | default | ruled: list rule, object rule |  | `frappe_platform.SystemSettings` | configuration | — |
| CRM Dropdown Item | child | `Hash(10)` | n/a |  | `crm_app.CRMDropdownItem` | configuration | — |

### Method paths (32)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.doc.get_data` | GET/POST | auth | `frappe_core/api/doc.py:get_data` | configuration | — |
| `crm.api.doc.get_fields` | GET/POST | auth | `crm_app/api/doc.py:get_fields` | configuration | — |
| `crm.api.doc.get_filterable_fields` | GET/POST | auth | `crm_app/api/doc.py:get_filterable_fields` | configuration | — |
| `crm.api.doc.get_group_by_fields` | GET/POST | auth | `crm_app/api/doc.py:get_group_by_fields` | configuration | — |
| `crm.api.doc.get_quick_filters` | GET/POST | auth | `crm_app/api/doc.py:get_quick_filters` | configuration | — |
| `crm.api.doc.sort_options` | GET/POST | auth | `crm_app/api/doc.py:sort_options` | configuration | — |
| `crm.api.doc.update_quick_filters` | GET/POST | auth | `crm_app/api/doc.py:update_quick_filters` | configuration | — |
| `crm.api.exchange_rate.get_exchange_rate` | GET/POST | auth | `crm_app/api/exchange_rate.py:get_exchange_rate` | configuration | — |
| `crm.api.get_translations` | GET/POST | guest | `crm_app/api/misc.py:get_translations` | configuration | — |
| `crm.api.settings.create_email_account` | GET/POST | auth | `crm_app/api/settings.py:create_email_account` | configuration | — |
| `crm.api.views.get_views` | GET/POST | auth | `crm_app/api/views.py:get_views` | configuration | — |
| `crm.demo.api.clear_demo_data` | POST | auth | `crm_app/api/demo.py:clear_demo_data` | configuration | — |
| `crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout` | GET/POST | auth | `crm_app/api/fields_layout.py:get_fields_layout` | configuration | — |
| `crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections` | GET/POST | auth | `crm_app/api/fields_layout.py:get_sidepanel_sections` | configuration | — |
| `crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.save_fields_layout` | POST | auth | `crm_app/api/fields_layout.py:save_fields_layout` | configuration | — |
| `crm.fcrm.doctype.crm_view_settings.crm_view_settings.create_or_update_standard_view` | POST | auth | `crm_app/api/view_settings.py:create_or_update_standard_view` | configuration | — |
| `crm.fcrm.doctype.crm_view_settings.crm_view_settings.create` | POST | auth | `crm_app/api/view_settings.py:create` | configuration | — |
| `crm.fcrm.doctype.crm_view_settings.crm_view_settings.delete` | POST/DELETE | auth | `crm_app/api/view_settings.py:delete` | configuration | — |
| `crm.fcrm.doctype.crm_view_settings.crm_view_settings.fetch_and_update_kanban_columns` | POST | auth | `crm_app/api/view_settings.py:fetch_and_update_kanban_columns` | configuration | — |
| `crm.fcrm.doctype.crm_view_settings.crm_view_settings.pin` | POST | auth | `crm_app/api/view_settings.py:pin` | configuration | — |
| `crm.fcrm.doctype.crm_view_settings.crm_view_settings.public` | POST | auth | `crm_app/api/view_settings.py:public` | configuration | — |
| `crm.fcrm.doctype.crm_view_settings.crm_view_settings.set_as_default` | POST | auth | `crm_app/api/view_settings.py:set_as_default` | configuration | — |
| `crm.fcrm.doctype.crm_view_settings.crm_view_settings.update` | POST/PUT | auth | `crm_app/api/view_settings.py:update` | configuration | — |
| `crm.www.crm.get_context_for_dev` | POST | guest | `crm_app/api/boot.py:get_context_for_dev` | configuration | — |
| `frappe.apps.get_apps` | GET/POST | auth | `crm_app/api/desk.py:get_apps` | configuration | — |
| `frappe.desk.form.load.getdoctype` | GET/POST | auth | `crm_app/api/form_load.py:getdoctype` | configuration | — |
| `frappe.integrations.frappe_providers.frappecloud_billing.current_site_info` | GET/POST | auth | `crm_app/api/desk.py:current_site_info` | configuration | — |
| `frappe.model.utils.user_settings.get` | GET/POST | auth | `crm_app/api/user_settings.py:get` | configuration | — |
| `frappe.model.utils.user_settings.save` | GET/POST | auth | `crm_app/api/user_settings.py:save` | configuration | — |
| `frappe.onboarding.get_onboarding_status` | GET/POST | auth | `crm_app/api/onboarding.py:get_onboarding_status` | configuration | — |
| `frappe.onboarding.update_user_onboarding_status` | GET/POST | auth | `crm_app/api/onboarding.py:update_user_onboarding_status` | configuration | — |
| `frappe.utils.telemetry.pulse.client.boot_config` | GET/POST | auth | `crm_app/api/desk.py:boot_config` | configuration | — |

## SHARED_ACTIONS

The mixins live in `core` (REBUILD_PLAN S24); each resource opts in.

### Method paths (7)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.doc.delete_bulk_docs` | GET/POST | auth | `crm_app/api/doc.py:delete_bulk_docs` | core | — |
| `crm.api.doc.get_linked_docs_of_document` | GET/POST | auth | `crm_app/api/doc.py:get_linked_docs_of_document` | core | — |
| `crm.api.doc.remove_linked_doc_reference` | GET/POST | auth | `crm_app/api/doc.py:remove_linked_doc_reference` | core | — |
| `frappe.client.rename_doc` | POST | auth | `crm_app/api/client.py:client_rename_doc` | core | — |
| `frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs` | POST | auth | `crm_app/api/bulk_update.py:submit_cancel_or_update_docs` | core | — |
| `frappe.desk.reportview.export_query` | GET/POST | auth | `crm_app/api/reportview.py:export_query` | core | — |
| `frappe.desk.search.search_link` | GET/POST | auth | `crm_app/api/client.py:search_link` | core | — |

## CONTACTS

### Doctypes (9)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| Address | main | default | ruled: list rule, object rule |  | `frappe_platform.Address` | contacts | — |
| CRM Industry | main | `FieldValue('industry')` | reviewed-open — reference data - industry vocabulary, shown on organisation forms |  | `crm_app.CRMIndustry` | contacts | — |
| CRM Organization | main | `FieldValue('organization_name')` | reviewed-open — upstream's role table gives every CRM role read, write, create and delete, and upstream adds no row-level hook (hooks.py). Holds shared customer organisations. |  | `crm_app.CRMOrganization` | contacts | — |
| Contact | main | default | ruled: list rule, object rule |  | `frappe_platform.Contact` | contacts | — |
| Gender | main | `FieldValue('gender')` | ruled: list rule, object rule |  | `frappe_platform.Gender` | contacts | — |
| Salutation | main | `FieldValue('salutation')` | ruled: list rule, object rule |  | `frappe_platform.Salutation` | contacts | — |
| Contact Email | child | `Hash(10)` | n/a |  | `frappe_platform.ContactEmail` | contacts | — |
| Contact Phone | child | `Hash(10)` | n/a |  | `frappe_platform.ContactPhone` | contacts | — |
| Dynamic Link | child | `Hash(10)` | n/a |  | `frappe_platform.DynamicLink` | contacts | — |

### Method paths (5)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.contact.create_new` | GET/POST | auth | `crm_app/api/contact.py:create_new` | contacts | — |
| `crm.api.contact.get_linked_deals` | GET/POST | auth | `crm_app/api/contact.py:get_linked_deals` | contacts | — |
| `crm.api.contact.search_emails` | GET/POST | auth | `crm_app/api/contact.py:search_emails` | contacts | — |
| `crm.api.contact.set_as_primary` | GET/POST | auth | `crm_app/api/contact.py:set_as_primary` | contacts | — |
| `crm.api.session.get_organizations` | GET/POST | auth | `crm_app/api/session.py:get_organizations` | contacts | — |

## NOTIFICATIONS

### Doctypes (1)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| CRM Notification | main | `Hash(10)` | ruled: list rule, object rule |  | `crm_app.CRMNotification` | notifications | — |

### Method paths (2)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.notifications.get_notifications` | GET/POST | auth | `crm_app/api/notifications.py:get_notifications` | notifications | — |
| `crm.api.notifications.mark_as_read` | GET/POST | auth | `crm_app/api/notifications.py:mark_as_read` | notifications | — |

## SLA

### Doctypes (6)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| CRM Holiday List | main | `FieldValue('holiday_list_name')` | reviewed-open — reference data - business calendar, read by the SLA engine |  | `crm_app.CRMHolidayList` | sla | — |
| CRM Service Level Agreement | main | `FieldValue('sla_name')` | ruled: list rule, object rule |  | `crm_app.CRMServiceLevelAgreement` | sla | — |
| CRM Holiday | child | `Hash(10)` | n/a |  | `crm_app.CRMHoliday` | sla | — |
| CRM Rolling Response Time | child | `Hash(10)` | n/a |  | `crm_app.CRMRollingResponseTime` | sla | — |
| CRM Service Day | child | `Hash(10)` | n/a |  | `crm_app.CRMServiceDay` | sla | — |
| CRM Service Level Priority | child | `Hash(10)` | n/a |  | `crm_app.CRMServiceLevelPriority` | sla | — |

## SALES

### Doctypes (12)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| CRM Communication Status | main | `FieldValue('status')` | reviewed-open — reference data - communication status vocabulary |  | `crm_app.CRMCommunicationStatus` | sales | — |
| CRM Deal | main | `NamingSeries('CRM-DEAL-.YYYY.-')` | ruled: list rule, object rule |  | `crm_app.CRMDeal` | sales | — |
| CRM Deal Status | main | `FieldValue('deal_status')` | reviewed-open — reference data - status vocabulary, rendered in every list view |  | `crm_app.CRMDealStatus` | sales | — |
| CRM Lead | main | `NamingSeries('CRM-LEAD-.YYYY.-')` | ruled: list rule, object rule |  | `crm_app.CRMLead` | sales | — |
| CRM Lead Source | main | `FieldValue('source_name')` | reviewed-open — reference data - source vocabulary, shown on every lead form |  | `crm_app.CRMLeadSource` | sales | — |
| CRM Lead Status | main | `FieldValue('lead_status')` | reviewed-open — reference data - status vocabulary, rendered in every list view |  | `crm_app.CRMLeadStatus` | sales | — |
| CRM Lost Reason | main | `FieldValue('lost_reason')` | reviewed-open — reference data - reasons offered when a deal is marked lost |  | `crm_app.CRMLostReason` | sales | — |
| CRM Product | main | `FieldValue('product_code')` | reviewed-open — upstream's role table gives every CRM role read, write, create and delete, and upstream adds no row-level hook (hooks.py). Holds the shared product and price catalogue. |  | `crm_app.CRMProduct` | sales | — |
| CRM Territory | main | `FieldValue('territory_name')` | reviewed-open — reference data - territory tree, shown on lead and deal forms |  | `crm_app.CRMTerritory` | sales | — |
| CRM Contacts | child | `Hash(10)` | n/a |  | `crm_app.CRMContacts` | sales | — |
| CRM Products | child | `Hash(10)` | n/a |  | `crm_app.CRMProducts` | sales | — |
| CRM Status Change Log | child | `Hash(10)` | n/a |  | `crm_app.CRMStatusChangeLog` | sales | — |

### Method paths (8)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.onboarding.get_first_deal` | GET/POST | auth | `crm_app/api/onboarding.py:get_first_deal` | sales | — |
| `crm.api.onboarding.get_first_lead` | GET/POST | auth | `crm_app/api/onboarding.py:get_first_lead` | sales | — |
| `crm.fcrm.doctype.crm_deal.api.get_deal_contacts` | GET/POST | auth | `crm_app/api/deal.py:get_deal_contacts` | sales | — |
| `crm.fcrm.doctype.crm_deal.crm_deal.add_contact` | POST | auth | `crm_app/api/deal.py:add_contact` | sales | — |
| `crm.fcrm.doctype.crm_deal.crm_deal.create_deal` | POST | auth | `crm_app/api/deal.py:create_deal` | sales | — |
| `crm.fcrm.doctype.crm_deal.crm_deal.remove_contact` | POST | auth | `crm_app/api/deal.py:remove_contact` | sales | — |
| `crm.fcrm.doctype.crm_deal.crm_deal.set_primary_contact` | POST | auth | `crm_app/api/deal.py:set_primary_contact` | sales | — |
| `crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal` | POST | auth | `crm_app/api/lead.py:convert_to_deal` | sales | — |

## ACTIVITIES

### Doctypes (12)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| Assignment Rule | main | `Prompt()` | ruled: list rule, object rule | RO: `last_user`, `current_index` | `frappe_platform.AssignmentRule` | activities | — |
| CRM Call Log | main | `FieldValue('id')` | reviewed-open — upstream's role table gives every CRM role read, write, create and delete, and upstream adds no row-level hook (hooks.py). Holds shared call history and recordings. |  | `crm_app.CRMCallLog` | activities | — |
| CRM Task | main | `AutoIncrement()` | reviewed-open — collaborative - upstream grants all roles full CRUD and `pages/Tasks.vue` is a company-wide board. Deferring to the parent would empty it |  | `crm_app.CRMTask` | activities | — |
| Comment | main | `Hash(10)` | ruled: list rule, object rule, destination re-check |  | `frappe_platform.Comment` | activities | — |
| Communication | main | `Hash(10)` | ruled: list rule, object rule, destination re-check |  | `frappe_platform.Communication` | activities | — |
| Email Template | main | `Prompt()` | ruled: list rule, object rule |  | `frappe_platform.EmailTemplate` | activities | — |
| FCRM Note | main | `Hash(10)` | reviewed-open — same as CRM Task - `pages/Notes.vue` is company-wide, and a note can legitimately have no parent at all |  | `crm_app.FCRMNote` | activities | — |
| File | main | `Hash(10)` | ruled: list rule, object rule, destination re-check |  | `frappe_platform.File` | activities | — |
| Tag | main | `Prompt()` | ruled: list rule, object rule |  | `frappe_platform.Tag` | activities | — |
| ToDo | withheld | `Hash(10)` | withheld — `specs/UNROUTED_DOCTYPES.md` | RO: `assignment_rule` | `frappe_platform.ToDo` | activities | — |
| Assignment Rule Day | child | `Hash(10)` | n/a |  | `frappe_platform.AssignmentRuleDay` | activities | — |
| Assignment Rule User | child | `Hash(10)` | n/a |  | `frappe_platform.AssignmentRuleUser` | activities | — |

### Method paths (22)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.activities.get_activities` | GET/POST | auth | `crm_app/api/activities.py:get_activities` | activities | — |
| `crm.api.assignment_rule.duplicate_assignment_rule` | GET/POST | auth | `crm_app/api/assignment_rule.py:duplicate_assignment_rule` | activities | — |
| `crm.api.assignment_rule.get_assignment_rules_list` | GET/POST | auth | `crm_app/api/assignment_rule.py:get_assignment_rules_list` | activities | — |
| `crm.api.comment.add_comment` | GET/POST | auth | `crm_app/api/comment.py:add_comment` | activities | — |
| `crm.api.delete_attachment` | DELETE/POST | auth | `crm_app/api/misc.py:delete_attachment` | activities | — |
| `crm.api.doc.get_assigned_users` | GET/POST | auth | `crm_app/api/doc.py:get_assigned_users` | activities | — |
| `crm.api.doc.remove_assignments` | GET/POST | auth | `crm_app/api/doc.py:remove_assignments` | activities | — |
| `crm.api.get_file_uploader_defaults` | GET/POST | auth | `crm_app/api/misc.py:get_file_uploader_defaults` | activities | — |
| `crm.fcrm.doctype.crm_call_log.crm_call_log.create_lead_from_call_log` | POST | auth | `crm_app/api/call_log.py:create_lead_from_call_log` | activities | — |
| `crm.fcrm.doctype.crm_call_log.crm_call_log.get_call_log` | GET/POST | auth | `crm_app/api/call_log.py:get_call_log` | activities | — |
| `crm.integrations.api.add_note_to_call_log` | GET/POST | auth | `crm_app/integrations/api.py:add_note_to_call_log` | activities | — |
| `crm.integrations.api.add_task_to_call_log` | GET/POST | auth | `crm_app/integrations/api.py:add_task_to_call_log` | activities | — |
| `crm.integrations.api.get_contact_by_phone_number` | GET/POST | auth | `crm_app/integrations/api.py:get_contact_by_phone_number` | activities | — |
| `crm.integrations.api.get_contact_lead_or_deal_from_number` | GET/POST | auth | `crm_app/integrations/api.py:get_contact_lead_or_deal_from_number` | activities | — |
| `frappe.automation.doctype.assignment_rule.assignment_rule.bulk_apply` | GET/POST | auth | `crm_app/assignment_rules.py:bulk_apply` | activities | — |
| `frappe.core.doctype.communication.email.make` | POST | auth | `crm_app/api/communication.py:make` | activities | — |
| `frappe.desk.form.assign_to.add_multiple` | POST | auth | `crm_app/api/client.py:assign_to_add_multiple` | activities | — |
| `frappe.desk.form.assign_to.add` | POST | auth | `crm_app/api/client.py:assign_to_add` | activities | — |
| `frappe.desk.form.assign_to.remove_multiple` | POST | auth | `crm_app/api/client.py:assign_to_remove_multiple` | activities | — |
| `frappe.desk.like.toggle_like` | POST | auth | `crm_app/api/client.py:toggle_like` | activities | — |
| `frappe.email.doctype.email_template.email_template.get_email_template` | GET/POST | auth | `crm_app/api/email_template.py:get_email_template` | activities | — |
| `upload_file` | POST | auth +request | `crm_app/api/upload.py:upload_file` | activities | — |

## DATA_IMPORT

Added 2026-11-12: the CSV import built on `main` after this map was seeded (PR 61).
It writes rows of every importable doctype through their normal create path, so it
comes after the units that build those doctypes.

### Doctypes (2)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| Data Import | main | `DataImportTimestamp()` | ruled: list rule, object rule | S: `job_claimed_at`; RO: `status`, `template_warnings`, `payload_count` | `frappe_platform.DataImport` | core | — |
| Data Import Log | withheld | `Hash(10)` | withheld — `specs/UNROUTED_DOCTYPES.md` |  | `frappe_platform.DataImportLog` | core | — |

### Method paths (4)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `frappe.core.doctype.data_import.data_import.download_template` | GET/POST | auth | `crm_app/api/data_import.py:download_template` | core | — |
| `frappe.core.doctype.data_import.data_import.form_start_import` | POST | auth | `crm_app/api/data_import.py:form_start_import` | core | — |
| `frappe.core.doctype.data_import.data_import.get_import_logs` | GET/POST | auth | `crm_app/api/data_import.py:get_import_logs` | core | — |
| `frappe.core.doctype.data_import.data_import.get_preview_from_template` | GET/POST | auth | `crm_app/api/data_import.py:get_preview_from_template` | core | — |

## DASHBOARD

### Doctypes (1)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| CRM Dashboard | main | `FieldValue('title')` | reviewed-open — chart definitions, not data - `get_dashboard` filters the numbers |  | `crm_app.CRMDashboard` | dashboard | — |

### Method paths (3)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.dashboard.get_chart` | GET/POST | auth | `crm_app/api/dashboard.py:get_chart` | dashboard | — |
| `crm.api.dashboard.get_dashboard` | GET/POST | auth | `crm_app/api/dashboard.py:get_dashboard` | dashboard | — |
| `crm.api.dashboard.reset_to_default` | POST | auth | `crm_app/api/dashboard.py:reset_to_default` | dashboard | — |

## INTEGRATIONS

### Doctypes (12)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| CRM Exotel Settings | single | default | ruled: list rule, object rule | S: `api_token`; E: `api_token`; R: `webhook_verify_token`, `api_key`, `account_sid` | `crm_app.CRMExotelSettings` | integrations | — |
| CRM Telephony Agent | main | `FieldValue('user')` | reviewed-open — upstream's role table gives every CRM role read, write, create and delete, and upstream adds no row-level hook (hooks.py). Holds each agent's telephony numbers. |  | `crm_app.CRMTelephonyAgent` | integrations | — |
| CRM Twilio Settings | single | default | ruled: list rule, object rule | S: `api_secret`, `auth_token`; E: `api_secret`, `auth_token`; R: `api_key`, `twiml_sid` | `crm_app.CRMTwilioSettings` | integrations | — |
| ERPNext CRM Settings | single | default | ruled: list rule, object rule | S: `api_secret`; E: `api_secret`; R: `api_key`, `erpnext_site_url` | `crm_app.ERPNextCRMSettings` | integrations | — |
| Facebook Lead Form | main | `FieldValue('id')` | ruled: list rule, object rule |  | `crm_app.FacebookLeadForm` | integrations | — |
| Facebook Page | main | `FieldValue('id')` | ruled: list rule, object rule | S: `access_token`; E: `access_token` | `crm_app.FacebookPage` | integrations | — |
| Failed Lead Sync Log | main | `Hash(10)` | ruled: list rule, object rule |  | `crm_app.FailedLeadSyncLog` | integrations | — |
| Lead Sync Source | main | default | ruled: list rule, object rule | S: `access_token`; E: `access_token` | `crm_app.LeadSyncSource` | integrations | — |
| WhatsApp Message | main | `Hash(10)` | ruled: list rule, object rule, destination re-check |  | `crm_app.WhatsAppMessage` | integrations | — |
| CRM Product Sync Issue | child | `AutoIncrement()` | n/a |  | `crm_app.CRMProductSyncIssue` | integrations | — |
| CRM Telephony Phone | child | `Hash(10)` | n/a |  | `crm_app.CRMTelephonyPhone` | integrations | — |
| Facebook Lead Form Question | child | `Hash(10)` | n/a |  | `crm_app.FacebookLeadFormQuestion` | integrations | — |

### Method paths (26)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.whatsapp.create_whatsapp_message` | GET/POST | auth | `crm_app/integrations/whatsapp/api.py:create_whatsapp_message` | integrations | — |
| `crm.api.whatsapp.get_whatsapp_messages` | GET/POST | auth | `crm_app/integrations/whatsapp/api.py:get_whatsapp_messages` | integrations | — |
| `crm.api.whatsapp.is_whatsapp_enabled` | GET/POST | auth | `crm_app/integrations/whatsapp/api.py:is_whatsapp_enabled` | integrations | — |
| `crm.api.whatsapp.is_whatsapp_installed` | GET/POST | auth | `crm_app/integrations/whatsapp/api.py:is_whatsapp_installed` | integrations | — |
| `crm.api.whatsapp.react_on_whatsapp_message` | GET/POST | auth | `crm_app/integrations/whatsapp/api.py:react_on_whatsapp_message` | integrations | — |
| `crm.api.whatsapp.send_whatsapp_template` | GET/POST | auth | `crm_app/integrations/whatsapp/api.py:send_whatsapp_template` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.dismiss_sync_issue` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:dismiss_sync_issue` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_customer_link` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:get_customer_link` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_external_companies` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:get_external_companies` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_open_sync_issues` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:get_open_sync_issues` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_product_sync_status` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:get_product_sync_status` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_quotation_url` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:get_quotation_url` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.is_erpnext_installed` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:is_erpnext_installed` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.prefill_quotation_items` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:prefill_quotation_items` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.run_product_sync` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:run_product_sync` | integrations | — |
| `crm.integrations.api.is_call_integration_enabled` | GET/POST | auth | `crm_app/integrations/api.py:is_call_integration_enabled` | integrations | — |
| `crm.integrations.api.set_default_calling_medium` | GET/POST | auth | `crm_app/integrations/api.py:set_default_calling_medium` | integrations | — |
| `crm.integrations.exotel.handler.handle_request` | GET/POST | guest | `crm_app/integrations/exotel/handler.py:handle_request` | integrations | — |
| `crm.integrations.exotel.handler.is_integration_enabled` | GET/POST | auth | `crm_app/integrations/exotel/handler.py:is_integration_enabled` | integrations | — |
| `crm.integrations.exotel.handler.make_a_call` | GET/POST | auth | `crm_app/integrations/exotel/handler.py:make_a_call` | integrations | — |
| `crm.integrations.twilio.api.generate_access_token` | GET/POST | auth | `crm_app/integrations/twilio/handler.py:generate_access_token` | integrations | — |
| `crm.integrations.twilio.api.is_enabled` | GET/POST | auth | `crm_app/integrations/twilio/handler.py:is_enabled` | integrations | — |
| `crm.integrations.twilio.api.twilio_incoming_call_handler` | GET/POST | guest +request | `crm_app/integrations/twilio/handler.py:twilio_incoming_call_handler` | integrations | — |
| `crm.integrations.twilio.api.update_call_status_info` | GET/POST | guest +request | `crm_app/integrations/twilio/handler.py:update_call_status_info` | integrations | — |
| `crm.integrations.twilio.api.update_recording_info` | GET/POST | guest +request | `crm_app/integrations/twilio/handler.py:update_recording_info` | integrations | — |
| `crm.integrations.twilio.api.voice` | GET/POST | guest +request | `crm_app/integrations/twilio/handler.py:voice` | integrations | — |
