# Manual API testing guide

How to test the Django backend by hand, in an order that teaches the codebase one layer
at a time. Two companions:

| File                                                   | What                                                                                                                  |
| ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| [`http/00_walkthrough.http`](http/00_walkthrough.http) | Every request below, ready to click through in VS Code's REST Client, or to replay with `backend/scripts/run_http.py` |
| [`ROUTES.md`](ROUTES.md)                               | The full inventory, with a blank **Tested** column to fill in as you go                                               |

**Every expected status below was verified on 10 Sep 2026** by replaying the whole
`.http` file against a throwaway database (51 checks, all passing). If a request answers
differently, that is a finding, not a typo in this guide.

---

## The suite — fourteen files that cover every endpoint

The walkthrough below is the learning path. The **suite** is the numbered files in
`docs/http/`, one per area, 1021 requests in all, and it is what to run after any change
to the backend. Each block's title carries the status it expects; the runner compares.

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts\run_http.py ..\docs\http\02_resource_grammar.http > ..\docs\http\last_run.txt 2>&1
python scripts\run_http.py ..\docs\http\01_auth.http ..\docs\http\02_resource_grammar.http

python scripts\run_http.py ..\docs\http\0*.http ..\docs\http\1*.http --mark
python scripts\run_http.py ..\docs\http\99_lockout.http     # last: locks logins for 60 s
```

The first command runs files `00` to `13` in order, one after another, and prints a
PASS or FAIL line per block and a total per file. `--mark` writes each file's name into
the **Tested** column of `ROUTES.md` for every endpoint and doctype it touched, with a
count of red lines if there were any. The second command runs the lockout test on its
own, because eleven failed logins lock this machine's address for a minute and every
login after it, yours included, is refused until the minute is up.

**Results on 15 Sep 2026**, against the demo database, after all 22 findings were
fixed (the 11 Sep run before any fix was 900 of 944; the 13 Sep run after the first
eight was 912). Every red line is a numbered entry in [`FINDINGS.md`](FINDINGS.md); a
file stays red until its findings are fixed or recorded as deliberate divergences.
Today every file is green.

| File                                   | Result  | Red lines are        |
| -------------------------------------- | ------- | -------------------- |
| 01 auth                                | 42 / 42 | clean (5, 6 fixed)   |
| 02 resource grammar                    | 81 / 81 | clean (1 to 4 fixed); 10.10b, the duplicate name, added 20 Sep |
| 03 leads                               | 73 / 73 | clean (7 fixed); convert_to_deal added 15 Sep |
| 04 deals                               | 92 / 92 | clean (8, 9 fixed); deal contacts and create_deal added 15 Sep; 7.14 is a hand-testing helper |
| 05 contacts, organizations             | 86 / 86 | clean (10 to 14 fixed); 8.14 is a hand-testing helper |
| 06 tasks, notes, calls                 | 66 / 66 | clean (15, 16 fixed); get_call_log and lead-from-call added 15 Sep |
| 07 views and metadata                  | 99 / 99 | clean (17 fixed); getdoctype and user settings added 16 Sep |
| 08 activities, comments, notifications | 97 / 97 | clean (18, 19 fixed); email.make added 16 Sep |
| 09 users and invitations               | 76 / 76 | clean                |
| 10 dashboard                           | 35 / 35 | clean (20, 21 fixed) |
| 11 permissions matrix                  | 92 / 92 | clean                |
| 12 settings singletons                 | 54 / 54 | clean                |
| 13 bulk and misc                       | 111 / 111 | clean (22 fixed); the five small Desk calls, bulk assign, bulk edit and the template picker added 16 Sep; the boot call's three blocks (9.9–9.11) added 23 Sep, not yet replayed |
| 99 lockout                             | 14 / 14 | clean                |

Three things to know before running it:

- **File 09 spends three of the five `change_password` calls allowed per five minutes.**
  Run it twice inside that window and the change-back is refused, leaving ada's password
  as the temporary one in the file.
- **Each file cleans up what an earlier run left behind before it creates anything**, so a
  run that died halfway does not make the next one fail. Every record it creates is
  prefixed `ZZ`.
- **The whole suite writes to the database it is pointed at.** It creates and deletes its
  own records only, but it does toggle two FCRM Settings flags (forecasting and the sales
  hierarchy) and resets the Manager Dashboard layout, restoring each at the end.

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

The first page after `yarn dev` is slow: frappe-ui is served as source and Vite
transpiles some 1,300 files before `main.js` can run, a minute or two on this machine
(FINDINGS.md 29). The screen is blank until then; the browser's Network tab shows the
modules streaming in. Reloads after that are quick. Start the server once and leave it
running, since every restart is cold, and never start a second Vite against the same
tree. The two lines it prints at startup (no local frappe-ui plugin, no build output
directory) are bench assumptions and mean nothing here. If it prints the first line and
nothing else, read FINDINGS.md 48: frappe-ui's proxy plugin loops forever on Windows,
which is why `vite.config.js` sets the proxy itself.

**Reference data.** Run `python manage.py seed_defaults` once after `migrate`. It writes
what Frappe CRM's install step writes (countries, languages, salutations, genders, statuses, the Quick Entry and
side-panel layouts, industries, lead sources, lost reasons, quick filters, the user menu,
the standard form scripts, the dashboard) and keeps rows that exist (FINDINGS.md 42, 43
and 45). Without it
the create dialogs show every field, the lead and deal pages have no status dropdown,
and the user menu at the top of the sidebar is empty.

**Files.** Uploads land under `backend/media/` (FINDINGS.md 49). Run
`pip install -r requirements.txt` after pulling: `Pillow` was added for the resizing the
uploader asks for on large pictures, and `XlsxWriter` for the Excel export of the list
views (FINDINGS.md 51). The http suite covers neither `upload_file`, whose body is
multipart, nor `export_query`, whose answer is a file; `tests/test_upload_file.py`,
`tests/test_export_query.py` and the browser log do.

**Encryption key.** Set `FIELD_ENCRYPTION_KEY` in `.env` before adding an email account
or telephony settings in the browser (readme, "The encryption key"). Without it the
password cannot be stored and Settings → Email → Accounts → Add fails with "invalid
credentials", a sentence that screen prints for any error (FINDINGS.md 65). Restart
`runserver` after editing `.env`.

**Credentials.** The local database already holds `Administrator` (System Manager) and
eight Sales Users named `ada`, `grace`, `alan`, `edsger`, `barbara`, `donald`,
`margaret`, `katherine`, all `@example.com`. Their passwords are not in the repo. Set the
two the walkthrough needs:

```powershell
python manage.py changepassword Administrator
python manage.py changepassword ada@example.com
```

Then put both in the `@admin_pwd` / `@sales_pwd` lines at the top of the `.http` file.

**Tooling.** Install the _REST Client_ extension (`humao.rest-client`) in VS Code, open
`http/00_walkthrough.http`, and click **Send Request** above each block. Block 1.1 captures
the tokens; every later block reads them. **Access tokens die after five minutes** — when
you start seeing 401s, re-send 1.1 (or 1.10).

**Recording.** Tick the **Tested** column in `ROUTES.md` as you go. Note anything
surprising next to it; those notes are the output of this exercise. Browser sessions
are recorded in `BROWSER_TESTING.md` instead: one table per screen, one row per action,
and a generated API coverage table at the end (`backend/scripts/browser_coverage.py`)
that ticks each endpoint off as the rows that reach it pass.

---

## The rule for the whole exercise

**Do not read the code first. Send the request, look at the response, then open the
file that produced it.** The codebase is 20,000 lines; read cold, it will not stick.
Each step names the two or three files that explain what you just saw.

---

## Step 1 — auth and envelopes

_Teaches:_ the three generic views, the two envelopes, the error shape, JWT lifetimes.
_Open afterwards:_ `frappe_core/method_views.py`, `frappe_core/exceptions.py`,
`frappe_core/api/auth.py`.

| Block | Request                                      | Expect                                                                                     |
| ----- | -------------------------------------------- | ------------------------------------------------------------------------------------------ |
| 1.1   | `POST login` with `usr`/`pwd`                | 200. `message` holds `access`, `refresh`, `user`, `full_name`, `home_page`                 |
| 1.2   | `GET frappe.auth.get_logged_user`            | 200, `{"message": "Administrator"}`                                                        |
| 1.3   | Same, no token                               | 401, `exc_type: AuthenticationError`                                                       |
| 1.4   | A method that does not exist                 | 404, `exc_type: DoesNotExistError`                                                         |
| 1.5   | Wrong password                               | 401, `"Invalid login credentials"` — upstream's exact wording                              |
| 1.6   | `usr` but no `pwd`                           | 417, `exc_type: ValidationError`. **417 is Frappe's code for a validation error**, not 400 |
| 1.7   | `token/refresh`                              | 200, a **new** pair. Refresh tokens rotate and are single-use                              |
| 1.8   | Refresh again with the **old** refresh token | 401, blacklisted                                                                           |
| 1.9   | `logout` with the new refresh token          | 200. Note the access token still works for up to five minutes — `KNOWN_ISSUES.md` §6       |

**What to notice in the error body.** Every error carries the same five keys:
`exception`, `exc_type`, `_server_messages`, `message`, `messages`. The frontend branches
on `exc_type` and displays `messages[0]`. `_server_messages` is a JSON string containing
JSON strings, which looks wrong and is exactly what frappe-ui parses.

---

## Step 2 — one doctype through all five CRUD routes

_Teaches:_ the generic resource views, the filter grammar, naming, the standard columns.
_Doctype:_ **CRM Organization** — its `name` is just the organization name, and it has no
permission rule, so nothing gets in the way.
_Open afterwards:_ `frappe_core/views.py`, `frappe_core/filters.py`,
`frappe_core/models.py:77` (BaseDocument), `crm_app/models/core_sales.py:55`.

| Block     | Request                                                    | Expect                                                                                                                                           |
| --------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| 2.1       | `POST /api/resource/CRM Organization`                      | **201**. `name` equals `organization_name`, verbatim — that is the `field:` naming strategy                                                      |
| 2.2       | Same name again                                            | 409, `exc_type: DuplicateEntryError`                                                                                                             |
| 2.3       | `GET .../Acme Test Co`                                     | 200. Look for `owner`, `modified_by`, `creation`, `modified`, `_assign`, `_comments` — none are in the model class, all come from `BaseDocument` |
| 2.4       | `GET` the list                                             | 200, newest first, 20 per page by default                                                                                                        |
| 2.5       | `fields=[...]` and `filters=[["website","like","%acme%"]]` | 200, one row, only the requested columns                                                                                                         |
| 2.6       | Same with `%ACME%`                                         | Same row. `like` is case-insensitive on purpose; Postgres alone would say no                                                                     |
| 2.7       | `in`, dict-form filters, `order_by`, `limit_page_length=1` | 200, one row. Three filter shapes are accepted: list of triples, dict, and `{"field": ["op", value]}`                                            |
| 2.8       | `fields=["no_such_field"]`                                 | 417. Unknown names raise, they are not silently dropped                                                                                          |
| 2.9       | `fields=["owner__password"]`                               | 417. Relation traversal is refused                                                                                                               |
| 2.10      | `PUT` with two fields                                      | 200. **PUT is partial** — only the fields sent change. `modified` moves, `creation` does not                                                     |
| 2.11–2.12 | Create `R/GA`, then `GET .../R/GA`                         | 201 then 200. Names may contain slashes and the URL pattern accepts them                                                                         |
| 2.13      | `DELETE` both                                              | 200, `{"data": null}`                                                                                                                            |
| 2.14      | Read the deleted one                                       | 404                                                                                                                                              |
| 2.15      | `GET /api/resource/ToDo`                                   | 404 — a withheld doctype answers exactly like a nonexistent one                                                                                  |

---

## Step 3 — CRM Lead, then the method endpoints its screen uses

_Teaches:_ naming series, model-level validation, the list engine, assignment, the
timeline, and why some CRUD wears a method name.
_Open afterwards:_ `crm_app/models/core_sales.py:405` (CRMLead, and the mixins above
it), `frappe_core/api/doc.py` (get_data), `crm_app/api/activities.py`,
`crm_app/api/client.py`.

| Block     | Request                                                                 | Expect                                                                                                                               |
| --------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| 3.1       | Create a lead with `first_name`, `last_name`, `email`, **`lead_owner`** | 201. `name` is `CRM-LEAD-2026-000NN` from the naming series; `status` was set to `New` by the model, not by you                      |
| 3.2       | Read it                                                                 | `lead_name` is `"Walkthrough Lead"` — composed by `set_full_name` in the model                                                       |
| 3.3       | `crm.api.doc.get_data` for CRM Lead                                     | 200. **One payload carries `data`, `columns`, `rows`, and view metadata.** This, not `/api/resource/`, is what the list screen calls |
| 3.4       | Same with `{"lead_owner": "@me"}`                                       | `@me` resolved to the caller before the query ran                                                                                    |
| 3.5       | `frappe.desk.form.assign_to.add` with `["ada@example.com"]`             | 200. Writes a **ToDo** row; that row is what grants ada access                                                                       |
| 3.6       | Read the lead's `_assign`                                               | Now lists ada. This column is a cache of ToDo, refreshed by signal                                                                   |
| 3.7       | `crm.api.comment.add_comment`                                           | 200                                                                                                                                  |
| 3.8       | `crm.api.activities.get_activities`                                     | 200. The timeline: creation, assignment, comment, merged from several tables                                                         |
| 3.9       | `frappe.client.set_value`                                               | 200. **CRUD wearing a method name** — the frontend calls it, so it exists; behaves like PUT                                          |
| 3.10      | `PUT {"status": "Contacted"}`                                           | 200. Also writes a `CRM Status Change Log` child row with the time spent in `New`                                                    |
| 3.11–3.12 | List deals, then read one                                               | Child tables (`contacts`, `products`) arrive inline                                                                                  |
| 3.13      | Delete the lead                                                         | 200                                                                                                                                  |

**The invariant to carry away.** `lead_owner` is the _access_ column, not `owner`. Step 4
shows what happens when it is left blank.

---

## Step 4 — the same records as a Sales User

_Teaches:_ the row-level permission engine, and what it does and does not protect.
_Open afterwards, and only now:_ `crm_app/permissions/org_hierarchy.py`,
`crm_app/permissions/platform_docs.py`, `specs/SECURITY_MODEL.md`.

| Block   | Request                                                   | Expect                                                                                                                   |
| ------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| 4.1     | Login as ada                                              | 200                                                                                                                      |
| 4.2     | `get_data` for CRM Lead                                   | Only leads she owns or is assigned to. Compare the count with 3.3                                                        |
| 4.3     | Read a deal that is not hers                              | **403**, `exc_type: PermissionError`. A 404 would mean it does not exist; the two are distinguishable, matching upstream |
| 4.4     | List organizations                                        | All of them. No row rule — reference data is shared by design                                                            |
| 4.5–4.6 | Create a lead **without** `lead_owner`, then read it back | 201, then **403**. She created it and cannot see it. Upstream's rule; the browser fills the field, the API does not      |
| 4.7     | Administrator deletes it                                  | 200                                                                                                                      |
| 4.8     | `POST /api/resource/CRM Sales Hierarchy`                  | 403. The org tree is an input to the permission engine, so writing it is System Manager only                             |
| 4.9     | Read her own `User` row                                   | 200, and `groups` / `password` are absent — `SENSITIVE_FIELDS` never reach the wire                                      |
| 4.10    | Filter `User` on `groups`                                 | **400**, "Invalid Filter". Hiding a field from output is not enough; a filter would turn the row count into an oracle    |

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

The frontend called **20 dotted paths nothing served**. They were found on 10 Sep 2026 by
scanning `frontend/src` for `call('...')` sites; the existing guard
(`tests/test_phase3_endpoints.py::test_every_frontend_dotted_path_resolves`) matches
only `url:` and `method:` keys, so these were invisible to it and were recorded nowhere
else. **All twenty are served now**: the eight that are CRM code on 15 Sep 2026, the
seven Desk plumbing calls and the five framework calls behind buttons on 16 Sep 2026.
The guard matches `call('...')` sites as well since then, so a new unserved path fails a
test instead of waiting to be found by hand, and file 14, which existed to keep the gap
visible, is retired.

**Served since 15 Sep 2026** (ported from the CRM app into `crm_app/api/deal.py`,
`lead.py` and `call_log.py`; their blocks moved out of file 14 into the file of their area):

| Path                                                                                        | Called from                                     | Now covered by                     |
| ------------------------------------------------------------------------------------------- | ----------------------------------------------- | ---------------------------------- |
| `crm.fcrm.doctype.crm_deal.crm_deal.create_deal`                                            | `Modals/DealModal.vue`                          | `04_deals.http` 5.17 to 5.20       |
| `crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal`                                        | `ConvertToDealModal.vue`, `ListBulkActions.vue` | `03_leads.http` 6.10 to 6.13       |
| `crm.fcrm.doctype.crm_deal.api.get_deal_contacts`                                           | `pages/Deal.vue`                                | `04_deals.http` 5.10, 5.13, 5.15   |
| `crm.fcrm.doctype.crm_deal.crm_deal.add_contact` / `remove_contact` / `set_primary_contact` | `pages/Deal.vue`                                | `04_deals.http` 5.9 to 5.16        |
| `crm.fcrm.doctype.crm_call_log.crm_call_log.get_call_log`                                   | `pages/CallLogs.vue`, `Activities/CallArea.vue` | `06_tasks_notes_calls.http` 4.7b   |
| `crm.fcrm.doctype.crm_call_log.crm_call_log.create_lead_from_call_log`                      | `CallLogDetailModal.vue`                        | `06_tasks_notes_calls.http` 4.7c to 4.7f |

**Served since 16 Sep 2026, the five framework calls behind buttons** (ported from
Frappe's desk and email modules into `crm_app/api/communication.py`, `client.py`,
`bulk_update.py` and `email_template.py`):

| Path                                                                                        | Called from                                     | Does here                                                                                          | Covered by |
| ------------------------------------------------------------------------------------------- | ----------------------------------------------- | -------------------------------------------------------------------------------------------------- | ---------- |
| `frappe.core.doctype.communication.email.make`                                              | `CommunicationArea.vue`                         | Logs the Communication, copies the attachments, sends through the Email Account matching the sender (else the default outgoing one) over its own SMTP settings; queued through Celery, or inline with `now: 1` | `08_activities_comments_notifications.http` 6.20 to 6.31 |
| `frappe.desk.form.assign_to.add_multiple` / `remove_multiple`                               | `AssignmentModal.vue`, `ListBulkActions.vue`    | Assigns or unassigns every named document, write permission on each, the whole batch in one transaction | `13_bulk_and_misc.http` §10 |
| `frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs`                  | `EditValueModal.vue`                            | Updates a field on each document through the same path as a PUT, inline under 20 documents, Celery up to 500, refused above | `13` §10 |
| `frappe.email.doctype.email_template.email_template.get_email_template`                     | `EmailEditor.vue`                               | Renders the template's subject and body with Jinja against the lead or deal                        | `13` §10 |

**Desk plumbing the pages call on load, served since 16 Sep 2026** (the UI tolerated
their 404s, at the cost of a console error per page and a form store with no field
definitions):

| Path                                                                        | What it does here                                                                      | Covered by |
| --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | ---------- |
| `frappe.apps.get_apps`                                                      | The one-entry app list, the CRM itself; the switcher then has nothing to switch to     | `13_bulk_and_misc.http` §9 |
| `frappe.core.doctype.user.user.get_timezones`                               | The timezone names from Python's `zoneinfo`, an approximation of `pytz.common_timezones` | `13` §9 |
| `frappe.desk.form.load.getdoctype`                                          | A doctype's field definitions and its child tables' from `doctype_meta.json`, plus the caller's user settings, as top-level `docs` / `user_settings` keys the way frappe-ui expects | `07_views_and_metadata.http` §9 |
| `frappe.model.utils.user_settings.save`                                     | Per-user, per-doctype view preferences, merged at the top level, in a plain `UserSettings` table | `07` §9 |
| `frappe.integrations.frappe_providers.frappecloud_billing.current_site_info` | Empty, for System Managers; this port can never be a Frappe Cloud site, and any billing added later reports through this call | `13` §9 |
| `frappe.utils.telemetry.pulse.client.boot_config`                           | `{"enabled": false}` until `POSTHOG_PROJECT_ID` and `POSTHOG_HOST` are set in `.env`  | `13` §9 |
| `crm.demo.api.clear_demo_data`                                              | The role gate, then upstream's early return: demo seeding was never ported (`PORT_PLAN.md` §2), so there is no recorded demo state to clear | `13` §9 |
| `crm.www.crm.get_context_for_dev` (served since 23 Sep 2026)                | The boot values `main.js` copies onto `window` before it mounts: formats from the System Settings row, the timezone pair, empty translations, three false site flags. Guest-allowed; called in production too, since no HTML carries them here (FINDINGS.md 26) | `13` §9 |

`getdoctype` is still the one to watch: if a form renders with no fields, or a Select
with no options, start there.

The controller methods were assigned to phase 1 by `PHASE_3_ENDPOINTS.md` §3 ("port them
with their doctype") and to phase 3 by the phase-1 spec; neither did, and the progress
files called them "deliberately unported". All twenty are served now. What is *not*
ported inside them is written in each module's docstring rather than left to be
discovered: read receipts, print formats, delayed sends and inbound mail for
`email.make`; the "enqueued" alert and the progress bar for bulk edit; demo seeding
behind `clear_demo_data`.

---

## Browser tests (Playwright)

`frontend/tests/e2e/` drives the real app in a real Chromium against the two dev servers.
It is the layer the http suite cannot reach: findings 26 to 43 were all faults a browser
saw and a request-level test could not (a blank page, a spinner that never stops, a
menu with no items).

**Before running.** Django on 8000 with the demo data and `python manage.py seed_defaults`
applied; the passwords in `docs/http/.env` (`ADMIN_PWD`, `SALES_PWD`, `MANAGER_PWD`,
read by `playwright.config.js` and never printed); your own `yarn dev` on 8080, which
the runner reuses. If yours sits on another port, `E2E_BASE_URL=http://localhost:8081`;
if none is running, the runner starts one and stops it afterwards. `@playwright/test` is
pinned to the release whose Chromium build is already on this machine; another machine
runs `npx playwright install chromium` once.

