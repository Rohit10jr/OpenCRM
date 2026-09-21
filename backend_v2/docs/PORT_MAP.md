# Port map — every old endpoint and doctype, and where it goes

**Seeded on 2026-09-16** from `docs/ROUTES.md` (123 method paths, 58 doctypes) and the
`docs/http/*.http` files, by a one-off script. **Maintained by hand from here on**: when
a row moves, edit the row. Do not regenerate it; that would erase the Status column.

This file is the **one home of per-row status**. Unit status lives in
`backend_v2/specs/README.md` and nowhere else.

**The rows are the old paths.** `backend_v2` serves REST routes under `/api/v1/` instead
(REBUILD_PLAN S6), each answering like the old path it replaces. **The route map** — a
**New route** column giving each row its method, REST path and any reshaped input
(REBUILD_PLAN S7, S8) — is added after all the planning documents are reviewed
(REBUILD_PLAN O6). Until then the **New app** and **Unit** columns say where a row's code
will live, and the route it will have is still to be designed.

**Paths are from the repository root.** The **Old source** column is the exception: it
is relative to `backend/`, exactly as `docs/ROUTES.md` prints it.

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
| `frappe_platform.UserSettings` | Per-user list-view state behind `frappe.model.utils.user_settings.*` | metadata | METADATA | — |
| SimpleJWT `token_blacklist` tables | Rotated and logged-out refresh tokens | accounts | FOUNDATION | — |

---

## Which unit turns each `.http` file green

The `.http` files use the old paths, so against `backend_v2` each request is sent through
the route map (REBUILD_PLAN section 6). A file can only pass in full once every unit it
touches is built. Touched units are found by scanning each file for method paths,
resource doctypes and `doctype` parameters, so treat this as a guide: a block can depend
on seed data from a unit the scan cannot see.

| File | Units it touches | Green once this unit is built |
|---|---|---|
| `00_walkthrough.http` | FOUNDATION, ACCOUNTS, METADATA, CONTACTS, SALES, ACTIVITIES | ACTIVITIES |
| `01_auth.http` | FOUNDATION, ACCOUNTS | ACCOUNTS |
| `02_resource_grammar.http` | FOUNDATION, CONTACTS, SALES | SALES |
| `03_leads.http` | FOUNDATION, METADATA, CONTACTS, SALES, ACTIVITIES | ACTIVITIES |
| `04_deals.http` | FOUNDATION, SETTINGS, METADATA, CONTACTS, SALES, DOCUMENTS | DOCUMENTS |
| `05_contacts_organizations.http` | FOUNDATION, CONTACTS, SALES, DOCUMENTS | DOCUMENTS |
| `06_tasks_notes_calls.http` | FOUNDATION, METADATA, CONTACTS, SALES, ACTIVITIES, DOCUMENTS, TELEPHONY | TELEPHONY |
| `07_views_and_metadata.http` | FOUNDATION, METADATA, CONTACTS, SALES, ACTIVITIES, SLA | SLA |
| `08_activities_comments_notifications.http` | FOUNDATION, NOTIFICATIONS, SALES, ACTIVITIES | ACTIVITIES |
| `09_users_and_invitations.http` | FOUNDATION, ACCOUNTS, SETTINGS, SALES, ACTIVITIES | ACTIVITIES |
| `10_dashboard.http` | FOUNDATION, DASHBOARD | DASHBOARD |
| `11_permissions_matrix.http` | FOUNDATION, ACCOUNTS, SETTINGS, METADATA, SALES, ACTIVITIES, DASHBOARD, DOCUMENTS | DOCUMENTS |
| `12_settings_singletons.http` | FOUNDATION, SETTINGS, SALES, TELEPHONY, INTEGRATIONS | INTEGRATIONS |
| `13_bulk_and_misc.http` | FOUNDATION, ACCOUNTS, SETTINGS, CONTACTS, NOTIFICATIONS, SALES, ACTIVITIES, DOCUMENTS | DOCUMENTS |
| `99_lockout.http` | FOUNDATION, ACCOUNTS | ACCOUNTS |

---

## FOUNDATION

