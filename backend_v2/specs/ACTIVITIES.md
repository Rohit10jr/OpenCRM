# ACTIVITIES — comments, email, notes, tasks, call logs, files, tags, likes, assignments

**Status: Provisional** — the scope is right, the details are guesses. **Rewrite against
`backend_v2/docs/AS_BUILT.md` before building.** Paths are from the repository root.

## 1. Scope

App `activities`: everything that hangs off a lead or a deal and appears on its timeline.
The `PORT_MAP.md` rows under **ACTIVITIES**:

- **Doctypes:** Comment, Communication, FCRM Note, CRM Task (integer key), **CRM Call
  Log**, File, Tag, Email Template, **Assignment Rule** and its child tables Assignment
  Rule Day and Assignment Rule User, and ToDo (withheld — no route)
- **Method paths (22):** `upload_file`;
  `frappe.automation.doctype.assignment_rule.assignment_rule.bulk_apply`;
  `crm.api.activities.get_activities`,
  `crm.api.comment.add_comment`, `crm.api.delete_attachment`,
  `crm.api.get_file_uploader_defaults`, `crm.api.doc.get_assigned_users`,
  `crm.api.doc.remove_assignments`, `crm.api.assignment_rule.*` (2),
  `frappe.desk.form.assign_to.add`, `add_multiple`, `remove_multiple`,
  `frappe.desk.like.toggle_like`, `frappe.core.doctype.communication.email.make`,
  `frappe.email.doctype.email_template.email_template.get_email_template`; and the call-log
  calls `get_call_log`, `create_lead_from_call_log`, `crm.integrations.api.add_note_to_call_log`,
  `add_task_to_call_log`, `get_contact_by_phone_number`,
  `get_contact_lead_or_deal_from_number`
- **The list definitions** for Task, Note and Call Log

**Call logs belong here, not with the phone providers:** logging a call by hand works with
no Twilio or Exotel configured, the Call Logs page is core CRM, and calls sit on the
timeline beside notes and tasks. The providers are in INTEGRATIONS.

**Assignment rules live here; their engine does not.** The engine that decides who a saved
document goes to is in SHARED_ACTIONS, because SALES calls it on save and is built first.
This unit builds the Assignment Rule doctypes, their routes, `bulk_apply` and the rules'
access, on top of that engine.

## 2. Depends on

SALES (the records activities hang off), NOTIFICATIONS (mentions and assignments create
notifications), SHARED_ACTIONS (the assignment engine).

## 3. Read in `backend/` first

- `frappe_platform/models.py` — Comment, Communication, File, Tag, Email Template, ToDo
- `crm_app/models/core_sales.py` — CRM Task, FCRM Note; `crm_app/models/telephony.py` —
  CRM Call Log
- `crm_app/permissions/attachments.py` — the rule that defers to the parent record
- `frappe_core/assignment.py`, `frappe_core/doc_caches.py`, `crm_app/async_signals.py`
- Assignment rules: `frappe_platform/models.py` (Assignment Rule and its rows),
  `crm_app/permissions/assignment_rule.py`, `crm_app/api/assignment_rule.py`,
  `crm_app/assignment_rules.py` (`bulk_apply`, and the engine SHARED_ACTIONS ports)
- Uploads: `crm_app/api/upload.py`, `frappe_platform/files.py`, `frappe_core/file_views.py`
- `crm_app/api/activities.py`, `api/comment.py`, `api/client.py` (assign and like),
  `api/assignment_rule.py`, `api/misc.py`, `api/communication.py`,
  `crm_app/communication.py`, `api/email_template.py`, `crm_app/tasks.py`
- Call logs: `crm_app/api/call_log.py`, the call-log parts of `crm_app/integrations/api.py`,
  `integrations/call_log.py`, `integrations/phone.py`