```powershell
cd frontend
yarn test:e2e                     # the whole suite, headless, one worker
yarn test:e2e -g "leads"          # one file or test, by name
yarn test:e2e:headed              # watch it
yarn test:e2e:ui                  # Playwright's inspector
yarn test:e2e:report              # the HTML report of the last run, with traces of failures
```

**How it is built.** `auth.setup.js` signs in once as Administrator through the real form
and saves the browser state; every other test starts signed in. `fixtures.js` adds two
things to every test: an uncaught exception in the page fails the test, since that is
how the sidebar (38) and the leads list (40) went blank without a single failed
request; and `api`, a backend client signed in as Administrator, for seeding rows and
removing them again, so the browser only does what the test is about. Every row a test
makes carries an `E2E` prefix and is deleted at the end of the test.

| File | Covers |
| --- | --- |
| `auth.spec.js` | The form, a wrong password, the redirect to and from login, the open-redirect guard, sign-out and the refresh token's revocation |
| `navigation.spec.js` | The sidebar, all seven list pages (rows or the empty state, never a blank pane), the notifications panel, the catch-all page |
| `dashboard.spec.js` | The seventeen tiles, the period control, Refresh, the administrator's edit mode |
| `leads.spec.js` | List row, page tabs, the status dropdown, Create Lead, its mandatory check, Delete |
| `deals.spec.js` | A seeded deal's page, Create Deal with a new organization and contact |
| `contacts-organizations.spec.js` | New Contact, New Organization, an organization's page |
| `activities.spec.js` | Create Task and reopen it, Create Note, a call log's details |
| `settings.spec.js` | The user menu, the Settings dialog and its General page, About |
| `roles.spec.js` | What a Sales User does not get: dashboard editing, management settings |

A cold `yarn dev` makes the first test slow (the setup step allows minutes for it); a
warm server runs the suite in a few minutes. The `Tested` column of `ROUTES.md` §5 is
the place to record what a green run covers.

## Two practices that save the most time

- **Use the frontend as a guide, not just a target.** Open the Leads page with the
  browser's Network tab filtered to `/api/`. It shows exactly which endpoints that screen
  calls, in what order, with what parameters. Faster than reading for learning the method
  endpoints.
- **Do not fight the token.** Five-minute access tokens are painful with raw curl. The
  `.http` file, or any REST client with a saved login and a token variable, makes it a
  non-issue.
