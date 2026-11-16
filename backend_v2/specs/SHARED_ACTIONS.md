# SHARED_ACTIONS — bulk delete, linked documents, bulk update, rename, link search, export, and the conditions evaluator

**Status: Done** — gate passed 16 Nov 2026 (PRs #67, #68). Rewritten 16 Nov 2026 against `backend_v2/docs/AS_BUILT.md` and the
spec check (`tasks/SHARED_ACTIONS_00_spec_check_verdict.md`, 15 findings). Paths are from
the repository root. Open questions are at §6; the ones not yet answered are marked.

## 1. Scope

Lives in `core`, as `core/mixins/` and `core/conditions.py` — no app of its own. The
operations many resources offer, built as **mixins** a resource's `DocumentViewSet` opts
in to (REBUILD_PLAN S24). In the old backend each took a doctype name as data; here each
becomes the resource's own route (S25 rule 4):

| Mixin | Gives a resource | Old path it replaces |
|---|---|---|
| Bulk delete | `POST /api/v1/<resource>/bulk-delete/` | `crm.api.doc.delete_bulk_docs` |
| Linked documents | `GET /api/v1/<resource>/<name>/linked-documents/` | `crm.api.doc.get_linked_docs_of_document` |
| Unlink | `POST /api/v1/<resource>/<name>/linked-documents/` | `crm.api.doc.remove_linked_doc_reference` |
| Bulk update | `POST /api/v1/<resource>/bulk-update/` | `frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs` |
| Rename | `POST /api/v1/<resource>/<name>/rename/` | `frappe.client.rename_doc` |
| Link search | `GET /api/v1/<resource>/search/` | `frappe.desk.search.search_link` |
| List export | `GET /api/v1/<resource>/export/` | `frappe.desk.reportview.export_query` |

**List export is a `core` mixin here** (REBUILD_PLAN §4's app table, line 108); S24's list
omits it by oversight. The list view (`get_data`) and field metadata (`crm.api.doc.get_fields`)
are CONFIGURATION's, so `test_bulk_edit_fields.py` is CONFIGURATION's too.

**Routes.** A mixin's routes are DRF `@action`s on the mixin class, exactly as
`DocumentViewSet` already writes `value/` and `<name>/permissions/` (`backend_v2/core/views.py:184,220`).
That is FOUNDATION's settled form of rule 9: the resource is registered explicitly on its
app's `DocumentRouter` in `urls.py`, and **every generated route has its own row in
`PORT_MAP.md`**, written by the unit that opts the resource in. No mixin takes a resource
name as input.

**Not here:**

- **The assignment engine** (the port of `backend/crm_app/assignment_rules.py`) — **moved
  to the new ASSIGNMENTS unit** (A-7, [`ASSIGNMENTS.md`](ASSIGNMENTS.md)). It reads and
  writes Assignment Rule, its child rows, ToDo, `assign_to_user` and the template renderer
  (`assignment_rules.py:24-39`, `:174-184`, `:291-312`, `:413-436`), all built later; a
  stand-in would be replaced.
- **Ordinary single delete** is FOUNDATION's `DocumentViewSet.destroy`
  (`backend_v2/core/views.py:274-279`), already mapped from `frappe.client.delete`. The
  delete dialog calls it; it is a dependency here, not a mixin.
- **Which resource opts in to what** is each resource unit's (table below); its gate proves
  the routes on its own records.

### Who opts in (from the frontend)

| Operation | Resources (frontend source) | Unit that opts in |
|---|---|---|
| Bulk delete, linked documents, unlink | Lead, Deal, Contact, Organization, Task, Call Log (`frontend/src/components/ListBulkActions.vue:17-30,107-121`) | SALES, CONTACTS, ACTIVITIES |
| Bulk update | Lead, Deal, Contact, Organization, Task; Call Log hides it (`CallLogsListView.vue:175-183`) | SALES, CONTACTS, ACTIVITIES |
| Rename | Organization, SLA, Assignment Rule, Email Account, Email Template (`pages/Organization.vue:304-310`, `SlaPolicyView.vue:438-445`, `AssignmentRuleView.vue:735-743`, `EmailEdit.vue:191-196`, `EditEmailTemplate.vue:223-231`) | CONTACTS, SLA, ACTIVITIES, CONFIGURATION (Email Account, A-12) |
| Link search | every Link control's target | every unit, per resource |
| Export | every list using `ViewControls.vue:569-588` | every unit with a list view |

### The conditions evaluator

The port of `backend/crm_app/conditions.py`: the CRM editor's condition JSON, **evaluated
as data; saved Python is never executed** (FINDINGS 80). A malformed condition raises
`ConditionError` with a reason; `evaluate_safely` returns `(False, reason)`
(`conditions.py:37-65, 85-110`). It reads a document's values through a plain dictionary,
so it needs no later model. SLA uses it to pick an agreement; the assignment engine,
wherever Q-7 puts it, to pick a rule.

## 2. Depends on

FOUNDATION. Everything is tested on `tests_support` resources (§5), which already have
every reference shape this unit needs.

## 3. Read in `backend/` first

- `crm_app/api/doc.py` — bulk delete (`authorize_bulk_delete`, `perform_bulk_delete`,
  `delete_bulk_docs`, :637-828) and linked documents (:461-634)
- `crm_app/tasks.py:321-345` — the queued bulk delete and its reauthorization
- `crm_app/api/bulk_update.py`, `crm_app/bulk_update.py` — bulk update and its worker
- `crm_app/api/client.py` — `client_rename_doc` (:476-495), `search_link` (:653-735,
  `_search_doctypes` :191-210, `_user_query_filters` :45-60)
- `frappe_core/rename.py` — rename
- `frappe_core/delete_doc.py`, `frappe_core/children.py:283-326` (cleanup table),
  `frappe_core/links.py`
- `crm_app/api/reportview.py:162-226` — export
- `crm_app/conditions.py`
- `docs/FINDINGS.md` 13, 54, 80; `UPSTREAM_BUGS.md` #39; `specs/KNOWN_ISSUES.md:618-624`
- **What FOUNDATION built, to reuse and not rebuild:** `backend_v2/core/delete.py:29-87`
  (dynamic-link refusal), `core/children.py:300-378` (polymorphic-child and `Version`
  cleanup, the batch form), `core/views.py:94-181` (the queryset, `_object_by_name`,
  `has_object_rule`, the field allowlists), `core/query.py` (`fetch_rows`),
  `core/naming.py` (`validate_name`), `core/models.py:74` (`DYNAMIC_LINK_FIELDS`),
  `core/tasks.py`, and `tests_support` (`Widget`, `PointingDocument`, `DynamicReference`,
  `WidgetRow`)
- The framework source, only where `backend/` is silent: `frappe/model/rename_doc.py`,
  `frappe/model/delete_doc.py`, `frappe/desk/doctype/bulk_update/bulk_update.py`,
  `frappe/desk/search.py`, `frappe/desk/reportview.py` (`git show version-15:<path>`)

### The old tests

S14: tests that call the API are **ported** (expected answers unchanged); tests of
internals are **read and rewritten**. Here, only the generic mechanism can be tested —
on `tests_support` resources. **The real-doctype cases are proven by the unit that opts
that resource in**, and are listed in its spec under "Carried from SHARED_ACTIONS".

| File | Kind | Here (generic) | Real-doctype cases go to |
|---|---|---|---|
| `test_bulk_actions.py` | API | bulk update bands, failures, refusals | SALES (Lead); `add_multiple`/`remove_multiple` → ACTIVITIES |
| `test_delete_dependants.py` | API + ORM | **already rewritten** by FOUNDATION (`backend_v2/tests/test_delete_dependants.py`) — extend, don't duplicate | ACTIVITIES, SALES |
| `test_delete_link_check.py`, `test_delete_dialog_links.py`, `test_unlink_linked_docs.py` | API | the scan, titles, dedup, unlink skipping, bulk delete with links | SALES, CONTACTS, ACTIVITIES |
| `test_rename.py` | API | every reference shape, unique columns, refusals | CONTACTS (Contact + email/phone rows, Organization), SALES, ACTIVITIES |
| `test_reference_doctype_search.py` | API | search, the DocType branch (Q-8) | ACTIVITIES, SALES (the saved-reference case, :56-82) |
| `test_export_query.py` | API (+ one helper test) | formats, inputs, row rules, formatting | ACTIVITIES (Task), SALES (Lead) |
| `test_conditions.py` | internal | rewrite, on dictionaries | SALES (the model-conversion case, :279-295) |
| `test_phase3_endpoints.py`, `test_phase5_async.py`, `test_name_lookup.py` | API | their shared-action cases: bulk delete worker, linked documents with a slashed name | — |
| `test_address.py`, `test_currency.py`, `test_language.py`, `test_salutation_gender.py`, `test_email_template_rule.py` | API | — | their resources' units (search, rename permission) |
| `test_bulk_edit_fields.py` | API | — | CONFIGURATION (`get_fields`) |
| `test_assignment_engine.py`, `test_assignment.py`, `test_assignment_rule_*.py`, `test_task_assignment.py`, `test_owner_assignment.py`, `test_contact_delete_rule.py` | — | — | the engine's unit (Q-7), ACTIVITIES, SALES, CONTACTS |

## 4. Must not be lost

**Permissions are per endpoint, as the old one had them** — a mixin reuses the ViewSet's
hooks (`get_queryset()`, `has_object_rule()`, the field allowlists), but keeps whether the
old endpoint used list visibility, an object rule, both, or silent skipping:

| Operation | Old permission behaviour |
|---|---|
| Bulk delete | list-rule queryset as a batched prefilter, then the object `delete` rule on every existing survivor, before deleting any (`doc.py:642-688`) |
| Linked documents | `read` on the source, then each linked doctype's list rule (`doc.py:473-521`) |
| Unlink | loads each named item directly; **silently skips** missing, malformed, unknown or write-denied items; no check on the source (`doc.py:598-634`) |
| Bulk update | per document, as the caller; the queued worker **rechecks as the requesting user** (`bulk_update.py:111-134`) |
| Rename | loads by name, then the object `write` rule; a refusal is a **417 in `validate_rename`'s wording**, not a 404 (`client.py:476-495`) |
| Search, export | the list-rule queryset and the field allowlists (`fetch_rows`) |

**Bulk delete** (`doc.py:727-828`):
- Refusals, each a 417: `Doctype is required` (gone here: the resource is the URL),
  `Items are required`, `Items must be a list`.
- The threshold counts **existing authorized targets**, after missing names are dropped:
  more than ten (`BULK_DELETE_ENQUEUE_THRESHOLD = 10`) is queued on Celery, and the worker
  reauthorizes (`tasks.py:321-345`). Both paths answer `{"message": "success"}`.
- The batch is one transaction. It scans linked documents in a bounded number of queries,
  clears the references it can write, deletes linked rows when `delete_linked` is set,
  silently keeps linked rows whose own delete is refused, and **refuses the whole batch
  if a remaining reference the caller cannot see blocks a target**. Then the cleanup
  table (FOUNDATION's, extended by ACTIVITIES) and the targets go.

**Linked documents and unlink** (`doc.py:461-634`):
- The answer is a list of `{"doc", "title", "reference_docname", "reference_doctype"}`,
  with special titles for Call Log, Deal and Notification (`:461-469`) — each added by the
  unit that builds that model.
- It **deduplicates by document name alone**, so two doctypes sharing a name overwrite
  one another (`:489-502`). Copy it; it is a candidate for KNOWN_ISSUES.
- Unlink takes `items`, `remove_contact`, `delete`, and the port-added `doctype`/`docname`
  that clear direct Link fields (`frontend/src/components/DeleteLinkedDocModal.vue:219-228`).
  In v2 the source is the URL's resource and name. It answers `"success"`.

**Bulk update** (`api/bulk_update.py:31-77`, `bulk_update.py:34-134`):
- Below 20 documents: inline, answering the list of failed names. 20 to 500: queued,
  answering `None`. Above 500: a 417 titled `Too Many Documents`, with
  `Bulk operations only support up to 500 documents.`
- A scalar `docnames` becomes a one-item list; `data` is JSON text or an object;
  `task_id` is accepted and ignored. `action` stays an input (`update`; `submit` and
  `cancel` fail each document, since nothing is submittable; unknown actions fail each).
- **Upstream bug #39 is fixed, as in the old backend:** a missing document goes into the
  failures and the rest continue (`UPSTREAM_BUGS.md:1024-1055`).
- Each document commits on its own; failures are logged and collected.
- Upstream's `Bulk operation is enqueued in background.` alert is deliberately absent
  (`KNOWN_ISSUES.md:618-624`).

**Rename** (`frappe_core/rename.py`, `client.py:476-495`):
- **Identity-preserving and transactional**: one transaction copies the row under the new
  name, repoints every followed reference, deletes the old row, and restores the parked
  values of unique columns other than the key, so the rename does not collide with
  itself (`rename.py:113-139`). The first port skipped the repointing and **deleted a
  renamed contact's email and phone rows and its deal links** (FINDINGS 13).
- References followed: Django foreign keys, polymorphic child `parent`s, and doctype/name
  pairs. The old code lists seven global pairs (`rename.py:30-38`); here each model's
  `DYNAMIC_LINK_FIELDS` declares them (`core/models.py:74`). That equals the old seven
  pairs only if every model with one of those column shapes declares it, so **a guard test
  requires every `*_doctype` + `*_name`/`*_docname`/`*_doc` pair to be declared** (A-9).
  Plain-text Link columns (`TEXT_LINK_FIELDS`) are **not** repointed, as in the old code
  (rename never calls `links.py`): parity. Repointing them is PE-5, `proposed` and parked
  for the owner (A-9, `backend_v2/docs/PARITY_EXCEPTIONS.md`; the root
  `specs/KNOWN_ISSUES.md` is read-only here, so PE-5 is the record).
- `merge` raises rather than being ignored. The four refusals and the merge refusal are
  417 `ValidationError`s in `validate_rename`'s wording (`client.py:478-493`).

**Link search** (`client.py:653-735`):
- Three answer shapes: `[{"value", "description"}]` normally; with
  `SHOW_TITLE_FIELD_IN_LINK` also `label`, the title, with the name moved into
  `description` (`:718-729`); and the DocType branch's answer, which is not a resource:
  it becomes **`GET /api/v1/doctypes/search/`** in `core`, same inputs and answer, read
  from `core.doctypes` (A-8; the frontend's Link controls send it for every
  `options: "DocType"` field, `frontend/src/components/Controls/Link.vue:132-140,178-185`).
- Inputs: `txt`, `filters`, `page_length`, `query`, `reference_doctype`, surplus keywords,
  and `ignore_user_permissions` — **accepted and ignored**, because honouring it would
  let an autocomplete list rows the caller cannot see. Rows exclude disabled ones unless
  `include_disabled`; search covers the name and the declared title field.
- Resource-specific branches belong to the resource's unit: User's `ignore_user_type`
  (`:683-691`, ACCOUNTS), Address's dynamic-link filter rewrite (CONTACTS). The mixin
  offers a hook for them.

**Export** (`reportview.py:162-226`):
- The answer is a **raw download, not the envelope**: status 200, `text/csv` or the XLSX
  type, `Content-Disposition: attachment; filename="<title>.<ext>"`. Exactly `"CSV"`
  selects CSV; anything else selects XLSX.
- Inputs: `fields`, `filters`, `or_filters`, `order_by`, `file_format_type`, `title`,
  `selected_items`, `page_length`, `start`. `selected_items` replaces both filter sets;
  `page_length` and `start` are deliberately ignored, so there is no row cap.
- It reads through the list-rule queryset and field allowlists: a hidden or manager-only
  field never reaches the file. The old tests pin CSV quoting, the workbook, duration
  formatting and HTML stripping (`test_export_query.py:55-135`).

**Conditions are data, never code** (§1).

## 5. Acceptance

- pytest, on `tests_support` resources: the generic cases of every file in §3's table,
  ported with their expected answers unchanged; new tests for each item in §4 no old test
  covers; each endpoint's permission behaviour as a matrix (allowed, denied, invisible);
  the conditions evaluator on its own.
- **Reuse FOUNDATION's fixtures**: `Widget` is the target; `PointingDocument.widget` a
  protected FK (`tests_support/models.py:187-192`), `DynamicReference` a doctype/name
  pair (`:241-246`), `WidgetRow.related_widget` a link from a child table (`:104-136`),
  and `Version` the change history. Add a fixture only for a shape these lack (a unique
  column other than the key, for rename), under `isolate_apps` or in `tests_support`,
  never at import time in a test module (guard 4).
- The guards stay green: every mixin route reads through `get_queryset()` or
  `_object_by_name()`; no direct manager reads in `core/mixins/` (the A-6 scan covers it).
- **The `.http` blocks are proven by the units that opt in**: the rename blocks of
  `05_contacts_organizations.http` with CONTACTS, the bulk blocks of `13_bulk_and_misc.http`
  and `11_permissions_matrix.http` with the resources they touch.
- AS_BUILT gains a recipe, "Opting a resource in to a shared action", and each later
  unit's spec a "Carried from SHARED_ACTIONS" list.

## 6. Questions

Settled in this rewrite (the spec check's findings 7, 14, 15; logged in the progress report):

- **References rename follows** are declared with FOUNDATION's `DYNAMIC_LINK_FIELDS`, and
  foreign keys and polymorphic parents are found from model metadata. No new registry.
- **How a resource opts in:** by adding the mixin class to its `DocumentViewSet`'s bases;
  each mixin uses only the ViewSet's existing hooks, plus a named hook where a resource
  needs its own branch (search's User and Address branches, linked-document titles).
- **Export ownership:** `core` (§1).

Decided on the owner's behalf by the supervising session with a Codex second opinion
(16 Nov 2026; for the owner's review):

- **A-7 — the assignment engine** goes to a new unit, ASSIGNMENTS, after NOTIFICATIONS and
  before SLA (§1 "Not here"; `specs/README.md`).
- **A-8 — DocType link search** is `GET /api/v1/doctypes/search/` in `core` (§4).
- **A-9 — rename and plain-text Links**: parity, plus the declaration guard (§4);
  repointing them is parked for the owner as a proposed parity exception.
- **A-10 — how a mixin applies another resource's row rules** (the linked-documents scan
  and bulk delete read and write rows of other models):
  1. `core.resources.rules_for(model)` resolves a routed model's rules from the production
     routers' explicit registrations — no registry, no new declaration.
  2. `list_rule` and `has_object_rule` become `@staticmethod`s (or delegate to the app's
     `permissions.py`), so they cannot depend on `self.request`; FOUNDATION's ViewSets and
     its AS_BUILT recipe change with them, and a guard checks it.
  3. One model registered on two different production ViewSets is refused by a Django
     system check.
  4. **Child rows follow the old sequence exactly**: admitted with no list rule, each
     resolved to its *actual* parent, and only the parent's
     `has_object_rule(user, parent, "read")` applied during discovery (`"write"` at unlink
     and delete) — never the parent's `list_rule` (`backend/crm_app/api/doc.py:384-422`).
  5. Any other model the scan reaches must be routed, a child, in
     `IGNORE_LINKS_ON_DELETE`, or declare `ROW_RULES = "<app>.permissions.<name>"`; a guard
     fails otherwise. No silent fallback.