- `specs/UNROUTED_DOCTYPES.md` (ToDo), `specs/VERSION_HISTORY.md` (the timeline reads the
  change history), `specs/KNOWN_ISSUES.md` §3 and §7
- `docs/FINDINGS.md` entries 15, 16, 18, 19 and 22
- Tests to read and write again: `test_assignment.py`,
  `test_assignment_notifications.py`, `test_task_assignment.py`, `test_doc_caches.py`,
  `test_email_make.py`, `test_versions.py`, `test_telephony_shared.py`
- **Tests to port** (REBUILD_PLAN S14): `test_attachment_access.py`,
  `test_assignment_rule_doctype.py`, `test_assignment_rule_endpoints.py`,
  `test_call_log_endpoints.py`, `test_email_template.py`, `test_email_template_rule.py`,
  `test_lead_call_tab.py`, `test_upload_file.py`, and this unit's routes in
  `test_phase3_endpoints.py`. The spec check confirms the list.

## 4. Must not be lost

- **Comment, Communication and File read if you can read their record and write if you
  can write it**, through every door, with the destination re-check on update. Before
  this rule they leaked content from records the caller could not see (KNOWN_ISSUES §3,
  which took three mechanisms to close).
- **A private file attached to nothing is readable only by its owner** (finding 22).
- **ToDo has no route.** Upstream ships an escalation through it (bug #16).
- **`remove_assignments` accepts `ignore_permissions` and ignores it** — upstream lets a
  caller skip the check.
- **The `_assign`, `_comments` and `_liked_by` caches are written with a plain update**
  that never bumps `modified`, and nothing access-related ever reads them.
- **A task's `assigned_to` is a real assignment** (finding 15), and **assigning notifies
  the assignee** (finding 18).
- **Deleting a record removes its comments, communications, ToDos and notifications**
  (finding 19).
- **`email.make`** queues the send on Celery, honours `now` to send inside the request,
  claims the row under a lock before sending so it cannot go twice, copies to the session
  user's own address, and threads with `message_id` / `in_reply_to`.
- **An email subject with a line break is a 417 `ValidationError`, not a 500**, on the
  inline send path too (KNOWN_ISSUES §7, fixed in `backend/`).
- **Email templates render in a Jinja2 sandbox** — template text is user-authored.
- **Assignment rules:** the rule's access as `crm_app/permissions/assignment_rule.py`
  decides it; `last_user` and `current_index` are read-only; `bulk_apply` applies the
  rules to the documents named, through the same engine a save uses. A ToDo created by a
  rule records it (`ToDo.assignment_rule`, read-only).
- **`upload_file`** (multipart, from the CRM's uploader and the editor's image button):
  attaching to a record needs **write** permission on that record, and copying an
  existing file needs **read** permission on it (`check_write_permission` and the source
  check in `crm_app/api/upload.py`).
- **Call logs:** a call resolves to its lead, deal or contact by phone number (the
  `phonenumbers` library — it runs with no provider configured).
  **`create_lead_from_call_log` answers 404 for a missing call before checking write
  permission**, and ignores standard fields in the lead details.
- **Task and Note boards are company-wide by design.** CRM Call Log is open to every CRM
  role, reviewed and kept as upstream's role table grants; **Tag and Email Template now
  have a list rule and an object rule** in `backend/` (REBUILD_PLAN S21). Carry each over
  as `PORT_MAP.md` records it.

## 5. Acceptance

- pytest: every test in the port list passing with its expected answers unchanged; new
  tests for each item in section 4 no old test covers; the attachment rule as a matrix
  over readable and unreadable parents, through every door.
- `docs/http/08_activities_comments_notifications.http` and `06_tasks_notes_calls.http` in
  full.
- The body comparison over the same blocks.

## 6. Open questions

None. The line-break 500 was fixed in `backend/`, so parity copies the fix; the one
remaining KNOWN_ISSUES §7 candidate (`remove_multiple`) is in `PARITY_EXCEPTIONS.md`.