### Doctypes (2)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| User | main | default | ruled: list rule, object rule | S: `groups`, `user_permissions`, `is_superuser`, `is_staff`, `reset_password_key`, `last_reset_password_key_generated_on`; RO: `enabled`, `user_type` | `frappe_platform.User` | accounts | — |
| Version | withheld | `Hash(10)` | withheld — `specs/UNROUTED_DOCTYPES.md` |  | `frappe_core.Version` | core | — |

### Method paths (11)

The seven `frappe.client.*` rows are the generic document calls. In `backend_v2` they
become the base ViewSet's CRUD, which every resource inherits, so their new routes are
each resource's own collection and document routes. FOUNDATION builds the base; each unit
proves it on its own resources.

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `frappe.auth.get_logged_user` | GET/POST | auth | `frappe_core/api/auth.py:183` | accounts | — |
| `frappe.client.delete` | DELETE/POST | auth | `crm_app/api/client.py:203` | documents | — |
| `frappe.client.get` | GET/POST | auth | `crm_app/api/client.py:54` | documents | — |
| `frappe.client.get_doc_permissions` | GET/POST | auth | `crm_app/api/client.py:248` | documents | — |
| `frappe.client.get_list` | GET/POST | auth | `crm_app/api/client.py:72` | documents | — |
| `frappe.client.get_single_value` | GET/POST | auth | `crm_app/api/client.py:97` | documents | — |
| `frappe.client.insert` | POST | auth | `crm_app/api/client.py:170` | documents | — |
| `frappe.client.set_value` | POST/PUT | auth | `crm_app/api/client.py:144` | documents | — |
| `login` | POST | guest | `frappe_core/api/auth.py:39` | accounts | — |
| `logout` | POST/GET | auth | `frappe_core/api/auth.py:127` | accounts | — |
| `token/refresh` | POST | guest | `frappe_core/api/auth.py:146` | accounts | — |

## ACCOUNTS

### Doctypes (2)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| CRM Invitation | main | `Hash(10)` | ruled: list rule, object rule | S: `key` | `crm_app.CRMInvitation` | accounts | — |
| CRM Sales Hierarchy | main | `Hash(10)` | ruled: list rule, object rule |  | `crm_app.CRMSalesHierarchy` | accounts | — |

### Method paths (13)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.accept_invitation` | GET/POST | guest | `crm_app/api/auth_pages.py:311` | accounts | — |
| `crm.api.auth.oauth_providers` | GET/POST | guest | `crm_app/api/auth.py:17` | accounts | — |
| `crm.api.get_user_signature` | GET/POST | auth | `crm_app/api/misc.py:42` | accounts | — |
| `crm.api.invite_by_email` | GET/POST | auth | `crm_app/api/misc.py:75` | accounts | — |
| `crm.api.session.get_user_info` | GET/POST | auth | `crm_app/api/session.py:138` | accounts | — |
| `crm.api.session.get_users` | GET/POST | auth | `crm_app/api/session.py:62` | accounts | — |
| `crm.api.user.add_existing_users` | GET/POST | auth | `crm_app/api/user.py:110` | accounts | — |
| `crm.api.user.change_password` | GET/POST | auth | `crm_app/api/user.py:54` | accounts | — |
| `crm.api.user.remove_crm_roles_from_user` | GET/POST | auth | `crm_app/api/user.py:182` | accounts | — |
| `crm.api.user.update_user_role` | GET/POST | auth | `crm_app/api/user.py:128` | accounts | — |
| `frappe.core.doctype.user.user.get_timezones` | GET/POST | auth | `crm_app/api/desk.py:111` | accounts | — |
| `frappe.core.doctype.user.user.reset_password` | POST | guest | `crm_app/api/auth_pages.py:45` | accounts | — |
| `frappe.core.doctype.user.user.update_password` | POST | guest | `crm_app/api/auth_pages.py:99` | accounts | — |

## SETTINGS

### Doctypes (3)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| Email Account | main | `FieldValue('email_account_name')` | ruled: list rule, object rule | S: `password`, `api_secret`; E: `password`, `api_secret`; R: `smtp_server`, `smtp_port`, `email_server`, `incoming_port`, `login_id`, `domain`, `api_key`, `frappe_mail_site`, `signature`, `no_smtp_authentication`, `awaiting_password` | `frappe_platform.EmailAccount` | crm_settings | — |
| FCRM Settings | single | default | ruled: list rule, object rule | R: `access_key` | `crm_app.FCRMSettings` | crm_settings | — |
| CRM Dropdown Item | child | `Hash(10)` | n/a |  | `crm_app.CRMDropdownItem` | crm_settings | — |

