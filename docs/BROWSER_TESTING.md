# Browser testing log

What a person clicked in the Vue app against the Django backend, and what happened.
`ROUTES.md` is the machine inventory (every endpoint, with the http suite's marks); this
file is the human one: one table per screen, one row per user action. A failure gets a
number in `FINDINGS.md`, the same numbering the http suite uses, and the row points at it.

**How to read a row.** *How* is the one-line recipe. *Calls* are the backend methods the
action fires, so a failure can be traced from the Network tab to `ROUTES.md`. *Result* is
`ok`, `failed` or `skipped` with a word why; blank means not yet done. *Finding* is the
`FINDINGS.md` number when it failed. *Auto* marks the rows the Playwright suite also
covers (`frontend/tests/e2e`), filled in once that suite is green.

## Session

| | |
|---|---|
| Date | 29 Sep 2026 |
| Branch, commit | `phase-8-followup`, ede1206 plus the uncommitted fixes for findings 45 to 49 |
| Account | `Administrator` (System Manager); role passes come later, see the end |
| Servers | Django `runserver` on 8000, `yarn dev` on 8080 |
| Database | the local demo data, migrated to `frappe_platform` 0010 and `crm_app` 0010, `seed_defaults` applied |

**Load time.** The app is slow to load throughout these passes. Logged as finding 55 and
`specs/KNOWN_ISSUES.md` 9, and deliberately left alone until the testing is finished and
the branch is merged.

## Coverage

Kept current by `backend/scripts/browser_coverage.py`, which also fills the API
coverage section at the end; run it after recording results.

<!-- coverage:start -->
| Screens done | Rows ok | Rows failed | Rows skipped | Endpoints confirmed |
|---|---|---|---|---|
| 9 of 12 with rows | 151 | 6 | 0 | 84 of 102 |
<!-- coverage:end -->

Screens planned: Notes, Tasks, Call Logs, Leads, Deals, Contacts, Organizations,
Dashboard, Settings, Sign in and out. The `/api/resource/` routes (45 doctypes) are not in this
log: the Vue app never calls them (it reads and writes through `frappe.client.*` and
`crm.api.doc.*`), so the http suite covers them and `ROUTES.md` carries those marks.

## App boot (any page)

The calls the shell makes on every load after sign-in, before a screen's own. Recorded
from the Notes pass; every one answered 200.

| # | Action | How | Calls | Result | Finding | Auto |
|---|---|---|---|---|---|---|
| B1 | Page load | Sign in, or reload any page; the sidebar, the user menu and the notification bell render | `crm.www.crm.get_context_for_dev`, `frappe.utils.telemetry.pulse.client.boot_config`, `crm.api.session.get_users`, `frappe.client.get_single_value`, `crm.api.notifications.get_notifications`, `crm.integrations.api.is_call_integration_enabled`, `frappe.client.get`, `frappe.apps.get_apps`, `crm.api.views.get_views` | ok | 50 (icon only) | e2e |
| B2 | Getting started panel | Shown to every CRM user on the desktop sidebar while their stored status (`User.onboarding_status`) has an unfinished step, and the panel opens by itself on each load until then; a Sales User gets 8 steps, a manager 9 (Invite your team). Steps link to your first lead and first deal. Done or skipped, the sidebar shows Help instead; the panel's ⋯ → Reset onboarding steps brings it back. The browser caches the status per user (`localStorage` `onboardingStatus`, `isOnboardingStepsCompletedfrappecrm<user>`), so a user whose row says all done opens to an empty panel once on a fresh browser (upstream 49). "Clear demo data" shows only when the site says demo data was created, which the local port does not | `crm.api.onboarding.get_first_lead`, `crm.api.onboarding.get_first_deal`, `crm.demo.api.clear_demo_data` | ok | upstream 49 | |

## Notes (`/crm/notes`)

| # | Action | How | Calls | Result | Finding | Auto |
|---|---|---|---|---|---|---|
| N1 | List loads | Sidebar → Notes; cards show, or "No Notes Found" | `crm.api.doc.get_data`, `getdoctype`, `get_filterable_fields`, `get_quick_filters`, `sort_options`, `crm.api.views.get_views` | ok | | e2e |
| N2 | Create | Create → title "Test note 1", a line of body → Create; the card appears | `get_fields_layout`, `frappe.client.insert`, `get_data` | ok | | e2e |
| N3 | Open and edit | Click the card → "Edit Note" → change the title → Update; the card shows the new title | `frappe.client.get`, `get_doc_permissions`, `get_assigned_users`, `frappe.client.get_list`, `frappe.client.set_value` | ok | | |
| N4 | Delete | Three-dots on the card → Delete (no confirmation); the card is gone | `frappe.client.delete` | ok | | |
| N5 | Search, filter, sort | Type in the search box; Filter → add one; Sort → pick a field; the cards follow, and the view keeps the choice | `create_or_update_standard_view`, `get_data`, `crm.api.views.get_views` | ok | | |
| N6 | Reload | The refresh button beside the view name | `get_data` | ok | | |
| N7 | Add and remove a quick filter | Gear beside the quick filters → tick a field → Save; then untick it → Save | `update_quick_filters`, `get_quick_filters` | ok | | |
| N8 | Edit the create dialog's layout | Create → gear icon → move a field → Save; the dialog reopens with the new order | `get_fields_layout`, `save_fields_layout` | ok | | |
| N9 | Picture in a note | Create or edit → image button in the editor → pick a PNG; it appears in the body | `upload_file` | ok (after the fix; failed before it: "Method upload_file not found") | 49 (fixed) | |
| N10 | Reference fields | Create → gear → add "Reference Document Type" and "Reference Doc" → Save; Create → pick "CRM Lead" in the first, a lead in the second → Create; the note shows on that lead's Notes tab | `search_link` (DocType, then the chosen doctype), `frappe.client.insert` | ok (after the fix; failed before it: the Reference Document Type dropdown was empty) | 54 (fixed) | |
| N11 | Remove a picture before saving | Edit a note that has a picture in its body → delete the picture in the editor → Update; the file goes with it | `crm.api.delete_attachment` | ok | | |

The `search_link`, `getdoctype` and `frappe.client.insert` 404s seen in this pass all
came from N10 (finding 54). The manifest icon 404 on every load is finding 50.

## Tasks (`/crm/tasks`)

| # | Action | How | Calls | Result | Finding | Auto |
|---|---|---|---|---|---|---|
| T1 | List loads | Sidebar → Tasks; rows show, or "No Tasks Found" | `get_data`, `getdoctype`, `get_filterable_fields`, `get_quick_filters`, `sort_options`, `crm.api.views.get_views` | ok | | e2e |
| T2 | Create | Create → title "Test task 1", a priority, a due date, Assigned To yourself → Create; the row appears | `get_fields_layout`, `search_link` (User, finding 46), `frappe.client.insert`, `get_data` | ok | | e2e |
| T3 | Open and edit | Click the row → "Edit Task" → Status "Todo" → Update | `frappe.client.get`, `frappe.client.set_value` | ok | | e2e (open only) |
| T4 | Kanban move | View dropdown → Kanban → drag the task to another column → back to List; the status changed | `get_data` (kanban), `frappe.client.set_value` | ok | | |
| T5 | Delete | Tick the row → Delete in the bar; the row is gone | `frappe.client.delete` | ok | | |
| T6 | Export | Three-dots beside the view name → Export → Excel or CSV → Export; a file downloads with the list's columns | `frappe.desk.reportview.export_query` | ok (after the fix; failed before it: no file, the method was not served) | 51 (fixed) | |
| T7 | Bulk edit | Tick two rows → Edit in the bar → Field "Priority", Value "High" → Update; both rows change | `crm.api.doc.get_fields`, `submit_cancel_or_update_docs` | ok (after the fix; failed before it: the Field dropdown was empty, 52) | | |
| T8 | Kanban cards | View dropdown → Kanban; each card shows the title, the description, the priority icon, its age, and a button to the linked lead or deal when there is one | `get_data` (kanban) | ok (after the fix; failed before it: title and the task's id number only, 53) | | |
| T9 | Bulk delete | Tick several rows → Delete in the bar → confirm; the rows are gone | `crm.api.doc.delete_bulk_docs` | ok | | |
| T10 | Columns | Gear at the end of the header row → add, remove and reorder columns → Apply; then Reset to Default; the list follows each time | `create_or_update_standard_view`, `crm.fcrm.doctype.crm_view_settings.crm_view_settings.update`, `get_data` | ok | | |
| T11 | Filter and sort | Filter → add one on a field, edit its value, remove it; Sort → pick a field and a direction, change it; the rows follow | `get_filterable_fields`, `sort_options`, `search_link`, `create_or_update_standard_view`, `get_data` | ok | | |
| T12 | Save a view and edit it | Three-dots beside the view name → Save as new view → name it → Save; it appears in the view dropdown; Edit → rename → Save | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.create`, `crm.fcrm.doctype.crm_view_settings.crm_view_settings.update`, `crm.api.views.get_views` | ok | | |
| T13 | Make a view public, pin it | View dropdown → three-dots on the saved view → Make Public; Pin View; it moves to the Public and Pinned groups and shows in the sidebar | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.public`, `crm.fcrm.doctype.crm_view_settings.crm_view_settings.pin` | ok | | |
| T14 | Default view, delete a view | Switch to Kanban → three-dots beside the view name → Set As Default; reopening Tasks lands on the kanban. Three-dots → Duplicate → a name → Create; on the copy, three-dots → Delete View → confirm; it leaves the dropdown | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.set_as_default`, `crm.fcrm.doctype.crm_view_settings.crm_view_settings.create`, `crm.fcrm.doctype.crm_view_settings.crm_view_settings.delete` | ok | | |
| T15 | Kanban column settings | In Kanban → the dot on a column header → a colour → Apply; three-dots on a header → Delete hides it; drag a header to reorder; Add Column brings the hidden one back; Reload Columns refetches them. The gear beside the view name → Kanban Settings → Title Field, Fields Order → Apply | `fetch_and_update_kanban_columns`, `create_or_update_standard_view` | ok | | |
| T16 | Bulk assign | Tick rows → Edit → Field "Assigned To", a user → Update; the rows show the assignee. The task list hides the Assign To and Clear Assignment menu items (`TasksListView.vue`, as upstream), so those two belong to the Leads and Deals rows | `submit_cancel_or_update_docs` | ok | | |
| T18 | Bulk unassign | Tick assigned rows → Edit → "Assigned To", leave the value empty → Update; the assignee should be gone | not traced |  | 70 | |
| T17 | Reference fields | As N10 on the task dialog; the task shows on that lead's Tasks tab | `search_link` (DocType, then the chosen doctype), `frappe.client.insert` | ok (after the fix; failed before it: the Reference Document Type dropdown was empty) | 54 (fixed) | |

## Call Logs (`/crm/call-logs`)

| # | Action | How | Calls | Result | Finding | Auto |
|---|---|---|---|---|---|---|
| C1 | List loads | Sidebar → Call Logs; rows show, or "No Call Logs Found" | `get_data`, `getdoctype`, `get_filterable_fields`, `get_quick_filters`, `sort_options`, `crm.api.views.get_views` | ok | | e2e |
| C2 | Create | Create → Type Outgoing, From `+91 98 1`, To `+91 98 2`, Status Completed, Duration 90, Caller yourself → Create; the row appears | `get_fields_layout`, `search_link` (User), `frappe.client.insert`, `get_data` | ok | | |
| C3 | Open | Click the row → "Call Details" | `crm.fcrm.doctype.crm_call_log.crm_call_log.get_call_log` | ok | | e2e |
| C4 | Edit | In Call Details → pencil "Edit Call Log" → change Duration → Update | `frappe.client.get`, `frappe.client.set_value` | ok | | |
| C5 | Add a note to the call | Call Details → Options → Add Note → write one → save; it shows in the details | `crm.integrations.api.add_note_to_call_log` | ok | | |
| C6 | Add a task to the call | Call Details → Options → Add Task → save; it shows in the details | `crm.integrations.api.add_task_to_call_log` | ok | | |
| C7 | Create a lead from the call | Call Details → Create Lead; the new lead's page opens | `crm.fcrm.doctype.crm_call_log.crm_call_log.create_lead_from_call_log` | ok | | |
| C8 | Delete | Tick the row → Delete in the bar | `frappe.client.delete` | ok | | |
| C9 | Bulk edit and bulk delete | Tick rows → Edit → a field and a value → Update; tick rows → Delete → confirm | `crm.api.doc.get_fields`, `submit_cancel_or_update_docs`, `crm.api.doc.delete_bulk_docs` | ok | | |
| C10 | Filter, sort, columns | As T10 and T11 on this list, including Reset to Default | `get_filterable_fields`, `sort_options`, `create_or_update_standard_view`, `crm.fcrm.doctype.crm_view_settings.crm_view_settings.update`, `get_data` | ok | | |
| C11 | Saved view, public, pinned | As T12 and T13 on this list | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.create`, `crm.fcrm.doctype.crm_view_settings.crm_view_settings.public`, `crm.fcrm.doctype.crm_view_settings.crm_view_settings.pin`, `crm.api.views.get_views` | ok | | |
| C12 | Reference fields | As N10 on the call log dialog; the call shows on that lead's Calls tab | `search_link` (DocType, then the chosen doctype), `frappe.client.insert`, `crm.api.activities.get_activities` | ok (after two fixes; failed before them: first the Reference Document Type dropdown was empty, 54; then the reference saved but the call did not show on the lead's Calls tab, 69) | 54 (fixed), 69 (fixed) | |

## Leads (`/crm/leads`)

Example record: Ms Priya Sharma, `priya.sharma@example.com`, +91 98765 00011, Female;
organization "Sharma Textiles" (typed, it is a text field on a lead), website
`sharmatextiles.example.com`, 51-200 employees, territory Karnataka, annual revenue
500000, any industry; status New, lead owner yourself. Make a second lead the same way
for the bulk rows, and keep one unconverted for L21.

| # | Action | How | Calls | Result | Finding | Auto |
|---|---|---|---|---|---|---|
| L1 | List loads | Sidebar → Leads; rows show, or "No Leads Found" | `get_data`, `getdoctype`, `get_filterable_fields`, `get_quick_filters`, `sort_options`, `crm.api.views.get_views` | ok | | e2e |
| L2 | Create | Create → Salutation, First Name, Last Name, Email, Mobile No, Gender, Organization, Website, No. of Employees, Territory, Annual Revenue, Industry, Status, Lead Owner → Create; the lead's page opens. Without a First Name the dialog refuses | `get_fields_layout`, `search_link` (Salutation, Gender, CRM Territory, CRM Industry, User), `frappe.client.insert` | ok | | e2e |
| L3 | Open | Click the row; the header shows the assignees and the status, the tabs run Activity to Attachments, and the side panel shows the fields | `frappe.client.get`, `get_sidepanel_sections`, `crm.api.activities.get_activities`, `crm.api.doc.get_assigned_users`, `frappe.client.get_doc_permissions` | ok | | e2e |
| L4 | Edit side-panel fields | Side panel → change Mobile No, Website and Annual Revenue; each saves when the field loses focus, and the Activity tab records the change | `frappe.client.set_value` | ok | | |
| L5 | Status | The status button in the header → Contacted, then Nurture; the button follows and the Activity tab records each change | `frappe.client.set_value` | ok | | e2e |
| L6 | Assign | The assign button in the header → pick a user → Update; the avatar shows. Open it again → remove that user → Update | `frappe.desk.form.assign_to.add`, `crm.api.doc.remove_assignments`, `crm.api.doc.get_assigned_users` | ok | | |
| L7 | Picture | Hover the avatar → Upload Image → pick one; then Change Image; then Remove Image | `upload_file`, `frappe.client.set_value` | ok | 49 (fixed) | |
| L8 | Comment | Comments tab → New Comment → some text with an `@` mention of another user → Comment; it shows on the Comments tab and in Activity | `crm.api.comment.add_comment` | ok | | |
| L9 | Note on the lead | Notes tab → New Note → a title and a body → Create; open it → change it → Update; three-dots → Delete | `frappe.client.insert`, `frappe.client.set_value`, `frappe.client.delete` | ok | | |
| L10 | Task on the lead | Tasks tab → New Task → a title, an assignee, a due date → Create; change its status from the row; delete it | `frappe.client.insert`, `frappe.client.set_value`, `frappe.client.delete` | ok | | |
| L11 | Call log on the lead | Calls tab → Log a Call → type, numbers, duration → Create; the call shows on the tab; click it for its detail | `frappe.client.insert`, `crm.api.activities.get_activities`, `crm.fcrm.doctype.crm_call_log.crm_call_log.get_call_log` | ok | 69 (fixed), 72 | |
| L12 | Attachment | Attachments tab → Upload Attachment (or the paperclip in the side panel) → pick a file → Upload; it lists; the lock icon switches it between private and public; the bin deletes it | `crm.api.get_file_uploader_defaults`, `upload_file`, `frappe.client.set_value`, `frappe.client.delete` | ok | 49 (fixed) | |
| L13 | Email | Needs an outgoing email account (S10). Emails tab → New Email → To, Subject, a body → Send; it shows on the Emails tab | `crm.api.get_user_signature`, `frappe.email.doctype.email_template.email_template.get_email_template`, `frappe.core.doctype.communication.email.make`, `crm.api.contact.search_emails` | ok: the email shows on the Emails tab; delivery waits for the Celery worker, which was not running | | |
| L14 | Data tab | Data tab → change two fields → the "Not Saved" badge shows → Save; reload and they are kept | `get_fields_layout`, `frappe.client.set_value` | ok | | |
| L15 | Side-panel layout | The pencil above the side panel fields (Edit Fields Layout) → move a field or add one → Save; the panel redraws | `get_sidepanel_sections`, `save_fields_layout` | ok | | |
| L16 | List tools | Filter, sort, columns, quick filters and a saved view, as T10 to T13 | `get_filterable_fields`, `sort_options`, `create_or_update_standard_view`, `get_data` | ok | | |
| L17 | Group By and Kanban | View dropdown → Group By → pick a field; then Kanban → drag a card to another status column; the lead's status follows | `get_data`, `frappe.client.set_value`, `crm.api.doc.get_group_by_fields` | ok | | |
| L18 | Bulk edit, assign, clear | Tick two rows → Edit → a field and a value → Update. Tick again → Assign To → a user → Update. Tick again → Clear Assignment → confirm | `submit_cancel_or_update_docs`, `frappe.desk.form.assign_to.add_multiple`, `frappe.desk.form.assign_to.remove_multiple` | ok | 71 | |
| L19 | Convert to Deal | On a lead's page → Convert to Deal → leave Organization and Contact as new (or switch on Choose Existing and pick one) → Convert; the new deal's page opens, and the lead leaves the leads list | `get_fields_layout`, `crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal` | ok (after the fix; failed before it: "Error converting to deal: Internal Server Error") | 73 (fixed) | |
| L20 | Bulk convert | Tick two leads → Convert to Deal in the bar → confirm; both become deals | `crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal` | ok | | |
| L21 | Delete | On an unconverted lead's page → the bin in the side panel → the dialog lists what links to it → Delete; back on the list, the row is gone | `crm.api.doc.get_linked_docs_of_document`, `frappe.client.delete` | ok | | e2e |
| L22 | Bulk delete | Tick rows → Delete in the bar → confirm; the rows are gone | `crm.api.doc.delete_bulk_docs` | ok | | |
| L23 | Like a lead | Columns gear → add "Like" → a heart column appears. The heart on a row → it fills red; the heart in the column header → only liked rows stay (it is the `_liked_by` filter); the header heart again → all rows; the row heart again → unliked | `frappe.desk.like.toggle_like`, `get_data` | ok, and the same on the Deals list | | |

The WhatsApp tab and Make a Call belong to the integrations and are out of scope.

## Organizations (`/crm/organizations`)

Example record: "Acme Test Org", website `acme-test.example.com`, annual revenue 250000,
11-50 employees, industry Technology, address "Acme HQ" (Office, 12 MG Road, Bengaluru,
Karnataka, India, 560001).

| # | Action | How | Calls | Result | Finding | Auto |
|---|---|---|---|---|---|---|
| O1 | List loads | Sidebar → Organizations; rows show, or "No Organizations Found" | `get_data`, `getdoctype`, `get_filterable_fields`, `get_quick_filters`, `sort_options`, `crm.api.views.get_views` | ok | | e2e |
| O2 | Create | Create → Organization Name, Website, Annual Revenue, Territory, No. of Employees, Industry → Create; the organization's page opens | `get_fields_layout`, `search_link` (CRM Territory, CRM Industry), `frappe.client.insert` | ok | | e2e |
| O3 | Address from the field | On the page → side panel → Address → Create New → Address Title "Acme HQ", Type Office, line 1, City, State, Country, Pincode → Create; the field shows "Acme HQ-Office" | `get_fields_layout`, `search_link` (Address, Country), `frappe.client.insert`, `frappe.client.set_value` | ok | 45 (fixed) | e2e |
| O4 | Open | Click the row; the side panel shows the fields, with the Deals and Contacts tabs beside it | `frappe.client.get`, `get_sidepanel_sections`, `frappe.client.get_list` | ok | | e2e |
| O5 | Edit a field | Side panel → change Website and No. of Employees; each saves when the field loses focus | `frappe.client.set_value` | ok | | |
| O6 | Rename | Side panel → Organization Name → "Acme Test Org 2" → click away; the page title and the URL change to the new name, and the list shows it | `frappe.client.rename_doc` | ok | | |
| O7 | Logo | Hover the avatar → Upload → pick an image; it shows on the page and in the list | `upload_file`, `frappe.client.set_value` | ok | 49 (fixed) | |
| O8 | List tools | Filter, sort, columns and a saved view, as T10 to T13 | `get_filterable_fields`, `sort_options`, `create_or_update_standard_view`, `get_data` | ok | | |
| O9 | Delete | On the page → Delete → the dialog lists what links to it → "Delete" the linked items → Delete; back on the list, the row is gone | `crm.api.doc.get_linked_docs_of_document`, `frappe.client.delete` | ok | | |
| O10 | Unlink before delete | With a deal linked to the organization: Delete → "Unlink all" → the deal should leave the list so the organization can be deleted | `crm.api.doc.remove_linked_doc_reference` | failed: the deal stays linked; the same happens upstream (upstream bug 42) | 56 | |
| O11 | Territory | In the create dialog or the side panel → Territory → Create New → "India" as a group, then "Karnataka" with parent India → pick it; the field keeps it | `search_link` (CRM Territory), `get_fields_layout`, `frappe.client.insert`, `frappe.client.set_value` | ok | | |
| O12 | Edit the address | Side panel → Address → Edit → change the lines → Update; reopening Edit shows the new values (the field keeps showing the record's id, which is set once at creation) | `frappe.client.get`, `frappe.client.set_value` | ok | | |
| O13 | A deal on the organization | Deals → Create → pick this organization → Create; the deal shows on the organization's Deals tab | `crm.fcrm.doctype.crm_deal.crm_deal.create_deal`, `frappe.client.get_list` | ok | | |
| O14 | Remove the logo | With a logo set: hover the avatar → Remove Image; the avatar goes back to the initials, on the page and in the list | `frappe.client.set_value` | ok (after the fix; failed before it: the logo stayed, Change Image worked) | 68 (fixed) | |

## Contacts (`/crm/contacts`)

Example record: Mr Ravi Test, `ravi.test@example.com`, +91 98765 43210, Male, company
"Acme Test Org", designation Purchase Manager, address "Acme HQ-Office". Salutation and
Gender are dropdowns, as upstream, since finding 66 (1 Oct 2026); before it they were
text boxes here.

| # | Action | How | Calls | Result | Finding | Auto |
|---|---|---|---|---|---|---|
| K1 | List loads | Sidebar → Contacts; rows show, or "No Contacts Found" | `get_data`, `getdoctype`, `get_filterable_fields`, `get_quick_filters`, `sort_options`, `crm.api.views.get_views`, `crm.api.session.get_organizations` | ok | | e2e |
| K2 | Create | Create → Salutation, First Name, Last Name, Email, Mobile No, Gender, Company Name, Designation, Address → Create; the contact's page opens | `get_fields_layout`, `search_link` (Address), `frappe.client.insert` | ok | 44 (labels, open) | e2e |
| K3 | Open | Click the row; the side panel shows the fields, with the Deals tab beside it | `frappe.client.get`, `get_sidepanel_sections`, `crm.api.contact.get_linked_deals` | ok | | e2e |
| K4 | Edit a field | Side panel → change Designation and Mobile No; each saves when the field loses focus | `frappe.client.set_value` | ok | | |
| K5 | Picture | Hover the avatar → Upload → pick an image | `upload_file`, `frappe.client.set_value` | ok | 49 (fixed) | |
| K6 | List tools | Filter, sort, columns and a saved view, as T10 to T13 | `get_filterable_fields`, `sort_options`, `create_or_update_standard_view`, `get_data` | ok | | |
| K7 | Delete | On the page → Delete → the dialog lists what links to it → Delete; back on the list, the row is gone | `crm.api.doc.get_linked_docs_of_document`, `frappe.client.delete` | ok | | |
| K8 | Quick filters | The contacts list shows three quick filters, as upstream: Status (Passive, Open, Replied), Email Address, Phone. Status and Email Address narrow the list; Phone finds nothing for a number added in the CRM, here and upstream (K11, upstream bug 44) | `get_quick_filters`, `get_data` | ok | 44 (fixed) | |
| K9 | A second email and number | On the page → Email dropdown → add an address → it lists; click one to make it primary; same for Mobile No | `crm.api.contact.create_new`, `crm.api.contact.set_as_primary` | ok (after the fix; failed before it: the new number was added but could not be picked) | 67 (fixed) | |
| K10 | Edit and remove a number or an address | In either dropdown → pencil on a row → change it → save; x on a row → it is gone; the field above follows when the row was the primary | `frappe.client.set_value`, `frappe.client.delete` | ok | 67 (fixed) | |
| K11 | Filter by number | Filter → Mobile No → part of the number; the contact is found. The Phone quick filter finds nothing for a number added in the CRM, here and upstream: it reads a different column (upstream bug 44) | `get_data` | ok | | |

## Settings (user menu → Settings)

One row per section of the dialog, in its own order. The four Integrations sections
(Telephony, WhatsApp, ERPNext, Lead Syncing) are out of scope, as in the API coverage.
Everything below System Configuration is shown to managers only.

| # | Action | How | Calls | Result | Finding | Auto |
|---|---|---|---|---|---|---|
| S1 | Profile | Profile → change first and last name → Save; upload a picture; Change Password → a new one twice → Update, then sign in with it | `frappe.client.set_value`, `upload_file`, `crm.api.user.change_password` | ok | | e2e (opens) |
| S2 | Preferences | Preferences → pick another time zone → Save; reload and it is kept | `frappe.core.doctype.user.user.get_timezones`, `frappe.client.get`, `frappe.client.set_value` | ok | | |
| S17 | Language | Preferences → Language → the dropdown lists languages by name → pick one → Save; the page reloads and the choice is kept (the interface stays in English: no translations are shipped) | `search_link` (Language), `frappe.client.set_value` | ok (after the fix; failed before it: the dropdown was empty, 58) | | |
| S18 | Theme | Preferences → Theme → light, dark, system; the app repaints at once and keeps the choice after a reload | none, the choice is kept in the browser | ok | | |
| S3 | General | General → Timeline timestamp format (Relative, Exact) and Timeline sort order (Oldest First, Newest First); each saves at once; a lead's or deal's activity timeline follows | `frappe.client.get`, `frappe.client.set_value` | ok | | |
| S19 | Update timestamp on new communication | With a Celery worker running: switch on → comment on an old lead → its Last Modified becomes "just now" and it rises in the list; switch off → a comment leaves it where it was | `frappe.client.set_value`, `crm.api.comment.add_comment` | ok (with a worker the lead's Last Modified moves; without one it does not, the job waits in the queue) | | |
| S20 | Mark as replied, reopen on new communication | The two switches save. Upstream then sets the lead's or deal's communication status to Replied when an email is sent and to Open when one is received, where an SLA applies | `frappe.client.set_value` |  | 60 | |
| S4 | Dashboard switches | Dashboard → Enable Forecasting on → Update → a deal without an Expected Closure Date is refused; Auto Update Expected Deal Value on → a deal's products set its expected value | `frappe.client.set_value` | failed: Update refuses with "Please select a currency before saving"; the Dashboard section needs a currency once forecasting is on, and the port has no Currency doctype to pick one from (63) | 63 | |
| S21 | Dashboard currency and provider | Dashboard → Dashboard Currency → pick one; Exchange Rate Provider → pick one → Update | `search_link` (Currency), `frappe.client.set_value` | failed: the currency dropdown lists nothing, and the provider select stays disabled because no currency is set | 63 | |
| S5 | Defaults | Defaults → the date, time and number formats load; change one → Update | `getdoctype`, `frappe.client.get`, `frappe.client.set_value` | failed: the section goes blank when opened | 64 | |
| S6 | Brand | Brand → a brand name, a logo, a favicon → Update; the sidebar header shows them, and shows them to every other account too (sign in as Ada to check) | `upload_file`, `frappe.client.set_value` | ok; retest as Ada after 85 | 85 (fixed) | |
| S7 | Users | Users → the list shows; change one user's role; Add Existing User → pick one → Add; Remove on a user | `crm.api.session.get_users`, `crm.api.user.update_user_role`, `crm.api.user.add_existing_users`, `crm.api.user.remove_crm_roles_from_user` | ok | | |
| S8 | Invite User | Invite User → an address, a role → Send Invites; it shows under Pending Invites; delete the invite | `crm.api.invite_by_email`, `frappe.client.get_list`, `frappe.client.delete` | ok: the invite shows and can be deleted; the mail itself went to the worker's console, not to Gmail, since system mail uses Django's EMAIL_BACKEND, the console locally | 79 | |
| S9 | Sales Hierarchy | Sales Hierarchy → add a user under a manager; move one; the tree redraws | `frappe.client.get_list`, `frappe.client.insert`, `frappe.client.set_value` | ok | | |
| S10 | Email accounts | Email → Accounts → Add → a service, an address, a password, Enable Outgoing ticked → Add; open it → change a field → Update. Then go back to S16: Profile → Email Settings → Add Email should now list this account | `crm.api.settings.create_email_account`, `frappe.client.set_value`, `frappe.client.rename_doc` | ok (after the fix and the key; failed before them: "invalid credentials" with a correct Gmail app password, the server had no encryption key) | 65 (fixed) | |
| S11 | Email templates | Email → Templates → New → a name, a subject, a body → Create; open it → rename → Update; delete it | `frappe.client.get_list`, `frappe.client.insert`, `frappe.client.rename_doc`, `frappe.client.delete` | ok | | |
| S12 | Assignment rules | Assignment Rules → New → a name, a condition, users → Create; toggle it off; Duplicate; rename; delete | `crm.api.assignment_rule.get_assignment_rules_list`, `frappe.client.insert`, `frappe.client.set_value`, `crm.api.assignment_rule.duplicate_assignment_rule`, `frappe.client.rename_doc`, `frappe.client.delete` |  | 80 | |
| S13 | SLA policies | SLA Policies → New → a name, priorities, working hours → Create; open it → rename → Update | `frappe.client.get_list`, `frappe.client.insert`, `frappe.client.get`, `frappe.client.rename_doc` | ok | | |
| S14 | Home actions | Home Actions → add an item with a label and a link → Update; it shows in the user menu | `frappe.client.set_value` | ok | | |
| S15 | Signature | Profile → Email Settings → type a signature → Update; a new email on a lead or deal starts with it | `frappe.client.get`, `frappe.client.set_value` | ok | | |
| S16 | Add Email in the profile | After S10: Profile → Email Settings → Add Email → pick the outgoing account → Update; reload and the row is still there; the composer's From offers it | `frappe.client.get_list`, `frappe.client.set_value` | ok (after the fix; failed before it: the pick had nowhere to be stored) | 57 (fixed) | |
| S22 | Duplicate an SLA policy | SLA Policies → three-dots on a policy → Duplicate → a name → Duplicate; the copy opens, with the same priorities and working hours and Set as default off | `frappe.client.get`, `frappe.client.insert` | ok (after the fix; failed before it: nothing happened, the fetched document had no doctype) | 82 (fixed) | |

## Notifications (sidebar → Notifications)

To have one to look at: sign in as another user, assign a lead to yourself-as-admin or
mention that user in a comment (`@name`), then sign back in.

| # | Action | How | Calls | Result | Finding | Auto |
|---|---|---|---|---|---|---|
| NT1 | Open the panel | Sidebar → Notifications; a panel slides out beside the sidebar with your notifications, or "No New Notifications"; the badge counts the unread ones | `crm.api.notifications.get_notifications` | ok (after the fix; failed before it: nothing happened on the click) | 61 (fixed), 62 | |
| NT2 | Open a notification | Click a row; the lead or deal it is about opens and the row is no longer marked unread | `crm.api.notifications.mark_as_read` | ok | | |
| NT3 | Mark all as read | The tick icon at the top of the panel; the badge clears | `crm.api.notifications.mark_as_read` | ok | | |
| NT4 | A notification arrives | With the panel closed, have another user assign you a lead; the badge goes up without a reload | `crm.api.notifications.get_notifications` | ok | | |

## Dashboard (`/crm/dashboard`)

Done as `Administrator` on 1 Oct 2026. The Edit button is shown to administrators only,
and the Sales User box to administrators and managers; both belong to the role passes.

| # | Action | How | Calls | Result | Finding | Auto |
|---|---|---|---|---|---|---|
| DB1 | Page loads | Sidebar → Dashboard; the seventeen default tiles draw for the last 30 days | `crm.api.dashboard.get_dashboard` | ok | 41 (fixed) | e2e |
| DB2 | Refresh | The Refresh button; the tiles load again | `crm.api.dashboard.get_dashboard` | ok | | e2e |
| DB3 | Period | The range dropdown → Last 7, 30, 60 and 90 Days; the numbers and charts follow | `crm.api.dashboard.get_dashboard` | ok | | e2e |
| DB4 | Custom range | The range dropdown → Custom Range → pick a start and an end date; clearing it goes back to Last 30 Days | `crm.api.dashboard.get_dashboard` | ok | | |
| DB5 | Sales User | The Sales User box → pick a user; the tiles show that user's numbers; clear it for everyone's | `search_link` (User), `crm.api.dashboard.get_dashboard` | ok | 46 (fixed) | |
| DB6 | Add a chart | Edit → Chart → a type (Spacer, Number, Axis, Donut) and a chart → Add; the tile appears → Save; it is still there after a reload | `crm.api.dashboard.get_chart`, `frappe.client.set_value` | ok | | |
| DB7 | Remove a chart | Edit → the x on a tile → Save; it stays gone after a reload | `frappe.client.set_value` | ok | | |
| DB8 | Rearrange | Edit → drag a tile to another place, or its corner to resize it → Save; the order is kept after a reload. Cancel instead of Save puts everything back, with no call | `frappe.client.set_value` | ok | | e2e (Edit and Cancel) |
| DB9 | Reset to Default | Edit → Reset to Default; the seventeen default tiles come back in their places | `crm.api.dashboard.reset_to_default`, `crm.api.dashboard.get_dashboard` | ok | | |

## Deals (`/crm/deals`)

Example records. Deal A, everything new: organization "Nova Retail", website
`novaretail.example.com`, 11-50 employees, territory Karnataka, annual revenue 800000,
any industry; contact Mr Arjun Mehta, `arjun.mehta@example.com`, +91 98765 00022, Male;
status Qualification, deal owner yourself. Deal B, everything existing: organization
"Acme Test Org 2" and contact "Ravi Test" from the earlier passes. Make a third and a
fourth the quick way for the bulk and delete rows.

**Reload the page before each Create Deal and before each Convert to Deal.** The
dialog's form is kept for the page session and never cleared (finding 74, upstream bug
45), so without a reload a new deal takes values from the last one.

| # | Action | How | Calls | Result | Finding | Auto |
|---|---|---|---|---|---|---|
| D1 | List loads | Sidebar → Deals; rows show, or "No Deals Found" | `get_data`, `getdoctype`, `get_filterable_fields`, `get_quick_filters`, `sort_options`, `crm.api.views.get_views`, `crm.api.session.get_organizations` | ok | | |
| D2 | Create, all new | Create → Organization Name, Website, No. of Employees, Territory, Annual Revenue, Industry; Salutation, First Name, Last Name, Email, Mobile No, Gender; Status, Deal Owner → Create; the deal's page opens, and the organization and the contact now exist on their own lists | `get_fields_layout`, `search_link` (CRM Territory, CRM Industry, User), `crm.fcrm.doctype.crm_deal.crm_deal.create_deal` | ok | | e2e |
| D3 | Create, all existing | Create → switch on Choose Existing Organization and Choose Existing Contact → pick one of each → Create; no new organization or contact is made | `search_link` (CRM Organization, Contact), `crm.fcrm.doctype.crm_deal.crm_deal.create_deal` | ok | | |
| D4 | Open | Click the row; the header shows the assignees and the status, the tabs run Activity to Attachments, and the side panel shows the Contacts section, the organization and the deal's fields | `frappe.client.get`, `get_sidepanel_sections`, `crm.fcrm.doctype.crm_deal.api.get_deal_contacts`, `crm.api.activities.get_activities`, `crm.api.doc.get_assigned_users`, `frappe.client.get_doc_permissions` | ok | | e2e |
| D5 | Edit side-panel fields | Side panel → change Next Step, Probability and the closing date; each saves when the field loses focus, and the Activity tab records the change | `frappe.client.set_value` | ok | | |
| D6 | Status | The status button in the header → Negotiation, then Ready to Close; the button follows and the Activity tab records each change | `frappe.client.set_value` | ok | | |
| D7 | Mark as Lost | Status → Lost → the Lost Reason dialog opens → a reason and notes → Save. Saving with no reason is refused; so is "Other" with no notes | `search_link` (CRM Lost Reason), `frappe.client.set_value` | ok | | |
| D8 | Mark as Won | On another deal: status → Won; the button follows | `frappe.client.set_value` | ok | | |
| D9 | Contacts on the deal | Side panel → Contacts → the picker → an existing contact → "Contact Added"; picking the same one again → "Contact Already Added"; three-dots on a contact → Set as Primary Contact; three-dots → Remove | `search_link` (Contact), `crm.fcrm.doctype.crm_deal.crm_deal.add_contact`, `crm.fcrm.doctype.crm_deal.crm_deal.set_primary_contact`, `crm.fcrm.doctype.crm_deal.crm_deal.remove_contact`, `crm.fcrm.doctype.crm_deal.api.get_deal_contacts` | ok | | |
| D10 | New contact from the deal | Contacts → the picker → Create New → fill the contact dialog → Create; the new contact is added to the deal | `get_fields_layout`, `frappe.client.insert`, `crm.fcrm.doctype.crm_deal.crm_deal.add_contact` | ok | | |
| D11 | Change the organization | Side panel → Organization → pick another one; the logo and the organization fields follow | `search_link` (CRM Organization), `frappe.client.set_value` | ok | | |
| D12 | Assign | As L6: the assign button in the header → a user → Update; then remove them | `frappe.desk.form.assign_to.add`, `crm.api.doc.remove_assignments`, `crm.api.doc.get_assigned_users` | ok | | |
| D13 | Comment | As L8: Comments tab → New Comment with an `@` mention → Comment | `crm.api.comment.add_comment` | ok | | |
| D14 | Note, task and call on the deal | As L9 to L11: Notes tab → New Note; Tasks tab → New Task; Calls tab → Log a Call; each shows on its tab, and can be edited and deleted | `frappe.client.insert`, `frappe.client.set_value`, `frappe.client.delete`, `crm.api.activities.get_activities` | ok | | |
| D15 | Attachment | As L12: Attachments tab → Upload Attachment → a file; private/public; delete | `crm.api.get_file_uploader_defaults`, `upload_file`, `frappe.client.set_value`, `frappe.client.delete` | ok | | |
| D16 | Email | Needs an outgoing email account (S10). As L13: Emails tab → New Email → Send | `frappe.core.doctype.communication.email.make`, `crm.api.contact.search_emails` | ok | | |
| D17 | Data tab and products | Data tab → change a field → Save. Then Products → Add Row → Product (Create New: a name and a rate, or pick one) → a quantity → Save; the row's amount and the totals follow | `get_fields_layout`, `search_link` (CRM Product), `frappe.client.insert`, `frappe.client.set_value` | ok | | |
| D18 | Side-panel layout | As L15: the pencil above the side panel fields → move a field → Save | `get_sidepanel_sections`, `save_fields_layout` | ok | | |
| D19 | List tools | Filter, sort, columns, quick filters and a saved view, as T10 to T13 | `get_filterable_fields`, `sort_options`, `create_or_update_standard_view`, `get_data` | ok | | |
| D20 | Group By and Kanban | View dropdown → Group By → pick a field; then Kanban → drag a card to another open status column; the deal's status follows | `get_data`, `frappe.client.set_value`, `crm.api.doc.get_group_by_fields` | ok | | |
| D21 | Bulk edit, assign, clear | Tick two rows → Edit → a field and a value → Update. Tick again → Assign To → a user → Update. Tick again → Clear Assignment → confirm | `submit_cancel_or_update_docs`, `frappe.desk.form.assign_to.add_multiple`, `frappe.desk.form.assign_to.remove_multiple` | ok | | |
| D22 | Delete | On a deal's page → the bin in the side panel → the dialog lists what links to it → Delete; back on the list, the row is gone | `crm.api.doc.get_linked_docs_of_document`, `frappe.client.delete` | ok | 75 (fixed) | |
| D23 | Bulk delete | Tick rows → Delete in the bar → confirm; the rows are gone | `crm.api.doc.delete_bulk_docs` | ok | 75 (fixed) | |
| D24 | Create again without reloading | After D3, without reloading the page: Create → the switches off → a new organization name and contact → Create. Expected a deal on the new organization | `crm.fcrm.doctype.crm_deal.crm_deal.create_deal` | failed: the deal was made with values from the earlier deals; the dialog's form is shared for the page session and keeps the hidden organization pick, upstream and here alike (upstream bug 45) | 74 | |
| D25 | Filter by clicking a cell | In the list, click a deal's Annual Revenue cell; the list is filtered on that amount, the chip shows it, and the page still opens on the next visit (the filter is kept with the standard view) | `get_data`, `create_or_update_standard_view` | ok (after the fix; failed before it: the filter was filed as "$ 500,000.00", the list answered 417 and the page would not open again) | 77 (fixed) | |
| D26 | Products grid fields | Data tab → Products → the gear on the grid (Edit Grid Fields) → change the Fields Order, add or remove a column → Save; the grid keeps it after a reload. Reset only discards edits not yet saved; a saved layout stays (upstream does the same, checked 13 Oct 2026) | `frappe.model.utils.user_settings.save` | ok | 84 (version gap) | |

The WhatsApp tab and Make a Call belong to the integrations and are out of scope.

## Sign in and out (`/crm/login`)

The port's one sanctioned deviation from upstream's wire protocol: a JWT pair instead
of a session cookie (`frontend/JWT_PATCH.md`). The rows below are what a person sees of
it. A5 needs a short token life: set `JWT_ACCESS_TOKEN_LIFETIME_MINUTES=1` in the root
`.env`, restart runserver, and put it back afterwards.

| # | Action | How | Calls | Result | Finding | Auto |
|---|---|---|---|---|---|---|
| A1 | Sign in | Signed out, open `/crm/login` → email and password → Log in; the app opens | `login`, then the boot calls of B1 | ok | | e2e |
| A2 | Wrong password | A wrong password → "Invalid login credentials", the form stays and nothing is stored. A disabled account with its right password → "User disabled or missing" | `login` | ok | | e2e |
| A3 | A protected page while signed out | Signed out, open `/crm/deals` directly → the login page; after signing in you land on `/crm/deals`, not the home page | `login` | ok | | e2e |
| A4 | The session survives a reload | Reload any page: still signed in, no login page, the user menu shows you | `frappe.auth.get_logged_user`, the boot calls | ok | | e2e |
| A5 | Token refresh | With the one-minute token life: sign in, wait two minutes, click anything; it works with no login page, the pair was renewed behind the click | `token/refresh` | ok | | |
| A6 | Sign out | User menu → Log out → the login page; Back does not show the app; a reload stays on the login page | `logout` | ok | | e2e |
| A7 | Forgot password | Login page → Forgot Password → your address → Send; the worker's console prints the link (system mail through the config account, so `EMAIL_HOST` must be set in `.env`, finding 79; with none the worker logs "Please setup default outgoing Email Account") → open it → a new password twice → Update; sign in with it | `frappe.core.doctype.user.user.reset_password`, `frappe.core.doctype.user.user.update_password`, `login` | ok | 79 | e2e (form only) |
| A8 | Accept an invitation | The link the worker printed for S8 (same `EMAIL_HOST` need as A7; an invitation sent with no account is not retried, so send a new one after setting it) → set a password → the invited user lands in the app, with the role the invite gave | `crm.api.accept_invitation`, `login` |   | 79 | |
| A9 | A wrong URL | Signed in, open `/crm/leaderssf` → "Invalid page or not permitted to access" (upstream's `InvalidPage.vue`, its catch-all route); open a lead URL with a wrong id → "Document not found" from the lead page | `frappe.client.get` | failed: a wrong path with a second segment (/crm/leadsdss/CRM-LEAD-...) drew a blank page, here and on the demo; the one-segment cases showed their messages. Router patched; retried 13 Oct 2026: ok, both URLs show their messages | 83 (fixed, patch) | |

## Endpoints no screen reaches

Of the 101 in-scope endpoints, these are the ones a person cannot fire by using the app,
plus the three whose rows are still open, so the API-coverage count below has a known
ceiling: everything else is covered by the http suite only (`ROUTES.md`). Settled 7 Oct
2026.

**Not reachable by ordinary use (7)**

| Endpoint | What it does | Why no click reaches it |
|---|---|---|
| `crm.api.auth.oauth_providers` | Lists the OAuth sign-in providers for the login page | This frontend version never asks, and the port has no providers |
| `crm.api.get_translations` | Returns the translation dictionary for a language | Served for fidelity; this version reads translations from the boot values (`KNOWN_ISSUES.md` 10) |
| `crm.api.exchange_rate.get_exchange_rate` | The rate between a deal's currency and the dashboard currency | Needs the Currency port (finding 63); today a stub answering 1 |
| `frappe.client.get_value` | One field of one record | A framework call `frappe-ui` can make internally; the screens use `get` and `get_list` |
| `frappe.model.utils.user_settings.get` | The read side of a user's grid settings | The app gets them inside `getdoctype`'s `user_settings` instead |
| `frappe.onboarding.get_onboarding_status` | The onboarding wizard's progress | Called from inside the `frappe-ui` package, only for a user who has not dismissed the wizard |
| `frappe.onboarding.update_user_onboarding_status` | Saves that progress | The same |

**Reachable, but not on purpose (1)**

| Endpoint | What it does | Why no row names it |
|---|---|---|
| `crm.api.session.get_user_info` | One user's name, picture and roles | The users store calls it only to resolve an email it does not recognise, which no action triggers deliberately |

**Named by rows still open (3)**

| Endpoint | Row |
|---|---|
| `frappe.core.doctype.user.user.reset_password` | A7 |
| `frappe.core.doctype.user.user.update_password` | A7 |
| `crm.api.accept_invitation` | A8 |

So the ceiling is 93 of 101 by hand, 90 until A7 and A8 are done.

## Role passes

The rows where permissions differ, repeated as Sales Manager (`grace@example.com`) and
Sales User (`ada@example.com`) after the Administrator pass: delete on each doctype,
another user's records, the Settings sections, the dashboard's Edit button. Recorded as
extra columns on those rows rather than separate tables.

### Results, 14 Oct 2026

Three of the four areas done as Grace and then Ada, with Enable Sales Hierarchy off,
locally and on the hosted demo for comparison. Deletes (area 1) are still to do.

| Area | Grace (Sales Manager) | Ada (Sales User) | Verdict |
|---|---|---|---|
| Another user's leads and deals | Sees and edits Administrator's leads; the owner filter works | Sees only the leads she owns or is assigned; Administrator's are not listed | **ok, matches upstream**: a Sales User outside the hierarchy gets own and assigned records whatever the switch says (`crm/permissions/org_hierarchy.py:53-60`, here `crm_app/permissions/org_hierarchy.py:187`); the switch only widens that to the subtree. The demo behaves the same. The tester's brief had said "everyone sees everything with the switch off", which was wrong |
| Another user's notes and tasks | Edits Administrator's | Edits Administrator's | ok: no owner rule on either, as upstream |
| Settings sections | Every group | Profile, Preferences, Email → Templates, Integrations → Telephony only | ok |
| Dashboard | User filter, no Edit | Neither | ok |
| Delete: lead, deal | Deletes what she sees | Deletes what she sees | ok: all three roles hold delete upstream; visibility is the hierarchy rule above |
| Delete: note, task, call log, organization | Deletes any | Deletes any | ok: all three roles hold delete upstream, no owner condition |
| Delete: contact (K7) | Deleted Administrator's | Deleted Administrator's | **finding 86**: upstream lets a rep or manager delete only a contact they created (`contact.json`, the `All` row with `if_owner`); the demo refused both. Ruled 14 Oct 2026; retest |
| Delete: address | No control in the frontend | No control | ok: the address modal creates and edits, "remove" clears the link; the API refuses both, as upstream (System Manager only) |
| Delete: email account | No control in the frontend | No page | ok: an account is disabled, not deleted; through the API a manager may delete here where upstream allows System Manager only, divergence 2 in `specs/SECURITY_MODEL.md` |
| Email templates (S11) | Created, edited, deleted | Created, edited, deleted | **finding 87**: upstream's `email_template.json` is System Manager for create, edit and delete, read for everyone else, and CRM adds nothing; the port had no rule. Ruled 14 Oct 2026 to match upstream; retest: both see the list and the mail editor's picker, both refused on New, edit and delete |

## API coverage

Every method endpoint the port serves, except the integrations, with the Django
implementation and the Frappe CRM (or framework) source it was ported from. A box is
ticked when a screen row that reaches the endpoint is marked ok, and flagged when one
failed. Generated: do not edit by hand.

<!-- api-coverage:start -->
| | Method | Django | Upstream | Reached from | Result |
|---|---|---|---|---|---|
| ☐ | `crm.api.accept_invitation` | `crm_app/api/auth_pages.py:311` | `crm/api/__init__.py:79-106` | A8 |  |
| ☑ | `crm.api.activities.get_activities` | `crm_app/api/activities.py:461` | `crm/api/activities.py:13-20` | C12, L3, L11, D4, D14 | ok: C12, L3, L11, D4, D14 |
| ☐ | `crm.api.assignment_rule.duplicate_assignment_rule` | `crm_app/api/assignment_rule.py:32` | `crm/api/assignment_rule.py:27-32` | S12 |  |
| ☐ | `crm.api.assignment_rule.get_assignment_rules_list` | `crm_app/api/assignment_rule.py:16` | `crm/api/assignment_rule.py:4-24` | S12 |  |
| ☐ | `crm.api.auth.oauth_providers` | `crm_app/api/auth.py:17` | `crm/api/auth.py:4-39` |  |  |
| ☑ | `crm.api.comment.add_comment` | `crm_app/api/comment.py:118` | `crm/api/comment.py:69-90` | L8, S19, D13 | ok: L8, S19, D13 |
| ☑ | `crm.api.contact.create_new` | `crm_app/api/contact.py:75` | `crm/api/contact.py:63-80` | K9 | ok: K9 |
| ☑ | `crm.api.contact.get_linked_deals` | `crm_app/api/contact.py:44` | `crm/api/contact.py:29-60` | K3 | ok: K3 |
| ☑ | `crm.api.contact.search_emails` | `crm_app/api/contact.py:141` | `crm/api/contact.py:109-145` | L13, D16 | ok: L13, D16 |
| ☑ | `crm.api.contact.set_as_primary` | `crm_app/api/contact.py:104` | `crm/api/contact.py:87-111` | K9 | ok: K9 |
| ☑ | `crm.api.dashboard.get_chart` | `crm_app/api/dashboard.py:846` | `crm/api/dashboard.py:64-88` | DB6 | ok: DB6 |
| ☑ | `crm.api.dashboard.get_dashboard` | `crm_app/api/dashboard.py:829` | `crm/api/dashboard.py:25-61` | DB1, DB2, DB3, DB4, DB5, DB9 | ok: DB1, DB2, DB3, DB4, DB5, DB9 |
| ☑ | `crm.api.dashboard.reset_to_default` | `crm_app/api/dashboard.py:819` | `crm/api/dashboard.py:19-23` | DB9 | ok: DB9 |
| ☑ | `crm.api.delete_attachment` | `crm_app/api/misc.py:126` | `crm/api/__init__.py:155-167` | N11 | ok: N11 |
| ☑ | `crm.api.doc.delete_bulk_docs` | `crm_app/api/doc.py:668` | `crm/api/doc.py:795-837` | T9, C9, L22, D23 | ok: T9, C9, L22, D23 |
| ☑ | `crm.api.doc.get_assigned_users` | `crm_app/api/doc.py:248` | `crm/api/doc.py:607-625` | N3, L3, L6, D4, D12 | ok: N3, L3, L6, D4, D12 |
| ☑ | `crm.api.doc.get_data` | `frappe_core/api/doc.py:211` | `crm/api/doc.py:256-271` | N1, N2, N5, N6, T1, T2, T4, T8, T10, T11, C1, C2, C10, L1, L16, L17, L23, O1, O8, K1, K6, K8, K11, D1, D19, D20, D25 | ok: N1, N2, N5, N6, T1, T2, T4, T8, T10, T11, C1, C2, C10, L1, L16, L17, L23, O1, O8, K1, K6, K8, K11, D1, D19, D20, D25 |
| ☑ | `crm.api.doc.get_fields` | `crm_app/api/doc.py:321` | `crm/api/doc.py:639-651` | T7, C9 | ok: T7, C9 |
| ☑ | `crm.api.doc.get_filterable_fields` | `crm_app/api/doc.py:96` | `crm/api/doc.py:54-109` | N1, T1, T11, C1, C10, L1, L16, O1, O8, K1, K6, D1, D19 | ok: N1, T1, T11, C1, C10, L1, L16, O1, O8, K1, K6, D1, D19 |
| ☑ | `crm.api.doc.get_group_by_fields` | `crm_app/api/doc.py:102` | `crm/api/doc.py:112-160` | L17, D20 | ok: L17, D20 |
| ☑ | `crm.api.doc.get_linked_docs_of_document` | `crm_app/api/doc.py:472` | `crm/api/doc.py:677-718` | L21, O9, K7, D22 | ok: L21, O9, K7, D22 |
| ☑ | `crm.api.doc.get_quick_filters` | `crm_app/api/doc.py:146` | `crm/api/doc.py:163-204` | N1, N7, T1, C1, L1, O1, K1, K8, D1 | ok: N1, N7, T1, C1, L1, O1, K1, K8, D1 |
| ☑ | `crm.api.doc.remove_assignments` | `crm_app/api/doc.py:263` | `crm/api/doc.py:589-604` | L6, D12 | ok: L6, D12 |
| ⚠ | `crm.api.doc.remove_linked_doc_reference` | `crm_app/api/doc.py:557` | `crm/api/doc.py:769-792` | O10 | failed: O10 (finding 56) |
| ☑ | `crm.api.doc.sort_options` | `crm_app/api/doc.py:74` | `crm/api/doc.py:24-51` | N1, T1, T11, C1, C10, L1, L16, O1, O8, K1, K6, D1, D19 | ok: N1, T1, T11, C1, C10, L1, L16, O1, O8, K1, K6, D1, D19 |
| ☑ | `crm.api.doc.update_quick_filters` | `crm_app/api/doc.py:202` | `crm/api/doc.py:207-224` | N7 | ok: N7 |
| ☐ | `crm.api.exchange_rate.get_exchange_rate` | `crm_app/api/exchange_rate.py:48` | `crm/api/exchange_rate.py:9-27` |  |  |
| ☑ | `crm.api.get_file_uploader_defaults` | `crm_app/api/misc.py:159` | `crm/api/__init__.py:170-180` | L12, D15 | ok: L12, D15 |
| ☐ | `crm.api.get_translations` | `crm_app/api/misc.py:31` | `crm/api/__init__.py:12-19` |  |  |
| ☑ | `crm.api.get_user_signature` | `crm_app/api/misc.py:42` | `crm/api/__init__.py:22-50` | L13 | ok: L13 |
| ☑ | `crm.api.invite_by_email` | `crm_app/api/misc.py:75` | `crm/api/__init__.py:106-152` | S8 | ok: S8 |
| ☑ | `crm.api.notifications.get_notifications` | `crm_app/api/notifications.py:33` | `crm/api/notifications.py:6-49` | B1, NT1, NT4 | ok: B1, NT1, NT4 |
| ☑ | `crm.api.notifications.mark_as_read` | `crm_app/api/notifications.py:100` | `crm/api/notifications.py:52-64` | NT2, NT3 | ok: NT2, NT3 |
| ☑ | `crm.api.onboarding.get_first_deal` | `crm_app/api/onboarding.py:30` | `crm/api/onboarding.py:17-24` | B2 | ok: B2 |
| ☑ | `crm.api.onboarding.get_first_lead` | `crm_app/api/onboarding.py:17` | `crm/api/onboarding.py:5-14` | B2 | ok: B2 |
| ☑ | `crm.api.session.get_organizations` | `crm_app/api/session.py:158` | `crm/api/session.py:155-165` | K1, D1 | ok: K1, D1 |
| ☐ | `crm.api.session.get_user_info` | `crm_app/api/session.py:138` | `crm/api/session.py:130-152` |  |  |
| ☑ | `crm.api.session.get_users` | `crm_app/api/session.py:62` | `crm/api/session.py:33-127` | B1, S7 | ok: B1, S7 |
| ☑ | `crm.api.settings.create_email_account` | `crm_app/api/settings.py:69` | `crm/api/settings.py:5-53` | S10 | ok: S10 |
| ☑ | `crm.api.user.add_existing_users` | `crm_app/api/user.py:110` | `crm/api/user.py:51-70` | S7 | ok: S7 |
| ☑ | `crm.api.user.change_password` | `crm_app/api/user.py:54` | `crm/api/user.py:9-48` | S1 | ok: S1 |
| ☑ | `crm.api.user.remove_crm_roles_from_user` | `crm_app/api/user.py:182` | `crm/api/user.py:124-163` | S7 | ok: S7 |
| ☑ | `crm.api.user.update_user_role` | `crm_app/api/user.py:128` | `crm/api/user.py:73-121` | S7 | ok: S7 |
| ☑ | `crm.api.views.get_views` | `crm_app/api/views.py:12` | `crm/api/views.py:5-16` | B1, N1, N5, T1, T12, C1, C11, L1, O1, K1, D1 | ok: B1, N1, N5, T1, T12, C1, C11, L1, O1, K1, D1 |
| ☑ | `crm.demo.api.clear_demo_data` | `crm_app/api/demo.py:18` | `crm/demo/api.py:clear_demo_data` | B2 | ok: B2 |
| ☑ | `crm.fcrm.doctype.crm_call_log.crm_call_log.create_lead_from_call_log` | `crm_app/api/call_log.py:82` | `crm/fcrm/doctype/crm_call_log/crm_call_log.py:245-297` | C7 | ok: C7 |
| ☑ | `crm.fcrm.doctype.crm_call_log.crm_call_log.get_call_log` | `crm_app/api/call_log.py:28` | `crm/fcrm/doctype/crm_call_log/crm_call_log.py:189-242` | C3, L11 | ok: C3, L11 |
| ☑ | `crm.fcrm.doctype.crm_deal.api.get_deal_contacts` | `crm_app/api/deal.py:84` | `crm/fcrm/doctype/crm_deal/api.py` | D4, D9 | ok: D4, D9 |
| ☑ | `crm.fcrm.doctype.crm_deal.crm_deal.add_contact` | `crm_app/api/deal.py:57` | `crm/fcrm/doctype/crm_deal/crm_deal.py:358-366` | D9, D10 | ok: D9, D10 |
| ⚠ | `crm.fcrm.doctype.crm_deal.crm_deal.create_deal` | `crm_app/api/deal.py:200` | `crm/fcrm/doctype/crm_deal/crm_deal.py:456-475` | O13, D2, D3, D24 | failed: D24 (finding 74) |
| ☑ | `crm.fcrm.doctype.crm_deal.crm_deal.remove_contact` | `crm_app/api/deal.py:65` | `crm/fcrm/doctype/crm_deal/crm_deal.py:369-377` | D9 | ok: D9 |
| ☑ | `crm.fcrm.doctype.crm_deal.crm_deal.set_primary_contact` | `crm_app/api/deal.py:74` | `crm/fcrm/doctype/crm_deal/crm_deal.py:380-388` | D9 | ok: D9 |
| ☑ | `crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout` | `crm_app/api/fields_layout.py:112` | `crm/fcrm/doctype/crm_fields_layout/crm_fields_layout.py:29-107` | N2, N8, T2, C2, L2, L14, L19, O2, O3, O11, K2, D2, D10, D17 | ok: N2, N8, T2, C2, L2, L14, L19, O2, O3, O11, K2, D2, D10, D17 |
| ☑ | `crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections` | `crm_app/api/fields_layout.py:213` | `crm/fcrm/doctype/crm_fields_layout/crm_fields_layout.py:110-143` | L3, L15, O4, K3, D4, D18 | ok: L3, L15, O4, K3, D4, D18 |
| ☑ | `crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.save_fields_layout` | `crm_app/api/fields_layout.py:243` | `crm/fcrm/doctype/crm_fields_layout/crm_fields_layout.py:189-210` | N8, L15, D18 | ok: N8, L15, D18 |
| ☑ | `crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal` | `crm_app/api/lead.py:55` | `crm_lead.py:494-516` | L19, L20 | ok: L19, L20 |
| ☑ | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.create` | `crm_app/api/view_settings.py:150` | `crm/fcrm/doctype/crm_view_settings/crm_view_settings.py:45-81` | T12, T14, C11 | ok: T12, T14, C11 |
| ☑ | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.create_or_update_standard_view` | `crm_app/api/view_settings.py:273` | `crm/fcrm/doctype/crm_view_settings/crm_view_settings.py:214-291` | N5, T10, T11, T15, C10, L16, O8, K6, D19, D25 | ok: N5, T10, T11, T15, C10, L16, O8, K6, D19, D25 |
| ☑ | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.delete` | `crm_app/api/view_settings.py:190` | `crm/fcrm/doctype/crm_view_settings/crm_view_settings.py:119-123` | T14 | ok: T14 |
| ☑ | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.fetch_and_update_kanban_columns` | `crm_app/api/view_settings.py:318` | `crm/fcrm/doctype/crm_view_settings/crm_view_settings.py:294-308` | T15 | ok: T15 |
| ☑ | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.pin` | `crm_app/api/view_settings.py:232` | `crm/fcrm/doctype/crm_view_settings/crm_view_settings.py:138-143` | T13, C11 | ok: T13, C11 |
| ☑ | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.public` | `crm_app/api/view_settings.py:204` | `crm/fcrm/doctype/crm_view_settings/crm_view_settings.py:126-135` | T13, C11 | ok: T13, C11 |
| ☑ | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.set_as_default` | `crm_app/api/view_settings.py:246` | `crm/fcrm/doctype/crm_view_settings/crm_view_settings.py:197-211` | T14 | ok: T14 |
| ☑ | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.update` | `crm_app/api/view_settings.py:170` | `crm/fcrm/doctype/crm_view_settings/crm_view_settings.py:84-116` | T10, T12, C10 | ok: T10, T12, C10 |
| ☑ | `crm.integrations.api.add_note_to_call_log` | `crm_app/integrations/api.py:116` | `crm/integrations/api.py:74-95` | C5 | ok: C5 |
| ☑ | `crm.integrations.api.add_task_to_call_log` | `crm_app/integrations/api.py:140` | `crm/integrations/api.py:98-134` | C6 | ok: C6 |
| ☑ | `crm.integrations.api.is_call_integration_enabled` | `crm_app/integrations/api.py:63` | `crm/integrations/api.py:36-43` | B1 | ok: B1 |
| ☑ | `crm.www.crm.get_context_for_dev` | `crm_app/api/boot.py:39` | `crm/www/crm.py:get_boot` | B1 | ok: B1 |
| ☑ | `frappe.apps.get_apps` | `crm_app/api/desk.py:40` | `frappe/apps.py:17-55` | B1 | ok: B1 |
| ☑ | `frappe.auth.get_logged_user` | `frappe_core/api/auth.py:183` | `frappe/auth.py:get_logged_user` | A4 | ok: A4 |
| ☐ | `frappe.automation.doctype.assignment_rule.assignment_rule.bulk_apply` | `crm_app/assignment_rules.py:472` | `frappe/automation/doctype/assignment_rule/assignment_rule.py:69-420` |  |  |
| ☑ | `frappe.client.delete` | `crm_app/api/client.py:359` | `frappe/client.py:delete` | N4, T5, C8, L9, L10, L12, L21, O9, K7, K10, S8, S11, S12, D14, D15, D22 | ok: N4, T5, C8, L9, L10, L12, L21, O9, K7, K10, S8, S11, D14, D15, D22 |
| ⚠ | `frappe.client.get` | `crm_app/api/client.py:106` | `frappe/client.py:get` | B1, N3, T3, C4, L3, O4, O12, K3, S2, S3, S5, S13, S15, S22, D4, A9 | failed: S5 (finding 64), A9 (finding 83 (fixed, patch)) |
| ☑ | `frappe.client.get_doc_permissions` | `crm_app/api/client.py:496` | `frappe/client.py:get_doc_permissions` | N3, L3, D4 | ok: N3, L3, D4 |
| ☑ | `frappe.client.get_list` | `crm_app/api/client.py:124` | `frappe/client.py:get_list` | N3, O4, O13, S8, S9, S11, S13, S16 | ok: N3, O4, O13, S8, S9, S11, S13, S16 |
| ☑ | `frappe.client.get_single_value` | `crm_app/api/client.py:250` | `frappe/client.py:get_single_value` | B1 | ok: B1 |
| ☐ | `frappe.client.get_value` | `crm_app/api/client.py:212` | `frappe/client.py:get_value` |  |  |
| ☑ | `frappe.client.insert` | `crm_app/api/client.py:326` | `frappe/client.py:insert` | N2, N10, T2, T17, C2, C12, L2, L9, L10, L11, O2, O3, O11, K2, S9, S11, S12, S13, S22, D10, D14, D17 | ok: N2, N10, T2, T17, C2, C12, L2, L9, L10, L11, O2, O3, O11, K2, S9, S11, S13, S22, D10, D14, D17 |
| ☑ | `frappe.client.rename_doc` | `crm_app/api/client.py:460` | `frappe/model/rename_doc.py:rename_doc` | O6, S10, S11, S12, S13 | ok: O6, S10, S11, S13 |
| ⚠ | `frappe.client.set_value` | `crm_app/api/client.py:297` | `frappe/client.py:set_value` | N3, T3, T4, C4, L4, L5, L7, L9, L10, L12, L14, L17, O3, O5, O7, O11, O12, O14, K4, K5, K10, S1, S2, S17, S3, S19, S20, S4, S21, S5, S6, S9, S10, S12, S14, S15, S16, DB6, DB7, DB8, D5, D6, D7, D8, D11, D14, D15, D17, D20 | failed: S4 (finding 63), S21 (finding 63), S5 (finding 64) |
| ☑ | `frappe.core.doctype.communication.email.make` | `crm_app/api/communication.py:76` | `frappe/core/doctype/communication/email.py:make` | L13, D16 | ok: L13, D16 |
| ☑ | `frappe.core.doctype.user.user.get_timezones` | `crm_app/api/desk.py:111` | `frappe/core/doctype/user/user.py:783-785` | S2 | ok: S2 |
| ☑ | `frappe.core.doctype.user.user.reset_password` | `crm_app/api/auth_pages.py:45` | `frappe/core/doctype/user/user.py:1041-1067` | A7 | ok: A7 |
| ☑ | `frappe.core.doctype.user.user.update_password` | `crm_app/api/auth_pages.py:99` | `frappe/core/doctype/user/user.py:826-880` | A7 | ok: A7 |
| ☑ | `frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs` | `crm_app/api/bulk_update.py:27` | `frappe/desk/doctype/bulk_update/bulk_update.py:54-79` | T7, T16, C9, L18, D21 | ok: T7, T16, C9, L18, D21 |
| ☑ | `frappe.desk.form.assign_to.add` | `crm_app/api/client.py:518` | `frappe/desk/form/assign_to.py:add` | L6, D12 | ok: L6, D12 |
| ☑ | `frappe.desk.form.assign_to.add_multiple` | `crm_app/api/client.py:541` | `frappe/desk/form/assign_to.py:148-156` | L18, D21 | ok: L18, D21 |
| ☑ | `frappe.desk.form.assign_to.remove_multiple` | `crm_app/api/client.py:584` | `frappe/desk/form/assign_to.py:191-201` | L18, D21 | ok: L18, D21 |
| ⚠ | `frappe.desk.form.load.getdoctype` | `crm_app/api/form_load.py:151` | `frappe/desk/form/load.py:getdoctype` | N1, T1, C1, L1, O1, K1, S5, D1 | failed: S5 (finding 64) |
| ☑ | `frappe.desk.like.toggle_like` | `crm_app/api/client.py:624` | `frappe/desk/like.py:toggle_like` | L23 | ok: L23 |
| ☑ | `frappe.desk.reportview.export_query` | `crm_app/api/reportview.py:161` | `frappe/desk/reportview.py:427-575` | T6 | ok: T6 |
| ⚠ | `frappe.desk.search.search_link` | `crm_app/api/client.py:650` | `frappe/desk/search.py:search_link` | N10, T2, T11, T17, C2, C12, L2, O2, O3, O11, K2, S17, S21, DB5, D2, D3, D7, D9, D11, D17 | failed: S21 (finding 63) |
| ☑ | `frappe.email.doctype.email_template.email_template.get_email_template` | `crm_app/api/email_template.py:73` | `frappe/email/doctype/email_template/email_template.py:52-58` | L13 | ok: L13 |
| ☐ | `frappe.model.utils.user_settings.get` | `crm_app/api/user_settings.py:113` | `frappe/model/utils/user_settings.py:get` |  |  |
| ☑ | `frappe.model.utils.user_settings.save` | `crm_app/api/user_settings.py:100` | `frappe/model/utils/user_settings.py:save` | D26 | ok: D26 |
| ☐ | `frappe.onboarding.get_onboarding_status` | `crm_app/api/onboarding.py:54` | `frappe/onboarding.py:6-9` |  |  |
| ☐ | `frappe.onboarding.update_user_onboarding_status` | `crm_app/api/onboarding.py:62` | `frappe/onboarding.py:12-25` |  |  |
| ☑ | `frappe.utils.telemetry.pulse.client.boot_config` | `crm_app/api/desk.py:161` | `config/settings/base.py` | B1 | ok: B1 |
| ☑ | `login` | `frappe_core/api/auth.py:39` | `frappe/auth.py:LoginManager (session login; JWT here, JWT_PATCH.md)` | A1, A2, A3, A7, A8 | ok: A1, A2, A3, A7 |
| ☑ | `logout` | `frappe_core/api/auth.py:127` | `frappe/auth.py:LoginManager.logout (JWT here)` | A6 | ok: A6 |
| ☑ | `token/refresh` | `frappe_core/api/auth.py:146` | `none, the JWT deviation (JWT_PATCH.md)` | A5 | ok: A5 |
| ☑ | `upload_file` | `crm_app/api/upload.py:80` | `frappe/handler.py:131-244` | N9, L7, L12, O7, K5, S1, S6, D15 | ok: N9, L7, L12, O7, K5, S1, S6, D15 |

84 of 102 endpoints confirmed; 9 not yet named by any row.

**Excluded, integrations** (Twilio, Exotel, WhatsApp, ERPNext, lead sync, Frappe Cloud), not part of this log:

- `crm.api.whatsapp.create_whatsapp_message`
- `crm.api.whatsapp.get_whatsapp_messages`
- `crm.api.whatsapp.is_whatsapp_enabled`
- `crm.api.whatsapp.is_whatsapp_installed`
- `crm.api.whatsapp.react_on_whatsapp_message`
- `crm.api.whatsapp.send_whatsapp_template`
- `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.dismiss_sync_issue`
- `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_customer_link`
- `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_external_companies`
- `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_open_sync_issues`
- `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_product_sync_status`
- `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_quotation_url`
- `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.is_erpnext_installed`
- `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.prefill_quotation_items`
- `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.run_product_sync`
- `crm.integrations.api.get_contact_by_phone_number`
- `crm.integrations.api.get_contact_lead_or_deal_from_number`
- `crm.integrations.api.set_default_calling_medium`
- `crm.integrations.exotel.handler.handle_request`
- `crm.integrations.exotel.handler.is_integration_enabled`
- `crm.integrations.exotel.handler.make_a_call`
- `crm.integrations.twilio.api.generate_access_token`
- `crm.integrations.twilio.api.is_enabled`
- `crm.integrations.twilio.api.twilio_incoming_call_handler`
- `crm.integrations.twilio.api.update_call_status_info`
- `crm.integrations.twilio.api.update_recording_info`
- `crm.integrations.twilio.api.voice`
- `frappe.integrations.frappe_providers.frappecloud_billing.current_site_info`
<!-- api-coverage:end -->
