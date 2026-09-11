# Manual API testing guide

How to test the Django backend by hand, in an order that teaches the codebase one layer
at a time. Two companions:

| File | What |
|---|---|
| [`http/00_walkthrough.http`](http/00_walkthrough.http) | Every request below, ready to click through in VS Code's REST Client, or to replay with `backend/scripts/run_http.py` |
| [`ROUTES.md`](ROUTES.md) | The full inventory, with a blank **Tested** column to fill in as you go |

**Every expected status below was verified on 10 Sep 2026** by replaying the whole
`.http` file against a throwaway database (51 checks, all passing). If a request answers
differently, that is a finding, not a typo in this guide.

---

## 0. Before you start

**Servers.** Two PowerShell windows:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python manage.py runserver 8000
```

```powershell
cd frontend
yarn dev            # http://localhost:8080/crm
```

**Credentials.** The local database already holds `Administrator` (System Manager) and
eight Sales Users named `ada`, `grace`, `alan`, `edsger`, `barbara`, `donald`,
`margaret`, `katherine`, all `@example.com`. Their passwords are not in the repo. Set the
two the walkthrough needs:

```powershell
python manage.py changepassword Administrator
python manage.py changepassword ada@example.com
```

Then put both in the `@admin_pwd` / `@sales_pwd` lines at the top of the `.http` file.

**Tooling.** Install the *REST Client* extension (`humao.rest-client`) in VS Code, open
`http/00_walkthrough.http`, and click **Send Request** above each block. Block 1.1 captures
the tokens; every later block reads them. **Access tokens die after five minutes** — when
you start seeing 401s, re-send 1.1 (or 1.10).

**Recording.** Tick the **Tested** column in `ROUTES.md` as you go. Note anything
surprising next to it; those notes are the output of this exercise.

---

## The rule for the whole exercise

**Do not read the code first. Send the request, look at the response, then open the
file that produced it.** The codebase is 20,000 lines; read cold, it will not stick.
Each step names the two or three files that explain what you just saw.

---

## Step 1 — auth and envelopes

*Teaches:* the three generic views, the two envelopes, the error shape, JWT lifetimes.
*Open afterwards:* `frappe_core/method_views.py`, `frappe_core/exceptions.py`,
`frappe_core/api/auth.py`.

| Block | Request | Expect |
|---|---|---|
| 1.1 | `POST login` with `usr`/`pwd` | 200. `message` holds `access`, `refresh`, `user`, `full_name`, `home_page` |
| 1.2 | `GET frappe.auth.get_logged_user` | 200, `{"message": "Administrator"}` |
| 1.3 | Same, no token | 401, `exc_type: AuthenticationError` |
| 1.4 | A method that does not exist | 404, `exc_type: DoesNotExistError` |
| 1.5 | Wrong password | 401, `"Invalid login credentials"` — upstream's exact wording |
| 1.6 | `usr` but no `pwd` | 417, `exc_type: ValidationError`. **417 is Frappe's code for a validation error**, not 400 |
| 1.7 | `token/refresh` | 200, a **new** pair. Refresh tokens rotate and are single-use |
| 1.8 | Refresh again with the **old** refresh token | 401, blacklisted |
| 1.9 | `logout` with the new refresh token | 200. Note the access token still works for up to five minutes — `KNOWN_ISSUES.md` §6 |

**What to notice in the error body.** Every error carries the same five keys:
`exception`, `exc_type`, `_server_messages`, `message`, `messages`. The frontend branches
on `exc_type` and displays `messages[0]`. `_server_messages` is a JSON string containing
JSON strings, which looks wrong and is exactly what frappe-ui parses.

---

## Step 2 — one doctype through all five CRUD routes

*Teaches:* the generic resource views, the filter grammar, naming, the standard columns.
*Doctype:* **CRM Organization** — its `name` is just the organization name, and it has no
permission rule, so nothing gets in the way.
*Open afterwards:* `frappe_core/views.py`, `frappe_core/filters.py`,
`frappe_core/models.py:77` (BaseDocument), `crm_app/models/core_sales.py:55`.

| Block | Request | Expect |
|---|---|---|
| 2.1 | `POST /api/resource/CRM Organization` | **201**. `name` equals `organization_name`, verbatim — that is the `field:` naming strategy |
| 2.2 | Same name again | 409, `exc_type: DuplicateEntryError` |
| 2.3 | `GET .../Acme Test Co` | 200. Look for `owner`, `modified_by`, `creation`, `modified`, `_assign`, `_comments` — none are in the model class, all come from `BaseDocument` |
| 2.4 | `GET` the list | 200, newest first, 20 per page by default |
| 2.5 | `fields=[...]` and `filters=[["website","like","%acme%"]]` | 200, one row, only the requested columns |
| 2.6 | Same with `%ACME%` | Same row. `like` is case-insensitive on purpose; Postgres alone would say no |
| 2.7 | `in`, dict-form filters, `order_by`, `limit_page_length=1` | 200, one row. Three filter shapes are accepted: list of triples, dict, and `{"field": ["op", value]}` |
| 2.8 | `fields=["no_such_field"]` | 417. Unknown names raise, they are not silently dropped |
| 2.9 | `fields=["owner__password"]` | 417. Relation traversal is refused |
| 2.10 | `PUT` with two fields | 200. **PUT is partial** — only the fields sent change. `modified` moves, `creation` does not |
| 2.11–2.12 | Create `R/GA`, then `GET .../R/GA` | 201 then 200. Names may contain slashes and the URL pattern accepts them |
| 2.13 | `DELETE` both | 200, `{"data": null}` |
| 2.14 | Read the deleted one | 404 |
| 2.15 | `GET /api/resource/ToDo` | 404 — a withheld doctype answers exactly like a nonexistent one |

---

## Step 3 — CRM Lead, then the method endpoints its screen uses

*Teaches:* naming series, model-level validation, the list engine, assignment, the
timeline, and why some CRUD wears a method name.
*Open afterwards:* `crm_app/models/core_sales.py:405` (CRMLead, and the mixins above
it), `frappe_core/api/doc.py` (get_data), `crm_app/api/activities.py`,
`crm_app/api/client.py`.

| Block | Request | Expect |
|---|---|---|
| 3.1 | Create a lead with `first_name`, `last_name`, `email`, **`lead_owner`** | 201. `name` is `CRM-LEAD-2026-000NN` from the naming series; `status` was set to `New` by the model, not by you |
| 3.2 | Read it | `lead_name` is `"Walkthrough Lead"` — composed by `set_full_name` in the model |
| 3.3 | `crm.api.doc.get_data` for CRM Lead | 200. **One payload carries `data`, `columns`, `rows`, and view metadata.** This, not `/api/resource/`, is what the list screen calls |
| 3.4 | Same with `{"lead_owner": "@me"}` | `@me` resolved to the caller before the query ran |
| 3.5 | `frappe.desk.form.assign_to.add` with `["ada@example.com"]` | 200. Writes a **ToDo** row; that row is what grants ada access |
| 3.6 | Read the lead's `_assign` | Now lists ada. This column is a cache of ToDo, refreshed by signal |
| 3.7 | `crm.api.comment.add_comment` | 200 |
| 3.8 | `crm.api.activities.get_activities` | 200. The timeline: creation, assignment, comment, merged from several tables |
| 3.9 | `frappe.client.set_value` | 200. **CRUD wearing a method name** — the frontend calls it, so it exists; behaves like PUT |
| 3.10 | `PUT {"status": "Contacted"}` | 200. Also writes a `CRM Status Change Log` child row with the time spent in `New` |
| 3.11–3.12 | List deals, then read one | Child tables (`contacts`, `products`) arrive inline |
| 3.13 | Delete the lead | 200 |

**The invariant to carry away.** `lead_owner` is the *access* column, not `owner`. Step 4
shows what happens when it is left blank.

---

## Step 4 — the same records as a Sales User

*Teaches:* the row-level permission engine, and what it does and does not protect.
*Open afterwards, and only now:* `crm_app/permissions/org_hierarchy.py`,
`crm_app/permissions/platform_docs.py`, `specs/SECURITY_MODEL.md`.

| Block | Request | Expect |
|---|---|---|
| 4.1 | Login as ada | 200 |
| 4.2 | `get_data` for CRM Lead | Only leads she owns or is assigned to. Compare the count with 3.3 |
| 4.3 | Read a deal that is not hers | **403**, `exc_type: PermissionError`. A 404 would mean it does not exist; the two are distinguishable, matching upstream |
| 4.4 | List organizations | All of them. No row rule — reference data is shared by design |
| 4.5–4.6 | Create a lead **without** `lead_owner`, then read it back | 201, then **403**. She created it and cannot see it. Upstream's rule; the browser fills the field, the API does not |
| 4.7 | Administrator deletes it | 200 |
| 4.8 | `POST /api/resource/CRM Sales Hierarchy` | 403. The org tree is an input to the permission engine, so writing it is System Manager only |
| 4.9 | Read her own `User` row | 200, and `groups` / `password` are absent — `SENSITIVE_FIELDS` never reach the wire |
| 4.10 | Filter `User` on `groups` | **400**, "Invalid Filter". Hiding a field from output is not enough; a filter would turn the row count into an oracle |

---

## Step 5 — everything else

Use the **Frontend uses** column in `ROUTES.md` to decide what matters. Roughly in order:

1. **Contact and Organization screens** — `crm.api.contact.*`, `Contact` CRUD with its child
   tables, `frappe.client.rename_doc`.
2. **Saved views and layouts** — `crm.fcrm.doctype.crm_view_settings.*`,
   `crm_fields_layout.*`, `crm.api.doc.get_quick_filters`. These are runtime UI
   configuration; `PHASE_4_METADATA.md` explains the model.
3. **Dashboard** — `crm.api.dashboard.get_dashboard` / `get_chart`.
4. **User administration** — `crm.api.user.*`, `crm.api.invite_by_email`, and the phase-8
   reset flow. `backend/scripts/walk_auth_flow.py` already walks that one end to end.
5. **Notifications, tasks, notes, call logs.**

**Skip for now:** Celery, realtime, the five integrations. They are behind flags or
invisible until the core works, and none of them changes how CRUD behaves.

---

## Gaps you will hit — read before testing through the browser

The frontend calls **20 dotted paths nothing serves**. They were found on 10 Sep 2026 by
scanning `frontend/src` for `call('...')` sites; the existing guard
(`tests/test_phase3_endpoints.py::test_every_frontend_dotted_path_resolves`) matches
only `url:` and `method:` keys, so these were invisible to it and are recorded nowhere
else. Every one answers 404.

**Product-breaking — a button in the UI does nothing or errors:**

| Path | Called from | Breaks |
|---|---|---|
| `crm.fcrm.doctype.crm_deal.crm_deal.create_deal` | `Modals/DealModal.vue` | **Creating a deal from the UI** |
| `crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal` | `ConvertToDealModal.vue`, `ListBulkActions.vue` | **Convert to deal.** The backend has `crm_app.conversion.convert_to_deal`; it is just not exposed |
| `crm.fcrm.doctype.crm_deal.api.get_deal_contacts` | `pages/Deal.vue` | The contacts panel on a deal |
| `crm.fcrm.doctype.crm_deal.crm_deal.add_contact` / `remove_contact` / `set_primary_contact` | `pages/Deal.vue` | Editing a deal's contacts |
| `crm.fcrm.doctype.crm_call_log.crm_call_log.get_call_log` | `pages/CallLogs.vue`, `Activities/CallArea.vue` | Opening a call log |
| `crm.fcrm.doctype.crm_call_log.crm_call_log.create_lead_from_call_log` | `CallLogDetailModal.vue` | Lead from a call |
| `frappe.core.doctype.communication.email.make` | `CommunicationArea.vue` | **Sending an email from a lead or deal** |
| `frappe.desk.form.assign_to.add_multiple` / `remove_multiple` | `AssignmentModal.vue`, `ListBulkActions.vue` | Bulk assign / unassign |
| `frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs` | `EditValueModal.vue` | Bulk edit |
| `frappe.email.doctype.email_template.email_template.get_email_template` | `EmailEditor.vue` | Picking an email template |

**Desk plumbing the UI is expected to tolerate failing:** `frappe.apps.get_apps`,
`frappe.core.doctype.user.user.get_timezones`, `frappe.desk.form.load.getdoctype`,
`frappe.model.utils.user_settings.save`,
`frappe.integrations.frappe_providers.frappecloud_billing.current_site_info`,
`frappe.utils.telemetry.pulse.client.boot_config`, `crm.demo.api.clear_demo_data`.
`getdoctype` and `user_settings.save` come from `stores/meta.js` and are worth watching:
if a form fails to render its fields, start there.

The controller methods were assigned to phase 1 by `PHASE_3_ENDPOINTS.md` §3 ("port them
with their doctype") and to phase 3 by the phase-1 spec; neither did, and the progress
files call them "deliberately unported". **Deciding whether to port the first table above
is the main open question this testing should settle**, because the API is complete
without them and the product is not.

---

## Two practices that save the most time

- **Use the frontend as a guide, not just a target.** Open the Leads page with the
  browser's Network tab filtered to `/api/`. It shows exactly which endpoints that screen
  calls, in what order, with what parameters. Faster than reading for learning the method
  endpoints.
- **Do not fight the token.** Five-minute access tokens are painful with raw curl. The
  `.http` file, or any REST client with a saved login and a token variable, makes it a
  non-issue.