### Method paths (7)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.exchange_rate.get_exchange_rate` | GET/POST | auth | `crm_app/api/exchange_rate.py:27` | crm_settings | — |
| `crm.api.get_translations` | GET/POST | guest | `crm_app/api/misc.py:31` | crm_settings | — |
| `crm.api.settings.create_email_account` | GET/POST | auth | `crm_app/api/settings.py:68` | crm_settings | — |
| `crm.demo.api.clear_demo_data` | POST | auth | `crm_app/api/demo.py:18` | crm_settings | — |
| `frappe.apps.get_apps` | GET/POST | auth | `crm_app/api/desk.py:40` | crm_settings | — |
| `frappe.integrations.frappe_providers.frappecloud_billing.current_site_info` | GET/POST | auth | `crm_app/api/desk.py:127` | crm_settings | — |
| `frappe.utils.telemetry.pulse.client.boot_config` | GET/POST | auth | `crm_app/api/desk.py:161` | crm_settings | — |

## METADATA

### Doctypes (4)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| CRM Fields Layout | main | `Format('{dt}-{type}')` | ruled: list rule, object rule |  | `crm_app.CRMFieldsLayout` | metadata | — |
| CRM Form Script | main | `Prompt()` | ruled: list rule, object rule |  | `crm_app.CRMFormScript` | metadata | — |
| CRM Global Settings | main | `Hash(10)` | reviewed-open — no secrets: holds only `dt`, `type` and a JSON blob. Upstream grants all three roles full CRUD (`crm_global_settings.json`), deliberately. Reproduced. |  | `crm_app.CRMGlobalSettings` | metadata | — |
| CRM View Settings | main | `AutoIncrement()` | ruled: list rule, object rule |  | `crm_app.CRMViewSettings` | metadata | — |

### Method paths (22)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.doc.get_data` | GET/POST | auth | `frappe_core/api/doc.py:211` | metadata | — |
| `crm.api.doc.get_fields` | GET/POST | auth | `crm_app/api/doc.py:296` | metadata | — |
| `crm.api.doc.get_filterable_fields` | GET/POST | auth | `crm_app/api/doc.py:95` | metadata | — |
| `crm.api.doc.get_group_by_fields` | GET/POST | auth | `crm_app/api/doc.py:101` | metadata | — |
| `crm.api.doc.get_quick_filters` | GET/POST | auth | `crm_app/api/doc.py:145` | metadata | — |
| `crm.api.doc.sort_options` | GET/POST | auth | `crm_app/api/doc.py:73` | metadata | — |
| `crm.api.doc.update_quick_filters` | GET/POST | auth | `crm_app/api/doc.py:201` | metadata | — |
| `crm.api.views.get_views` | GET/POST | auth | `crm_app/api/views.py:11` | metadata | — |
| `crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout` | GET/POST | auth | `crm_app/api/fields_layout.py:112` | metadata | — |
| `crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections` | GET/POST | auth | `crm_app/api/fields_layout.py:213` | metadata | — |
| `crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.save_fields_layout` | POST | auth | `crm_app/api/fields_layout.py:243` | metadata | — |
| `crm.fcrm.doctype.crm_view_settings.crm_view_settings.create` | POST | auth | `crm_app/api/view_settings.py:150` | metadata | — |
| `crm.fcrm.doctype.crm_view_settings.crm_view_settings.create_or_update_standard_view` | POST | auth | `crm_app/api/view_settings.py:273` | metadata | — |
| `crm.fcrm.doctype.crm_view_settings.crm_view_settings.delete` | POST/DELETE | auth | `crm_app/api/view_settings.py:190` | metadata | — |
| `crm.fcrm.doctype.crm_view_settings.crm_view_settings.fetch_and_update_kanban_columns` | POST | auth | `crm_app/api/view_settings.py:318` | metadata | — |
| `crm.fcrm.doctype.crm_view_settings.crm_view_settings.pin` | POST | auth | `crm_app/api/view_settings.py:232` | metadata | — |
| `crm.fcrm.doctype.crm_view_settings.crm_view_settings.public` | POST | auth | `crm_app/api/view_settings.py:204` | metadata | — |
| `crm.fcrm.doctype.crm_view_settings.crm_view_settings.set_as_default` | POST | auth | `crm_app/api/view_settings.py:246` | metadata | — |
| `crm.fcrm.doctype.crm_view_settings.crm_view_settings.update` | POST/PUT | auth | `crm_app/api/view_settings.py:170` | metadata | — |
| `frappe.desk.form.load.getdoctype` | GET/POST | auth | `crm_app/api/form_load.py:151` | metadata | — |
| `frappe.model.utils.user_settings.get` | GET/POST | auth | `crm_app/api/user_settings.py:113` | metadata | — |
| `frappe.model.utils.user_settings.save` | GET/POST | auth | `crm_app/api/user_settings.py:100` | metadata | — |

