# Findings from the API test suite

Defects the `docs/http/*.http` files turned up, one entry each. **Expected** is what
upstream Frappe does, read from its source; **Actual** is what this port answered. A
finding stays here until it is fixed or a decision records that the port diverges on
purpose, in which case the block's expectation is changed and the entry says so.

The block reference (`02 / 6.9`) is the file and block that reproduces it; run that file
through `backend/scripts/run_http.py` and the failing line is the reproduction.

| # | Block | Severity | Summary | Status |
|---|---|---|---|---|
| 1 | 02 / 6.9 | medium | A filter on a field the doctype does not have answers **500** | **fixed** 13 Sep 2026 |
| 2 | 02 / 10.9, 10.10 | high | A document without a name, or a name containing `<`, answers **500** | **fixed** 13 Sep 2026 |
| 3 | 02 / 10.11 | medium | Deleting a row another row links to answers **409 DuplicateEntryError** with Django's internal wording | **fixed** 13 Sep 2026 |
| 4 | 02 / 10.4, 10.5 | low | Serializer validation answers **400**, the port's own validation answers **417**, both as `ValidationError` | **fixed** 13 Sep 2026 |
| 5 | 01 / 1.11 | medium | An email typed in a different case cannot log in; upstream accepts `Ada@Example.com` | **fixed** 13 Sep 2026 |
| 6 | 01 / 1.4 | low | A malformed bearer token answers `exc_type: InvalidToken`, not `AuthenticationError` | **fixed** 13 Sep 2026 |
| 7 | 03 / 5.8 | medium | A child-table row missing a mandatory field reaches the database and answers **409 DuplicateEntryError**, not `MandatoryError` | **fixed** 14 Sep 2026 |
| 8 | 04 / 4.9, 5.1 | medium | Validation that depends on child rows runs **before the rows are written**, so expected-value auto-update and primary-contact derivation lag one save behind | **fixed** 14 Sep 2026 |
| 9 | 04 / 4.12, 5.1 | **high** | A child row whose Link is given by name, as every form sends it, answers **500** — deal contacts and product lines with a product code cannot be written | **fixed** 14 Sep 2026 |
| 10 | 05 / 2.7, 2.9, 2.10 | medium | Contact's primary-email and primary-phone rules are not applied on a document save: a lone email row is not made primary, a stray `email_id` is not cleared, two primaries are accepted | **fixed** 14 Sep 2026 |
| 11 | 05 / 2.13 | low | Email addresses are never validated — on a contact's email rows, and `crm_lead.py:146` explicitly validates a lead's email too | **fixed** 14 Sep 2026 |
| 12 | 05 / 3.12 | low | `crm.api.contact.*` on a contact that does not exist answers 417 `ValidationError`; upstream answers 403 `PermissionError` | **fixed** 14 Sep 2026 |
| 13 | 05 / 5.1–5.5 | **high** | `rename_doc` inserts a copy and deletes the original: a referenced document cannot be renamed, and renaming a contact **deletes** its email and phone rows and its deal links | **fixed** 14 Sep 2026 |
| 14 | 05 / 6.2, 6.3 | low | The territory tree is unmaintained: `lft`/`rgt` stay null and no tree resolver is registered, so `descendants of` answers 400. Latent — the frontend never sends it | **fixed** 14 Sep 2026 |
| 15 | 06 / 2.2, 2.4 | medium | A task's `assigned_to` never becomes an assignment: no ToDo, empty `_assign`, and changing it does not unassign the previous user | **fixed** 14 Sep 2026 |
| 16 | 06 / 2.8, 3.4, 4.7, 4.9 | **high** | Task, Note and Call Log declare no list columns or rows, so their three screens fall back to Name and Last Modified; call-log rows are not parsed and the document hides its `links` | **fixed** 14 Sep 2026 |
| 17 | 07 / 1.6, 5.8 | medium | A method endpoint given a doctype that does not exist answers **500**: `registry.DocTypeNotFound` is a bare `KeyError` the handler never maps | **fixed** 13 Sep 2026 |
| 18 | 08 / 3.11, 3.12 | medium | Assigning a document to someone never notifies them: nothing listens to ToDo writes, where `crm/api/todo.py` raises the Assignment notification | **fixed** 15 Sep 2026 |
| 19 | 08 / 7.2 | medium | Deleting a document leaves its comments, communications, ToDos and notifications behind; upstream removes them with the document | **fixed** 15 Sep 2026 |
| 20 | 10 / 2.15, 2.16 | medium | Six of upstream's nineteen dashboard charts were never built; a tile using one renders `Invalid chart name` | **fixed** 15 Sep 2026 |
| 21 | 10 / 2.18 | low | A dashboard date that does not parse answers **500**; upstream's `getdate` throws 417 "… is not a valid date string." | **fixed** 13 Sep 2026 |
| 22 | 13 / 4.8 | low | A **private** File attached to nothing is readable by every user; upstream lets only its owner read it | **fixed** 15 Sep 2026 |
| 23 | 05 / 8.2, by hand | medium | Deleting a contact re-validates the rows it is removing: a contact whose rows have two primaries answers **417** and cannot be deleted at all | **fixed** 15 Sep 2026 |
| 24 | 06 / 0.3–0.5, by hand | medium | A name that is not a number, on a doctype whose names are numbers (CRM Task, CRM View Settings), answers **500** on every lookup; upstream answers 404 | **fixed** 16 Sep 2026 |
| 25 | 12 / 2.2 run twice, by hand; 02 / 10.10b | low | Creating a document whose name already exists answers 409 with **Django's internal wording** ("duplicate key value violates unique constraint …"); upstream says "<DocType> **name** already exists", titled "Duplicate Name" | **fixed** 20 Sep 2026 |
| 26 | frontend: `yarn dev`, then `/crm` in a browser | high | The page is **blank**. The dev build waits for `crm.www.crm.get_context_for_dev` (the "boot values": date, number and currency formats, timezone, translations, site flags) before it mounts, and nothing serves it: 404, so the app never mounts. Upstream answers it in dev and writes the same values into the HTML in production; the port has neither | **fixed** 23 Sep 2026 |
| 27 | frontend: `yarn dev`, then `/crm` in a browser | high | Still **blank**, now before `main.js` runs: *"The requested module '/node_modules/debug/src/browser.js' does not provide an export named 'default'"*. frappe-ui has to be served raw, so its socket.io chain reaches the CommonJS `debug` package unconverted | **fixed** 23 Sep 2026 |
| 28 | frontend: `/crm` while logged out | high | The router sends a logged-out visitor to the phase 8 Login page, but `App.vue` has no branch that renders a public route: the page mounts and shows **nothing**. Upstream never needed one, its login lives outside the SPA | **fixed** 23 Sep 2026 |
| 29 | frontend: first load after `yarn dev` | high | A cold load fetched **3,234 modules** and took minutes on this machine: frappe-ui cannot be pre-bundled, its barrel is not rewritten for an installed copy, and every package it imports is served raw (reka-ui 564 files, echarts 556) | **fixed** 23 Sep 2026 |
| 30 | frontend: any screen using `call()` | high | frappe-ui's `call()`, imported directly in 32 files and by the router guard, and its two upload helpers build their own requests: **no bearer header**, so each one answered 401. The JWT patch covered `createResource` only | **fixed** 23 Sep 2026 |
| 31 | frontend: every page load | low | `app.use(FrappeUI)` starts upstream's socket.io client against port 9000, which nothing serves here, and it retries forever: three refused connections per minute in the console beside the port's own WebSocket | **fixed** 23 Sep 2026 |
| 32 | frontend: the login form | high | The token pair arrives (visible in the Network tab) but the page stays on Sign in: frappe-ui returns the login body **wrapped** in `message`, and the session store read the pair from the wrapper, storing nothing | **fixed** 24 Sep 2026 |
| 33 | frontend: right after signing in | high | "Access Denied" for every account, Administrator included. The users store was created on the first, logged-out visit, its fetch got a 401, and after login the guard waited on that same rejected fetch instead of fetching again | **fixed** 24 Sep 2026 |
| 34 | frontend: sign out, then sign in as someone else | medium | Sign-out was an in-app route change, so every store outlived it: the next person to sign in on the same tab inherited the previous user's users list, views and caches, each store believing it had already loaded | **fixed** 25 Sep 2026 |
| 35 | frontend: sign out | high | Sign-out called the backend with an **empty body**, so the refresh token was never blacklisted and a copy of it could mint access tokens for its full seven-day lifetime. Upstream's logout kills the session server-side at once | **fixed** 25 Sep 2026 |
| 36 | frontend: the login form's label | low | The field says "Email or username", but login matches `User.name` only, exactly as upstream: the port has no `username`, and Administrator's `email` is refused because its `name` is the word "Administrator". Frappe Cloud's own sign-in labels the field "Email" | open, decision pending |
| 37 | frontend: every settings screen; the sidebar on first load | high | The frontend asks for the `FCRM Settings` document **by its doctype's name**, as upstream names every single. The port named each singleton row `Settings`, so the request answered 404 | **fixed** 28 Sep 2026 |
| 38 | frontend: the app layout after signing in | high | Blank page: frappe-ui's own "who is signed in" helper reads Frappe's `user_id` **cookie**, which this port never set, so `useOnboarding()` in the sidebar returned nothing and the layout crashed | **fixed** 28 Sep 2026 |
| 39 | every screen with the onboarding panel | medium | frappe-ui's `useOnboarding` calls `frappe.onboarding.get_onboarding_status` and `update_user_onboarding_status` **from inside the package**, so the guard that scans `frontend/src` never saw them; both answered 404 on every screen | **fixed** 28 Sep 2026 |
| 40 | frontend: the leads and deals lists | high | Endless spinner although the data arrived: `_assign` came over as a decoded **list**, upstream sends a JSON **string**, and the page's `JSON.parse(lead._assign)` threw inside the row computation. The five lists without an `_assign` column rendered fine | **fixed** 28 Sep 2026 |
| 41 | frontend: the dashboard | high | Blank dashboard with every number in place: the port's default tile list was an older shape (`type` number/donut/bar and a `width`, no `layout`), and the grid needs a `layout` object and one of the four `*_chart` types the page knows. Upstream's seventeen tiles, verbatim; migration 0009 repairs the saved row | **fixed** 28 Sep 2026 |
| 42 | frontend: the user menu at the top of the sidebar | high | The menu (Apps, Settings, About, Log out) was **empty**: it is built from FCRM Settings' dropdown-item rows, which upstream seeds at install and the port never did, so Settings, About and Log out were unreachable from inside the app. Seeded on first load and by migration 0010 | **fixed** 28 Sep 2026 |
| 43 | frontend: every create dialog; the lead and deal page header; the Source and Industry pickers | high | Upstream's install step was never ported, so the reference rows it writes did not exist: no Quick Entry layouts (every dialog showed every field in unlabeled tabs), no form scripts (the status dropdown never rendered on a lead or deal, and probability did not follow status), no industries, lead sources, communication statuses or quick-filter selections. Ported as `crm_app/setup.py` and `manage.py seed_defaults` | **fixed** 28 Sep 2026 |
| 44 | frontend: the New Contact dialog and the contact side panel | low | Contact's field labels read "first name", "email id", "mobile no": the doctype is not in `doctype_meta.json`, so its labels come from the Django model's verbose names instead of upstream's JSON ("First Name", "Email Address", "Mobile No"). The model's fields now carry upstream's labels, and the contact's `status` field, missing until now, is back, so the contacts list has its three installed quick filters: Status, Email Address, Phone | **fixed** 1 Oct 2026 |
| 45 | frontend: the New Contact and New Organization dialogs, the contact and organization side panels | medium | The `address` Link field searches the `Address` doctype, which the port did not model: `search_link` answered 404 and the console logged an error on every open, and no address could be created. Address and Country ported from the framework; countries seeded | **fixed** 29 Sep 2026 |
| 46 | frontend: every User Link (owner and assignee pickers, the dashboard's Sales User filter) | high | The Link control sends `filters: {ignore_user_type: 1}`, a key upstream's `user_query` pops; the port read it as a field and answered **400** to every User search, so no owner or assignee could be picked | **fixed** 29 Sep 2026 |
| 47 | frontend: a deal's status change; the seeded forecasting script | medium | `frappe.client.get_value` was never served, so the forecasting script's lookup of the new status's probability 404'd and the probability stayed put. Found by the Codex review of finding 43 | **fixed** 29 Sep 2026 |
| 48 | frontend: `yarn dev` on Windows | high | The dev server never started: frappe-ui's proxy plugin looks for a Frappe bench by walking up the directory tree until the path equals `/`, which a Windows path never does, so it loops forever before the server binds. The proxy it would have set is now in `vite.config.js` directly | **fixed** 29 Sep 2026 |
| 49 | frontend: any upload — a picture in a note, a file on a lead, an email's attachment | high | `upload_file` was never served, and nothing served `/files/` or `/private/files/`, so every attachment in the product failed with "Method upload_file not found" and a File row was only ever metadata. Ported `frappe/handler.py:upload_file`, the File doctype's storage pipeline (hash, dedupe, name, write, move, delete) and the two serving routes, which check the File rule before opening a private file; the browser's own fetches of a private file carry the access token in a cookie scoped to that path | **fixed** 29 Sep 2026 |
| 50 | frontend: every page load | low | `GET /assets/crm/manifest/manifest-icon-192.maskable.png` answers 404 on each load. Upstream serves the PWA manifest's icons from the CRM app's `public/` folder under `/assets/crm/`; nothing here serves that path. The browser only wants it for the add-to-home-screen icon | open |
| 51 | frontend: Export in any list view | medium | `frappe.desk.reportview.export_query` was never served, and the frontend started the download by navigating to the URL, which carries no bearer token. Ported the export for the parameters the lists send (Excel and CSV, ticked rows, the view's filters and order, every matching row); the frontend now fetches the file with the header and hands it to the browser as a download | **fixed** 29 Sep 2026 |
| 52 | frontend: Bulk Edit in any list view | medium | The Field dropdown was empty. `crm.api.doc.get_fields` described the Django model's columns and never sent the `hidden` and `read_only` flags; the dialog keeps a field only when both are 0, and a missing key fails that test. It now serves the DocType's own field rows from the metadata, flags filled with their zero defaults, layout breaks excluded unless asked for | **fixed** 29 Sep 2026 |
| 53 | frontend: Kanban view of Tasks, Leads and Deals | medium | A task card showed its title and its id number, nothing else; upstream shows the description, the priority, the age and the linked lead or deal. The three models never declared `default_kanban_settings`, so `get_data` fell back to `["name"]`, and the frontend saved that fallback into the standard kanban view the first time a column was reordered. The models now carry upstream's defaults and migration `crm_app` 0011 repairs the saved rows | **fixed** 29 Sep 2026 |
| 54 | frontend: the Reference Document Type field of notes, tasks and call logs | medium | A Link to `DocType`. `search_link` answered 404 because the port has no DocType doctype, so the dropdown was empty and the Reference Doc beside it had nothing to search; the Link's "Create New" fallback then tried to open and insert a `DocType`, the other 404s of the Notes pass. `search_link` now answers a DocType search from the registry, ignoring permissions as upstream does | **fixed** 29 Sep 2026 |
| 55 | frontend: load time | medium | The app is slow to load during hand testing. Not investigated yet, by decision: to be looked at after the browser testing is finished and this branch is merged. What is known (finding 29's cold-start cost, the boot calls, the blocking boot-values request), what has never been measured (a warm reload, a production build) and the order to work in are in `specs/KNOWN_ISSUES.md` 9 | open, deferred |
| 56 | frontend: deleting an organization that has a deal | low | "Unlink all" in the delete dialog leaves the deal linked, so the organization still cannot be deleted; only "Delete", which removes the deal, gets through. The port matches upstream here: upstream's unlink blanks the generic reference pair only, which a deal does not have (upstream bug 42). Reproduced and pinned by a test. Decision 30 Sep 2026: leave as upstream for now, open a pull request for the fix once the browser testing is finished | open, PR after testing |
| 57 | frontend: Settings → Profile → Email Settings → Add Email | medium | The port's `User` has no `user_emails` table (upstream's `User Email` child rows), so an outgoing account picked under "Add Email" has nowhere to be stored, and the email composer's "from" switcher, which reads the same rows, can never offer one. Separately, and the same upstream: the dropdown says "No results" until an Email Account with Enable Outgoing exists, which is an empty state, not a fault. Ported: `User Email` child rows on `User`, filled by an account that carries the user's address and by a System Manager's Add Email, as upstream's permlevel 1 has it | **fixed** 6 Oct 2026 |
| 58 | frontend: Settings → Preferences → Language | medium | The Language dropdown was empty: it is a Link to the framework's `Language` doctype, which the port did not have, so its search answered 404. Ported the doctype, seeded from the framework's `languages.csv` by `seed_defaults`, everyone reads and System Manager writes; the picker shows the name and offers enabled languages only. The choice is stored on the user and changes nothing on screen, because the port ships no translations | **fixed** 30 Sep 2026 |
| 59 | frontend and backend: translations | medium | Nothing is translated. The boot values carry an empty `translated_messages`, so the Vue app stays in English whatever language a user picks, and the server's messages are English literals. Upstream translates both from the PO files each app ships. Deferred by decision until the browser testing is finished; the design, including translated server messages and Frappe's meaning of `enabled`, is in `specs/KNOWN_ISSUES.md` 10 | open, deferred |
| 60 | frontend: Settings → General → "Mark lead/deal as replied on response" and "Reopen lead/deal on new communication" | medium | The two switches are stored and nothing reads them. Upstream's `on_communication_update` sets the lead's or deal's `communication_status` to Replied for a sent email and to Open for a received one when the matching switch is on. The port's handler only bumps `modified`. Found by reading the code while laying out the Settings rows, not by a failing screen. Decision 30 Sep 2026: to be ported once the browser testing is finished | open, deferred |
| 61 | frontend: the Notifications panel, signed in as an administrator | high | An administrator's bell listed every user's notifications, and "Mark all as read" marked them read for everybody. Upstream's two notification methods filter on `to_user = session.user` for everyone; the port read through the permission rule, which is unrestricted for an administrator. Both now filter on the caller. This is also why the panel did not open: see 62 | **fixed** 30 Sep 2026 |
| 62 | frontend: the Notifications panel, for whoever is assigned a task that is not tied to a lead or deal | medium | The panel does not open at all: such a notification has no reference, the panel builds a link to the lead page from it, and the router refuses a link with no id, which takes the whole panel down. The data and the Vue file are both upstream's, so upstream has the same fault (upstream bug 43). Administrator hit it here only because of 61, which put other users' rows in the list | open, same as upstream |
| 63 | frontend: Settings → Dashboard → Dashboard Currency and Exchange Rate Provider | medium | The currency dropdown is empty: it is a Link to the framework's `Currency` doctype, which the port does not have, so its search answers 404. With no currency set the provider select stays disabled, and behind it the exchange-rate call is a stub that always answers 1 (a phase 3 decision). Decision 30 Sep 2026: port Currency once the browser testing is finished | **fixed** 15 Oct 2026: Currency ported, the four exchange-rate providers ported and applied on save; S4 and S21 to re-check |
| 64 | frontend: Settings → Defaults | medium | The section goes blank. The page reads and writes the framework's `System Settings` document and its metadata, neither of which the port has: both calls answer 404, the document never loads, and the template then reads a field off nothing. In the port the same six values (currency, the two precisions, number, date and time format) are fixed in Django settings and sent with the boot values, so they cannot be changed from the app. Decision 30 Sep 2026: to be built after the browser testing, as one piece of work with 63 (Currency) and the system-language step of 59 (translations) | **fixed** 15 Oct 2026: System Settings ported, the boot call reads it; System Manager only (`UPSTREAM_BUGS.md` 50); S5 to re-check |
| 65 | frontend: Settings → Email → Accounts → Add | high | Adding a real Gmail account with a correct app password ended in "Failed to create email account: invalid credentials". The login had succeeded; the save then failed because the local `.env` had no `FIELD_ENCRYPTION_KEY`, without which a password cannot be stored, and the screen prints that one sentence for any error at all. The key is now checked before the login, anything the mail libraries raise is a refusal and not a 500, and the setup docs say the key is required | **fixed** 1 Oct 2026; needs `FIELD_ENCRYPTION_KEY` in `.env` |
| 66 | frontend: Salutation and Gender on a contact, a lead and a deal | medium | Upstream offers both as dropdowns, Links to the framework's `Salutation` and `Gender` doctypes. The port had neither doctype: on a contact the two were plain text boxes, and on a lead or deal the dropdowns existed but listed nothing. Ported both doctypes, seeded with upstream's nine salutations and seven genders, everyone reads and System Manager writes, and the contact's two fields are declared Links | **fixed** 1 Oct 2026 |
| 67 | frontend: the Email and Mobile No dropdowns on a contact's page | high | Picking another number as primary answered "Only one Mobile No can be set as primary" and left two rows flagged, after which nothing on that contact would save. Editing or removing a number or an address from the dropdown answered 404. The flags are now written as one unit, old ones cleared first, and `frappe.client.set_value` / `delete` reach a contact's email and phone rows through the contact, as upstream's do | **fixed** 1 Oct 2026 |
| 68 | frontend: Remove Image on an organization's logo | medium | The menu item sends `organization_logo: null`, which upstream's `set_value` stores as an empty field. The port's text columns refuse `null` ("This field may not be null."), so the logo could be changed but never removed. `null` on a text field now means empty, on both write routes | **fixed** 5 Oct 2026 |
| 69 | frontend: the Calls tab of a lead or deal | high | A call log pointed at a lead (Reference Document Type and Reference Name) never showed on that lead's Calls tab. `get_linked_calls` found the call but returned it raw; upstream's last line runs every call through `parse_call_log`, and the call card reads `_caller` and `_receiver` off each row, so it could not be drawn. The port of that function had stopped one line short | **fixed** 5 Oct 2026 |
| 70 | frontend: bulk Edit on the task list, emptying Assigned To | low | Tick tasks → Edit → "Assigned To" left empty → Update does not clear the assignee; setting a user the same way works. The upstream demo behaves the same. Recorded without looking for the cause, by decision on 5 Oct 2026 | open, not investigated |
| 71 | frontend: bulk actions on a list (seen on Leads) | low | After a bulk action finishes (Edit, Assign To, Clear Assignment, Convert to Deal, Delete) the ticked rows stay ticked and have to be unticked by hand. Recorded on 5 Oct 2026 without looking for the cause or comparing with upstream, by decision | open, not investigated |
| 72 | frontend: a call log edited from a lead's Calls tab | low | Changing a call's time in its form and closing the form leaves the old value on the lead's Calls tab until the page is reloaded. Recorded on 5 Oct 2026 without looking for the cause or comparing with upstream, by decision | open, not investigated |
| 73 | frontend: Convert to Deal on a lead's page | high | "Error converting to deal: Internal Server Error". The dialog sends the deal's fields with `doctype` and `__newDocument` among them, and the port handed them to the model: `TypeError: CRMDeal() got unexpected keyword arguments: '__newDocument', 'doctype'`. Bulk convert, which sends no deal fields, worked. The dialog's form now goes through the deal's serializer, which keeps the deal fields and drops the rest | **fixed** 5 Oct 2026 |
| 74 | frontend: the Create Deal dialog, and Convert to Deal after it | medium | The dialog's form is one object shared for the whole page session (`data/document.js`) and is never cleared after a deal is created, so the next deal starts from the last one's values. Once "Choose Existing Organization" has been used, its pick stays in the form when the switch is off and hidden, and the server prefers it to the organization details typed, upstream and here alike. The Convert to Deal dialog reads the same object. Upstream bug 45; the frontend is upstream's, so the port reproduces it. Reloading the page clears it | open, upstream bug 45 |
| 75 | frontend: the delete dialog on a deal's page, and bulk delete | high | The dialog listed the deal's own contact row and its comments as "linked documents". Upstream lists neither: a child row is the document's own, and comments go with it. The contact row cannot be unlinked, so after "Unlink All" it was still listed and the Delete button never appeared; only "Delete All" could delete a deal that had a contact. Unlinking a comment orphaned it, in the dialog and in bulk delete. A contact's dialog listed the deal's contact row instead of the deal. The two finders now skip a child table's parent link and the framework's `ignore_links_on_delete` doctypes, and report a child row's link as its parent document | **fixed** 6 Oct 2026 |
| 76 | API: `frappe.client.delete` and `DELETE /api/resource/` on a document that other documents still point at by reference | low | Upstream refuses with `LinkExistsError` ("Cannot delete or cancel because … is linked with …") while a task, note or call log still references the document; the port deletes it and leaves the reference dangling. Not reachable from the Vue app, whose dialog hides Delete until the list is empty, except for a linked document the caller cannot see. Links through a foreign key are refused as upstream does | open, decision deferred |
| 77 | frontend: the Deals list would not open | high | Clicking a deal's Annual Revenue cell filed the cell's display string, "$ 500,000.00", as the filter (upstream bug 46), and the standard view saved it. Upstream's database casts the string to 0 and shows an empty list; the port's filter builder refused it with 417, and since the saved filter is replayed on every load the page never opened again, with no way to remove the chip. Filter values for numeric columns are now read for the number in them, so the click filters on the amount shown; a deliberate divergence, recorded with bug 46 | **fixed** 6 Oct 2026 |
| 78 | frontend: Settings → Home Actions, a standard row | low | The grid lets a standard entry's Type be changed to Separator although the doctype marks it read-only for standard rows; done to Settings, the entry vanishes and nothing in the app can bring it back, since the grid lives in Settings. Upstream bug 47, seen on the demo. The port reproduces it (the frontend is upstream's) and gives `seed_defaults --force` the job of restoring the standard rows, where upstream needs Desk | open, upstream bug 47; recovery added |
| 79 | Settings → Invite User (and every system mail: invitations, password resets) | medium | The invitation went to the Celery worker's console instead of the inbox. System mail was sent with Django's `EMAIL_BACKEND` from `DEFAULT_FROM_EMAIL` (`crm@example.com`), which `.env` leaves at the console backend locally, while a mail written on a lead went through the Email Account's own SMTP; and a site with no Email Account could not send a lead's mail at all, where upstream falls through to the account `site_config.json` describes. Seen 6 Oct 2026 (S8). Both now run upstream's four-step lookup, with Django's `EMAIL_*` settings as the port's `site_config.json` - the config account; `EMAIL_HOST=localhost` with the console backend for development | **fixed** 13 Oct 2026 |
| 80 | Settings → Assignment Rules → Save | high | Save does nothing. The screen posts `frappe.client.insert` for doctype `Assignment Rule`, a framework doctype the port does not model (`crm_app/api/assignment_rule.py`, a phase-3 decision: outside the nine platform doctypes), so the insert answers 404; the screen's error handler only clears its spinner, so nothing is shown. The list endpoint returns `[]` by the same decision. Upstream's engine is `frappe/automation/doctype/assignment_rule` (436 lines: round robin, load balancing, based on field, assign and unassign conditions, assignment days, applied on insert and update of leads and deals) plus the CRM's own JSON condition fields. Seen 6 Oct 2026 (S12). Decision wanted: port it, or defer with Currency and System Settings | open, decided 15 Oct 2026: port the engine and its four rule types, conditions from the JSON with no code run; build with the SLA engine (91) |
| 81 | Settings → SLA Policies → Assignment conditions | low | Add a custom condition, leave its fields empty, and try to remove it: the empty condition stays. Seen 6 Oct 2026 (S13); the same on the upstream demo, checked 7 Oct 2026, so it is upstream's (the condition builder is its frontend) and belongs with the upstream bugs once traced | open, upstream too, not traced |
| 82 | Settings → SLA Policies → Duplicate | medium | Duplicate did nothing. The screen fetches the policy with `frappe.client.get` and posts the whole document back into `frappe.client.insert` with the new name; upstream's documents always carry a `doctype` key (`as_dict`), the port's did not, so the insert answered 417 "doctype is required" and the screen, with no error handler, showed nothing. Every document the port serialises now carries `doctype`, child rows included | **fixed** 7 Oct 2026 |
| 83 | frontend: a wrong URL with a second segment, `/crm/leadsdss/CRM-LEAD-…` | low | A blank page where `/crm/leaderssf` shows "Invalid page or not permitted to access": upstream's catch-all route `/:invalidpath` matches one segment only, so a two-segment typo matches nothing. The same on the hosted demo (upstream bug 48). Patched here by decision: `/:invalidpath(.*)*`, the router's real catch-all, noted in `frontend/JWT_PATCH.md` | **fixed** 7 Oct 2026, by patch |
| 84 | the Products grid's Edit Grid Fields dialog (D26) looks different from the hosted upstream | low | Not a port fault: the port's frontend is upstream's pinned at `6583bfcdc` (11 Sep 2026), and `git fetch` on 7 Oct 2026 shows upstream `main` at `deedce73c` (30 Sep 2026), 514 commits ahead, three of them on the grid (`946c24d8f` align child table header with rows, `53080db04` fetch_from support in fields, `b29f99452` translate Select option labels). The grid files here are byte-identical to the pinned clone, and the port's `getdoctype` for `CRM Products` matches the pinned json field for field. Kept for the day the pin moves | open, version gap |
| 85 | Settings → Brand (S6): the logo and favicon showed for the account that uploaded them and for nobody else; the same for a profile photo and the lead, contact and organization images | medium | frappe-ui uploads privately unless told otherwise and the image uploaders never tell it otherwise, so each image is a private File row attached to nothing, which the File rule lets its owner alone read. Upstream has the same upload and the same rule, and shows the logo to everyone because a framework hook, `attach_files_to_document`, runs on every document save and attaches the file an Attach field names to that document; the File rule then defers to the document, and FCRM Settings is readable by every CRM role. The port had no such step. Ported as a `post_save` receiver on every doctype with an Attach field (`frappe_platform.files`), `ATTACH_FIELDS` declared on User and Contact, whose metadata is derived from the model | **fixed** 14 Oct 2026 |
| 86 | Contacts (K7), the role passes: Grace and Ada deleted a contact Administrator created; the hosted demo refuses both | medium | Upstream's `contact.json` gives Sales User and Sales Manager read, write and create on every contact and no delete; delete comes from the `All` row with `if_owner`, so the creator or a System Manager. The port registered no rule for Contact, so any CRM user deleted any contact: upstream protection read as a missing hook, the security exception `CLAUDE.md` names. Ruled: `contact_has_permission`, everything but delete open, delete for the creator or System Manager; the resource route, `frappe.client.delete`, the delete dialog and bulk delete all consult it | **fixed** 14 Oct 2026 |
| 87 | Settings → Email → Templates (S11), the role passes: Grace and Ada created, edited and deleted templates | medium | Upstream's `email_template.json` gives `Desk User`, the role every System User holds, read only, and System Manager create, write and delete; CRM adds nothing, and shows the page to every role. The port had no rule, so any CRM user rewrote the wording of mail sent in the company's name. Ruled: `email_template_has_permission`, read for everyone, the rest System Manager; every door consults it | **fixed** 14 Oct 2026 |
| 88 | Dashboard → "Deals by territory" and "Deals by salesperson", found reading the code for 63 | low | Upstream plots two series on each, the number of deals and their value in the dashboard currency (`dashboard.py:1029-1147`), with upstream's titles and subtitles. The port plots the count alone, under different subtitles | **fixed** 15 Oct 2026: both charts return upstream's two series, the value in the dashboard currency |
| 89 | Dashboard → the three average deal value cards, found in the review of 63 and 64 | medium | "Avg. deal value" counted lost deals, which upstream leaves out (`dashboard.py:387`); all three cards had their own titles and tooltips, and a percentage delta where upstream sends the difference of the averages | **fixed** 15 Oct 2026; the `%` upstream puts after that difference is `UPSTREAM_BUGS.md` 51, reproduced |
| 90 | the country and currency reference data, found in the review of 63 and 64 | low | `crm_app/data/country_info.json` was the framework's `develop` copy, not version-15's: Turkey was "Türkiye" and Turkmenistan's currency TMT, where version-15 has "Turkey" and TMM. The framework checkout this port reads is on `develop`, not the `version-15` CLAUDE.md names | **fixed** 15 Oct 2026: the version-15 file; a database seeded earlier keeps its two extra rows |
| 91 | every lead and deal: no SLA is ever applied, found comparing finding 80 | high | Upstream picks an SLA for each lead and deal on save and keeps its response deadline, first response and SLA status up to date (`set_sla` and `apply_sla`, about 420 lines in `crm_service_level_agreement`). The port's `apply_sla` is still the empty phase-1 placeholder, so the SLA Policies screen saves policies that nothing applies | open, recorded 15 Oct 2026 |

---

## 1. Unknown field in a filter → 500

**Block:** `02_resource_grammar.http` 6.9 — `filters=[["no_such_field","=","x"]]`

**Expected:** a 4xx with `exc_type: ValidationError`. The port's own contract
(`AS_BUILT.md` §4: "unknown row/field names raise, they are not dropped") and the comment
in `frappe_core/exceptions.py` on `FilterError` both say a malformed filter is a client
error, and `fields=` and `order_by=` already answer 417 for the same mistake.

**Actual:** 500. `filters.resolve_field_path` returns the name unchanged when the model
has no such field, `Q(no_such_field="x")` reaches the ORM, and Django raises `FieldError`,
which nothing catches. With `DEBUG=True` the body is the HTML debug page.

**Where:** `frappe_core/filters.py:build_q` — validate `fieldname` against
`concrete_field_names(model)` before building the `Q`, raising `FilterError`.

**Upstream, for the record:** `frappe/utils/data.py:get_filter` (version-15) checks the
*operator* against a fixed list and throws 417 `Operator must be one of ...` for a bad
one, and sanitises the column name against injection. It then asks
`meta.has_field(fieldname)`, and when the answer is no it only tries the child tables and
carries on; nothing throws. `prepare_filter_condition` builds the column into the SQL,
MariaDB rejects the unknown column, and the request fails with a database error. So
upstream is also a 500 here. The 4xx expectation is the port's
own contract, not a fidelity requirement, and it is the better behaviour: a typo in a
saved view's filter should not read as a server crash.

**Fixed 13 Sep 2026.** `build_q` checks the field against the model's concrete columns
before building the `Q` and raises `FilterError` with the sentence `fields=` already
uses, `Unknown field 'x' for this document type`, so the answer is 400 like every
other malformed filter. Block 02 / 6.9 is green.

## 2. Naming validation errors → 500

**Blocks:** `02_resource_grammar.http` 10.9 (no `organization_name`) and 10.10 (name
`ZZ <script>`)

**Expected:** two different answers from `frappe/model/naming.py` (version-15):

* no name on a `field:` doctype → `set_name_from_naming_options` (naming.py:206-210)
  throws `"{0} is required"` with the field's **label**, so **417** `ValidationError`
  with the message `Organization Name is required`. (This entry first said "No Name
  Specified for CRM Organization": that is `validate_name`'s sentence, which upstream
  only reaches when nothing at all set the name. The `field:` check fires first.)
* `<` or `>` in the name → `validate_name` throws `frappe.NameError`, declared with
  `http_status_code = 409`, so **409** with `exc_type: NameError` and the message
  `Name cannot contain special characters like '<', '>'`.

The frontend branches on neither; it displays `messages[0]`, so the sentence is what a
person sees.

**Actual:** 500 for both. `frappe_core/naming.py` raises its own `NameError_`, a plain
`ValueError` subclass, for every naming failure - the two above and five more. It is not
a `FrappeError`, so `frappe_exception_handler` returns `None` and Django's 500 handler
takes over. The message text was transcribed correctly; it never reaches the client.

**Where:** `frappe_core/naming.py` - raise `frappe_core.exceptions.ValidationError` for
the empty name and a `NameError` subclass of `FrappeError` (status 409) for the rest, so
both the status and the `exc_type` match upstream. **User-visible:** the Organization
form's Save with an empty name shows a generic failure instead of the message written
for it.

**Fixed 13 Sep 2026.** `NameError_` is gone. `validate_name` raises the port's
`ValidationError` for the empty name and a new `frappe_core.exceptions.NameError`
(409) for the other three rules; the `field:` strategy raises `"<Label> is required"`,
the `prompt` strategy `"Please set the document name"`, and the `format` strategy hands
an empty result to `validate_name` as upstream does. Blocks 02 / 10.9 and 10.10 are
green with the corrected expectations above.

## 3. Deleting a linked row → 409 with Django's wording

**Block:** `02_resource_grammar.http` 10.11 — `DELETE CRM Industry/ZZ Grammar Industry`
while an organization links to it

**Expected:** 417, `exc_type: LinkExistsError`, message
`Cannot delete or cancel because CRM Industry ZZ Grammar Industry is linked with CRM
Organization ZZ Grammar Alpha` (`frappe/model/delete_doc.py:check_if_doc_is_linked`).
The frontend shows that message.

**Actual:** 409, `exc_type: DuplicateEntryError`, message *"Cannot delete some instances
of model 'CRMIndustry' because they are referenced through protected foreign keys:
'CRMOrganization.industry'."* — Django's `ProtectedError` is a subclass of
`IntegrityError`, and the handler maps every `IntegrityError` to "Duplicate".

**Where:** `frappe_core/exceptions.py` — catch `ProtectedError` before `IntegrityError`
and render it as `LinkExistsError` (417) with the Frappe sentence. The referencing rows
are in `exc.protected_objects`.

**Fixed 13 Sep 2026.** The handler catches `ProtectedError` and `RestrictedError`
ahead of `IntegrityError` and renders a new `LinkExistsError` (417) whose message is
built the way `delete_doc.py:raise_link_exists_exception` builds it: the document, the
first referencing document by name, and for a reference in a child table the parent
plus `at Row: <idx>`. Block 02 / 10.11 is green.

## 4. Two status codes for one exc_type

**Blocks:** `02_resource_grammar.http` 10.4 (bad Select value) and 10.5 (Link to a
missing row)

**Expected:** 417. Every validation failure upstream is `frappe.exceptions.ValidationError`
with `http_status_code = 417`, and the port's own `ValidationError` uses 417.

**Actual:** 400. DRF's serializer raises its own `ValidationError`; the handler relabels
`exc_type` to `ValidationError` but keeps DRF's 400. So the same `exc_type` arrives as
400 from the serializer and 417 from model or filter code. The frontend branches on
`exc_type`, not the number, so nothing breaks; it is an inconsistency, and the reason the
suite keeps 417 as the expectation is that `PORT_PLAN.md` §3 fixes the wire protocol.

**Fixed 13 Sep 2026.** The handler answers 417 for DRF's `ValidationError`, so the
serializer and the port's own validation agree. Blocks 02 / 10.4 and 10.5 are green,
and the `400|417` titles that accepted this in files 03, 04, 06 and 07 are back to
`417`. `FilterError` keeps its 400: that is a separate, documented contract of the port.

**Where:** `frappe_core/exceptions.py`, the `drf_exceptions.APIException` branch — use 417
when the mapped `exc_type` is `ValidationError`.

## 5. Login is case-sensitive on the email

**Block:** `01_auth.http` 1.11 — `{"usr": "ADA@EXAMPLE.COM", "pwd": <correct>}`

**Expected:** 200. Upstream's `User.find_by_credentials` (`user.py`) looks the name up
with `frappe.db.get_value`, and MariaDB's default collation compares case-insensitively,
so any casing of the address logs in. The User primary key is stored lowercased
(`frappe_platform/models.py:226`) for exactly that reason.

**Actual:** 401 `Invalid login credentials`. `frappe_core/api/auth.py:login` lowercases
the name only for the lockout tracker key and passes the raw value to
`authenticate()`, which does an exact match on `name`.

**Where:** `login` — resolve the account case-insensitively before authenticating.
Not a blanket `.lower()`: the built-in `Administrator` is stored with its capital, so the
lookup should be `name__iexact` (or try exact, then lowercased). **User-visible:** anyone
whose mail client capitalises their address gets "Invalid login credentials" for a
correct password.

**Fixed 13 Sep 2026.** `login` resolves the stored spelling, exact first and then
`name__iexact`, before calling `authenticate`; the review pointed out that `iexact`
alone could match both the built-in `Administrator` and a user literally named
`administrator`. The disabled-account check reuses that lookup and, as upstream's
`LoginManager.authenticate` does, runs only after the password is verified. Block 01 /
1.11 is green; `tests/test_auth.py` covers the upper-case email, the mixed-case email,
`administrator` typed in lower case, the exact-name precedence, and a disabled account
with the right and the wrong password.

## 6. A malformed bearer token is not an `AuthenticationError`

**Block:** `01_auth.http` 1.4 — `Authorization: Bearer this-is-not-a-token`

**Expected:** 401 with `exc_type: AuthenticationError`, which is what every other
authentication failure in the port answers and what `frontend/src/stores/users.js:34`
branches on.

**Actual:** 401 with `exc_type: InvalidToken` and SimpleJWT's wording *"Given token not
valid for any token type"*. The handler maps `drf_exceptions.AuthenticationFailed` by
exact type; SimpleJWT's `InvalidToken` is a subclass and falls through to its own class
name.

**Where:** `frappe_core/exceptions.py` — match with `isinstance` rather than the exact
type, or add `InvalidToken` to the map. The status is already right, so the frontend's
refresh-on-401 works; only the label and message differ.

**Fixed 13 Sep 2026.** The handler matches DRF exceptions with `isinstance`, most
specific first, so every `AuthenticationFailed` subclass is an `AuthenticationError`,
and for those it keeps only the one sentence under SimpleJWT's `detail` instead of the
nested per-token-class breakdown. Block 01 / 1.4 is green.

## 7. A child row missing a mandatory field is a database error

**Block:** `03_leads.http` 5.8 — `PUT` a lead with
`products: [{"product_name": "ZZ No Rate", "qty": 1}]`

**Expected:** 417 with `exc_type: MandatoryError` and Frappe's message
`Error: Value missing for CRM Products: Rate` (`frappe/model/document.py:_validate_mandatory`
walks child rows too). The frontend branches on `MandatoryError` (`data/document.js:61`,
`Modals/DoctypeModal.vue:115`) to highlight the missing field.

**Actual:** 409, `exc_type: DuplicateEntryError`, message *"null value in column "rate" of
relation "crm_app_crmproducts" violates not-null constraint"*. The nested child payload
is written by `children.replace_children` without going through the child doctype's
serializer, so nothing checks required fields before the INSERT; the NOT NULL constraint
fires and the handler renders it as a duplicate.

**Where:** `frappe_core/serializers.py:_write_children` — validate each row through the
child's serializer (or check its required fields) before `replace_children`, raising
`MandatoryError`. Parent-level mandatory fields already answer correctly (03 / 2.5).

**Fixed 14 Sep 2026.** `children.prepare_rows` checks every row before anything is
deleted or written: a writable column that allows neither NULL nor blank and has no
default is mandatory, and each missing one is reported with upstream's child-row
wording, `Error: <strong>CRM Products</strong> Row #1: Value missing for: Rate`, one
message per value, as `MandatoryError` 417. Block 03 / 5.8 is green.

## 8. Child-dependent validation runs before the child rows are written

**Blocks:** `04_deals.http` 4.9 (with 4.9b/4.9c showing the catch-up), and 5.1 once
finding 9 is fixed.

**Expected:** upstream's `validate()` sees the child rows as part of the document, so a
single save that adds product lines moves `expected_deal_value` to the new total
(`crm_deal.py:240-248`, with `auto_update_expected_deal_value` on), and a single save that
adds a contact row makes it primary and copies its email, mobile and phone onto the deal
(`crm_deal.py:120-149`).

**Actual:** the port's serializer calls `instance.save()` first and writes the child rows
afterwards (`frappe_core/serializers.py:update`, then `_write_children`). `save()`
therefore runs `update_expected_deal_value` and `set_primary_contact` against the rows
that existed *before* this request. The totals are then refreshed by a bare `update()`,
so the very next save of any field catches up (4.9c passes), but the request that made
the change answers with stale derived values. For contacts the same order means a
contact added through the document is never made primary and the deal's email stays
empty until something else saves the deal.

**Where:** `frappe_core/serializers.py` — write the children before the final `save()`
(create the parent with `save()` first only to obtain a name, or run the derivations
again after `_write_children`), so the derived fields and the child rows land in the
same request as they do upstream.

**Fixed 14 Sep 2026.** On update the serializer writes the rows before the parent's
save, so `validate()` sees them; on create the parent is saved first for its name, the
rows are written, and it is saved once more so the derivations run. Both inside a
transaction, so a parent-level refusal takes the rows back. Blocks 04 / 4.9 and 5.1
are green in the same request; 4.9b and 4.9c now show no lag.

## 9. A child row whose Link is given by name answers 500

**Blocks:** `04_deals.http` 4.12 (`products: [{"product_code": "ZZ-P1", ...}]`) and 5.1,
5.3, 5.5, 5.8 (`contacts: [{"contact": "ZZ Primary"}]`)

**Expected:** 200. A Link field in a child row is written by name over the wire, exactly
as a top-level Link is; `ConvertToDealModal.vue`, the deal contacts panel and the product
grid all send `{"contact": "<name>"}` / `{"product_code": "<code>"}`.

**Actual:** 500 with `ValueError: Cannot assign "'ZZ Primary'": "CRMContacts.contact" must
be a "Contact" instance.` `children.replace_children` copies the row dict into
`create(**payload)` untouched; Django accepts a raw key only under the `_id` attname
(`contact_id`), which the docstring there acknowledges and which no Frappe client ever
sends. Top-level Links are fine because the parent goes through a DRF serializer, which
resolves the key; child rows bypass the serializer.

**Where:** `frappe_core/children.py:replace_children` — for every `ForeignKey` on the
child model, move a value supplied under the field name to its `attname`, and let a
missing target surface as the 417 `LinkValidationError` upstream raises
(`Could not find Row #1: Contact: ZZ Nobody`) rather than a 500. Finding 7's validation
pass would be the natural place. **User-visible:** adding a contact to a deal, or a
product with a code, fails outright through the document route.

**Fixed 14 Sep 2026.** `children.prepare_rows` moves a Link given under the field name
to the column Django writes after confirming the target exists; a missing target is
`LinkValidationError` 417 with upstream's wording, `Could not find Row #1: Contact:
ZZ Nobody`, and nothing is deleted before the rows pass. An instance or a raw key
under the attname still works, as the models' own callers use it. Blocks 04 / 4.12,
5.1, 5.3, 5.5 and 5.8 are green, and 05 / 4.1 now sends `contact` as the form does.

## 10. Contact's primary rules are not applied on a document save

**Blocks:** `05_contacts_organizations.http` 2.6/2.7 (a lone email row is not made
primary), 2.8/2.9 (a top-level `email_id` with no rows is not cleared), 2.10 (two
primary rows accepted)

**Expected:** `Contact.validate` (`contact.py:65`) calls `set_primary_email` and
`set_primary("phone")` / `set_primary("mobile_no")` on every save: one row means it is
primary; no rows means the mirror column is emptied; two primaries throw
`Only one Email ID can be set as primary.` (417).

**Actual:** the port's `Contact.save()` only derives `full_name`. The mirror columns are
refreshed by `sync_primary_values`, which runs from a signal when a *child row* is
written through `crm.api.contact.create_new` / `set_as_primary`, so those two endpoints
behave; a document saved through `/api/resource/Contact` with rows inline gets none of
the three rules. **User-visible:** a contact created with one email through the form
shows no primary, and a deal that later picks it up derives an empty email.

**Where:** `frappe_platform/models.py:Contact.save` — port the three methods, run them
after the child rows are written (finding 8's ordering applies here too).

**Fixed 14 Sep 2026.** `Contact.set_primary_email` and `Contact.set_primary` are
upstream's, verbatim, and `Contact.save` runs them on every save of an existing contact
(a create clears the three columns, since no row can exist yet; the document route
saves again once its rows are written). Two primaries throw `Only one <strong>Email
ID</strong> can be set as primary.` and the phone equivalents. The per-row re-sync
signal stands down while a document's rows are being replaced, so the rules see the
finished set, as upstream's single `validate` does. The earlier port's "first row when
none is primary" fallback is gone: with no primary flagged the column is empty. Blocks
05 / 2.6 to 2.12 are green.

## 11. Email addresses are never validated

**Block:** `05_contacts_organizations.http` 2.13 — an email row `not-an-email`

**Expected:** 417 `InvalidEmailAddressError`, *"not-an-email is not a valid Email
Address"*. Upstream validates every `Data` field whose `options` is `Email`
(`base_document.py:_validate_data_fields`), which covers `Contact Email.email_id`,
`Contact.email_id`, `CRM Lead.email` and `CRM Deal.email`; and `crm_lead.py:146` calls
`validate_email_address(self.email, throw=True)` explicitly on top.

**Actual:** 200; any string is stored. The port's `CRMLead.validate_email` ports only the
owner-equality check and drops the format check that precedes it.

**Where:** `frappe_core/serializers.py` (a validator for fields declared Email in
`doctype_meta.json`) and `CRMLead.validate_email`.

**Fixed 14 Sep 2026.** `BaseDocument.EMAIL_FIELDS` names a model's Email-typed
columns (`Contact.email_id`, `Contact Email.email_id`, `CRM Lead.email`,
`CRM Deal.email`), and every save validates them with a port of
`frappe.utils.validate_email_address`: comma-separated lists, `Name <addr>` forms, the
HTML-escaped value in `<value> is not a valid Email Address`, `InvalidEmailAddressError`
417. A deal's own column is derived from its contact rows on every save, upstream too,
so the check bites on the contact's row. Block 05 / 2.13 is green.

## 12. A missing contact is a validation error, not a permission error

**Block:** `05_contacts_organizations.http` 3.12

**Expected:** 403 `PermissionError`, `Not permitted`. Upstream asks
`frappe.has_permission("Contact", "write", name)`, which is False for a name that does
not exist, and throws `PermissionError`.

**Actual:** 417 `ValidationError` with the same words. `_require_contact` in
`crm_app/api/contact.py` uses `throw()` for the missing case and `PermissionError` only
for the denied case. Low, but the frontend branches on `PermissionError`.

**Same shape elsewhere:** `crm.api.comment.add_comment` on a document that does not
exist (`08 / 2.3`) answers 417 `ValidationError`; upstream's `frappe.get_doc` raises
`DoesNotExistError`, 404. Both are `throw()` used where a typed exception belongs.

**Fixed 14 Sep 2026.** `_require_contact` raises `PermissionError` for a missing
contact as for a denied one, and `add_comment` raises `DoesNotExistError` for a
doctype or document that does not exist. Blocks 05 / 3.12 and 08 / 2.3 are green.

## 13. rename_doc is insert-then-delete

**Blocks:** `05_contacts_organizations.http` 5.1/5.2 (organization referenced by a deal),
5.3–5.5 (contact with email rows and a deal link)

**Expected:** `frappe/model/rename_doc.py` renames in place: it updates the primary key
and every Link, Dynamic Link and child `parent` column that pointed at the old name
(`update_link_field_values`, `update_child_docs`), so the deal now points at
`ZZ Renamed Org`, and the renamed contact keeps its two email rows, two phone rows and
its place on the deal.

**Actual:** `frappe.client.rename_doc` in `crm_app/api/client.py` inserts a copy under
the new name and **deletes the original**. Two consequences:

* a document any row links to with `PROTECT` cannot be renamed at all — 409 with
  Django's "protected foreign keys" text (finding 3's rendering);
* a document whose links are `CASCADE` renames "successfully" and **loses them**: the
  contact came back with zero email rows and zero phone rows, and the deal's contacts
  table was emptied. Silent data loss on an action the UI offers.

**Where:** `client_rename_doc` — rename in place. Django cannot change a primary key with
`save()`, so the faithful port is: insert the copy, repoint every inbound FK and
polymorphic `parent`/`reference_name` column to the new name (the registry knows every
model, and `children.discover_child_tables` knows the child rows), then delete the
original. Until then the endpoint should refuse rather than cascade.

**Fixed 14 Sep 2026.** `frappe_core/rename.py:rename_document` inserts the copy with
`bulk_create` (no save hook, naming or version capture for what is not a new
document), repoints every foreign key in the schema that targets the model, including
the hidden ones on many-to-many through tables, the `parent` of multi-parent child rows,
and every Dynamic Link pair the models declare (`reference_doctype/reference_name`,
`reference_type/reference_name`, `attached_to_*`, `ref_doctype/docname`,
`link_doctype/link_name`), then deletes the original, all in one transaction. The
endpoint's refusals are `validate_rename`'s, with its wording and its 417: a missing
document, the same name, a taken name, no write permission. Blocks 05 / 5.1 to 5.6 are
green. Not ported: upstream's `allow_rename` flag, so a doctype upstream would refuse
to rename can be renamed here; nothing in the frontend reaches that.

## 14. The territory tree is unmaintained

**Blocks:** `05_contacts_organizations.http` 6.2 (`lft`/`rgt` null), 6.3
(`descendants of` → 400 "No tree resolver registered for 'CRM Territory'")

**Expected:** `CRM Territory` is `is_tree` upstream, so `frappe/utils/nestedset.py`
maintains `lft`/`rgt` on every write and `descendants of` finds the organization two
levels down.

**Actual:** neither. `crm_app/models/taxonomy.py:CRMTerritory` says phase 2 owns the tree
behaviour; phase 2 built `crm_app/permissions/tree.py` for the sales hierarchy only and
never registered a resolver, so `_TREE_RESOLVERS` is empty at runtime. Latent: the
frontend never sends a tree operator and nothing reads `lft`/`rgt`. Recorded so the
phase-2 spec's "give territory the same treatment" is known to be unfulfilled.

**Fixed 14 Sep 2026.** `crm_app/permissions/tree.py` rebuilds the territory's
`lft`/`rgt` on every write, under its own advisory lock, with the sales hierarchy's
walk generalised to any parent column (siblings by name, as `nestedset.py:rebuild_node`
does), and registers `territory_subtree_q` as the `CRM Territory` resolver:
`descendants of` excludes the node unless `(inclusive)`, `ancestors of` walks up, and a
node that does not exist matches nothing. Blocks 05 / 6.2 and 6.3 are green.

## 15. A task's assigned_to is not an assignment

**Blocks:** `06_tasks_notes_calls.http` 2.2 (create with `assigned_to`), 2.4 (change it)

**Expected:** `crm_task.py:30-56`: `after_insert` calls `assign_to.add` for
`assigned_to`, so the task gets a ToDo and `_assign == ["ada@example.com"]`; `validate`
on a later save unassigns the previous user and assigns the new one, so `_assign`
becomes exactly `["grace@example.com"]`. The task board's assignee chip reads
`_assign`, and the assignee's own task list is built from ToDo.

**Actual:** `_assign` stays `[]` throughout. `crm_app/models/core_sales.py:CRMTask`
has fields only; no lifecycle was ported. The `OwnerAssignmentMixin` used by Lead and
Deal does exactly this job and would fit with `owner_field = "assigned_to"` plus the
unassign-previous step.

**Fixed 14 Sep 2026.** `CRMTask.save` ports `crm_task.py:30-56`: a create assigns the
task to `assigned_to` (a ToDo, so `_assign` names the user and the assignee's task
list sees it); a later save whose `assigned_to` changed and is set cancels the previous
user's ToDo and assigns the new one; clearing the field leaves the assignment, as
upstream's early return does. Blocks 06 / 2.2 and 2.4 are green.

## 16. Task, Note and Call Log have no list definitions

**Blocks:** `06_tasks_notes_calls.http` 2.8 (task columns), 3.4 (note rows), 4.9
(call-log columns and parsed rows), 4.7 (call-log `links`)

**Expected:** each controller declares what its screen needs:

* `crm_task.py:57` — columns title, status, priority, due date, assigned to, modified;
* `fcrm_note.py:24` — no columns but rows `title, content, reference_doctype,
  reference_docname, owner, modified`, which the Notes page renders as cards;
* `crm_call_log.py:57` — columns starting with caller, and `parse_list_data` adds
  `_duration`, `_caller`, `_receiver` and `activity_type` to every row, which
  `CallLogs.vue` and `CallArea.vue` read directly;
* the call log's `links` child table (Table of Dynamic Link) comes back on the document.

**Actual:** `get_data` for all three falls back to the registry default, two columns
(`name`, `modified`) and generic rows. The Tasks and Call Logs screens would render
with only those two columns, and the Notes page cards would have no title or content to
show. The port writes Dynamic Link rows for a call log but the model declares no
`POLYMORPHIC_CHILD_TABLES` entry for `links`, so the document never shows them.

**Where:** `crm_app/models/core_sales.py` (`CRMTask.default_list_data`,
`FCRMNote.default_list_data`), `crm_app/models/telephony.py` (`CRMCallLog.default_list_data`,
`parse_list_data`, and `POLYMORPHIC_CHILD_TABLES = {"links": "Dynamic Link"}`). Lead,
Deal, Organization and Contact all have theirs; these three were missed.

**Fixed 14 Sep 2026.** `CRMTask.default_list_data`, `FCRMNote.default_list_data` and
`CRMCallLog.default_list_data` are upstream's, verbatim; `CRMCallLog.parse_list_data`
runs every list row through a port of `parse_call_log`, with `seconds_to_duration`
from `crm/utils` (`1h 1m 1s`, zero parts left out) and the caller and receiver as
label-plus-image pairs, "Unknown" for a number no contact holds; and
`POLYMORPHIC_CHILD_TABLES = {"links": "Dynamic Link"}` puts the link rows the
integrations write onto the document. The Notes page's empty column list still falls
back to Name and Last Modified in `get_data`, a documented guard the card grid never
reads. Blocks 06 / 2.8, 3.4, 4.7 and 4.9 are green.

## 17. An unknown doctype on a method endpoint answers 500

**Blocks:** `07_views_and_metadata.http` 1.6 (`get_fields`), 5.8 (`get_data`); the same
applies to `sort_options`, `get_filterable_fields`, `get_group_by_fields`,
`get_quick_filters`, `update_quick_filters` and every other endpoint that calls
`registry.get_entry(doctype)` first.

**Expected:** 404 `DoesNotExistError`. Upstream's `frappe.get_meta("No Such Doctype")`
raises `DoesNotExistError`, which the request handler renders as 404.

**Actual:** 500. `frappe_core/registry.py:DocTypeNotFound` subclasses `KeyError`, not
`FrappeError`, so `frappe_exception_handler` returns `None`. The resource routes are
unaffected only because `views._resolve_routable_entry` catches it and raises the port's
`DoesNotExistError` itself; the method endpoints call the registry directly.

**Where:** make `DocTypeNotFound` a subclass of `frappe_core.exceptions.DoesNotExistError`
(one line, and `_resolve_routable_entry`'s translation becomes redundant), or map it in
the handler alongside `Http404`.

**Fixed 13 Sep 2026.** `DocTypeNotFound` subclasses `DoesNotExistError` as well as
`KeyError`, reports `exc_type: DoesNotExistError`, and carries `DocType X not found`
as its message. Blocks 07 / 1.6 and 5.8 are green; the resource view's own
translation is left in place.

## 18. Assigning a document to someone never notifies them

**Blocks:** `08_activities_comments_notifications.http` 3.11, 3.12

**Expected:** `crm/api/todo.py:after_insert` (registered in `hooks.py:doc_events` for
`ToDo`) calls `notify_assigned_user`, which creates a `CRM Notification` of type
`Assignment` for the assignee with the text *"{owner} assigned a {doctype} {name} to
you"*, and `on_update` sends *"Your assignment on ... has been removed by ..."* when the
ToDo is cancelled. The bell menu is how a rep learns a lead was handed to them.

**Actual:** no row. `frappe_core/assignment.py` connects ToDo writes to the `_assign`
cache only; `crm_app/async_signals.py` listens to Comment, Communication and
Invitation. Mentions do notify (`notify_mentions` is ported), assignments do not. The
`crm/api/todo.py` module was never ported — `PHASE_3_ENDPOINTS.md` §2 group E noted it
"has no whitelisted endpoints, only doc_events hooks — those belong in phase 1", and
phase 1 did not pick them up.

**Where:** a `post_save` handler on ToDo in `crm_app/async_signals.py`, porting
`notify_assigned_user` and `get_notification_text`; `crm_app/api/notifications.py:get_hash`
already knows how to route an Assignment notification.

**Fixed 15 Sep 2026.** `crm_app/async_signals.py` ports `crm/api/todo.py` as a ToDo
`post_save` hook: on insert, the assignee of a lead or deal becomes its owner (the
"mirror assign_to" rule) and a lead, deal or task assignment raises a `CRM
Notification` of type Assignment with upstream's message and HTML text; when the ToDo
is cancelled, "Your assignment on … has been removed by …" and the owner is cleared.
Never for yourself, never twice; a task's notification lands on the task's own lead or
deal. Blocks 08 / 3.11 and 3.12 are green.

## 19. Deleting a document leaves its dependants behind

**Block:** `08_activities_comments_notifications.http` 7.2 — delete a lead, then list
comments by its name: 5 rows remain.

**Expected:** 0. `frappe/model/delete_doc.py:delete_doc` calls `delete_dynamic_links`
(ToDo, DocShare, Version, Comment rows keyed to the document) and
`delete_communications`, so nothing is left pointing at a name that no longer exists.

**Actual:** every Comment, Communication, ToDo, Version and CRM Notification row that
referenced the lead is still there. `frappe_core/children.py:delete_polymorphic_children`
covers only the polymorphic *child tables* (products, status log, rolling responses);
the reference-by-name doctypes have no cascade at all. `docs/internal/PROGRESS.md`
recorded this as a phase-1 concern ("Frappe also has an on_trash cascade this port
doesn't") and it was never closed.

**Consequences:** orphan rows accumulate forever; ToDos for a deleted lead keep
granting nothing but still count as assignments for the user; and when a naming series
is ever reset, a new document inherits the old one's comments and timeline.

**Where:** a `pre_delete` handler on every routable doctype (`frappe_core/children.py`
already hooks `post_delete`) that deletes Comment, Communication, ToDo, Version and
CRM Notification rows whose `reference_*` columns name the document.

**Fixed 15 Sep 2026.** `children.delete_references` runs from the `post_delete` hook
every registered model already has, doing what `delete_doc.py:delete_dynamic_links`
and the `clear_references` after it do for the doctypes the port has: ToDo, Version,
Comment and File rows keyed to the document are deleted, a Communication's reference is
cleared and the email kept. CRM Notification rows are left alone, as upstream leaves
them (no hook names them). The bulk delete cleans a whole batch in one query per
reference doctype and the per-row hook stands down, keeping the C9 shape. Block
08 / 7.2 is green.

## 20. Six dashboard charts were never built

**Blocks:** `10_dashboard.http` 2.15 (`sales_trend`), 2.16 (`funnel_conversion`)

**Expected:** a chart payload. `crm/api/dashboard.py` defines nineteen builders; the
dashboard editor in the frontend offers all of them.

**Actual:** `{"error": "Invalid chart name"}`, the same answer as for a name that never
existed. `crm_app/api/dashboard.py:UNPORTED_CHARTS` names the six deliberately:
`sales_trend`, `forecasted_revenue`, `funnel_conversion`,
`average_time_to_close_a_lead`, `average_time_to_close_a_deal`,
`deal_status_change_counts`. They are the time-series and duration-arithmetic charts,
and `docs/internal/PROGRESS_PHASE_3.md` records them as not done.

**Status:** known and recorded, not a surprise. Listed here so the suite has a line to
point at and so the gap is closed in one place when it is closed. The default layout
uses only ported charts, so the dashboard as shipped renders; a user who adds one of
the six from the editor gets a broken tile.

**Fixed 15 Sep 2026.** All six are built in `crm_app/api/dashboard.py` and registered
in `CHART_BUILDERS`: the two average-time-to-close numbers (won deals by `closed_date`,
the clock starting at the lead's creation for one and the deal's for the other, whole
days as `TIMESTAMPDIFF` counts them, the delta in days), `sales_trend` (leads, deals
and wins per day), `forecasted_revenue` (by month of expected closure over the twelve
months before today, a lost deal at full expected value, any other weighted by
probability, actual from won deals, empty strings where there is nothing),
`funnel_conversion` (the leads count, then each status reached from the status-change
log of deals not currently Lost, in position order) and the bare
`deal_status_change_counts` list the funnel is built on. They aggregate in Python over
the filtered rows rather than in SQL, and use the port's corrected previous-period
window. Blocks 10 / 2.15 and 2.16 are green.

## 21. An unparseable dashboard date answers 500

**Block:** `10_dashboard.http` 2.18 — `from_date: "yesterday"`

**Expected:** 417 `ValidationError`, *"yesterday is not a valid date string."*
(`frappe/utils/data.py:getdate`, version-15, catches `ParserError` and throws).

**Actual:** 500 `ValueError` from `crm_app/api/dashboard.py:_parse_date`, which nothing
catches. Low: the frontend's date picker only ever sends ISO dates, so it is reachable
by hand rather than by a click. Same family as findings 1, 2 and 17 — a plain Python
exception where a `FrappeError` was meant.

**Fixed 13 Sep 2026.** `_parse_date` uses dateutil's parser as `getdate` does, so the
formats upstream accepts are accepted, and an unparseable string raises
`ValidationError` with upstream's sentence verbatim, `frappe.bold` included:
`<strong>yesterday</strong> is not a valid date string.`, titled "Invalid Date". Block
10 / 2.18 is green.

## 22. A private, unattached File is readable by everyone

**Block:** `13_bulk_and_misc.http` 4.8 — ada uploads a private file attached to nothing;
grace reads its row.

**Expected:** 403. `frappe/core/doctype/file/file.py:has_permission` (version-15) grants
a public file to everyone, an owner their own upload, and an attached file per its
document; a private file that is none of those falls through to `return False`.

**Actual:** 200. `crm_app/permissions/attachments.py:_has_permission` treats a row
that references nothing as unhidden — the carve-out `specs/KNOWN_ISSUES.md` §3 recorded
for comments and communications ("an orphan hides nothing, and the product creates
them") — and `file_has_permission` reaches it after the public and own-upload
short-circuits. For a *private* file that is the opposite of upstream's fallback.

Metadata only today, since nothing serves file bytes; it becomes a real disclosure the
day a download route lands, which `KNOWN_ISSUES.md` already warns about.

**Where:** `file_has_permission` — after the two short-circuits, deny when
`is_private` and the file is attached to nothing, before deferring to `_has_permission`.

**Fixed 15 Sep 2026.** `file_has_permission` answers False for a file attached to
nothing once the public and own-upload short-circuits have passed (creating one is
still the upload itself), and `file_query_conditions` lists a file only when it is
public, yours, or attached to a document you may see. Block 13 / 4.8 is green.

## 23. Deleting a contact validates the rows it is removing

**Block:** `05_contacts_organizations.http` 8.2, run by hand on a contact left behind by
earlier clicking, whose three phone rows carried the same number twice, both flagged
primary phone. No block reproduces it from a clean database: a save refuses two
primaries (finding 10), so the rows had to be written some other way first.

**Expected:** 200. `frappe/model/delete_doc.py:207-227` deletes a document's child rows
with a plain query; nothing validates on the way out, so a document whose rows would
fail a save is still deletable.

**Actual:** 417 `ValidationError` "Only one <strong>Phone</strong> can be set as
primary." The cascade removes the rows one at a time, each removal fires
`_resync_contact` (the signal that keeps `email_id` / `mobile_no` / `phone` following
the rows), and that runs `sync_primary_values` over the rows still present - the
save-time rules, on a document that is going away. Any contact that reaches an
inconsistent state is then stuck: it cannot be saved and cannot be deleted.

**Where:** `frappe_platform/models.py`, `_resync_contact` - skip while the parent
contact itself is being deleted.

**Fixed 15 Sep 2026.** A counter brackets every Contact delete between its `pre_delete`
and `post_delete` signals (a model delete and a queryset delete alike), and the row
signal returns early while it is set. A row deleted on its own still re-derives the
contact's columns.

## 24. A name that cannot be a number answers 500 on a numbered doctype

**Block:** `06_tasks_notes_calls.http` 0.3 to 0.5, clicked by hand after 0.2 found no
leftover task. REST Client then sends the unresolved placeholder,
`{{old_tasks.response.body.$.data[0].name}}`, as the task's name. The runner never
showed it because it resolves an absent path differently.

**Expected:** 404 `DoesNotExistError`. `frappe.get_doc("CRM Task", "<anything>")`
queries the table for that name and finds nothing; the name's shape is not the
document's concern.

**Actual:** 500. CRM Task, CRM View Settings and CRM Product Sync Issue are the three
autoincrement doctypes, so their primary key is an integer column, and Django raises
`ValueError: Field 'name' expected a number but got '...'` from `filter(pk=name)` before
any query runs. Nothing mapped it. Every path that looks a document up by name was
open to it: the resource routes, `frappe.client.*`, the linked-document and assignment
endpoints, the view-settings endpoints.

**Where:** one lookup helper, `frappe_core.query.by_name`, used wherever a name from the
request is turned into a row.

**Fixed 16 Sep 2026.** `by_name(model, name)` casts the name with the primary key's own
`to_python` and answers an empty queryset when the cast fails, so every caller's
existing "None means not found" branch gives the 404. The resource view, the two
`_require_readable` helpers, `frappe.client.*`, `remove_assignments`,
`delete_attachment`, the deal-contact buttons and the view-settings endpoints all go
through it.

## 25. A duplicate name answers with Django's internal wording

**Block:** `12_settings_singletons.http` 2.2, run a second time by hand while its row
still existed: CRM Twilio Settings is a singleton with one fixed name (`Settings` at
the time; its doctype's own name since finding 37), so the second create collides. Reproduced from a clean run by `02_resource_grammar.http`
10.10b, which posts an organization under a name 1.1 already created.

**Expected:** 409 `DuplicateEntryError` with the message "CRM Organization
<strong>ZZ Grammar Alpha</strong> already exists", titled "Duplicate Name".
`frappe/model/base_document.py:598-606` catches the database's unique-key error on
insert, `msgprint`s exactly that, and raises `DuplicateEntryError`.

**Actual:** 409 `DuplicateEntryError`, the right class and status, but the message is
psycopg's: *"duplicate key value violates unique constraint
"crm_app_crmtwiliosettings_pkey" DETAIL: Key (name)=(Settings) already exists."* The
handler maps every `IntegrityError` to 409 with `str(exc)` as the sentence, which is
the same shape findings 3 and 7 had for their own cases and were fixed for; a genuine
duplicate was the one left.

**Where:** `frappe_core/serializers.py:create` - the one place every create goes
through (`/api/resource/`, `frappe.client.insert`, the deal and lead endpoints).

**Fixed 20 Sep 2026.** `create` catches the `IntegrityError` outside its savepoint,
works out the name the insert attempted (the naming field's value for `field:`
doctypes, the client's `name` for `prompt` ones, `Settings` for a singleton), and when
a row of that name exists raises `DuplicateEntryError` with upstream's sentence and
title. Any other integrity error keeps its raw text, as before, because it is not a
duplicate name.

## 26. The frontend's boot values have no source: a blank page under `yarn dev`

**Block:** none in the http suite. `yarn dev` in `frontend/`, then
`http://localhost:8080/crm` in a browser: the page stays blank. The console shows a 404
for `POST /api/method/crm.www.crm.get_context_for_dev` and an uncaught promise
rejection. Found 23 Sep 2026, the first time the frontend was started against the port.

**What the boot values are.** Before the CRM page draws its first screen it needs a
few facts about the site that live on the server: how to write dates, times, numbers
and money (`sysdefaults`: `date_format`, `time_format`, `number_format`,
`float_precision`, `currency_precision`, `rounding_method`, `currency`), the system
and user timezone, the translation table, and three flags that decide which banners
and menu items to show (`is_demo_site`, `demo_data_created`, `is_fc_site`). Upstream
calls this set the **boot** (`crm/www/crm.py:get_boot`). It is sent once, ahead of
everything else, so the first list renders with the right formats instead of drawing
wrong and redrawing after a second request. The frontend reads it from `window`:
`window.sysdefaults.date_format` in `utils/index.js:82` has no guard, so a missing
`sysdefaults` is a TypeError on every date cell, not a fallback.

**Expected:** upstream delivers the boot in two ways, depending on who served the page.

- *Production.* The browser asks Frappe for `/crm`. Frappe runs
  `crm/www/crm.py:get_context` (CRM-role check, then `get_boot()`) and renders
  `crm/www/crm.html`, the file `yarn build` writes from `frontend/index.html` (upstream
  git-ignores it). The frappe-ui vite plugin (`jinjaBootData`) has added a `<script>`
  to that file that writes `window["sysdefaults"] = ...` for every boot key, so the
  values arrive in the same response as the page and `main.js` mounts at once.
- *Development.* Vite serves `frontend/index.html` itself, so no template runs and
  that script is never written. `main.js:65-75` closes the gap: it posts to
  `crm.www.crm.get_context_for_dev`, copies every key of the reply onto `window`, and
  only then calls `app.mount`. Upstream declares that method `allow_guest=True` (the
  first visit has no session yet), POST-only, and refuses with "This method is only
  meant for developer mode" unless `developer_mode` is set, so a live site never
  answers it.

**Actual:** the port serves neither. The dotted path is not registered, so the dev call
answers 404 `DoesNotExistError`, the `.then` never runs and the app never mounts.
`config/urls.py` serves no `/crm` page at all, so production would mount the app with
every boot value undefined and crash on the first date.

The guard test `test_every_frontend_dotted_path_resolves` did not catch it because
this call is written with the prefix (`url: '/api/method/crm.www.crm.get_context_for_dev'`)
and `_PATH_RE` only matches bare dotted paths.

**Where:** `crm_app/api/boot.py`, one endpoint, and the fetch-then-mount step in
`frontend/src/main.js`.

**Fixed 23 Sep 2026**, the second of the two designs weighed that day: the frontend asks
for the boot values over JSON in every mode, and no HTML is ever rendered for them.
`crm.www.crm.get_context_for_dev` is registered under upstream's name, guest-allowed and
POST only, without upstream's developer-mode gate, because production calls it too and
nothing in the answer is secret. It returns the keys this frontend reads and nothing
else: `sysdefaults` from a new `FRAPPE_SYSDEFAULTS` dict in `config/settings/base.py`
(Frappe's own fallbacks for an unset default, each overridable from `.env`), since the
port has no System Settings doctype (upstream's `sysdefaults` is System Settings
republished through `frappe.db.set_default`, `system_settings.py:213-218`); `timezone`
from `TIME_ZONE` and the caller's `time_zone` column; empty `translated_messages`,
`translated_doctypes` and `state_options`; the three site flags false. `csrf_token`,
`site_name`, `socketio_port`, `frappe_version`, `default_route`, `setup_complete` and
`read_only_mode` are read by nothing in `frontend/src` and are left out. `main.js` now
makes the call in production as well as dev, and mounts even when it fails so that an
error is visible instead of a blank page; `frontend/JWT_PATCH.md` records it as the
third frontend deviation. `_PATH_RE` accepts the `/api/method/` prefix. Serving the built
`index.html` for `/crm/*` in production is a deployment item, not part of this finding.

## 27. frappe-ui's socket.io chain reaches a CommonJS package raw: still blank

**Block:** none in the http suite. `yarn dev`, then `http://localhost:8080/crm`, after
finding 26 was fixed: still blank, and this time the console error comes before
`main.js` runs at all:

```
Uncaught SyntaxError: The requested module '/node_modules/debug/src/browser.js'
does not provide an export named 'default' (at index.js:4:8)
```

A module error anywhere in the import graph aborts the whole bundle, so nothing mounts.

**Expected:** Vite pre-bundles dependencies with esbuild, which turns CommonJS packages
into ES modules the browser can import. Upstream's `vite.config.js` relies on that for
everything under `node_modules`, frappe-ui included.

**Actual:** two facts of this environment combine. First, frappe-ui `1.0.0-beta.29`
ships as source and its `TextEditor/commands.js` imports `~icons/lucide/*`, virtual
modules that only frappe-ui's own Vite plugin resolves; esbuild's pre-bundler cannot,
and fails with 31 unresolved imports. So the working copy had `optimizeDeps.exclude:
['frappe-ui']` added by hand, which is right: the package must be served raw. Second,
Vite's resolver never pre-bundles a bare import made from inside `node_modules`
(`skipOptimization` in `vite/dist/node/chunks`), so every package frappe-ui imports is
served raw as well. Its `utils/socketio.ts` imports `socket.io-client`, whose manager
imports `socket.io-parser`, whose export map carries a `development` condition
(`socket.io-parser/package.json:22`) that Vite's dev server honours, picking the
`esm-debug` build, whose line 4 is `import debugModule from "debug"`. `debug` is
CommonJS, so served raw it has no default export. The chain was proven by walking the
dev module graph through Vite's own transform pipeline: the one importer of
`/node_modules/debug/src/browser.js` was `socket.io-parser/build/esm-debug/index.js`.

The port's own `src/socket.js` no longer uses socket.io at all (phase 6), but
frappe-ui's barrel still imports it, and `main.js` imports the barrel.

**Where:** `frontend/vite.config.js`, `optimizeDeps.include`.

**Fixed 23 Sep 2026.** `socket.io-client` is listed in `optimizeDeps.include`. Vite
resolves an import of a listed package to its pre-bundled copy even when the importer
is inside `node_modules`, so frappe-ui's import now lands on an esbuild bundle that
carries socket.io-parser and a converted `debug` inside it. The same walk of the module
graph with that one line added finds no raw importer of `debug`. This is exactly the
rule Vite's documentation gives for excluded packages with CommonJS dependencies, and
the mechanism frappe-ui's own plugin already uses for `interactjs` and
`highlight.js/lib/core`. Both the `exclude` line and this `include` entry now carry a
comment saying why, so neither gets tidied away.

## 28. App.vue has no branch for the auth pages: a logged-out visitor sees nothing

**Block:** none in the http suite. Any visit to `/crm` without a token, once findings 26
and 27 were out of the way. The router guard (`router.js:264-272`) sends the visitor to
`Login`; the app mounts; the screen stays empty, with no console error.

**Expected:** the phase 8 login page. `PHASE_8_AUTH_AND_DESK.md` moved the four auth
screens inside the SPA (`pages/auth/Login.vue`, `ForgotPassword.vue`,
`UpdatePassword.vue`, `AcceptInvitation.vue`), each behind a route flagged
`meta.isPublic`, because upstream's redirect to the desk's `/login` page pointed at a URL
nothing in this port serves.

**Actual:** `App.vue`'s template has three branches: `NotPermitted` for that route, a
bare `router-view` for Onboarding, and the app `Layout` around a `router-view` when
`session.isLoggedIn`. A public route matches none of them, so the `router-view` that
would show `Login.vue` is never rendered. Upstream's template is the same three branches
and never needed a fourth: a logged-out visitor leaves the SPA before it mounts. Phase 8
added the pages and the guard, and its review ran the backend tests and an end-to-end
walk over HTTP, neither of which renders a template, so the missing branch was never
seen (the same blind spot `stores/session.js:acceptTokens` records).

**Where:** `frontend/src/App.vue`, the template.

**Fixed 23 Sep 2026.** A fourth branch, `<router-view v-else-if="$route.meta?.isPublic" />`,
placed before the `Layout` branch so the auth pages render outside the app shell, which
assumes a session. Ordering matters for the one public page a signed-in user may still
reach: `Accept Invitation` renders on its own rather than inside the sidebar.

## 29. A cold `yarn dev` load fetches 3,234 modules and takes minutes

**Block:** none in the http suite. Start `yarn dev`, open `/crm`, and wait. Measured by
walking the module graph through Vite's own transform pipeline and by loading the page
in headless Chrome over the DevTools protocol: on this machine a cold server served
about 12 modules a second, and the page needed 3,234 of them before `main.js` could
run. The blank screen in findings 26 to 28 was, part of the time, simply this.

**Expected:** Vite's dev server sends the app's own files raw and every dependency as
one pre-bundled file each, so a page needs a few hundred requests. Upstream's config
relies on that.

**Actual:** three things stack. frappe-ui cannot be pre-bundled (finding 27), so its
930 source files are served raw. Its `barrelImports` plugin, which rewrites
`import { X } from 'frappe-ui'` to a deep import so that one component does not drag
in the whole library, skips installed copies on purpose (`linkedOnly`, its default:
"an installed package is served as one optimized chunk", which is exactly what does not
happen here), so the barrel and everything behind it load: TipTap, CodeMirror, echarts.
And every package frappe-ui imports is served raw too, because Vite never pre-bundles a
bare import made from inside `node_modules`: reka-ui was 564 files, echarts and zrender
556, at about 40 ms each. The per-plugin split of a full walk put nine tenths of the
time in Vite's own TypeScript transpile and Vue compile; the frappe-ui plugins cost
nothing measurable.

**Where:** `frontend/vite.config.js`: the frappeui plugin's `barrelImports` option and
`optimizeDeps.include`.

**Fixed 23 Sep 2026.** `barrelImports: { linkedOnly: false }` turns the rewrite on,
which the plugin's own comment recommends for a package that cannot be pre-bundled.
And every package frappe-ui's source imports, by the exact specifier it uses
(`grep "from '" node_modules/frappe-ui/src`, 55 entries: reka-ui, echarts, the
tiptap and prosemirror family, dayjs/esm and its plugins, the codemirror and
floating-ui pairs, and a few small ones), is listed in `optimizeDeps.include`, so each
becomes one file. The graph is now the app's 364 source files, frappe-ui's 930, and
about 190 pre-bundled dependency chunks. A cold load still transpiles some 1,300
files and takes a minute or two here; a warm reload is quick. Two habits keep it that
way: start `yarn dev` once and leave it running, since every restart is cold, and
never run a second Vite server against the same tree at the same time.

## 30. frappe-ui's `call()` and upload helpers send no bearer header

**Block:** none in the http suite. Seen in the logged-in probe: the router guard's very
first request, `frappe.utils.telemetry.pulse.client.boot_config`, answered 401. It is
made with frappe-ui's `call()`.

**Expected:** every request the frontend makes carries the session. Upstream gets that
for free: the `sid` cookie rides on every request from the same origin, whoever builds
it.

**Actual:** the phase 0 JWT patch is `setConfig('resourceFetcher', jwtRequest)`, which
frappe-ui consults for `createResource`, `createListResource` and
`createDocumentResource`, the 225 call sites `JWT_PATCH.md` counts. frappe-ui's `call()`
(`utils/call.ts`) builds its own `fetch` and reads no config at all, and its two upload
helpers (`useFileUpload.ts`, `fileUploadHandler.ts`) build their own `XMLHttpRequest`.
Thirty-two files under `frontend/src` import `call` directly, the router guard among
them, and every attachment upload goes through the XHR path. All of those went out
with no `Authorization` header and answered 401 `AuthenticationError`. Nothing caught
it earlier because no phase ran the frontend in a browser.

**Where:** `frontend/src/auth/interceptor.js`, installed from `main.js`.

**Fixed 23 Sep 2026.** Rather than touch 32 components, the header is attached at the
two browser primitives: `window.fetch` and `XMLHttpRequest.prototype.open/send`, for
same-origin `/api/` URLs only, only when the caller has not set one (`jwtRequest` sets
its own), and never for the login and refresh endpoints, where a stale access token in
the header would be authenticated before the refresh ran. Refresh-on-401 stays in
`jwtRequest`: a bare `call()` that meets an expired token fails, as it did upstream
with an expired session. `JWT_PATCH.md` records it as the second half of the first
deviation.

## 31. Upstream's socket.io client still starts, against a port nothing serves

**Block:** none in the http suite. Seen in the logged-in probe: three
`net::ERR_CONNECTION_REFUSED` for `http://localhost:9000/socket.io/...` per minute.

**Expected:** phase 6 replaced socket.io with a raw WebSocket client (`src/socket.js`)
and `JWT_PATCH.md` says no component changed. The port has no socket.io server.

**Actual:** `app.use(FrappeUI)` in `main.js` takes the plugin's defaults, and
`socketio: true` is one of them (`frappe-ui/src/utils/plugin.ts`): the plugin calls its
own `initSocket()`, which dials `localhost:9000` and, being socket.io, retries with
backoff forever. `main.js` overwrites `$socket` with the port's client after the boot
call, so nothing reads the dead one, but it keeps knocking.

**Where:** `frontend/src/main.js`, the `app.use(FrappeUI, ...)` line.

**Fixed 23 Sep 2026.** `app.use(FrappeUI, { socketio: false })`. `$socket` is set once,
in `mount()`, to the port's client.

## 32. The login form receives the token pair and stores nothing

**Block:** none in the http suite. The first sign-in through the browser, 24 Sep 2026:
credentials accepted, `POST /api/method/login` answers 200 with `access` and `refresh`
under `message`, and the page stays on Sign in. Same for Administrator and for a user
created from the Django shell.

**Expected:** the tokens are stored, `isLoggedIn` flips, and the router takes the user
to the default view.

**Actual:** `stores/session.js`'s `login` resource passes the response to
`acceptTokens`, which destructures `{access, refresh}`. But frappe-ui's request layer
special-cases the login URL: `frappeRequest.ts` returns the **whole body** when
`url === '/api/method/login'`, because upstream's login answer keeps `home_page` and
`full_name` at the top level rather than under `message`. So the resource received
`{message: {access, refresh, ...}}`, read `access` off the wrapper, got `undefined`,
and stored nothing. `router.replace('/')` then ran with `isLoggedIn` still false and
the guard bounced back to Login. The other two pages that receive tokens,
`UpdatePassword.vue` and `AcceptInvitation.vue`, call ordinary endpoints, which the
same layer unwraps to `message`, so they were never affected, and the phase 8 review
walked the login over HTTP, where the body shape is exactly what was documented.

**Where:** `frontend/src/stores/session.js`, the `login` resource's `onSuccess`.

**Fixed 24 Sep 2026.** `acceptTokens(data?.message ?? data)`: the pair is read from
under `message` when the wrapper is present, and unchanged input still works should
frappe-ui ever drop the special case.

## 33. "Access Denied" for everyone right after signing in

**Block:** none in the http suite. Sign in as Administrator, or as any user with a CRM
role, once finding 32 stores the tokens: the next screen is Not Permitted, "You do not
have enough permissions to access Frappe CRM".

**Expected:** the default view. `isCrmUser()` looks the session user up in the
`crmUsers` list that `crm.api.session.get_users` returns, and Administrator is in it.

**Actual:** the users store is created the first time the router guard runs for a
non-public route, and that happens on the very first visit to `/crm`, before the
redirect to Login, while nobody is signed in. The store's `users` resource fetches on
creation (`auto: true`), answers 401, and frappe-ui leaves `fetched` false, `error` set
and `promise` pointing at that rejected fetch. After login the guard's "load users
first" step sees `fetched` false and awaits `users.promise`, which is the same
rejected fetch, catches the rejection, and continues with the store's empty initial
data. `isCrmUser()` finds nobody in an empty list and the guard sends everyone to Not
Permitted. Upstream never meets this: its login page lives in the desk, so signing in
is a full page load and every Pinia store is created fresh afterwards.

**Where:** `frontend/src/router.js`, the guard's users-loading step.

**Fixed 24 Sep 2026.** When the last attempt errored, the guard calls `users.reload()`
before awaiting the promise, so the list is fetched again with the token in place.
One place, and it also covers a session that expired and was renewed without leaving
the app.

**Reordered 25 Sep 2026.** The guard now decides "not logged in, go to Login" *before*
it creates the users store, so a logged-out visit to a protected URL fetches nothing at
all. Upstream's guard (`router.js:157-161, 221-222`) creates the store first and lets
its fetch fail, which costs nothing there because the page jump that follows discards
it. The re-fetch stays as the safety net for a store created early by something other
than the guard.

## 34. Sign-out keeps the previous user's stores alive

**Block:** none in the http suite. Sign in as a System Manager, sign out, sign in as a
Sales User in the same tab. The second session runs on the first user's users list,
views and caches.

**Expected:** upstream's sign-out is `window.location.href = '/login?redirect-to=/crm'`
(`stores/session.js:35`), a real page load: every Pinia store and every frappe-ui
resource cache is discarded, and the next sign-in starts from nothing.

**Actual:** phase 8 replaced that jump, whose URL nothing here serves, with
`router.replace({ name: 'Login' })`, an in-app route change. The tokens were cleared,
but the app and everything in its memory kept running. Each store believed it had
already loaded, so nothing fetched again for the new user. For two accounts with the
same role the lists are identical and nothing shows; a System Manager followed by a
Sales User leaves the Sales User looking at the wider user list.

**Where:** `frontend/src/stores/session.js`, the `logout` resource's `onSuccess`.

**Fixed 25 Sep 2026.** `window.location.assign('/crm/login')`: a real page load to the
port's own login page, which discards everything, the same effect upstream's jump had.
The `/crm` prefix is the router's base.

## 35. Sign-out never revoked the refresh token

**Block:** none in the http suite. Read from the code while reviewing finding 34: the
`logout` resource in `stores/session.js` is submitted with no arguments, so
`POST /api/method/logout` goes out with an empty body.

**Expected:** upstream's logout deletes the server-side session (`frappe/auth.py:364`,
`delete_session`); the `sid` cookie is dead from that instant and every later request
with it is a Guest. There is no window.

**Actual:** the port's logout endpoint (`frappe_core/api/auth.py:127-142`) blacklists
the refresh token *it is given*, and the blacklist app is installed, but the frontend
never gave it one. So sign-out cleared the browser's copy and revoked nothing: a
refresh token captured before sign-out kept minting access tokens for its full
lifetime, seven days by default. The access token is stateless and stays valid until it
expires regardless: five minutes by default, though the local `.env` sets 180 for hand
testing and must not ship that way.

**Where:** `frontend/src/stores/session.js`, the `logout` resource.

**Fixed 25 Sep 2026.** The resource gains a `makeParams` that reads the refresh token
from storage and sends it, so the backend blacklists it; the two call sites keep
calling `logout.submit()` unchanged. `tests/test_auth.py` pins both halves: a logout
carrying the token makes a later refresh with it answer 401, and a bare logout revokes
nothing, which is the contract the frontend now honours. The five-minute access-token
window is inherent to JWT and documented in `JWT_PATCH.md` rather than closed, since
closing it means a blacklist lookup on every request.

## 36. The login label promises "Email or username"; only the user's key is matched

**Block:** none in the http suite. Observed by hand, 25 Sep 2026: every demo user signs
in with their email, Administrator signs in only as "Administrator", and
`admin@example.com`, the address on its row, is refused.

**Expected:** what the label says. Frappe Cloud's sign-in page labels the same field
"Email" and nothing else.

**Actual:** both sides match the typed value against `User.name`, the document's
primary key, and nothing else. The port: `frappe_core/api/auth.py:75-83`, exact
spelling then case-insensitive. Upstream: `User.find_by_credentials`
(`user.py:743-749`) filters on `name`, and consults `mobile_no` or `username` only when
a System Settings switch is on, which the port does not model. Neither reads the
`email` column. It works for everyone because a User's key *is* the email: upstream's
`autoname` (`user.py:150-156`) sets `name = email.strip().lower()` for every user that
is not Administrator or Guest, whose key is their first name instead; the port does
the same in `User.save` (`frappe_platform/models.py`) and in `accept_invitation`
(`crm_app/api/auth_pages.py:418`), which creates the row with `name=address,
email=address`. So for every registered account "Email" is exactly right, and the one
account where the two differ is the built-in Administrator, which is refused by its
email on a Frappe site too. Only the phase 8 label is wrong: the port has no
`username` field, and the word invites exactly the attempt that fails.

**Where:** `frontend/src/pages/auth/Login.vue:20`, the field label.

**Decision pending.** Either the label becomes "Email", matching Frappe Cloud, with
the Administrator convention left as upstream has it; or the login lookup also
accepts the `email` column, a deliberate divergence that makes `admin@example.com`
work. The first is a one-word change and true to upstream; the second is friendlier
for the one built-in account.

## 37. Singletons were named `Settings`; upstream names them after their doctype

**Block:** none in the http suite, which was written against the port and asked for
`/api/resource/FCRM Settings/Settings`. Seen the first time the app ran signed in,
28 Sep 2026: `GET /api/method/frappe.client.get?doctype=FCRM+Settings&name=FCRM+Settings`
answered 404 `DoesNotExistError`.

**Expected:** 200. A single-row doctype's document is named after the doctype:
`frappe.get_single("FCRM Settings")` loads the document named `FCRM Settings`, and the
frontend hardcodes that name in five places (`stores/settings.js`, `router.js`,
`PersonaForm.vue`, `Settings/Hierarchy/Hierarchy.vue`, `Settings/HomeActions.vue`).
Every settings screen, and the sidebar on first load, makes this request.

**Actual:** `SingletonMixin` (`crm_app/models/telephony.py`) pinned every singleton row
to the name `Settings`: FCRM Settings, CRM Twilio Settings, CRM Exotel Settings and
ERPNext CRM Settings. Phase 1 chose it because the PKs are strings and a fixed name
keeps the row reachable through the generic route; upstream's convention was not
checked, and `naming.validate_name` even carries the exception that allows a single's
name to equal its doctype. The http suite followed the port's name and passed; the
frontend could not.

A second defect surfaced while fixing it: `register_doctype(..., is_single=True)`
recorded the flag on the registry entry only, never on the model's own `_doc_meta`, so
`model.is_single()` answered False for all four singletons. The old fixed name never
tripped `validate_name`; the doctype name did ("Name of ERPNext CRM Settings cannot be
ERPNext CRM Settings"). The registry now copies `is_single`, `is_child_table` and
`routable` from the entry into the model's metadata.

**Where:** `SingletonMixin.singleton_name`, `frappe_core/registry.py`'s metadata
assignment, `frappe_core/serializers.py`'s duplicate message, migration `crm_app/0008`,
and the tests and http blocks that used the old name.

**Fixed 28 Sep 2026.** The row is named after its doctype: `load()` and
`_assign_name()` use `singleton_name()`, which is `get_doctype()`. Migration 0008
renames the four existing rows through `frappe_core.rename.rename_document`, which also
repoints the CRM Dropdown Item rows that hold a foreign key to the FCRM Settings row.
The duplicate-name message reads "FCRM Settings **FCRM Settings** already exists", as
upstream's does; finding 25's reproduction used the old name. `tests/test_singleton_names.py`
pins the name on load, on create, through `frappe.client.get`, the resource route and
the duplicate refusal; `12_settings_singletons.http`, `04_deals.http` and
`11_permissions_matrix.http` address the rows by the new name. Run
`python manage.py migrate` after pulling.

## 38. frappe-ui reads Frappe's `user_id` cookie, and the port never set one

**Block:** none in the http suite. Seen right after finding 33 let a sign-in through,
28 Sep 2026: the leads list route loaded, the console showed
`TypeError: Cannot destructure property 'isOnboardingStepsCompleted' of
'useOnboarding(...)' as it is undefined` at `AppSidebar.vue:422`, and Vue abandoned the
whole layout.

**Expected:** the sidebar. Frappe sets a `user_id` cookie at login beside the session
cookie, and frappe-ui's `frappe/session.js` reads it to answer "who is signed in".
`useOnboarding()` (`frappe-ui/frappe/Onboarding/onboarding.js:12-14`) asks it and
returns nothing for a guest.

**Actual:** phase 0's JWT patch replaced the cookie read in the app's own session store
with a token read, but frappe-ui carries a second copy of the same helper inside the
package, and it was missed. With no cookie it answered nobody, `useOnboarding` returned
`undefined`, and the sidebar's destructuring threw during setup. The library exports
neither the helper nor a way to configure it.

**Where:** `frontend/src/auth/tokens.js`, beside the token storage.

**Fixed 28 Sep 2026.** `setTokens` also writes a `user_id` cookie with the id from the
access token, and `clearTokens` removes it. The value is URL-encoded because the
library parses `document.cookie` with `URLSearchParams`, which decodes it. The cookie
carries only the user id, which is public within the app, and the backend ignores
cookies entirely, so it grants nothing. `tests/unit/tokens.test.js` reads it back the
way the library does.

## 39. frappe-ui's own calls were invisible to the guard: the onboarding pair

**Block:** none in the http suite. The backend log after the first sign-in, 28 Sep
2026: `POST /api/method/frappe.onboarding.get_onboarding_status 404`, repeated on every
screen, because each page that shows the onboarding panel asks again.

**Expected:** 200 with the user's onboarding status, a JSON object keyed
`<app>_onboarding_status` that lives on the User row (`frappe/onboarding.py`), and a
sibling `update_user_onboarding_status(steps, appName)` that stores one app's steps.

**Actual:** neither path was served. The guard test scans `frontend/src` for the dotted
paths the app calls, and these two are called by `useOnboarding` inside the installed
frappe-ui package (`frappe/Onboarding/onboarding.js`), which no scan of the app's own
source reaches. The same blind spot hides six more library-side calls: the Link search,
the form-load bundle and the Frappe Cloud bridge, all three already served, and the
three Data Import calls, which are not (`KNOWN_ISSUES.md` 8). The frontend fires the
update without awaiting it, so the failure was a console error and a step that never
stayed ticked; the read returned 404 on every navigation.

**Where:** `crm_app/api/onboarding.py`, beside the CRM's own onboarding calls, and
`tests/test_phase3_endpoints.py`.

**Fixed 28 Sep 2026.** `User.onboarding_status` (migration `frappe_platform/0009`) and
the two endpoints: the read answers the parsed object or `{}`; the write stores the
steps under the app's key and keeps other apps' keys, through a queryset update so the
row's timestamps stay put, as upstream's `update_modified=False` intends. An unset
status reads as `{}` on the write path too, which upstream gets wrong
(`UPSTREAM_BUGS.md` 40). The guard gained a second scan over the package's
two source trees, with the three Data Import paths as its only exclusions, so a
library-side call can no longer go unserved unnoticed. `tests/test_onboarding_status.py`
covers the pair.

## 40. The JSON caches crossed the wire as lists; the frontend parses strings

**Block:** none in the http suite, which accepted either shape. Seen 28 Sep 2026: the
leads and deals lists showed a spinner forever while notes, tasks, call logs, contacts
and organizations rendered. The backend log had `crm.api.doc.get_data 200` for the
leads request. Fetching that response by hand showed
`"_assign": ["ada@example.com", "Administrator"]`, a real list.

**Expected:** `"_assign": "[\"ada@example.com\", \"Administrator\"]"`, a JSON string.
Upstream keeps `_assign`, `_liked_by` and `_comments` in Text columns holding JSON
(`base_document.py:520-523` lists them among the text fields) and hands them over
untouched, so the frontend parses them: `JSON.parse(lead._assign || '[]')` in
`Leads.vue:490` and `Deals.vue:456`, inside the computed that builds the rows, and
`JSON.parse(item)` in every list view's `isLiked`.

**Actual:** the port stores the three as `JSONField` (`frappe_core/models.py:151-153`),
the better column, and both output paths, `fetch_rows`'s `values()` and the DRF
serializer, produced the decoded list. `JSON.parse` of a list coerces it to a string
first, `"ada@example.com,Administrator"`, which is not JSON, so the row computation
threw, Vue abandoned the render, and the `v-else` spinner stayed. The five lists that
rendered have no `_assign` column in their default view. The http suite never noticed
because its `contains` and `count` checks pass on either shape.

**Where:** `frappe_core/query.py`, the new `wire_json_text`, applied in `fetch_rows`
and in `DocumentSerializer.to_representation`.

**Fixed 28 Sep 2026.** The three caches are encoded as JSON strings on every path that
hands a document or a row to the client; the columns, the assignment and like code,
and the `_assign like %user%` filter (`filters.py`, which already casts the column to
text) are unchanged. An empty cache goes out as `"[]"`, which both the guarded and the
unguarded parses accept. `tests/test_wire_shapes.py` pins the string on the resource
route, `frappe.client.get_list`, the list route and the empty case, and that the text
filter still matches; `test_task_assignment.py` and `test_hardening.py` decode before
comparing; blocks 02/10.7, 03/4.5, 03/4.7, 06/2.4 and 06/2.7 expect the string.

## 41. The dashboard's default tiles were in a shape the frontend cannot draw

**Block:** none in the http suite, which was written against the port's shape and
passed. Seen 28 Sep 2026: the dashboard page showed nothing for any period, after a
short wait, while `crm.api.dashboard.get_dashboard` answered 200 with three leads, five
ongoing deals and one won deal.

**Expected:** upstream's seventeen tiles. `DashboardGrid.vue` hands the grid each
tile's `layout` object (`x`, `y`, `w`, `h`, `i`), and `DashboardItem.vue` draws a tile
by its type and knows four: `number_chart`, `axis_chart`, `donut_chart` and `spacer`.
Upstream's `default_manager_dashboard_layout` (`crm_dashboard.py`) builds every tile
that way.

**Actual:** the port's `DEFAULT_DASHBOARD_LAYOUT` (`crm_app/api/dashboard.py`) was an
older shape: ten tiles of `{name, type, width}` with the types `number`, `donut` and
`bar`, and no `layout` at all. The grid received ten undefined positions and every tile
fell through all four type checks, so the page drew nothing; the wait was the data
arriving. `get_dashboard` had written that default into the "Manager Dashboard" row on
its first run (7 Sep), so the row read it back on every visit, and Reset to Default
would have written it again. The six charts the old list left out
(`average_won_deal_value`, the two time-to-close numbers, `sales_trend`,
`forecasted_revenue`, `funnel_conversion`) have had builders since finding 20; nothing
asked for them.

**Where:** `crm_app/api/dashboard.py`, the default; migration `crm_app/0009`.

**Fixed 28 Sep 2026.** The default is upstream's string, verbatim, and the row stores
it as upstream stores it. Migration 0009 rewrites a saved row whose tiles all lack
`layout`, which only the old default produces, and leaves an arranged layout alone.
`tests/test_dashboard_layout.py` pins the shape against the frontend's four types and
the grid keys, the string against the upstream file when it is present, the seventeen
filled tiles through the endpoint and the migration's three cases; `10_dashboard.http`
1.4 to 1.12 and 3.2 expect the new tiles. Run `python manage.py migrate` after pulling.

## 42. The user menu was empty: the standard dropdown items were never seeded

**Block:** none in the http suite; `12_settings_singletons.http` reads the settings row
and never looked at `dropdown_items`. Seen 28 Sep 2026 while preparing the browser
tests: `frappe.client.get` of FCRM Settings answered `"dropdown_items": []`, and the
database held no CRM Dropdown Item row at all.

**Expected:** six items. `UserDropdown.vue` builds the menu at the top of the sidebar
from `settings.dropdown_items` and dispatches on each row's `name1`: `app_selector`,
`settings`, `login_to_fc`, `about`, a separator and `logout`. Upstream writes those six
(`crm/hooks.py:314`, `standard_dropdown_items`) into the settings row at install
(`crm/install.py:530`) and re-syncs them after every migrate
(`fcrm_settings.py:after_migrate`). Without them there is no way to open Settings or
About, or to sign out, from inside the app.

**Actual:** the port has the CRM Dropdown Item child table and the settings serializer
sends it, but nothing ever wrote a row: `install.py` was never ported (`PORT_PLAN.md`
§2 covers the demo data only), and the FCRM Settings row on this database was created
bare on 24 Aug. The frontend's only fallback is an empty list.

**Where:** `crm_app/models/metadata.py`, beside the child model; migration
`crm_app/0010`.

**Fixed 28 Sep 2026.** `STANDARD_DROPDOWN_ITEMS` carries the hook's six entries
verbatim and `add_standard_dropdown_items` writes them, unless the row already has
items, which is upstream's install rule. `FCRMSettings.load` seeds a row it creates, so
a fresh database gets them on first use; migration 0010 seeds the rows that already
existed. `tests/test_dropdown_items.py` covers the list, the first load, idempotence,
the migration and the shape the frontend receives. Not ported: upstream's `validate`
refusal to delete a standard item ("Cannot delete standard items ...") and its
post-migrate re-sync; both belong with a settings-screen pass. Worth knowing beside it:
a single that has never been saved answers 404 here, where upstream's always exists.
This database had the row; `FCRMSettings.load()` is the path that creates one.

## 43. Install-time reference data was never seeded: layouts, scripts, sources, industries, quick filters

**Block:** none in the http suite. Seen 28 Sep 2026 while mapping the pages for the
browser tests: the database held no Quick Entry or Data Fields layout, no CRM Form
Script, no CRM Industry, CRM Lead Source or CRM Communication Status row, one lost
reason, and no quick-filter selection.

**Expected:** what `crm/install.py:after_install` writes when the app is installed on a
site: seven lead and seven deal statuses, two communication statuses, fourteen field
layouts (eight Quick Entry, four Side Panel, two Data Fields), fifty-one industries,
fourteen lead sources, nine lost reasons, six quick-filter selections, the six user-menu
items, three standard form scripts and the manager dashboard. The frontend assumes them:
every create dialog reads its fields from the doctype's Quick Entry layout; the lead and
deal pages show the status dropdown in their header only after a form script has run
(`data/script.js:184` sets `document.statuses`, and `Lead.vue:21` renders on it); the
Source and Industry pickers list the rows; a deal's probability follows its status
through the forecasting script; the product table totals through the product scripts.

**Actual:** the port has every model but no install step: `install.py` was never
ported, and `PORT_PLAN.md` §2 mentions only the demo data. On this database the statuses
came with the demo data (six of the seven lead statuses; "Converted" was missing), the
four Side Panel layouts and one lost reason had been written by hand, and nothing else
existed. So every create dialog showed every field of the doctype in unlabeled tabs,
the status dropdown never appeared on a lead or deal page, Source and Industry offered
nothing, and a deal's probability stayed put when its status changed.

**Where:** `crm_app/setup.py`, new; `crm_app/management/commands/seed_defaults.py`;
`crm_app/api/dashboard.py`'s `create_default_manager_dashboard`, which the two dashboard
endpoints now share with it.

**Fixed 28 Sep 2026.** `crm_app/setup.py` is `after_install`, function for function,
with upstream's data verbatim, and `python manage.py seed_defaults` runs it as
Administrator. Every function keeps a row that exists, so a re-run never overwrites an
administrator's changes; `--force` rewrites the field layouts and the dashboard, as
upstream's `restore_defaults` does; the two product scripts are brought back in line
with the code when they differ, as upstream does on every migrate. Not ported, because
the port has no such mechanism: the property setters and custom fields upstream adds to
Email Template, Email Account, Web Form and Assignment Rule; the columns they add are
part of the models here. `tests/test_seed_defaults.py` covers each group, the two
endpoints that serve the layouts and the quick filters, idempotence, `--force`, the
script re-sync and the command. Run `python manage.py seed_defaults` once after
`migrate` on an existing database; this one has been seeded. One thing the product
scripts reach for is still missing: `crm_products.get_product_rate_details`, which the
script calls when a product is picked in a deal's products table, is not served, so that
pick logs a 404 and leaves the rate at 0. The totals themselves are computed server-side
(`test_phase3_endpoints.py`, C4). That belongs to a products pass.

## 44. Contact's field labels are the model's verbose names, not upstream's

**Block:** none in the http suite. Seen 28 Sep 2026 in the New Contact dialog once the
Quick Entry layout existed (finding 43): the fields read "first name", "last name",
"email id", "mobile no", "company name".

**Expected:** "First Name", "Last Name", "Email Address", "Mobile No", "Company Name",
the labels in Frappe's `contact.json`, which is what the dialog and the side panel
show upstream.

**Actual:** `get_fields_layout` expands each fieldname through `doctype_meta.json`, and
Contact, a framework doctype rather than one of the CRM's, is not in that file
(`backend/scripts/generate_field_meta.py` reads the CRM app's doctypes), so the labels
fall back to the Django field's verbose name. Address and the other framework doctypes
the layouts name have the same gap.

**Where:** `backend/crm_app/data/doctype_meta.json` and the script that generates it.

**Fixed 1 Oct 2026**, by the route Address took rather than through the generator: each
`Contact` field carries `contact.json`'s label as its verbose name (migration
`frappe_platform` 0013, state only), which is where both the forms and the filters read
it. The same comparison with upstream found the contact's `status` field missing
(Passive / Open / Replied, default Passive): `crm/install.py:514` installs the contacts
list with three quick filters, `status`, `email_id` and `phone`, and the first had been
silently dropped for want of the column. It is added, and the list now shows Status,
Email Address and Phone. Two differences remain and change nothing on screen: upstream
marks `email_id`, `mobile_no` and `phone` with `options` Email and Phone, and types
`image` as Attach Image.

## 45. The Address doctype is not modelled; the address Link field searches it

**Block:** none in the http suite. Seen 28 Sep 2026 in the first browser run: the New
Contact and New Organization dialogs, and the contact and organization pages, each
logged `search_link DoesNotExistError`, and the failing request was
`frappe.desk.search.search_link` with `doctype: "Address"`.

**Expected:** an autocomplete over Address rows, and the AddressModal that creates one
(`frappe.client.insert` of an Address with a `links` row back to the organization or
contact). Upstream's Contact and Organization side panels and quick-entry layouts carry
the `address` field, and the seeded layouts (finding 43) now show it here too.

**Actual:** the port had no Address model, no registration and no routes, so the Link
control's first search answered 404 and the console showed an error every time one of
those dialogs opened; the "create" option of the field opened the Address dialog, whose
save then failed the same way. `Address.country` is a Link to `Country`, which the port
did not have either.

**Where:** `frappe_platform/models.py` (`Country`, `Address`), migration
`frappe_platform/0010`, `crm_app/permissions/platform_docs.py`, `crm_app/setup.py`
(`add_countries`, from a copy of the framework's `country_info.json` in `crm_app/data`),
`crm_app/api/client.py` (`search_link`'s Address filters).

**Fixed 29 Sep 2026.** Both doctypes ported from the framework. Address carries
`address.json`'s fields with upstream's labels, its `links` Table of Dynamic Link, and
the controller's behaviour: the name is `<title>-<type>` with a numbered suffix on a
collision, the title is mandatory, link rows take the linked document's title and are
deduplicated, a preferred billing or shipping flag is cleared on the other addresses of
the same document, and an address created without links takes the owner's contact's
links. `search_link` honours `address_query`'s `link_doctype` and `link_name` keys and
hides disabled addresses. Permissions are upstream's: every role reads, writes and
creates an address and only System Manager deletes one; everyone reads countries and
System Manager maintains them. `seed_defaults` writes the 250 countries. Not ported:
`get_address_display` and the Address Template it renders, which no CRM screen calls;
the Currency rows the country import also writes; and the title falling back to the
first link's title at naming time, which needs rows that do not exist yet when the name
is assigned here. `tests/test_address.py` covers all of it; the browser fixture's
allowance for this finding is removed, so the tests insist on it.

## 46. Every User Link answered 400: `ignore_user_type` was read as a field

**Block:** none in the http suite, which never sent the key. Seen 28 Sep 2026 in the
first browser run: `search_link ValidationError` on every dialog and page with a User
Link, and on the dashboard; the request was `frappe.desk.search.search_link` with
`doctype: "User", filters: {"ignore_user_type": 1}`, the answer 400 "Unknown field
'ignore_user_type' for this document type".

**Expected:** the enabled System Users. The CRM's Link control sends that key for every
User field (`Field.vue:487`, `SidePanelLayout.vue:529`, `AssignToBody.vue:13`,
`Grid.vue:636`, `Dashboard.vue:92`). Upstream routes User searches through the
doctype's standard query, `user.py:user_query`, which pops `ignore_user_type` from the
filters, hides Website Users unless a System User sent the flag, and lists enabled
accounts only. `search_widget` likewise pops `include_disabled` and hides switched-off
rows of any doctype that carries an `enabled` or `disabled` check.

**Actual:** the port's `search_link` handed the filters to the query engine untouched,
which rejected the unknown field. No owner, assignee or sales-user filter could be
picked anywhere in the app.

**Where:** `crm_app/api/client.py`, `search_link`.

**Fixed 29 Sep 2026.** Both keys are popped before the query; User searches get
`user_query`'s rules (`enabled = 1`, and `user_type != "Website User"` unless a System
User sent the flag); other doctypes with an `enabled` or `disabled` field hide their
switched-off rows unless `include_disabled` was sent.
`test_phase3_endpoints.py::test_search_link_user_takes_the_frontends_ignore_user_type_key`
covers the flag, the disabled account and the Website User.

## 47. `frappe.client.get_value` was never served; the forecasting script needs it

**Block:** none in the http suite. Found 28 Sep 2026 by the Codex review of the
install-step port (finding 43): the seeded forecasting script runs on a deal's status
change and calls `frappe.client.get_value` for the new status's probability, and the
port's `frappe.client.*` had `get`, `get_list`, `get_single_value`, `set_value`,
`insert`, `delete`, `rename_doc` and `get_doc_permissions`, but not `get_value`.

**Expected:** `frappe/client.py:get_value(doctype, fieldname, filters, as_dict, parent)`:
one row's fields by name or by filters, as a dict (or `{}`), or the bare value(s) when
`as_dict` is false.

**Actual:** 404, so the script's `await call(...)` rejected, the probability stayed at
its old value, and the console logged the failure on every status change.

**Where:** `crm_app/api/client.py`, beside the other `frappe.client.*` calls.

**Fixed 29 Sep 2026.** Ported with upstream's shapes, through `fetch_rows` so the row
rules and restricted-field checks of `get_list` apply. `tests/test_client_get_value.py`
covers the script's exact call, the list and dict forms of `fieldname`, a name as the
filter, `as_dict` off, no match, an unknown doctype and a row a Sales User may not read.
`test_seed_defaults.py::test_every_method_the_seeded_scripts_call_is_served` now scans
the seeded scripts for `call("...")` and holds every path but the product-rate lookup
(finding 43) to the whitelist. The same review found the one `.values()` path finding
40 had missed, `crm.api.views.get_views`, which goes through `wire_json_text` now, and
a method name the library-side guard could not see because `pulse.ts` keeps it in a
constant; the guard follows such constants into `call()` now.

## 48. `yarn dev` never started on Windows: frappe-ui's proxy plugin loops forever

**Block:** none in the http suite. Seen 29 Sep 2026: `yarn dev` printed
"Local frappe-ui vite plugin not found, using npm package" and nothing more, twice,
however long it was left. Reproduced with `vite --debug`: the config file loads, that
line prints, and the process then burns CPU indefinitely with no further output; timing
each frappe-ui plugin constructor on its own put the stall in `frappeProxy()`.

**Expected:** the second startup line, "No common_site_config.json found, using default
port 8000", then the server on 8080.

**Actual:** `frappeProxy()` calls `getCommonSiteConfig()`, which calls `findBenchPath()`
(`node_modules/frappe-ui/vite/utils.js:25-36`): starting from the working directory it
walks up with `path.resolve(currentDir, '..')` until it finds a folder holding both
`sites` and `apps`, or until `currentDir === '/'`. On Windows the walk ends at `D:\`,
which never equals `/`, and `path.resolve('D:\\', '..')` is `D:\` again, so without a
bench-shaped ancestor the loop never exits. Nothing on this machine's path has those
two folders. `findAppName` (`utils.js:48-64`) has the same loop, reached only through
`siteBanner` and `buildConfig` when a `frontendRoute` is passed, which this config does
not do. Why the same server started on the days before is not established; nothing in
the lockfile or the installed package changed (`frappe-ui` 1.0.0-beta.29, installed
1 Sep). Recorded as upstream bug 41, a frappe-ui defect rather than a CRM one.

**Where:** `frontend/vite.config.js`.

**Fixed 29 Sep 2026.** `frappeProxy: false`, and the settings that plugin would have
produced are written into `server` directly: port 8080 offset by the backend port, the
same proxy rule (upstream's source list plus `ws`), the same host-preserving router,
and the same `FRAPPE_WEB_SERVER_PORT` override. Nothing the browser sees changes.

## 49. Nothing could upload a file: `upload_file` was never served, nor `/files/`

**Block:** none in the http suite, which has no multipart body. Seen 29 Sep 2026 in the
Notes pass of `BROWSER_TESTING.md` (N9): the image button in the note editor answered
"Method upload_file not found"; the terminal showed `POST /api/method/upload_file 404`.

**Expected:** `frappe/handler.py:upload_file` (130-244), registered under its bare name
(`handler.py:get_attr` looks a dotless `cmd` up in its own module): take the multipart
form the two uploaders send - the CRM's `filesUploaderHandler.ts` for attachments,
frappe-ui's `fileUploadHandler.ts` behind the editor's image button and the comment and
email boxes - check write permission on the document being attached to, store the bytes,
answer with the File row. Then `/files/<name>` from the web server and
`/private/files/<name>` through `download_private_file` (`utils/response.py:296-308`),
which refuses guests and anyone the File rule refuses.

**Actual:** no such method in the registry, and `config/urls.py` had only `admin/` and
`api/`. `File` was a metadata row: `KNOWN_ISSUES.md` 3 recorded it as such ("nothing
currently serves the bytes") and set the condition for the day something would - a
permission check at the serving layer. Every attachment anywhere in the product was
dead: pictures in notes, files on leads and deals, email attachments, the profile image.

**Where:** `backend/crm_app/api/upload.py` (new), `backend/frappe_platform/files.py`
(new), `backend/frappe_platform/models.py` (`File`), `backend/frappe_core/file_views.py`
(new), `backend/config/urls.py`, `backend/frappe_core/method_views.py`,
`frontend/src/auth/tokens.js`.

**Fixed 29 Sep 2026.**

- `upload_file`: `handler.py:131-244` for a signed-in user (the guest branch is dead
  here, the method is not guest-callable). The `file` part, or `file_url` alone, or
  `library_file_name`; chunked uploads assembled in a `.temp-` file and answered with
  nothing until the last chunk; `optimize` through `frappe/utils/image.py:optimize_image`
  when Pillow is installed (added to `requirements.txt`; without it the picture is kept
  at full size); `ALLOWED_MIMETYPES` for a user without desk access, with upstream's
  wording. `method` - handing the bytes to a whitelisted function instead of making a
  File - is refused: no screen sends it.
- The File model carries `file.py`'s pipeline: `before_insert` (103-138) and
  `save_file` (858-940) hash, deduplicate against a row with the same bytes and privacy,
  name without collisions (`utils.py:generate_file_name`) and write under `MEDIA_ROOT`,
  `files/` for public and `private/files/` for private, the layout
  `communication.attachment_path` was already reading; a flipped `is_private` moves the
  bytes and rewrites the URL (313-394), the attachments panel's "Make public"; the last
  row naming a file deletes it (680-694), also under the cascade that removes a deleted
  document's files; an attachment is noted on the document's timeline as upstream's
  `Attachment` and `Attachment Removed` comments (978-994).
- One check is deliberately not ported: `validate_file_on_disk` (462-470), which refuses
  a row whose local URL names nothing on disk. `add_comment` and `email.add_attachments`
  copy rows by URL, every attachment fixture builds one, and the port had eight phases of
  such rows before it could store bytes. Such a row is metadata; when the file is on disk
  the hash and size are filled from it. The model docstring records the choice.
- `/files/<name>` is public, as upstream's web server serves it; `/private/files/<name>`
  asks `file_has_permission` through `find_file_by_url` (`utils.py:494-507`) and answers
  upstream's 403 text when the caller is nobody or the rule refuses. Markup types
  (`FORCE_DOWNLOAD_EXTENSIONS`) are sent as downloads, never inline.
- A browser cannot put a header on the `<img>` a note embeds, so `tokens.js` keeps the
  access token in an `access_token` cookie as well, `path=/private/files`,
  `SameSite=Lax`, rewritten on refresh and cleared at logout. `file_views` reads it there
  and nowhere else, on a GET; it is never read under `/api/`. `frontend/JWT_PATCH.md`
  and `specs/SECURITY_MODEL.md` have the reasoning.
- `MethodView._build_payload` merged a form body with `dict.update`, which copies a
  QueryDict's raw value lists: `is_private` arrived as `["1"]`. It now takes one value
  per key, files included.

Covered by `tests/test_upload_file.py`. Not ported, and noted in `SECURITY_MODEL.md`:
the folder tree, the per-doctype attachment limit, the site-wide extension whitelist,
`download_file`, thumbnails, and `validate_not_referenced_in_attach_field`.

## 50. The PWA manifest icon is not served

**Block:** none. Seen 29 Sep 2026 on every page load:
`GET /assets/crm/manifest/manifest-icon-192.maskable.png 404`.

**Expected:** upstream ships the icon in `crm/public/manifest/`, which Frappe serves as
`/assets/crm/manifest/...`; `frontend/index.html` links the manifest and the browser
fetches the icon for the add-to-home-screen prompt.

**Actual:** the Vite proxy forwards `/assets` to the backend, which has no route for it.
Cosmetic: nothing on screen depends on the icon. Open; the fix is a static route for the
CRM's `public/` folder, or moving the manifest into `frontend/public/`.

## 51. Export from a list view: the method was missing, and the download carried no token

**Block:** none in the http suite (the answer is a file, and the runner compares JSON).
Seen 29 Sep 2026 in the Tasks pass of `BROWSER_TESTING.md` (T6): Export → Excel did not
produce a file.

**Expected:** `ViewControls.vue:565-590` builds
`/api/method/frappe.desk.reportview.export_query?file_format_type=Excel&title=CRM Task&doctype=CRM Task&fields=[...]&filters={...}&order_by=...&page_length=...&selected_items=[...]`
and navigates to it; upstream (`frappe/desk/reportview.py:427-575`) runs the
report-builder query and answers with the file, `Sr` plus the column labels as the header
row, the `sid` cookie having authenticated the navigation.

**Actual:** two faults. The method was not in the registry, so the navigation landed on a
404 JSON body. And had it existed, a navigation carries no `Authorization` header: the
interceptor (`JWT_PATCH.md`) covers `fetch` and `XMLHttpRequest`, not a page load, the
same gap as a note's `<img>` in finding 49.

**Where:** `backend/crm_app/api/reportview.py` (new), `backend/frappe_core/method_views.py`,
`frontend/src/components/ViewControls.vue`.

**Fixed 29 Sep 2026.**

- `export_query` for the parameters the lists send: the column keys, the view's filters
  and order, `selected_items` replacing the filters with `name in` (488-489), every
  matching row (upstream drops `limit_page_length`, 432), `owner` fetched as upstream
  appends it (472-476). Rows come from `fetch_rows`, the query every list uses, so the
  doctype's row rule applies to an export exactly as to the screen. Labels follow
  `get_field_info` (623-668): `ID` for the name column, the field's label, the framework's
  for a standard column. Duration columns are formatted (`format_duration`), HTML columns
  flattened for CSV (`handle_html`, without html2text). CSV as `get_csv_bytes` with
  `pop_csv_params`' defaults; Excel through XlsxWriter, upstream's library, with the bold
  header and sized columns of `make_xlsx` (added to `requirements.txt`; CSV needs
  nothing). Not ported, nothing here sends them: `export_in_background`,
  `visible_names`, `add_totals_row`, `translate_values`; `can_export` is a role flag this
  port does not model.
- `MethodView` passes a Django `HttpResponse` returned by a handler through unwrapped,
  which is upstream's `frappe.response.type = "binary"`.
- `exportRows` fetches the URL (the interceptor adds the header), reads the filename from
  `Content-Disposition`, and hands the blob to the browser as a download; a failure shows
  the server's message in a toast instead of a JSON page. The deviation is recorded in
  `frontend/JWT_PATCH.md` beside the private-file cookie.

Covered by `tests/test_export_query.py`.

## 52. Bulk Edit offered no fields: `get_fields` never sent the flags the dialog filters on

**Block:** `07 / views` has no block for it. Seen 29 Sep 2026 in the Tasks pass of
`BROWSER_TESTING.md` (T7): tick rows → Edit → the Field dropdown is empty; the request
answered 200.

**Expected:** `crm/api/doc.py:639-651`: `frappe.get_meta(doctype).fields` minus the
value-less types and `Read Only`, each a DocField row with every flag present (`hidden:
0`, `read_only: 0`, `reqd`, `options`, `description`, ...). `EditValueModal.vue:76-82`
keeps `f.hidden == 0 && f.read_only == 0` and renders an input by `fieldtype`, with
`options` for a Select or a Link.

**Actual:** the port built the list from the Django model's concrete fields with four keys
(`label`, `fieldname`, `fieldtype`, `options`), so `hidden` and `read_only` were
`undefined`, `undefined == 0` is false, and the dialog's filter kept nothing. The same
answer served `SettingsPage.vue`, which asks with `allow_all_fieldtypes` and lays its
form out from the Tab, Section and Column Breaks the model list never contained. Labels
were the model's verbose names and the order the model's, not the DocType's.

**Where:** `backend/crm_app/api/doc.py`.

**Fixed 29 Sep 2026.** `get_fields` reads `field_meta.get_fields(doctype)`, the DocType's
own rows from `doctype_meta.json` (the platform doctypes fall back to the model as
before), drops `no_value_fields` and `Read Only` unless `allow_all_fieldtypes`, and
passes each row through `docfield()`, which restores the zero flags the generator
leaves out (`hidden`, `read_only`, `reqd`, `permlevel`, `in_list_view`,
`in_standard_filter`) and the `options` / `description` / `default` keys the frontend
destructures. Covered by `tests/test_bulk_edit_fields.py`.

## 53. Kanban cards showed the record's number: no model declared its kanban defaults

**Block:** `06 / kanban` answers 200 with `kanban_fields: ["name"]`, which nothing in the
http suite asserted against. Seen 29 Sep 2026 in the Tasks pass of `BROWSER_TESTING.md`
(T8): each card showed the task's title and a number.

**Expected:** `crm_task.py:112-118`: `column_field: status`, `title_field: title`,
`kanban_fields: ["description", "priority", "creation"]`; `crm_lead.py:487` and
`crm_deal.py:350` declare theirs the same way. `crm/api/doc.py:388-399` reads them when
the request names no title field and no card fields, and `Tasks.vue:74-154` renders each
name in `kanban_fields` off the card's row: the description, the priority icon, "3 days
ago", and the button to the linked lead or deal.

**Actual:** none of the three port models defined `default_kanban_settings`, so
`registry.default_kanban_settings()` answered `None` and `_kanban` fell back to
`title_field = "name"` and `kanban_fields = ["name"]`. The number on the card was the
task's `name`, an autoincrement id. Worse, the frontend saves the kanban settings it was
given the moment a column is reordered (`create_or_update_standard_view`), so the dev
database's standard kanban view for CRM Task held `["name"]` and would have kept showing
it after the models were fixed.

**Where:** `backend/crm_app/models/core_sales.py` (the three models),
`backend/crm_app/migrations/0011_kanban_fields_reset.py`.

**Fixed 29 Sep 2026.** `default_kanban_settings` on `CRMLead`, `CRMDeal` and `CRMTask`,
verbatim from upstream. Migration 0011 rewrites a saved kanban view of the three whose
`kanban_fields` is exactly the fallback `["name"]`, or whose `title_field` is `name`, to
the doctype's defaults; a view a person configured is left alone. Covered by
`tests/test_kanban_defaults.py`.

## 54. The Reference Document Type dropdown was empty: no search answers for `DocType`

**Block:** none in the http suite. Seen 29 Sep 2026 in the Notes pass of
`BROWSER_TESTING.md` (N10; the same field is on tasks, T17, and call logs, C12): after
adding "Reference Document Type" and "Reference Doc" to the create dialog, the first
dropdown offered nothing, where upstream lists the doctypes.

**Expected:** `fcrm_note.json:34-37`, `crm_task.json:79-82`, `crm_call_log.json:125-128`
declare `reference_doctype` as a Link to `DocType`, and `reference_docname` as a Dynamic
Link on it. The Link control searches `frappe.desk.search.search_link` with
`doctype: "DocType"`; upstream's `search_widget` answers that one search with
`ignore_permissions=True` (`search.py:294`), so every role can pick a reference, listing
DocType rows that contain the typed text, the ones that start with it first.

**Actual:** `search_link` resolved every doctype through the registry, and `DocType` is
not a doctype this port has, so the call answered 404 and the dropdown stayed empty. The
Reference Doc beside it searches whatever the first field names, so it had nothing to
search either. That accounts for the terminal's unexplained 404s of the pass: the
`search_link` ones are this field (the control searches on mount and again when its
filters settle), and the `getdoctype` and `frappe.client.insert` ones are the Link
control's "Create New" fallback for the typed text, which opens the quick-entry dialog
for a `DocType` and tries to insert one.

**Where:** `backend/crm_app/api/client.py`.

**Fixed 29 Sep 2026.** `search_link` answers a `DocType` search from the registry
(`_search_doctypes`): every registered doctype, the typed text matched anywhere in the
name with the names that start with it first, a condition on `name` in the Link's filters
honoured in either spelling, ten at a time. No permission check, as upstream. Once the
first field holds `CRM Lead`, the second searches leads as it always could, and the
insert carries the pair. Covered by `tests/test_reference_doctype_search.py`.

## 55. The frontend is slow to load (open, deferred)

**Block:** none. Recorded 30 Sep 2026 from the hand testing in `BROWSER_TESTING.md`: the
Vue app takes too long to load.

**Status:** open and deliberately not investigated. The decision is to finish the
browser testing and merge `phase-8-followup` first, then see what can be done.

**What is known, and where to start:** `specs/KNOWN_ISSUES.md` 9. In short: finding 29's
cold-start cost is the one measured number (a minute or two per `yarn dev` start, bound
by the CPU); the app makes about ten calls before the first screen settles, and waits for
the boot-values call before it mounts; nobody has timed a warm reload or a production
build, so whether the slowness exists outside the dev server is not established. The
first step is to measure those three cases.

**Seen again, 12 Oct 2026**, after `node_modules` was deleted and reinstalled: the dev
server took 48 seconds to report ready and the first page load several minutes, on a
machine with 368 MB of its 4 GB free. Not a regression. A reinstall also discards Vite's
pre-bundled dependency cache, which that first load rebuilds, and a timing taken while
the machine is paging measures the paging. Both are written up in
`specs/KNOWN_ISSUES.md` 9, with the rule that any measurement records free memory
beside it. The `brace_expansion` warning the dev server prints at every start is
unrelated and explained there too.

## 56. "Unlink all" leaves an organization's deal linked (open, same as upstream)

**Block:** none. Seen 30 Sep 2026 in the Organizations pass of `BROWSER_TESTING.md`
(O10): with a deal linked to the organization, Delete → "Unlink all" did not release the
deal; "Delete" in the same dialog, which removes the deal, did.

**Expected by a user:** Unlink detaches the deal from the organization, so the
organization can be deleted and the deal survives.

**What upstream does:** `crm/api/doc.py:721-749`. `remove_doc_link` sets
`reference_doctype` and `reference_docname` to empty on the linked document and saves
it. Those are the fields a task, note or call log uses to point at a lead or deal. A CRM
Deal points at its organization through the `organization` Link field and has no such
pair, so nothing changes: the deal is still linked, the dialog lists it again, and
deleting the organization is refused ("Cannot delete or cancel because CRM Organization
... is linked with CRM Deal ..."). Recorded as upstream bug 42.

**What the port does:** the same. `_clear_reference` (`crm_app/api/doc.py`) blanks the
pair on models that have it and does nothing otherwise, and the organization's delete is
refused with the same sentence (`PROTECT` on `CRMDeal.organization`, finding 3).
`tests/test_unlink_linked_docs.py` pins the three cases: a task is unlinked, a deal is
not, and "Delete" frees the organization.

**Status:** open, by the project's rule for a user-visible upstream bug: reproduce it and
record the choice. Diverging would mean having unlink clear the Link field that actually
holds the reference (`deal.organization = None`), which is what the button promises; it
is a decision for the owner, not a port defect.

**Decision, 30 Sep 2026:** leave it as it is for now. A pull request for the fix is to be
opened once the browser testing is finished. Until then the port keeps upstream's
behaviour, and `tests/test_unlink_linked_docs.py` will need its second case turned round
when the fix lands. The fix itself: in `remove_doc_link` (upstream) and `_clear_reference`
(here), for a linked document that has no reference pair, clear the Link field that names
the record being deleted, found the same way `get_linked_docs` found it.

## 57. A user's outgoing email accounts cannot be stored: `User` has no `user_emails`

**Block:** none. Seen 30 Sep 2026 in the Settings pass of `BROWSER_TESTING.md` (S16):
Profile → Email Settings → Add Email opened a dropdown that said "No results", on the
local app and on an upstream demo alike.

**Two separate things.**

*The empty dropdown is an empty state, not a fault, and upstream behaves the same.*
`UserEmailSettings.vue:140-146` lists Email Accounts with `enable_outgoing = 1`, less the
ones already on the user. Until an account is added under Settings → Email → Accounts
with Enable Outgoing ticked, there is nothing to list, and the dropdown has no message
saying so. The list is also cached under `Outgoing Email Accounts`, so an account added
in the same session may need a reload before it shows.

*What comes next is a gap in this port.* Upstream's `User` carries a `user_emails` child
table (`user.json:420-424`, rows of `User Email`: `email_account`, `email_id`,
`enable_outgoing`, ...). Picking an account pushes a row onto `user.doc.user_emails` and
Update saves the user; `EmailEditor.vue:266` then reads the same rows to offer the
"from" address when composing. The port's `User` has no such table and no `User Email`
doctype, so the pick has nowhere to go: the row is expected to vanish on reload, and the
composer can never offer a second sender.

**Where:** `backend/frappe_platform/models.py` (`User`), a new `User Email` child table.

**Status:** open. The fix is a child-table model on `User` with a migration, its place in
the user serializer, and the field-visibility review every new doctype gets
(`specs/AS_BUILT.md`, the phase-4 checklist): upstream puts `user_emails` at permlevel 1,
which is how it keeps a Sales User from attaching accounts to themselves.

**Fixed 6 Oct 2026**, after S10 passed and the composer's From dropdown was seen empty
with the Send button disabled, where the upstream demo offers the account.
`frappe_platform.UserEmail` is the child table (`User Email`, migration 0015):
`email_account`, with `email_id`, `awaiting_password` and `enable_outgoing` fetched from
it, and `used_oauth`, off. Two things fill it, as upstream has them:

* an Email Account save links the account to the user whose address it is and keeps
  the row's flags current (`email_account.py:1072-1115`, `setup_user_email_inbox`);
  the rows go with the account;
* a System Manager's Add Email on the Profile screen, through `frappe.client.set_value`.

The permlevel: `User.PRIVILEGED_WRITE_FIELDS = ("user_emails",)`, System Manager only,
a new field tool in `frappe_core.field_security`. A Sales User's pick is dropped before
validation and the rest of the save goes through, which is what upstream's
`_validate_perm_levels` does by resetting the field. `frappe.client.get` on a user now
carries the rows inline, which is what the composer builds its From dropdown from.

Covered by `tests/test_user_emails.py`.

## 58. The Language dropdown was empty: the port had no `Language` doctype

**Block:** none in the http suite. Seen 30 Sep 2026 in the Settings pass of
`BROWSER_TESTING.md` (S17): Preferences → Language opened an empty dropdown.

**Expected:** `PreferencesSettings.vue:63` is `<Link doctype="Language">` bound to
`user.doc.language`. `Language` is a framework doctype
(`frappe/core/doctype/language/language.json`): named after `language_code`, with
`language_name` as its title and search field and `show_title_field_in_link` set, so the
picker lists names ("English") with the code beneath, enabled rows only. The framework
fills it from `frappe/geo/languages.csv` when a site is set up
(`language.py:sync_languages`).

**Actual:** no such doctype in the port, so `search_link` answered 404 and the list was
empty. The same class of gap as `Country` (finding 45) and the `DocType` search
(finding 54).

**Where:** `backend/frappe_platform/models.py` (`Language`), migration `frappe_platform`
0011, `backend/crm_app/setup.py` (`add_languages`), `backend/crm_app/data/languages.csv`,
`backend/crm_app/permissions/platform_docs.py`, `backend/crm_app/api/client.py`.

**Fixed 30 Sep 2026.** `Language` is modelled (`language_code` as the name,
`language_name`, `flag`, `based_on`, `enabled`) and seeded by `seed_defaults` from a copy
of the framework's list: 82 rows, enabled as the file says. Everyone reads, System Manager
writes, as `language.json` grants. `search_link` matches the name as well as the code and,
for a doctype that shows its title in a Link, answers `value` / `label` / `description` as
`build_for_autosuggest` does; a disabled language is offered only with
`include_disabled`. Covered by `tests/test_language.py`.

**What choosing a language does here:** it is stored on the user and the page reloads,
and nothing else changes. The port ships no translation catalogues
(`crm.api.get_translations` answers `{}`), so the interface stays in English. That is a
recorded limit of the port, not part of this finding; it is finding 59.

## 59. Nothing is translated (open, deferred)

**Block:** none. Recorded 30 Sep 2026, once the Language picker worked (finding 58) and
choosing a language changed nothing on screen.

**Expected:** upstream translates the interface and the server's messages from the PO
files each app ships (`crm/locale`, 33 languages; `frappe/locale`, 39). The page's boot
values carry the merged dictionary for the user's language as `translated_messages`, and
every server-side string goes through `_()`.

**Actual:** the boot call answers `translated_messages: {}` (`crm_app/api/boot.py:65`),
so the Vue app's every lookup falls back to English, and the server's 200 user-facing
messages are English literals.

**Status:** open, deferred by decision until the browser testing is finished. Two
requirements from the owner are part of it: the chosen language must also apply to the
messages the server sends, and `enabled` on a Language must mean what it means in
Frappe (offered in the picker, accepted for a guest's browser language, honoured by the
boot dictionary).

**The design:** `specs/KNOWN_ISSUES.md` 10. In short: read the PO files with a Python
parser into Frappe's dictionary shape; resolve each request's language the way
`get_language` does; return the dictionary in the boot values, which translates the
interface; add a `_()` that `throw()` applies to literal messages, and rewrite the
roughly 75 f-string messages as upstream's `"... {0}".format(...)` templates so they can
be looked up; guard the lot with a test against `main.pot`.

## 60. Two General settings are stored and never acted on

**Block:** none. Found 30 Sep 2026 by reading the code behind the General page of
Settings (`BROWSER_TESTING.md` S20), not from a failing screen: both switches save and
reload correctly.

**Expected:** `crm/utils/__init__.py:173-193` and `260-290`. When a Communication on a
lead or deal is saved, `_get_communication_status` answers `Open` for a received one if
`auto_reopen_on_new_communication` is on, and `Replied` for a sent one if
`auto_mark_replied_on_response` is on. `on_communication_update` writes that to the
document's `communication_status`, provided the communication is the latest on it, in
the same update that bumps `modified`. The page says both apply only where an SLA is
enabled, since that is the only place the status is shown.

**Actual:** the two columns exist on `FCRMSettings` (`crm_app/models/metadata.py:345-346`)
and no code reads them. The port's handler for a new communication
(`crm_app/async_signals.py`) implements only the third switch,
`update_timestamp_on_new_communication`.

**Reach:** "Replied on response" would fire when an email is sent from a lead or deal,
which the port can do. "Reopen on new communication" needs a received email, and the port
does not fetch incoming mail (`KNOWN_ISSUES.md` 7), so that half has no trigger here even
once it is written.

**Where:** `backend/crm_app/async_signals.py`.

**Status:** open, deferred. Decision 30 Sep 2026: to be ported once the browser testing is
finished. The fix is a port of `_get_communication_status` and the status write in the
communication handler, with the latest-communication check, and a test that sends an
email from a lead with an SLA and reads the status back.

**The third switch, for the record:** `update_timestamp_on_new_communication` was verified
in the browser the same day (`BROWSER_TESTING.md` S19), with and without a Celery worker:
with one, a comment moves the lead's Last Modified; without one the job waits in the
queue and nothing moves, which is how a queued job is meant to behave.

## 61. An administrator's bell held everyone's notifications

**Block:** `08 / notifications` replays as users who are not administrators, so it never
saw this. Seen 30 Sep 2026 in the browser (`BROWSER_TESTING.md` NT1): clicking
Notifications in the sidebar did nothing. The dev database held 64 notifications, none
addressed to Administrator, and `get_notifications` answered all 64 to Administrator.

**Expected:** `crm/api/notifications.py:8-13` selects `WHERE to_user = session.user`, and
`mark_as_read` (52-57) filters on `{"to_user": user, "read": False}`. Both are the
caller's own rows whoever the caller is.

**Actual:** both port handlers read through `base_queryset("CRM Notification", user)` on
the stated belief that the permission rule *is* `to_user = user`. It is, for an ordinary
user. For Administrator and System Managers the rule is unrestricted, as upstream's
`get_permission_query_conditions` is, so an administrator's bell listed every user's
notifications, the badge counted them all, and "Mark all as read" would have marked them
read for everybody. Among those rows were some with no reference, which is what stopped
the panel from opening (finding 62).

**Where:** `backend/crm_app/api/notifications.py`.

**Fixed 30 Sep 2026.** Both handlers add `to_user = user` to the query. The permission
rule is unchanged: an administrator can still read every row through
`/api/resource/CRM Notification`, as upstream allows. Covered by
`tests/test_notification_scope.py`.

## 62. A notification with no lead or deal behind it takes the panel down (open, same as upstream)

**Block:** none. Found 30 Sep 2026 while tracing finding 61.

**Expected by a user:** the panel opens, and a notification about a task that is not tied
to a lead or deal either goes to the task or is not a link.

**What upstream does:** `crm/api/todo.py:126-131`. A task assignment's notification takes
its reference from the task's own `reference_doctype` / `reference_docname`, empty for a
task made on the Tasks page. `get_notifications` answers `route_name: "Lead"` with an
empty `reference_name` for it, `Notifications.vue` renders every row as a `RouterLink` to
`{ name: 'Lead', params: { leadId: '' } }`, and vue-router throws
`Missing required param "leadId"` inside the render. The panel never appears for a user
who holds one such row. Recorded as upstream bug 43.

**What the port does:** the same. The rows are created the same way and the Vue file is
upstream's unchanged. After finding 61's fix Administrator no longer sees other users'
rows, so the panel opens there; a user who was assigned a standalone task (in the dev
database, several of the demo Sales Users) will still find the bell dead.

**Status:** open, by the project's rule for a user-visible upstream bug. The fix is in the
frontend: a row with no reference rendered as plain text, or sent to the Tasks page. A
candidate for the same pull request as finding 56.

## 63. The dashboard currency cannot be chosen: the port has no `Currency` doctype (open, deferred)

**Block:** none. Seen 30 Sep 2026 in the Settings pass of `BROWSER_TESTING.md` (S21):
Settings → Dashboard → Dashboard Currency opened an empty dropdown, and Exchange Rate
Provider stayed disabled.

**Expected:** `DashboardSettings.vue` shows `<Link doctype="Currency">` until a currency
is set, after which it is fixed ("Once set, cannot be edited"). `Currency` is a framework
doctype, filled from the same `country_info.json` the countries come from
(`frappe/geo/doctype/country/country.py:import_country_and_currency`). With a currency
set, the provider select is enabled and `crm.api.exchange_rate.get_exchange_rate` asks
the chosen service for a rate when a deal is in another currency.

**Actual:** no `Currency` doctype in the port, so `search_link` answers 404 and the list
is empty; the same gap as `Country` (finding 45) and `Language` (finding 58). The
provider select is disabled by the frontend because no currency is set
(`:disabled="!settings.doc?.currency"`). Behind it, the exchange-rate call is a stub that
always answers 1, a recorded phase 3 decision (`crm_app/api/exchange_rate.py`): the
`service_provider` and `access_key` settings are stored and nothing reads them.

**Doctype ported, 15 Oct 2026** (branch `currency-and-system-settings`): `Currency` in
`frappe_platform`, its 149 rows written by migration 0017 from the copy of
`country_info.json` the countries come from, with upstream's nine defaults enabled
(`frappe_platform/reference_data.py:add_currencies`); the picker lists the enabled ones.
Every role reads, System Manager writes. `currency` on a deal, an organization and FCRM
Settings is now a validated Link, and the dashboard's currency prefix is the symbol
(`$` with none set), not the code. Tests: `tests/test_currency.py`. S4 and S21 are for
the tester to re-check.

**Exchange rates ported, 15 Oct 2026**, the second half: `crm/api/exchange_rate.py` in
full in `crm_app/api/exchange_rate.py`, the four providers with upstream's fallbacks
between the two free ones, the access-key refusal and the three fetch-failure messages
verbatim, cached per pair per day. Calls go through `crm_app/integrations/http.py` with
upstream's five-second timeout and no retry. A deal and an organization take the rate
on save when their currency changed or no rate is held (`ExchangeRateMixin`,
`crm_deal.py:273-280`, `crm_organization.py:34-41`), into the dashboard currency (USD when
none is set); the dashboard's three average cards now count `deal_value * exchange_rate`,
as upstream's do (the forecast chart already did). `ENABLE_EXCHANGE_RATE_API`, on by
default, switches the provider calls off for a site without outbound internet (every
rate 1); the test settings turn it off. Tests: `tests/test_exchange_rate.py`. The
territory and salesperson charts did not plot value at all, which is finding 88.

**After the review, 15 Oct 2026:** a partial save (`save(update_fields=...)`, upstream's
`db.set_value`) no longer asks for a rate. Records saved before this work held rate 1
(deals) or none (organizations) whatever their currency, and upstream's rule only
recomputes on a currency change, so `manage.py refresh_exchange_rates` writes the rate
upstream would have: run it once after `migrate`. It is a command, not a migration,
because it calls the provider.

**Status (before the fix):** open, deferred. Decision 30 Sep 2026: port Currency once the browser testing
is finished. Two steps then. First the doctype, the way Language was done: a model, a
seed from `country_info.json` through `seed_defaults`, upstream's role table, and the
title shown in the picker. Then, separately, the four providers behind the stub, which
is outbound HTTP and belongs with the integrations layer (`crm_app.integrations.http`).

## 64. Settings → Defaults goes blank: the port has no `System Settings`

**Block:** none. Seen 30 Sep 2026 in the Settings pass of `BROWSER_TESTING.md` (S5):
choosing Defaults in the Settings dialog left its main area empty.

**Expected:** `DefaultsSettings.vue` loads the framework's single `System Settings`
document (`createDocumentResource({ doctype: 'System Settings' })`) and that doctype's
metadata (`getMeta('System Settings')`), and offers six of its fields: `currency` (a Link
to `Currency`), `currency_precision`, `number_format`, `float_precision`, `date_format`
and `time_format`. The five selects take their options from the metadata
(`system_settings.json`: for example `yyyy-mm-dd`, `dd-mm-yyyy`, `dd/mm/yyyy`,
`dd.mm.yyyy`, `mm/dd/yyyy`, `mm-dd-yyyy` for the date). Only System Manager holds the
doctype upstream. The values feed `frappe.defaults`, which is what the page's boot values
carry as `sysdefaults` and what every number, date and amount on screen is formatted by.

**Actual:** neither exists in the port. `frappe.client.get` and `getdoctype` both answer
404, `settings.doc` stays empty, and the template reads `settings.doc.currency` with no
guard, which throws inside the render and leaves the section blank. The values themselves
do exist here, as `settings.FRAPPE_SYSDEFAULTS` (`config/settings/base.py:250-258`,
overridable from the environment), and `crm_app/api/boot.py:63` sends them with the boot
call. So formatting works, at the defaults; it just cannot be changed from the app.

**Where:** a new single doctype in `frappe_platform`, its entry in the field metadata,
`crm_app/api/boot.py`.

**Decision, 30 Sep 2026:** deferred until the browser testing is finished, and to be
built as one piece of work with finding 63 (Currency) and finding 59 (translations):
Currency and System Settings first, the translation steps on top. `KNOWN_ISSUES.md` 10
carries the order.

**Status:** open, deferred. The fix is a `System Settings` single carrying at least those six
fields, seeded from the current `FRAPPE_SYSDEFAULTS` so nothing changes on the day it
lands; the framework's JSON added to the metadata generator so the selects get their
options; `boot.py` reading the row instead of the Django setting; and System Manager
alone writing it. Three other open items meet here and are best done together: the
`currency` field needs the `Currency` doctype (finding 63), the system language the
translation work needs is `System Settings.language` (finding 59, step 2 of
`KNOWN_ISSUES.md` 10), and the dashboard's own currency setting reads the same list.

**Fixed, 15 Oct 2026** (branch `currency-and-system-settings`): a `System Settings` single
in `frappe_platform` with the seven fields the CRM reads (the six on the page, plus
`rounding_method`), their options copied from `system_settings.json`; date, time and
number format required, as there. Migration 0019 writes the row from
`FRAPPE_SYSDEFAULTS`, so the formats did not change on the day; the boot call now reads
the row, and writes it again if it is missing. `currency` is a validated Link to the
Currency doctype from finding 63. `language` waits for finding 59. Tests:
`tests/test_system_settings.py`. S5 is for the tester to re-check, as System Manager.

**Who reads it, 15 Oct 2026:** System Manager alone, for reading as well as writing, as
`system_settings.json` says. Upstream offers the Defaults tab to a Sales Manager too, who
then gets a blank panel: confirmed on the hosted demo and recorded as `UPSTREAM_BUGS.md`
50, reproduced here rather than widened. The boot call reads the row server-side, so
nobody needs read on the doctype to have their numbers and dates formatted.

## 65. "Invalid credentials" for a correct password: the server had no encryption key

**Block:** `09 / email account` replays with made-up credentials and expects a refusal, so
it could not see this. Seen 1 Oct 2026 in the Settings pass of `BROWSER_TESTING.md`
(S10): a real Gmail address with an app password made minutes earlier, and the screen
answered "Failed to create email account: invalid credentials".

**Expected:** `crm/api/settings.py:5-46`. Upstream logs in to the mail server with the
credentials, saves the account, and the list shows it. Anything that goes wrong on the
way is re-thrown as its own text (`except Exception as e: frappe.throw(str(e))`).

**Actual, three things stacked:**

1. *The screen cannot tell you what went wrong.* `EmailAdd.vue:147-149` sets its error to
   the literal "Failed to create email account: invalid credentials" in `onError`,
   whatever the server said. That is upstream's file, unchanged.
2. *The local server could not store any password.* The port keeps a mail password
   encrypted at rest (`frappe_core/secrets.py`), with a key from `FIELD_ENCRYPTION_KEY`
   in `.env`. The dev `.env` had none, and nothing in the setup docs said one was needed.
   So the order of events was: log in to Gmail, succeed, try to save, raise
   `MissingEncryptionKey`. Reproduced with made-up values and the login check switched
   off: the save fails on this machine whatever the credentials.
3. *A pasted app password could be a 500.* Google shows an app password in four groups;
   copied from the page it can carry non-breaking spaces, which `smtplib` cannot encode.
   That raised `UnicodeEncodeError` out of the check uncaught. Upstream's catch-all turns
   it into a refusal; the port had no catch-all.

Ruled out on the way: the network (both Gmail ports answer from this machine) and the
SMTP conversation itself (a wrong password reaches AUTH and is refused cleanly).

**Where:** `backend/crm_app/api/settings.py`, `backend/frappe_core/secrets.py`,
`readme.md`, `docs/TESTING_GUIDE.md`.

**Fixed 1 Oct 2026.**

- `create_email_account` checks for the key before it logs in (`secrets.ensure_key`), so
  a server that cannot store the password says "FIELD_ENCRYPTION_KEY is not set" in the
  response without a pointless login first.
- The live check is wrapped as upstream wraps it: a port exception passes through, and
  anything else the mail libraries raise becomes a 417 carrying its own text.
- `readme.md` ("The encryption key") and `TESTING_GUIDE.md` say the key is required, how
  to make one, and that the server must be restarted after editing `.env`.

**Still needed on each machine:** a `FIELD_ENCRYPTION_KEY` line in `.env`. The code cannot
supply one; a key generated silently would be lost on the next deploy and take every
stored credential with it.

**Not changed:** the screen's fixed sentence. It is upstream's frontend. The true reason is
in the response body (browser Network tab) and in the server terminal.

Covered by `tests/test_email_account_setup.py`.

## 66. Salutation and Gender were not dropdowns: the port had neither lookup doctype

**Block:** none in the http suite. Seen 1 Oct 2026 in the Contacts pass of
`BROWSER_TESTING.md`: the contact's Salutation and Gender were text boxes, where an
upstream demo shows a dropdown for each.

**Expected:** `contact.json` declares `salutation` as a Link to `Salutation` and `gender`
as a Link to `Gender`; `crm_lead.json` and `crm_deal.json` do the same for their own
copies of the fields. Both targets are one-field framework doctypes
(`frappe/contacts/doctype/salutation`, `.../gender`), filled by the setup wizard
(`install_fixtures.py:20-49`): Mr, Ms, Mx, Dr, Mrs, Madam, Miss, Master, Prof, and Male,
Female, Other, Transgender, Genderqueer, Non-Conforming, Prefer not to say.

**Actual:** the port had neither doctype, and the gap showed two ways. A contact's field
metadata is derived from its Django model, where the two are text columns, so the forms
drew text boxes. A lead's and a deal's metadata is upstream's JSON, which says Link, so
their forms drew dropdowns whose search answered 404: they had been empty all along.

**Where:** `backend/frappe_platform/models.py` (`Salutation`, `Gender`,
`Contact.LINK_FIELDS`), migration `frappe_platform` 0012, `backend/crm_app/setup.py`,
`backend/crm_app/permissions/platform_docs.py`, `backend/frappe_core/field_meta.py`.

**Fixed 1 Oct 2026.** Both doctypes are modelled, named after their one field, and seeded
by `seed_defaults` with upstream's lists. Everyone reads and System Manager writes, as the
two JSON files grant. On `Contact`, `LINK_FIELDS` names the target of the two columns and
the derived metadata says Link, which is the shape the lead and the deal already had: a
text column in the model, a Link in the metadata.

**A value that names nothing is refused, as upstream refuses it** (added the same day,
on the owner's instruction). Upstream's `Document._validate_links` runs on every save
and throws `LinkValidationError`, "Could not find <Label>: <value>"
(`base_document.py:1040-1054`). The port had that for foreign-key Links only; its text
Links stored whatever was typed. `frappe_core/links.py`, called from
`BaseDocument.save`, now holds every text Link to the rule when its target doctype is
registered. Nothing is listed by hand: the fields come from the doctype's metadata, so
the rule reaches `salutation` and `gender` on Contact, CRM Lead and CRM Deal, `gender`
on CRM Contacts, `address` on CRM Organization and `product` on CRM Product Sync Issue.
A case-only difference is rewritten to the stored spelling, since upstream on MariaDB
matches without regard to case and saves the stored name: `mr` becomes `Mr`.

Because a save can now be refused for want of a row, the two lists cannot be left to
`seed_defaults` alone. Migration `frappe_platform` 0014 writes them
(`frappe_platform/reference_data.py`), so every database has them, the test database
included; `seed_defaults` puts back one that was deleted. The dev database was checked
before the rule went in: no existing row would be refused.

Covered by `tests/test_salutation_gender.py`.

This also closes the larger half of finding 44 as it affects the screens: the contact's
form now behaves as upstream's for these two fields. Its remaining labels still come
from the model.

## 67. A second number could not be picked, and a number could not be edited or removed

**Block:** none in the http suite. Seen 1 Oct 2026 in the Contacts pass of
`BROWSER_TESTING.md` (K9): a new number was added to a contact from the Mobile No
dropdown, and clicking it did not select it.

**Expected:** the dropdown does three things to a row (`useContactFields.ts`). Clicking
one calls `crm.api.contact.set_as_primary`, which loads the contact, flags the chosen row
and clears the rest in memory, and saves once (`crm/api/contact.py:87-112`). The pencil
calls `frappe.client.set_value` on `Contact Email` or `Contact Phone`, and the x calls
`frappe.client.delete` on the same; the framework takes a child row in both, checks write
on the parent, and saves or removes the row through the parent
(`frappe/client.py:213-223`, `551-572`).

**Actual:** two separate faults.

1. *Pick.* The port's `set_as_primary` saved the rows one at a time. Each row's save
   re-derives the contact, and the row being promoted was saved while the old primary
   still held its flag. The contact's own rule, "Only one **Mobile No** can be set as
   primary.", then refused it with a 417, **after** the new row's flag was already
   written. The contact was left with two rows flagged, and from then on every save of
   that contact failed on the same rule, which is the "could not save" seen on the page.
2. *Edit and remove.* `frappe.client.set_value` and `frappe.client.delete` refused every
   child table with a 404, so neither button on a row did anything.

**Where:** `backend/crm_app/api/contact.py` (`set_as_primary`),
`backend/crm_app/api/client.py` (`_child_row_and_parent`, `_set_child_value`,
`_delete_child_row`), `backend/frappe_platform/models.py` (`CLIENT_EDITABLE` on
`ContactEmail` and `ContactPhone`).

**Fixed 1 Oct 2026.**

- `set_as_primary` writes the flags as two set-based updates inside one transaction, the
  old flags cleared before the new one is set, then re-derives the contact once. No
  moment exists with two rows flagged, and a failure leaves nothing half-written.
- The two client methods accept a child row whose model says `CLIENT_EDITABLE`. They find
  the parent through the row, check write on the parent, change or remove the row, and
  save the parent, so the contact's `email_id`, `mobile_no` and `phone` follow. Only the
  two contact tables are opted in; the reason for not opening every child table, as
  upstream does, is in `specs/SECURITY_MODEL.md`.

**Data:** one contact in the dev database had been left with two primary mobiles by the
fault. It was repaired by hand, keeping the number flagged last.

**The filter, checked and left alone.** The Mobile No filter finds a contact by its
primary mobile number, in whole or in part. The **Phone** quick filter finds nothing for
a number added on the contact screens, and upstream is the same: it filters the `phone`
column, which those screens never fill. Recorded as upstream bug 44.

Covered by `tests/test_contact_numbers.py`.

## 68. The organization's logo could be changed but not removed

**Block:** none in the http suite; seen in the browser on 5 Oct 2026
(`BROWSER_TESTING.md` O14), signed in as Administrator. The upstream demo removes it.

**Expected:** once a logo is set, `Organization.vue` offers Change Image and Remove
Image. Remove Image calls `changeOrganizationImage('')`, which submits
`organization_logo: file?.file_url || null`, so `null` is what reaches
`frappe.client.set_value`. Upstream's `set_value` (`frappe/client.py`) does
`doc.set(fieldname, value)` and saves; a Data field holding None is stored empty, and the
avatar goes back to the initials.

**Actual:** the port's `client_set_value` writes through the doctype's serializer.
`organization_logo` is `CharField(blank=True, null=False)`, which DRF maps to a field
with `allow_null=False`, so the request answered 400 "This field may not be null." and
the logo stayed. The contact page's Remove Image sends `''` instead, so it was not
affected. But the same refusal waited for any text or select column a client clears with
`null`, on `/api/resource/` too, and in the list's bulk Edit dialog: `EditValueModal.vue`
sends `fieldVal || null` for an emptied value, and `bulk_action` writes through the same
serializer, so emptying a text or select field for several rows at once put every row in
the `failed` list, which the dialog does not show. It looked like nothing happened.

**Where:** `frappe_core/serializers.py`, `DocumentSerializer`.

**Fixed 5 Oct 2026.** `DocumentSerializer.to_internal_value` turns `None` into `""` for
every text and choice field that does not itself allow null, before validation, so
`null` means "empty" on both write routes, as it does upstream. A field the model
declares nullable keeps `None`, and a field that refuses blank still refuses it.

Covered by `tests/test_null_as_blank.py`.

## 69. A call log pointed at a lead did not show on the lead's Calls tab

**Block:** none in the http suite; seen in the browser on 5 Oct 2026
(`BROWSER_TESTING.md` C12), signed in as Administrator. On the upstream demo the same
edit puts the call on the lead's page.

**Expected:** a call log carries Reference Document Type and Reference Name. A lead's or
a deal's page asks `crm.api.activities.get_activities`, whose second bucket is the calls
`get_linked_calls` finds for that name (`crm/api/activities.py:376-467`). The function's
last line is `calls = [parse_call_log(call) for call in calls]`, which adds `_caller`,
`_receiver`, `_duration`, `activity_type` and `show_recording`; `CallArea.vue` reads
`call._caller.image` and `call._receiver.label` straight off each row.

**Actual:** the reference saved correctly and `get_linked_calls` found the call, but
returned it as read from the table. With no `_caller` on the row the call card throws
while rendering, so the tab showed nothing. The port's docstring cited lines 373-459:
it had stopped one line short of the parse. Nothing caught it because the demo call logs
have no reference, and the one test of this function only checks which names come back.

**Where:** `crm_app/api/activities.py`, `get_linked_calls`.

**Fixed 5 Oct 2026.** `get_linked_calls` runs every call through `parse_call_log`
(`crm_app/models/telephony.py`, already ported for the call-log list), for the lead page
and the deal page alike.

Covered by `tests/test_lead_call_tab.py`.

## 70. Bulk Edit cannot empty a task's Assigned To

**Block:** none in the http suite; seen in the browser on 5 Oct 2026
(`BROWSER_TESTING.md` T18), signed in as Administrator.

**Expected:** not settled. The task list hides the Assign To and Clear Assignment menu
items (`TasksListView.vue`, `hideAssign: true`), so the bulk Edit dialog is the only way
to change the assignee of several tasks at once, and emptying its value is the only way
to clear it.

**Actual:** tick tasks → Edit → Field "Assigned To", no value → Update: the rows keep
their assignee. Setting a user the same way works (T16). The upstream demo behaves the
same.

**Not investigated,** by decision on 5 Oct 2026: recorded only, to be looked at with the
other post-testing items. What is known comes from reading the dialog, not from tracing
this failure: `EditValueModal.vue` sends `{assigned_to: fieldVal || null}` to
`submit_cancel_or_update_docs` and does not show the response's `failed` list. Whether
the request is sent at all, and what answers it, has not been checked on either side.

**Status:** open. If the cause is upstream's own, it also belongs in the
`UPSTREAM_BUGS` file and in the upstream PR with bugs 42, 43 and 44.

## 71. The ticked rows stay ticked after a bulk action

**Block:** none in the http suite; seen in the browser on 5 Oct 2026 on the leads list
(`BROWSER_TESTING.md` L18, L20, L22), signed in as Administrator.

**Actual:** tick rows → run a bulk action (Edit, Assign To, Clear Assignment, Convert to
Deal, Delete). The action itself works, but when it finishes the rows are still ticked
and the selection bar is still up; they have to be unticked by hand.

**Not investigated, and not compared with upstream,** by decision on 5 Oct 2026:
recorded only. What is known comes from reading `ListBulkActions.vue`, not from tracing
this: each action is handed an `unselectAll` callback and calls `reload(unselectAll)`
when it finishes, so the selection is meant to clear.

**Status:** open.

## 72. A call log edited from a lead does not refresh on the lead's Calls tab

**Block:** none in the http suite; seen in the browser on 5 Oct 2026 on a lead's Calls
tab (`BROWSER_TESTING.md` L11), signed in as Administrator.

**Actual:** open a call from the lead's Calls tab → change its time in the form → save
and close. The tab still shows the old value; a reload of the page shows the new one, so
the change is saved.

**Not investigated, and not compared with upstream,** by decision on 5 Oct 2026:
recorded only. The tester's own guess is that the form and the tab hold the call in two
separate pieces of state.

**Status:** open.

## 73. Convert to Deal on a lead's page answered 500

**Block:** none in the http suite, which sends `deal: {"next_step": ...}` or no deal at
all; seen in the browser on 5 Oct 2026 (`BROWSER_TESTING.md` L19). The dialog showed
"Error converting to deal: Internal Server Error". Bulk convert from the list (L20)
worked.

**Expected:** `ConvertToDealModal.vue` posts `lead`, `deal: deal.doc`,
`existing_contact` and `existing_organization` to
`crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal`. `deal.doc` comes from
`useDocument('CRM Deal')`, and a new document starts as `{__newDocument: true, doctype}`
(`data/document.js`), so those two keys arrive on every conversion, before any field the
user fills in. Upstream ends `create_deal` with `new_deal.update(deal)`
(`crm_lead.py:375-376`): every key is set on the document, and `insert` saves the ones
that are fields.

**Actual:** `conversion.create_deal` merged the dict into its payload and called
`CRMDeal.objects.create(**payload)`:
`TypeError: CRMDeal() got unexpected keyword arguments: '__newDocument', 'doctype'`.
So the button failed for everyone, every time; only the bulk action, which sends no
deal form, could convert a lead. A Link in the form (a status, an owner) would have
failed the same way, because the model wants `status_id`, not `status`.

**Where:** `crm_app/api/lead.py`, the endpoint; `crm_app/conversion.py` is unchanged.

**Fixed 5 Oct 2026.** The endpoint passes the form's deal fields through the deal's
serializer, as the Create Deal door in `crm_app/api/deal.py` does: the read-only rules
of `frappe.client.insert` apply, values are validated, a Link is taken by name, and keys
that are not deal fields are dropped. Checked against the dev database with the dialog's
exact payload inside a rolled-back transaction: 200 and a deal.

Covered by `tests/test_lead_endpoints.py` (the three tests under "what the modal really
sends").

## 74. New deals were made with an earlier deal's values

**Block:** none in the http suite; seen in the browser on 6 Oct 2026
(`BROWSER_TESTING.md` D24), signed in as Administrator. After a few deals were created
correctly, a deal created with new details came out with values from the earlier ones.

**Expected:** each Create Deal starts from an empty form and makes a deal from what was
typed.

**Actual:** `useDocument('CRM Deal')` with no name hands every caller the one
`documentsCache['CRM Deal']['']` object for the page session (`data/document.js:110-111`),
and `DealModal.vue` never clears it: on success it only navigates (`:214-218`). So the
next Create Deal starts from the last deal's values. Worse, once "Choose Existing
Organization" has been used, its pick stays in `deal.doc.organization` after the switch
is turned off; the field is hidden with its section, `createDeal()` nulls `contact` for
the equivalent case but not `organization` (`:179`), and the server prefers
`doc.organization` to the organization details typed (`crm_deal.py:468`, and the port's
`crm_app/api/deal.py` the same way). The deal lands on the old organization and the
typed one is never created. The Convert to Deal dialog reads the same object
(`ConvertToDealModal.vue:129`), so a conversion after a Create Deal carries that
dialog's leftover website, territory, revenue, industry, status, owner and organization
over the lead's own values.

**Where:** the frontend, which is upstream's byte for byte; recorded as upstream bug 45
and confirmed on the upstream demo on 6 Oct 2026.
Not a browser or server-state problem: the object lives in the page's memory, so a page
reload clears it and a server restart changes nothing.

**Status:** open, reproduced on purpose (the frontend is upstream's). Workaround until
the upstream PR: reload the page before creating or converting a deal after another
deal has been created. The D-rows were recorded with that workaround.

## 75. The delete dialog listed a deal's own contact row and its comments

**Block:** none in the http suite; found 6 Oct 2026 on request, by comparing the two
delete paths of a deal (`BROWSER_TESTING.md` D22, D23) with upstream and probing the
port against the dev database inside rolled-back transactions.

**Expected:** `DeleteLinkedDocModal.vue` asks `crm.api.doc.get_linked_docs_of_document`
what links to the record, offers Delete All and Unlink All while the list has rows, and
shows the Delete button only once it is empty. Upstream's list comes from the
framework's `get_linked_docs` and `get_dynamic_linked_docs`
(`frappe/model/delete_doc.py:313-470`): Link and Dynamic Link fields in other doctypes,
minus the doctypes the `ignore_links_on_delete` hook names (`frappe/hooks.py:455-470`:
Comment, Communication, ToDo, File, Version, Activity Log and the rest, plus the CRM's
Failed Lead Sync Log), which `delete_doc` deletes with the document. A child row's own
`parent` column is not a Link field, so a document's own child rows are never listed;
a child row that *does* link to the record is reported as its parent document
(`delete_doc.py:352-384`). For a deal with a contact row, four comments, three tasks,
two notes and two call logs, the list is the tasks, notes, calls and the notifications.

**Actual:** the port's `_link_sources` walked every FK in the registry, child tables
and their parent FKs included, and `_dynamic_link_sources` skipped nothing. So the
list for that deal also held `CRM Contacts <row id>` and four `Comment <id>` rows.
Three consequences:

1. A contact row has no reference pair, so Unlink All left it listed and the Delete
   button never appeared. A deal with a contact, which every deal made through the
   dialog has, could only be deleted with Delete All, which also deletes its tasks and
   notes.
2. Unlinking a comment blanked its reference and the comment was left orphaned, in
   the dialog and in `delete_bulk_docs` with "Delete" (which clears links first), where
   upstream deletes the comments with the deal.
3. A contact's dialog listed `CRM Contacts <row id>` for each deal it is on instead of
   the deal, and Unlink set that row's contact to nothing instead of taking the contact
   off the deal.

Nothing caught it because the tests of this endpoint check names, permission and a
lead's tasks, never a document with child rows or comments.

**Where:** `crm_app/api/doc.py`, `_link_sources` and `_dynamic_link_sources`, used by
both `get_linked_docs_of_document` and the bulk scan `_linked_docs_for_batch`.

**Fixed 6 Oct 2026.** `_link_sources` skips a child table's parent FK (the FK whose
reverse name is the row's `parentfield`, the same walk `client.py` uses) and every
doctype in `IGNORE_LINKS_ON_DELETE`, the hook's list; a child table's other FKs are
reported as the row's parent document, skipping the record itself and a parent the
caller cannot read. `_dynamic_link_sources` skips the same doctypes. Probed again on
the same deal: the list is the tasks, notes, calls and notifications; Unlink All
empties it; the delete then removes the deal and its comments and leaves the tasks
unlinked. A contact's dialog now lists the deals it is on, and `remove_contact` takes
it off them, as upstream's `remove_contact_link` does.

Not covered: a call log attached to a deal only through its `links` child table
(`Dynamic Link` rows, written by the telephony integrations) is not listed, where
upstream lists the call. Out of the browser log's scope with the integrations.

Covered by `tests/test_delete_dialog_links.py`.

## 76. A delete goes through while other documents still reference the record

**Block:** none; seen in the same probe as 75, on the API only.

**Expected:** upstream's `frappe.delete_doc` runs `check_if_doc_is_linked` and
`check_if_doc_is_dynamically_linked` (`delete_doc.py:388-498`) and refuses with
`LinkExistsError`, "Cannot delete or cancel because CRM Deal X is linked with CRM Task
Y", while a task, note, call log or notification still points at the record. That
refusal is why the dialog exists.

**Actual:** `frappe.client.delete` and `DELETE /api/resource/` on a deal with a task
still referencing it answer 200; the deal goes and the task keeps `reference_docname`
pointing at nothing. A reference through a foreign key is refused as upstream does
(`ProtectedError` becomes `LinkExistsError`, `frappe_core/exceptions.py:244`); the
`reference_doctype` / `reference_docname` convention is not checked.

**Reach:** not from the Vue app in the ordinary case, since the dialog hides Delete
until its list is empty. The one gap is a linked document the caller cannot see: the
port's list is permission-filtered, so a Sales User whose dialog shows nothing can
delete a deal that a manager's private note still points at.

**Status:** open, decision deferred to after the browser testing. Adding the check
means every delete scans the dynamic link sources, and a good many tests delete
documents that still have references; it should be decided and done as one piece.

## 77. The Deals list would not open: a saved filter the port refused

**Block:** none in the http suite; reported 6 Oct 2026 as "the Deals list page is not
loading, every other list loads" (`BROWSER_TESTING.md` D25), signed in as
Administrator. The six calls the page makes answered 200 with the default view; the
failure was in the user's saved standard view.

**Expected:** a list page replays the standard view's saved filters on every load
(`ViewControls.vue:463`, `create_or_update_standard_view`). Clicking a cell filters
the list on that cell's value (`ViewControls.vue:1321-1337`). For a currency cell the
list's row object holds the display string, "$ 500,000.00" (`pages/Deals.vue:406`),
so that string is what gets filed and saved: upstream bug 46. Upstream's
`frappe.get_list` hands it to MariaDB, which casts it to 0 for the comparison; the
list comes back empty and the page opens.

**Actual:** Administrator's standard view on CRM Deal held
`{"annual_revenue": "$ 500,000.00"}` (and Grace's, "$ 700,000.00"). The port's
`build_q` handed the string to Django's `DecimalField`, which refused it:
417 "“$ 500,000.00” value must be a decimal number." Replayed on every load, the
refusal meant the page never rendered, and the filter chip that would remove it was
never drawn. Other lists were fine only because no currency cell had been clicked on
them; Leads and Organizations format the same way and would lock the same way.

**Where:** `frappe_core/filters.py`, `build_q`.

**Fixed 6 Oct 2026.** A filter value for a numeric column is now read for the number
in it before the comparison: sign and point kept, everything else dropped, so
"$ 500,000.00" compares as 500000 and "₹ 7,00,000.00" as 700000; a string with no
number in it is 0, MariaDB's answer. Applies to `=`, `!=`, `<`, `>`, `<=`, `>=`, `in`,
`not in` and `between`; `like` and `is` already work on the column's text and are left
alone. A deliberate divergence from upstream's empty list, recorded under upstream
bug 46: the click now filters on the amount shown. The saved views are untouched; the
chip appears on the next load and can be removed as usual.

Covered by `tests/test_numeric_filter_values.py`.

## 78. Home Actions let the Settings entry be turned into a separator

**Block:** none in the http suite; seen 6 Oct 2026 on the upstream demo during the
Settings pass (`BROWSER_TESTING.md` S14): the Settings row's Type was changed to
Separator by mistake, Update went through, and Settings was gone from the user menu.

**Expected:** `crm_dropdown_item.json` marks Type read-only for a standard row
(`read_only_depends_on: eval:doc.is_standard`), so the six shipped entries keep their
kind.

**Actual:** the Home Actions grid (`Grid.vue`, `GridRowModal.vue`) does not read
`read_only_depends_on`, and the server does not refuse the change either, upstream or
here. A Separator row draws a divider and nothing else (`UserDropdown.vue:91-104`), and
Settings is a modal opened from that menu with no route of its own, so the grid that
would undo the change is unreachable. Desk is no way back either: there the row's Type
and Is Standard are read-only by the doctype's own rules, deleting a standard row is
refused by `FCRMSettings.validate`, Restore Defaults and `bench migrate` add missing
standard rows but never repair a changed one. The database is what is left; the console
command is in the upstream-bug entry.

**Where:** the frontend, upstream's; recorded as upstream bug 47.

**Status:** open, reproduced (the frontend is upstream's). **Recovery added 6 Oct 2026:**
`seed_defaults --force` restores the six standard rows by their Name (Label, Type, Route,
Icon; a missing one re-added), leaves `hidden` and custom rows alone, and a plain rerun
still writes nothing. Covered in `tests/test_seed_defaults.py`.

## 79. System mail bypassed the Email Account, and a site with no account could not send

**Block:** none in the http suite; seen 6 Oct 2026 in the Settings pass
(`BROWSER_TESTING.md` S8): Settings → Invite User, and the invitation went to the Celery
worker's console instead of the inbox, while a mail written on a lead reached the relay.

**Expected:** every mail leaves through the outgoing Email Account lookup, and a
deployment with no Email Account at all can still send from a configured address. That
is what the Frappe Cloud demo shows: a site with no Email Account sends its invitations
and password resets from `notifications@<site>`, and Settings → Email Accounts shows
nothing, because the account that sends them is not a document. A mail written on a lead
falls through to the same account, from the user's own address unless the account's
sender flag is on.

**What upstream does:** `EmailAccount.find_outgoing` + `find_default_outgoing`
(`frappe/email/doctype/email_account/email_account.py:506-540`) has four steps: an
outgoing account whose address is the sender's; an incoming-and-outgoing account whose
`append_to` is the reference doctype; the default outgoing account; and `find_from_config`
(`:493-498`), an **unsaved** Email Account (`from_record`, `:478-481`) built from
`site_config.json` by `get_account_details_from_site_config` (`:563-600`): `mail_server`
(unset means no account, `{}`), `mail_port`, `use_tls` (falling back to whether
`mail_login` is set), `mail_login`, `mail_password`, `auto_email_id` (falling back to
`mail_login`, then `notifications@example.com`), `email_sender_name` (default `Frappe`,
and it becomes the account's `name`) and `always_use_account_email_id_as_sender`; flagged
`_from_site_config`, never saved. System mail passes no sender (`frappe.sendmail` from
`crm_invitation.py:45-51` and the reset in `user.py`), so `QueueBuilder.sender`
(`email_queue.py:719-724`) takes the account's `default_sender`,
`formataddr((name, email_id))` (`email_account.py:468-469`): `Frappe <notifications@…>`.
Nothing to send through throws `OutgoingEmailError`, "Please setup default outgoing
Email Account from Tools > Email Account" (`:528-532`) - in front of the inviter, since
the invitation sends inside `after_insert`.

**What the port did:** two paths. A lead's mail ran steps 1-3 in
`crm_app.communication.find_outgoing_account` and went through the account's own SMTP
details; step 4 was left out as "`site_config.json`, which this port does not have", so
a site with no account was refused. System mail (`crm_app.mail`) never ran the lookup:
`default_sender()` borrowed the default outgoing account's *address*, or
`DEFAULT_FROM_EMAIL` (`crm@example.com`), and the message went through Django's
`EMAIL_BACKEND`, which `.env` leaves at the console backend - so the invitation printed
in the worker's terminal while the lead's mail reached the relay, and in production the
two would have left through two different servers.

**Fix (13 Oct 2026):** step 4 is ported, with Django's own mail settings as the port's
`site_config.json` (`config/settings/base.py`, each read from the environment):

| Setting | Upstream key |
|---|---|
| `EMAIL_HOST` | `mail_server`; empty means there is no config account |
| `EMAIL_PORT` | `mail_port`; unset, 465 with SSL, 587 with TLS, else 25 |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | `mail_login` / `mail_password`; no login means no SMTP authentication |
| `EMAIL_USE_TLS` | `use_tls`, defaulting to whether `EMAIL_HOST_USER` is set, and off whenever `EMAIL_USE_SSL` is on |
| `EMAIL_USE_SSL` | Django's own; the account's `use_ssl_for_outgoing`. Django's SMTP backend refuses both flags at once, so SSL drops TLS the way `frappe_core.mail.smtp_settings` does for a saved account (Codex, 13 Oct 2026: a login plus SSL with TLS unset defaulted TLS on and could not send) |
| `DEFAULT_FROM_EMAIL` | `auto_email_id`, then `EMAIL_HOST_USER`, then `notifications@example.com` |
| `EMAIL_SENDER_NAME` | `email_sender_name`, default `Frappe`: the account's name and the display name on system mail |
| `EMAIL_ALWAYS_USE_ACCOUNT_EMAIL_ID_AS_SENDER` | `always_use_account_email_id_as_sender` |

The names are Django's own on purpose: `django.core.mail.get_connection()` reads the
first six itself, so the config account is the one account whose transport is
`EMAIL_BACKEND` - `communication.open_backend` hands it to `get_connection()` - and the
console backend carries it in development. `communication.config_account()` builds the
unsaved `Email Account` from them, flagged `from_site_config`; `find_outgoing_account`
returns it after the default-outgoing step. `outgoing_account_for` does not stamp it on
`Communication.email_account`: the field names a row, the config account has none, and
since the stamp is read back by the lookup a "Frappe" there would make the queued send
find no account. `crm_app.mail.send` now runs the same lookup with no sender and no
doctype, sends From `formataddr((account.email_account_name, account.email_id))`
through `open_backend`, and raises `OutgoingEmailError` with upstream's sentence when
there is nothing; `default_sender()` is gone.

**Development:** `EMAIL_HOST=localhost` beside the console `EMAIL_BACKEND`
(`.env.example`). The host is never contacted; its being set is what makes the config
account exist, and the mail prints in the Celery worker's terminal as before.
`DEFAULT_FROM_EMAIL` should be set explicitly when `EMAIL_HOST_USER` is not an address,
since it falls back to the login the way upstream falls back to `mail_login`.

**The invitation trade-off:** `OutgoingEmailError` is not in `send_invitation_email`'s
`autoretry_for` - retrying would not make an account appear - so a deployment with no
account and no `EMAIL_HOST` fails the task once with a logged traceback, and
`email_sent_at` stays null, where upstream fails the invitation in front of the inviter.
That is the phase-5 decision to send from a task rather than inside the request, now
written on the task. The password-reset endpoint already catches everything and answers
its one sentence.

**Status:** fixed 13 Oct 2026. `tests/test_mail_config_account.py` covers the account's
field map, the lookup order, both From rules on a lead's mail, and the invitation and the
reset with and without the config account; `tests/test_phase5_async.py`,
`tests/test_auth_pages.py` and `tests/test_invitation_access.py` create their invitations
with the config account present, since an invitation with nothing to send through now
fails its task. `config/settings/test.py` pins `EMAIL_HOST` empty so a developer's
`.env` cannot vary what "no account" means under test.

## 80. Assignment Rules: the screen is there, the feature is not

**Block:** Settings → Assignment Rules (S12), 6 Oct 2026: Save did nothing. Compared in
full with upstream on 15 Oct 2026, to decide whether to port it.

**Why Save did nothing.** The screen posts `frappe.client.insert` for doctype `Assignment
Rule`, a framework doctype the port never modelled (a phase-3 decision: outside the nine
platform doctypes), so the insert answers 404, and the screen's error handler only
clears its spinner. `crm_app/api/assignment_rule.py` answers the list with `[]` and
refuses Duplicate, by the same decision.

**What upstream has** (framework `frappe/automation/doctype/assignment_rule` at
version-15, read with `git show version-15:`, plus CRM's additions):

| Piece | Upstream | Port |
|---|---|---|
| `Assignment Rule` doctype | 15 fields, named by prompt, System Manager only (`assignment_rule.json`) | missing |
| CRM's two fields | `assign_condition_json`, `unassign_condition_json`, custom fields from `install.py:600-627` | missing |
| Child tables | `Assignment Rule User` (user, weight), `Assignment Rule Day` (Monday to Sunday) | missing |
| `ToDo.assignment_rule` | the rule that made an assignment; un-assigning reads it | missing: the port's ToDo has no such column |
| The engine, `apply` | on every `on_update` (`hooks.py:172`), synchronous; rules by priority, skipping days not listed; un-assign, then assign only if nothing is left, then close or reopen (`assignment_rule.py:276-370`) | missing |
| Who is assigned | Round Robin and Load Balancing (the CRM screen offers these two, `AssigneeRules.vue:141-145`); Based on Field and Weighted Distribution in the engine only | missing |
| Conditions | Python expressions run with `frappe.safe_eval` against the document; a failure shows "Auto assignment failed: {0}" and the save goes on (`:200-209`) | missing |
| On assignment | clears existing assignees, assigns one user with the description rendered as a template and `notify=True`, records `last_user` for round robin (`:79-104`) | the parts exist: `frappe_core.assignment`, the assignee notification, the lead and deal owner sync from a ToDo |
| Due dates | `due_date_based_on` and `update_due_date` (`:373-420`); no control for it on the CRM screen | missing |
| Validation | refuses ToDo as the document type; names any day listed twice (`:44-68`) | missing |
| `bulk_apply` | whitelisted; nothing in the CRM frontend calls it | missing |
| `get_assignment_rules_list` | rules on leads and deals, with whether each has users (`crm/api/assignment_rule.py:4-23`); reads with `get_all`, which checks no permission | stub: `[]` |
| `duplicate_assignment_rule` | copies a rule under a new name (`:26-32`) | stub: refuses |
| The screens | `components/Settings/AssignmentRules/`, about 1,660 lines: the two endpoints plus `insert`, `get`, `set_value`, `rename_doc`, `delete` | present, nothing behind them |

**How conditions are stored.** The screen saves each condition twice: as JSON the screen
redraws from, and as a Python expression built from it by `convertToConditions`
(`frontend/src/utils/index.js:599`). Only the Python is evaluated. The screen falls back
to a raw-Python editor only for a rule with Python and no JSON
(`AssignmentRuleView.vue:548-557`), which only a rule made outside the CRM has. The
expression's meaning is what the converter writes, and a port must match it: "like" is
a case-sensitive contains, with no wildcards; "between" compares as text; "Yes" and "No"
are true and false; "is set" and "is not set" test for an empty value. The converter
does not escape a quote inside a "like", "in" or "between" value, so such a rule never
fires (`UPSTREAM_BUGS.md` 52). The screen is offered to a Sales Manager who cannot save
a rule (`UPSTREAM_BUGS.md` 53).

**How upstream evaluates a condition, and why it needs a sandbox.** The engine is the
framework's and predates the CRM's screen. In Frappe's Desk an administrator types the
condition as one Python expression, the same idea Frappe uses for other conditions,
because one expression can say almost anything. The CRM screen came later and, rather
than change the engine, converts its dropdown choices into that same expression. So the
engine holds a piece of text, and the only way to get a yes or no from text that is
Python is to run it. Running text someone else wrote is dangerous (an expression can
reach the operating system), so it is run through `frappe.safe_eval`
(`frappe/utils/safe_exec.py:132-158`, version-15), a sandbox:

* the text is normalised (NFKC) and parsed, and `lambda` and the walrus operator are
  refused outright;
* it is compiled with RestrictedPython's `compile_restricted` under Frappe's policy, which
  rewrites attribute and item access through guard functions, refuses names starting
  with an underscore, and blocks a list of attributes that reach the interpreter's
  internals (`UNSAFE_ATTRIBUTES`, `:773-797`: frame, code and traceback attributes,
  `format`, `format_map`);
* it runs with no built-ins at all, and only `int`, `float`, `round` and the guards as
  globals (`WHITELISTED_SAFE_EVAL_GLOBALS`, `:986-997`), with the document's fields as
  the local names.

Pros of upstream's way: anything expressible in Python can be a condition; one mechanism
for every doctype, SLA conditions included; the framework does the work. Cons: it runs
text that arrived from a browser, and a sandbox around a full language is a blocklist,
safe only while its rules are complete, which for Python sandboxes has repeatedly not
held; writing is limited to System Manager, which narrows the risk without removing it.
The two stored forms can drift apart, since only the expression is read. The expression
is built as a string, so it breaks on a quote (bug 52). A failing rule is silent: it
assigns nobody and says nothing on the rule. And the converter's meanings are odd: "like"
is a case-sensitive contains, "between" compares text, and a value the screen stores as
text compared with a date or a number raises in Python, so that condition never matches.

**How the port will evaluate a condition (decision 1, agreed 15 Oct 2026).** It reads the
JSON form, the list the screen saves before converting, for example
`[["status", "equals", "New"], "and", ["territory", "in", "EU, US"]]`, and checks it
with its own code. The user's input is data to compare against, never code to run:

* **Each condition is three things.** A field name, used only to read that field from
  the lead or deal; an operator, which must be one of the converter's list (equals,
  not equals, `<`, `<=`, `>`, `>=`, in, not in, like, not like, is, is not, between) or
  the condition is refused; and a value, only ever compared.
* **The same answer as the expression would give.** Each operator does what the
  converter's Python does, on the same values with the same types: "like" a
  case-sensitive contains, "between" a text comparison, "Yes" and "No" true and false,
  "is set" and "is not set" a test for an empty value, "in" a list split on commas.
  Where upstream's expression raises, a text value against a date or a number, or a
  field the document does not have, the condition does not match and the rule reports
  "Auto assignment failed", as upstream's does.
* **The same grouping.** The converter joins the parts with spaces, so Python's
  precedence applies: "and" before "or". A nested list is a bracketed group.
* **The expression is stored and never read.** The screen sends it and shows it, so it
  is kept; the engine ignores it.
* **A rule with an expression and no JSON is refused on save**, with a message saying
  the port evaluates only conditions built on the screen. Only a rule written by hand in
  Frappe's Desk has that shape, and the port has no Desk; it matters for data imported
  from a real Frappe site, where such rules must be rebuilt on the screen.
* **One evaluator for both features**: SLA conditions (finding 91) are stored the same
  way and will use it.

What this buys: nothing from a browser is ever executed, so there is no sandbox to
escape; a malicious condition sent straight to the API can at worst fail to match. Bug
52 cannot happen, since a quote is just a character in a value. Only one stored form is
read, so drift between the two cannot change an answer. What it costs: hand-written
Python rules are not supported, and the evaluator must follow the converter if upstream
changes it, which a test per operator, checked against the converter's output, will
catch. Whether to keep upstream's failing date and number comparisons or fix them as a
recorded divergence is still open; faithful is the default.

**Decisions, taken 15 Oct 2026** with the owner:

1. **Conditions:** evaluate the JSON as above, executing nothing; refuse a rule that has
   only Python. The conditions upstream cannot meet are fixed, not reproduced: a date is
   compared as a date and "between" takes its two bounds from the list the editor
   stores (`UPSTREAM_BUGS.md` 54, diverge). Correction to the discussion: number
   comparisons do work upstream, since the editor stores a number as a number
   (`CFCondition.vue:281`); dates and "between" are what fail.
2. **Rule types:** all four in the engine (Round Robin, Load Balancing, Based on Field,
   Weighted Distribution), though the screen offers two.
3. **Due dates and the close condition:** ported, though no CRM screen sets them.
4. **The list endpoint:** as upstream, no permission check, recorded as
   `UPSTREAM_BUGS.md` 55. An upstream pull request will propose the fix, and the port
   follows the outcome; a recorded exception to the security rule until then.
5. **Bug 53:** reproduced, as 50 was.
6. **The SLA engine (finding 91):** built too, sharing the condition evaluator.

**Building decisions, 15 Oct 2026:**

* **Where the engine runs:** after every save of every registered doctype, as upstream's
  `"*"` `on_update` hook does (`hooks.py:172`, version-15), behind the same cached check
  for which doctypes have an enabled rule, so a save with none costs one cache read. A
  rule for another doctype can only come through the API here, and it works rather than
  being stored and ignored.
* **Who builds it:** Codex, from one brief per commit; Claude plans, reviews and commits
  (CLAUDE.md, "Codex builds, Claude plans and reviews").
* **Two pull requests:** Assignment Rules first, on `assignment-rules`; the SLA engine
  (finding 91) second, on its own branch, reusing the condition evaluator.

**Status:** open, decided; being built on branch `assignment-rules`. Estimate: one to two
days with tests, and about the same again for the SLA engine.

## 82. Duplicate on an SLA policy did nothing: the document had no `doctype`

**Block:** none in the http suite; seen 7 Oct 2026 in the Settings pass
(`BROWSER_TESTING.md` S22), signed in as Administrator.

**Expected:** `SlaPolicyList.vue:198-230` fetches the policy with `frappe.client.get`
and posts the whole document back into `frappe.client.insert` with `default` off and the
new `sla_name`. Upstream's documents always carry `doctype`
(`base_document.py:as_dict`, line 704), child rows included, so the insert knows what to
make; `insert` then discards `name`, the stamps and the child rows' names and creates a
copy under the new name.

**Actual:** the port's serialised documents carried no `doctype`, so the insert answered
417 "doctype is required". The screen's create call has no error handler, so nothing
was shown. Probed with the screen's exact two calls on the dev database inside a
rolled-back transaction: 417 before, 200 and a copy after.

**Where:** `frappe_core/serializers.py`, `DocumentSerializer.to_representation`.

**Fixed 7 Oct 2026.** Every document the port serialises now names its doctype, child
rows included: `frappe.client.get`, the resource route, and the insert and set_value
responses, the shape upstream hands out everywhere. The rest of the round trip already
worked: `name`, `creation` and the other stamped fields are read-only on the way in,
and `prepare_rows` strips a child row's `name`.

Covered by `tests/test_document_doctype_key.py`.

---

## 85. The brand logo showed for the account that uploaded it and for nobody else

**Block:** Settings → Brand (S6), 14 Oct 2026. Administrator uploads a logo and a
favicon, presses Update, and sees them in the sidebar. Every other account sees the
default. The same holds for a profile photo and for the lead, contact and organization
images: each is visible to its uploader alone.

**Why.** frappe-ui's `FileUploader` (1.0.0-beta.29, the version CRM pins) sends
`is_private=1` unless its `uploadArgs` say otherwise, and none of the image uploaders in
this app say otherwise - `ImageUploader.vue` passes no arguments, and neither do the
uploaders on the lead, contact, organization and profile pages. Nor do they name a
document. So each image is a private File row attached to nothing. The port's File rule
(`crm_app/permissions/attachments.py`, upstream's `file.py:1066-1106`) lets a private
unattached file be read by its owner alone, so every other account's `<img>` gets a 403.
Confirmed in the local database: `/private/files/queryn-logo-plain.ico`, two rows, both
private, both unattached, both owned by Administrator.

**Why upstream shows it anyway.** Upstream has the same uploader and the same rule. What
it also has is `attach_files_to_document` (`frappe/core/doctype/file/utils.py:354-415`),
run from `frappe/hooks.py:205,227` on every document's `on_update`: for each Attach and
Attach Image field whose value is a file URL, it finds the unattached File row at that
URL and stamps it with the document, field and the privacy the URL implies, or creates a
URL-only row if there is none. From then on the File rule defers to the attached
document, and FCRM Settings is readable by every CRM role (SECURITY_MODEL.md), as a User
is here (divergence 5), so the logo and the avatars reach everyone. The port had no such
step: `upload_file` attaches only when the upload itself names a document, which these
uploaders never do.

**Fix (14 Oct 2026):** the hook is ported as `frappe_platform.files.attach_files_to_document`,
wired by `connect_attach_on_save` from `crm_app.apps.ready` to `post_save` of every
non-child doctype that declares an Attach field, so a doctype without one pays nothing.
The fields come from the DocType JSON for a CRM doctype and, for the platform doctypes
that ship none, from a new `ATTACH_FIELDS` declaration on the model, which
`field_meta._derive_from_model` reports as `Attach Image`: `User.user_image` and
`Contact.image`. Rows already uploaded attach the next time their document is saved -
pressing Update on the Brand page once is enough for the existing logo.

Covered by `tests/test_attach_on_save.py`.

---

## 86. Any CRM user could delete any contact

**Block:** Contacts (K7), the role passes, 14 Oct 2026. As Grace (Sales Manager) and as
Ada (Sales User), a contact Administrator had created could be deleted from its page.
The hosted demo refuses both with "Not permitted".

**Why.** Upstream's `contact.json` gives Sales User and Sales Manager read, write and
create on every contact and **no delete**. Delete comes from the `All` row, which carries
`if_owner`, so a contact is deleted by the user who created it or by a System Manager (and
the two Master Manager roles CRM never assigns), and by nobody else. CRM adds no
permission of its own to Contact: no hook in `hooks.py`, nothing in `install.py`. The port
registered no rule for Contact at all, and a doctype without a rule answers yes to every
question (`frappe_core.permissions.has_permission` returns `None`, which is "allowed"). So
any CRM user deleted any contact. This is the shape `CLAUDE.md` warns about: upstream had
protection in its role table, a layer the port does not model, and the absence of a hook
was read as the absence of a requirement. The same reading had been written down as the
open question on the Contact row of `tests/test_route_surface.py` ("upstream relies on
role permissions") since phase 4.

**Fix (14 Oct 2026):** `contact_has_permission` and `contact_query_conditions` in
`crm_app/permissions/platform_docs.py`, registered beside the Address rule: reads are
not narrowed, write and create are open to every role, delete is the creator's
(`owner`) or a System Manager's. Every door consults it: the resource route,
`frappe.client.delete`, the delete dialog and `delete_bulk_docs`, which refuses the
whole batch when one row is not the caller's. `SECURITY_MODEL.md` gains the Contact row;
`test_permissions.py` and `test_route_surface.py` move Contact to the ruled side, and
`docs/ROUTES.md` is regenerated. `CRM Organization` stays open on purpose: upstream gives
all three roles delete on it with no owner condition.

Covered by `tests/test_contact_delete_rule.py`.

---

## 87. Any CRM user could create, edit and delete email templates

**Block:** Settings → Email → Templates (S11), the role passes, 14 Oct 2026. As Grace
(Sales Manager) and as Ada (Sales User), New, an edit and Delete all succeeded.

**Why.** Upstream's `email_template.json` has two rows: `Desk User` with read only, and
`System Manager` with create, write, delete and the rest. `Desk User` is the role every
System User holds (`frappe/permissions.py:36`, `SYSTEM_USER_ROLE`), so every CRM user may
read and pick a template; only a System Manager may change one. CRM adds no permission of
its own - nothing in `hooks.py` or `install.py` touches the table, only a class override
and custom fields - and its Settings page lists Templates for every role, so upstream
shows a rep the page and refuses the writes. The port had no rule for `Email Template`,
and a doctype without one allows everything, so any CRM user could rewrite the wording of
mail sent in the company's name. Same shape as 86: upstream protection in the role
table, read as a missing hook. `test_route_surface.py` had carried the question on its
Email Template row since phase 4 ("writes change the wording of mail the system sends on
your behalf").

**Fix (14 Oct 2026):** `email_template_has_permission` and
`email_template_query_conditions` in `crm_app/permissions/platform_docs.py`: reads not
narrowed, so the list and the mail editor's picker keep working for everyone; create,
write and delete for System Manager. Registered beside the Contact rule; the resource
route and `frappe.client.set_value`, `rename_doc` and `delete`, which the Templates page
uses, all consult it. `SECURITY_MODEL.md` gains the section; Email Template moves to the
ruled side in `test_permissions.py` and `test_route_surface.py`; `docs/ROUTES.md` is
regenerated. Not a divergence: the port matches upstream's table exactly, unlike
`Email Account`, where managers may write (divergence 2).

Covered by `tests/test_email_template_rule.py`.

## 88. "Deals by territory" and "Deals by salesperson" plot the count and not the value

**Block:** none. Found 15 Oct 2026 reading `crm/api/dashboard.py` for finding 63, not in
the browser.

**Expected:** `get_deals_by_territory` and `get_deals_by_salesperson`
(`dashboard.py:1029-1147`) select `Count("*")` as `deals` and
`Sum(deal_value * IfNull(exchange_rate, 1))` as `value`, order by both, and return two
series: `deals` as bars on the left axis ("Number of deals") and `value` as a line on
the right ("Deal value (<symbol>)"), with the subtitles "Geographic distribution of
deals and revenue" and "Number of deals and total value per salesperson".

**Actual:** the port's two charts (`crm_app/api/dashboard.py`, `get_deals_by_territory`
and `get_deals_by_salesperson`) return one `count` series under "Count", and their own
subtitles. The upstream shape predates the port (it is in the February 2026 query-builder
refactor, `64097938d`), so this was a simplification at porting time, likely because
every rate was 1 then.

**Fix (15 Oct 2026):** `_deals_and_value` in `crm_app/api/dashboard.py` counts the deals
and sums `deal_value * exchange_rate` per territory or owner, most deals first, then most
value; the two charts return upstream's series, axes, titles and subtitles, "Empty" for a
deal with no territory and the owner's full name for a salesperson. One difference kept on
purpose: the port's queryset is permission-filtered, as every chart here is, where
upstream reads the table directly. Covered by
`tests/test_dashboard_charts.py::test_deals_by_territory_and_salesperson_carry_count_and_value`.

## 89. The average deal value cards were not upstream's

**Block:** none. Found 15 Oct 2026 by the review of findings 63 and 64 (a fresh Claude
reviewer; Codex was unavailable).

**Expected:** `dashboard.py:197-424`. "Avg. deal value" averages ongoing and won deals,
leaving lost ones out (`Status.type != "Lost"`, `:387`). The titles are "Avg. deal
value", "Avg. won deal value" and "Avg. ongoing deal value", with the tooltips "Average
deal value of ongoing & won deals", "Average deal value of won deals" and "Average deal
value of non won/lost deals". Each delta is `current - previous if previous else 0`, and
only the first card sends `deltaSuffix: "%"`.

**Actual:** the first card averaged every deal, so one large lost deal raised it; the
three had the port's own titles and tooltips; and every delta was a percentage with `%`.

**Fix (15 Oct 2026):** the filter, the six strings and the delta in
`crm_app/api/dashboard.py:_average_value` and its three callers. The `%` after an amount
is upstream's mistake, reproduced: `UPSTREAM_BUGS.md` 51. Covered by
`tests/test_exchange_rate.py::test_the_average_cards_are_upstreams` and
`::test_a_lost_deal_is_left_out_of_the_average`.

## 90. The country and currency data came from the framework's `develop` branch

**Block:** none. Found 15 Oct 2026 by the same review.

**What:** `crm_app/data/country_info.json`, copied for finding 45 and used again for 63,
was byte-identical to the framework's `develop` copy. Against version-15, which CRM's CI
pairs with, two entries differ: the country "Türkiye" is "Turkey", and Turkmenistan's
currency is TMM ("m", "Tennesi"), not TMT. The cause is the checkout: the framework
clone this port reads is on `develop`, not `version-15`. Reading it with
`git show version-15:<path>` gives the right files whichever branch is checked out.

**Fix (15 Oct 2026):** the version-15 file. A database seeded before keeps "Türkiye" and
TMT beside the new "Turkey" and TMM, since the seeds add missing rows and delete nothing.
Two other things the review found came from reading `develop`, and are corrected in the
same change: the Currency rule cited a `Desk User` `select` row that version-15's
`currency.json` does not have, so reading is now for the roles that table names; and
`add_currencies` noted an escaping of `number_format` that only `develop` does.

## 91. No SLA is ever applied to a lead or deal

**Block:** none on a screen. Found 15 Oct 2026 while comparing Assignment Rules with
upstream (finding 80), whose conditions share the SLA's format. Not recorded anywhere
before.

**Expected:** `crm_lead.py:84-85,106-107,387-410` and `crm_deal.py:86-87,110-111,202-220`.
`before_validate` runs `set_sla`, which picks the first enabled SLA whose condition the
document meets (`crm_service_level_agreement/utils.py:get_sla`, the condition run with
`frappe.safe_eval`), and `before_save` runs `apply_sla`, which hands the document to the
SLA's `apply` (`crm_service_level_agreement.py:74-359`): the response deadline from the
priority's response time within working hours and outside the holiday list, the first
response and its time, rolling responses, and the SLA status (First Response Due,
Rolling Response Due, Fulfilled, Failed). All of it is computed on write; there is no
scheduled job (`PHASE_5_ASYNC.md` §4).

**Actual:** `apply_sla` in `crm_app/models/core_sales.py` is the phase-1 placeholder
("PHASE 5 seam ... Phase 5 fills this in") and returns `None`, and there is no `set_sla`.
Phase 5 settled the design and asserted that no SLA job is scheduled, but never filled
the seam. So no lead or deal ever gets an SLA, a response deadline or an SLA status,
whatever the SLA Policies screen saves.

**Reach:** the SLA columns on lists and the SLA panel on a lead or deal stay empty.
Lead conversion sets the communication status to Replied only on a lead with an SLA,
so that branch never runs. The communication status from finding 60 is written, but the
page shows it only beside an SLA, so the S20 check needs this, or a look at the database.

**Decisions, 15 Oct 2026, with the owner:**

* **Conditions** are evaluated from the JSON form with no code run, by the evaluator
  built for finding 80; an SLA whose condition exists only as code is refused on save,
  saying only conditions built on the screen are supported. An SLA with no condition,
  the default one included, is unaffected. Upstream's save-time check ("The Condition
  '{0}' is invalid: {1}") still applies to the JSON form. The dev database's one SLA has
  no condition, so nothing stored breaks.
* **Time zone:** upstream counts "now", working hours and holidays in System Settings'
  `time_zone`, set by Frappe's setup wizard (`get_system_timezone`,
  `frappe/utils/data.py:324-326`, version-15, "Asia/Kolkata" only when unset). The port
  has no wizard and no such field, so the site's `TIME_ZONE` setting is the time zone, not
  a fallback: made readable from `.env`, added to `.env.example`, `UTC` when unset as
  today, and listed under "before you deploy", since working hours meant as local time
  are wrong by the zone's offset under `UTC`. Deadlines are stored in UTC and computed
  in that zone. The boot call already reports the same setting as the system zone.
* **Its own pull request**, after finding 80's, on its own branch.

**Status:** open; decided 15 Oct 2026 to build it after finding 80: SLA conditions are
stored in the same two forms as assignment conditions, and one evaluator serves both.
Upstream's engine is about 420 lines; an estimate like finding 80's, one to two days.
