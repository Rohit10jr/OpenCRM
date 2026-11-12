# ACTIVITIES — comments, email, notes, tasks, call logs, files, tags, likes, assignments

**Status: Provisional.** Written 2026-09-16; call logs moved in from the old TELEPHONY unit
on 2026-09-22 (REBUILD_PLAN S12). Written before FOUNDATION exists: the scope is right, the
details are guesses. **Rewrite against `backend_v2/docs/AS_BUILT.md` before running.**
Paths are from the repository root.

## 1. Scope

App `activities`: everything that hangs off a lead or a deal and appears on its timeline.
The `PORT_MAP.md` rows under **ACTIVITIES**:

- **Doctypes:** Comment, Communication, FCRM Note, CRM Task (integer key), **CRM Call
  Log**, File, Tag, Email Template, and ToDo (withheld — no route)
- **Method paths (20):** `crm.api.activities.get_activities`,
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

## 2. Depends on

SALES (the records activities hang off), NOTIFICATIONS (mentions and assignments create
notifications).

## 3. Read in `backend/` first

- `frappe_platform/models.py` — Comment, Communication, File, Tag, Email Template, ToDo
- `crm_app/models/core_sales.py` — CRM Task, FCRM Note; `crm_app/models/telephony.py` —
  CRM Call Log
- `crm_app/permissions/attachments.py` — the rule that defers to the parent record
- `frappe_core/assignment.py`, `frappe_core/doc_caches.py`, `crm_app/async_signals.py`
- `crm_app/api/activities.py`, `api/comment.py`, `api/client.py` (assign and like),
  `api/assignment_rule.py`, `api/misc.py`, `api/communication.py`,
  `crm_app/communication.py`, `api/email_template.py`, `crm_app/tasks.py`
- Call logs: `crm_app/api/call_log.py`, the call-log parts of `crm_app/integrations/api.py`,
  `integrations/call_log.py`, `integrations/phone.py`
- `specs/UNROUTED_DOCTYPES.md` (ToDo), `specs/VERSION_HISTORY.md` (the timeline reads the
  change history), `specs/KNOWN_ISSUES.md` §3 and §7
- `docs/FINDINGS.md` entries 15, 16, 18, 19 and 22
- Tests: `test_attachment_access.py`, `test_assignment.py`,
  `test_assignment_notifications.py`, `test_task_assignment.py`, `test_doc_caches.py`,
  `test_email_make.py`, `test_email_template.py`, `test_versions.py`,
  `test_call_log_endpoints.py`, `test_telephony_shared.py`

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
- **Email templates render in a Jinja2 sandbox** — template text is user-authored.
- **Call logs:** a call resolves to its lead, deal or contact by phone number (the
  `phonenumbers` library — it runs with no provider configured).
  **`create_lead_from_call_log` answers 404 for a missing call before checking write
  permission**, and ignores standard fields in the lead details.
- **Task and Note boards are company-wide by design.** Tag, Email Template and CRM Call
  Log are open to every authenticated user today, and keep that access (REBUILD_PLAN S21).

## 5. Acceptance

- pytest for each item in section 4; the attachment rule as a matrix over readable and
  unreadable parents, through every door.
- `docs/http/08_activities_comments_notifications.http` and `06_tasks_notes_calls.http` in
  full.
- The body comparison over the same blocks.

## 6. Open questions

- The KNOWN_ISSUES §7 candidates in `PARITY_EXCEPTIONS.md`: fix the 500 on a subject with
  a line break, or keep parity?