## CONTACTS

### Doctypes (6)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| CRM Industry | main | `FieldValue('industry')` | reviewed-open — reference data - industry vocabulary, shown on organisation forms |  | `crm_app.CRMIndustry` | contacts | — |
| CRM Organization | main | `FieldValue('organization_name')` | awaiting review — same as Contact - is org data meant to be company-wide? |  | `crm_app.CRMOrganization` | contacts | — |
| Contact | main | default | awaiting review — shared across leads and deals; upstream relies on role permissions |  | `frappe_platform.Contact` | contacts | — |
| Contact Email | child | `Hash(10)` | n/a |  | `frappe_platform.ContactEmail` | contacts | — |
| Contact Phone | child | `Hash(10)` | n/a |  | `frappe_platform.ContactPhone` | contacts | — |
| Dynamic Link | child | `Hash(10)` | n/a |  | `frappe_platform.DynamicLink` | contacts | — |

### Method paths (5)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.contact.create_new` | GET/POST | auth | `crm_app/api/contact.py:75` | contacts | — |
| `crm.api.contact.get_linked_deals` | GET/POST | auth | `crm_app/api/contact.py:44` | contacts | — |
| `crm.api.contact.search_emails` | GET/POST | auth | `crm_app/api/contact.py:130` | contacts | — |
| `crm.api.contact.set_as_primary` | GET/POST | auth | `crm_app/api/contact.py:104` | contacts | — |
| `crm.api.session.get_organizations` | GET/POST | auth | `crm_app/api/session.py:158` | contacts | — |

## NOTIFICATIONS

### Doctypes (1)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| CRM Notification | main | `Hash(10)` | ruled: list rule, object rule |  | `crm_app.CRMNotification` | notifications | — |

### Method paths (2)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.notifications.get_notifications` | GET/POST | auth | `crm_app/api/notifications.py:33` | notifications | — |
| `crm.api.notifications.mark_as_read` | GET/POST | auth | `crm_app/api/notifications.py:97` | notifications | — |

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
| CRM Product | main | `FieldValue('product_code')` | awaiting review — catalogue data; writes change prices used in deal totals |  | `crm_app.CRMProduct` | sales | — |
| CRM Territory | main | `FieldValue('territory_name')` | reviewed-open — reference data - territory tree, shown on lead and deal forms |  | `crm_app.CRMTerritory` | sales | — |
| CRM Contacts | child | `Hash(10)` | n/a |  | `crm_app.CRMContacts` | sales | — |
| CRM Products | child | `Hash(10)` | n/a |  | `crm_app.CRMProducts` | sales | — |
| CRM Status Change Log | child | `Hash(10)` | n/a |  | `crm_app.CRMStatusChangeLog` | sales | — |

### Method paths (8)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.onboarding.get_first_deal` | GET/POST | auth | `crm_app/api/onboarding.py:22` | sales | — |
| `crm.api.onboarding.get_first_lead` | GET/POST | auth | `crm_app/api/onboarding.py:9` | sales | — |
| `crm.fcrm.doctype.crm_deal.api.get_deal_contacts` | GET/POST | auth | `crm_app/api/deal.py:84` | sales | — |
| `crm.fcrm.doctype.crm_deal.crm_deal.add_contact` | POST | auth | `crm_app/api/deal.py:57` | sales | — |
| `crm.fcrm.doctype.crm_deal.crm_deal.create_deal` | POST | auth | `crm_app/api/deal.py:200` | sales | — |
| `crm.fcrm.doctype.crm_deal.crm_deal.remove_contact` | POST | auth | `crm_app/api/deal.py:65` | sales | — |
| `crm.fcrm.doctype.crm_deal.crm_deal.set_primary_contact` | POST | auth | `crm_app/api/deal.py:74` | sales | — |
| `crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal` | POST | auth | `crm_app/api/lead.py:20` | sales | — |

## ACTIVITIES

### Doctypes (8)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| CRM Task | main | `AutoIncrement()` | reviewed-open — collaborative - upstream grants all roles full CRUD and `pages/Tasks.vue` is a company-wide board. Deferring to the parent would empty it |  | `crm_app.CRMTask` | activities | — |
| Comment | main | `Hash(10)` | ruled: list rule, object rule, destination re-check |  | `frappe_platform.Comment` | activities | — |
| Communication | main | `Hash(10)` | ruled: list rule, object rule, destination re-check |  | `frappe_platform.Communication` | activities | — |
| Email Template | main | `Prompt()` | awaiting review — writes change the wording of mail the system sends on your behalf |  | `frappe_platform.EmailTemplate` | activities | — |
| FCRM Note | main | `Hash(10)` | reviewed-open — same as CRM Task - `pages/Notes.vue` is company-wide, and a note can legitimately have no parent at all |  | `crm_app.FCRMNote` | activities | — |
| File | main | `Hash(10)` | ruled: list rule, object rule, destination re-check |  | `frappe_platform.File` | activities | — |
| Tag | main | `Prompt()` | awaiting review — low risk, but writes are unconstrained |  | `frappe_platform.Tag` | activities | — |
| ToDo | withheld | `Hash(10)` | withheld — `specs/UNROUTED_DOCTYPES.md` |  | `frappe_platform.ToDo` | activities | — |

### Method paths (14)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.activities.get_activities` | GET/POST | auth | `crm_app/api/activities.py:453` | activities | — |
| `crm.api.assignment_rule.duplicate_assignment_rule` | GET/POST | auth | `crm_app/api/assignment_rule.py:26` | activities | — |
| `crm.api.assignment_rule.get_assignment_rules_list` | GET/POST | auth | `crm_app/api/assignment_rule.py:20` | activities | — |
| `crm.api.comment.add_comment` | GET/POST | auth | `crm_app/api/comment.py:118` | activities | — |
| `crm.api.delete_attachment` | DELETE/POST | auth | `crm_app/api/misc.py:126` | activities | — |
| `crm.api.doc.get_assigned_users` | GET/POST | auth | `crm_app/api/doc.py:247` | activities | — |
| `crm.api.doc.remove_assignments` | GET/POST | auth | `crm_app/api/doc.py:262` | activities | — |
| `crm.api.get_file_uploader_defaults` | GET/POST | auth | `crm_app/api/misc.py:159` | activities | — |
| `frappe.core.doctype.communication.email.make` | POST | auth | `crm_app/api/communication.py:76` | activities | — |
| `frappe.desk.form.assign_to.add` | POST | auth | `crm_app/api/client.py:270` | activities | — |
| `frappe.desk.form.assign_to.add_multiple` | POST | auth | `crm_app/api/client.py:293` | activities | — |
| `frappe.desk.form.assign_to.remove_multiple` | POST | auth | `crm_app/api/client.py:336` | activities | — |
| `frappe.desk.like.toggle_like` | POST | auth | `crm_app/api/client.py:371` | activities | — |
| `frappe.email.doctype.email_template.email_template.get_email_template` | GET/POST | auth | `crm_app/api/email_template.py:73` | activities | — |

## DASHBOARD

### Doctypes (1)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| CRM Dashboard | main | `FieldValue('title')` | reviewed-open — chart definitions, not data - `get_dashboard` filters the numbers |  | `crm_app.CRMDashboard` | dashboard | — |

### Method paths (3)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.dashboard.get_chart` | GET/POST | auth | `crm_app/api/dashboard.py:744` | dashboard | — |
| `crm.api.dashboard.get_dashboard` | GET/POST | auth | `crm_app/api/dashboard.py:717` | dashboard | — |
| `crm.api.dashboard.reset_to_default` | POST | auth | `crm_app/api/dashboard.py:699` | dashboard | — |

## SLA

### Doctypes (6)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| CRM Holiday List | main | `FieldValue('holiday_list_name')` | reviewed-open — reference data - business calendar, read by the SLA engine |  | `crm_app.CRMHolidayList` | sla | — |
| CRM Service Level Agreement | main | `FieldValue('sla_name')` | awaiting review — SLA definitions; writes change response deadlines |  | `crm_app.CRMServiceLevelAgreement` | sla | — |
| CRM Holiday | child | `Hash(10)` | n/a |  | `crm_app.CRMHoliday` | sla | — |
| CRM Rolling Response Time | child | `Hash(10)` | n/a |  | `crm_app.CRMRollingResponseTime` | sla | — |
| CRM Service Day | child | `Hash(10)` | n/a |  | `crm_app.CRMServiceDay` | sla | — |
| CRM Service Level Priority | child | `Hash(10)` | n/a |  | `crm_app.CRMServiceLevelPriority` | sla | — |

## DOCUMENTS

### Method paths (6)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.doc.delete_bulk_docs` | GET/POST | auth | `crm_app/api/doc.py:541` | documents | — |
| `crm.api.doc.get_linked_docs_of_document` | GET/POST | auth | `crm_app/api/doc.py:349` | documents | — |
| `crm.api.doc.remove_linked_doc_reference` | GET/POST | auth | `crm_app/api/doc.py:430` | documents | — |
| `frappe.client.rename_doc` | POST | auth | `crm_app/api/client.py:212` | documents | — |
| `frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs` | POST | auth | `crm_app/api/bulk_update.py:27` | documents | — |
| `frappe.desk.search.search_link` | GET/POST | auth | `crm_app/api/client.py:397` | documents | — |

## TELEPHONY

### Doctypes (5)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| CRM Call Log | main | `FieldValue('id')` | awaiting review — call history references leads and deals; recording URLs are on the row |  | `crm_app.CRMCallLog` | telephony | — |
| CRM Exotel Settings | single | default | ruled: list rule, object rule | S: `api_token`; E: `api_token`; R: `webhook_verify_token`, `api_key`, `account_sid` | `crm_app.CRMExotelSettings` | telephony | — |
| CRM Telephony Agent | main | `FieldValue('user')` | awaiting review — holds colleagues' phone numbers |  | `crm_app.CRMTelephonyAgent` | telephony | — |
| CRM Twilio Settings | single | default | ruled: list rule, object rule | S: `api_secret`, `auth_token`; E: `api_secret`, `auth_token`; R: `api_key`, `twiml_sid` | `crm_app.CRMTwilioSettings` | telephony | — |
| CRM Telephony Phone | child | `Hash(10)` | n/a |  | `crm_app.CRMTelephonyPhone` | telephony | — |

### Method paths (17)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.fcrm.doctype.crm_call_log.crm_call_log.create_lead_from_call_log` | POST | auth | `crm_app/api/call_log.py:82` | telephony | — |
| `crm.fcrm.doctype.crm_call_log.crm_call_log.get_call_log` | GET/POST | auth | `crm_app/api/call_log.py:28` | telephony | — |
| `crm.integrations.api.add_note_to_call_log` | GET/POST | auth | `crm_app/integrations/api.py:116` | telephony | — |
| `crm.integrations.api.add_task_to_call_log` | GET/POST | auth | `crm_app/integrations/api.py:140` | telephony | — |
| `crm.integrations.api.get_contact_by_phone_number` | GET/POST | auth | `crm_app/integrations/api.py:177` | telephony | — |
| `crm.integrations.api.get_contact_lead_or_deal_from_number` | GET/POST | auth | `crm_app/integrations/api.py:183` | telephony | — |
| `crm.integrations.api.is_call_integration_enabled` | GET/POST | auth | `crm_app/integrations/api.py:63` | telephony | — |
| `crm.integrations.api.set_default_calling_medium` | GET/POST | auth | `crm_app/integrations/api.py:79` | telephony | — |
| `crm.integrations.exotel.handler.handle_request` | GET/POST | guest | `crm_app/integrations/exotel/handler.py:187` | telephony | — |
| `crm.integrations.exotel.handler.is_integration_enabled` | GET/POST | auth | `crm_app/integrations/exotel/handler.py:52` | telephony | — |
| `crm.integrations.exotel.handler.make_a_call` | GET/POST | auth | `crm_app/integrations/exotel/handler.py:226` | telephony | — |
| `crm.integrations.twilio.api.generate_access_token` | GET/POST | auth | `crm_app/integrations/twilio/handler.py:263` | telephony | — |
| `crm.integrations.twilio.api.is_enabled` | GET/POST | auth | `crm_app/integrations/twilio/handler.py:32` | telephony | — |
| `crm.integrations.twilio.api.twilio_incoming_call_handler` | GET/POST | guest +request | `crm_app/integrations/twilio/handler.py:339` | telephony | — |
| `crm.integrations.twilio.api.update_call_status_info` | GET/POST | guest +request | `crm_app/integrations/twilio/handler.py:423` | telephony | — |
| `crm.integrations.twilio.api.update_recording_info` | GET/POST | guest +request | `crm_app/integrations/twilio/handler.py:402` | telephony | — |
| `crm.integrations.twilio.api.voice` | GET/POST | guest +request | `crm_app/integrations/twilio/handler.py:303` | telephony | — |

## INTEGRATIONS

### Doctypes (8)

| DocType | Kind | Naming | Old protection | Declared fields | Old model | New app | Status |
|---|---|---|---|---|---|---|---|
| ERPNext CRM Settings | single | default | ruled: list rule, object rule | S: `api_secret`; E: `api_secret`; R: `api_key`, `erpnext_site_url` | `crm_app.ERPNextCRMSettings` | integrations | — |
| Facebook Lead Form | main | `FieldValue('id')` | ruled: list rule, object rule |  | `crm_app.FacebookLeadForm` | integrations | — |
| Facebook Page | main | `FieldValue('id')` | ruled: list rule, object rule | S: `access_token`; E: `access_token` | `crm_app.FacebookPage` | integrations | — |
| Failed Lead Sync Log | main | `Hash(10)` | ruled: list rule, object rule |  | `crm_app.FailedLeadSyncLog` | integrations | — |
| Lead Sync Source | main | default | ruled: list rule, object rule | S: `access_token`; E: `access_token` | `crm_app.LeadSyncSource` | integrations | — |
| WhatsApp Message | main | `Hash(10)` | ruled: list rule, object rule, destination re-check |  | `crm_app.WhatsAppMessage` | integrations | — |
| CRM Product Sync Issue | child | `AutoIncrement()` | n/a |  | `crm_app.CRMProductSyncIssue` | integrations | — |
| Facebook Lead Form Question | child | `Hash(10)` | n/a |  | `crm_app.FacebookLeadFormQuestion` | integrations | — |

### Method paths (15)

| Dotted path | Verbs | Access | Old source | New app | Status |
|---|---|---|---|---|---|
| `crm.api.whatsapp.create_whatsapp_message` | GET/POST | auth | `crm_app/integrations/whatsapp/api.py:189` | integrations | — |
| `crm.api.whatsapp.get_whatsapp_messages` | GET/POST | auth | `crm_app/integrations/whatsapp/api.py:117` | integrations | — |
| `crm.api.whatsapp.is_whatsapp_enabled` | GET/POST | auth | `crm_app/integrations/whatsapp/api.py:99` | integrations | — |
| `crm.api.whatsapp.is_whatsapp_installed` | GET/POST | auth | `crm_app/integrations/whatsapp/api.py:104` | integrations | — |
| `crm.api.whatsapp.react_on_whatsapp_message` | GET/POST | auth | `crm_app/integrations/whatsapp/api.py:254` | integrations | — |
| `crm.api.whatsapp.send_whatsapp_template` | GET/POST | auth | `crm_app/integrations/whatsapp/api.py:233` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.dismiss_sync_issue` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:255` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_customer_link` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:90` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_external_companies` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:76` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_open_sync_issues` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:233` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_product_sync_status` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:278` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_quotation_url` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:117` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.is_erpnext_installed` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:65` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.prefill_quotation_items` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:186` | integrations | — |
| `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.run_product_sync` | GET/POST | auth | `crm_app/integrations/erpnext/api.py:309` | integrations | — |
