# SHARED_ACTIONS — bulk actions, rename, linked documents, link search, export, conditions and the assignment engine

**Status: Provisional** — the scope is right, the details are guesses. **Rewrite against
`backend_v2/docs/AS_BUILT.md` before building.** Paths are from the repository root.

## 1. Scope

Lives in `core`, as `core/mixins/` — no app of its own. The operations many resources
offer, built as **mixins** that a resource's ViewSet opts in to (REBUILD_PLAN S24). In the
old backend each of these took a doctype name as data; in `backend_v2` each becomes the
resource's own route:

| Mixin | Gives a resource | Old path it replaces |
|---|---|---|
| Bulk delete | `POST /api/v1/<resource>/bulk-delete/` | `crm.api.doc.delete_bulk_docs` |
| Bulk update | `POST /api/v1/<resource>/bulk-update/` | `frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs` |
| Rename | `POST /api/v1/<resource>/<name>/rename/` | `frappe.client.rename_doc` |
| Linked documents | `GET` and `POST` on `/api/v1/<resource>/<name>/linked-documents/` | `crm.api.doc.get_linked_docs_of_document`, `remove_linked_doc_reference` |
| Link search | `GET /api/v1/<resource>/search/` | `frappe.desk.search.search_link` |
| List export | `GET /api/v1/<resource>/export/` (CSV or Excel) | `frappe.desk.reportview.export_query` |

The exact routes go into the route map with the rules of REBUILD_PLAN S25. The list view
(`get_data`) and field metadata are mixins too, but they belong to CONFIGURATION.

**Two shared services, built here because units on both sides of SALES need them**
(owner, rebuild review):

- **The conditions evaluator** — the port of `backend/crm_app/conditions.py`. SLA uses
  it to pick the agreement that applies, and assignment rules to pick the rule. A
  condition is the CRM editor's JSON, **evaluated as data; saved Python is never
  executed** (FINDINGS 80).
- **The assignment engine** — the port of `backend/crm_app/assignment_rules.py`
  (version-15's Assignment Rule logic): which rule applies to a saved document, and who it
  goes to. SALES calls it when a lead or deal is saved, the way it calls SLA. The
  Assignment Rule doctypes, their routes and `bulk_apply` belong to ACTIVITIES, which
  builds on this engine.

**It runs right after FOUNDATION**, before the resource units, and is tested on the
test-only resources. Each resource's unit — SALES, CONTACTS, ACTIVITIES and the rest — then
adds the mixins it needs to its own ViewSets, so no unit ever edits another unit's files.

## 2. Depends on

FOUNDATION.

## 3. Read in `backend/` first

- `crm_app/api/doc.py` — bulk delete and the linked-document calls
- `crm_app/api/client.py` — `rename_doc` and `search_link`
- `frappe_core/rename.py` — renaming in place
- `crm_app/api/bulk_update.py`, `crm_app/bulk_update.py`, `crm_app/tasks.py`
- `frappe_core/delete_doc.py`, `frappe_core/links.py`, `crm_app/api/reportview.py` (export)
- `crm_app/conditions.py`, `crm_app/assignment_rules.py`; `docs/FINDINGS.md` 80
- `docs/FINDINGS.md` entry 13; `UPSTREAM_BUGS.md` #39
- The framework source for the originals: `frappe/model/rename_doc.py`,
  `frappe/model/delete_doc.py`, `frappe/desk/doctype/bulk_update/bulk_update.py`,
  `frappe/desk/search.py`, `frappe/desk/reportview.py`,
  `frappe/automation/doctype/assignment_rule/assignment_rule.py`
- Tests to read and write again: `test_conditions.py`, and the engine's cases in the
  assignment-rule tests
- **Tests to port** (REBUILD_PLAN S14): `test_bulk_actions.py`, `test_bulk_edit_fields.py`,
  `test_rename.py`, `test_delete_dependants.py`, `test_delete_dialog_links.py`,
  `test_delete_link_check.py`, `test_unlink_linked_docs.py`,
  `test_reference_doctype_search.py`, `test_export_query.py`. Their routes exist only once
  a resource opts in, so each is ported against the test-only resources here, and its
  blocks on real resources are proven by the units that opt in. The spec check confirms
  the list.

## 4. Must not be lost

- **Rename happens in place.** Every Link, Dynamic Link, child-row `parent` and change
  history entry that named the record is repointed, and unique columns other than the key
  are handled so the rename does not collide with itself. The first port inserted a copy
  and deleted the original, which **deleted a renamed contact's email and phone rows and
  its deal links** (finding 13). `merge` raises rather than being silently ignored. Every
  refusal is `validate_rename`'s wording, each a 417.
- **Bulk delete checks permission on every record** before deleting any, in a bounded
  number of queries. **Above ten records it is queued on Celery** and answers
  `"success"`. `Items are required` / `Items must be a list` are its refusals.
- **Bulk update runs inline below 20 records and returns the failures, is queued from 20
  to 500, and is refused above 500** with upstream's sentence: `Bulk operations only
  support up to 500 documents.`
- **Link search goes through the resource's queryset and field rules**, and **accepts
  `ignore_user_permissions` and ignores it**: honouring it would let an autocomplete list
  rows the caller cannot see. It answers `[{"value", "description"}]`.
- **Export reads through the resource's queryset and field rules** like every other door:
  a hidden or manager-only field never reaches the file.
- **Conditions are data, never code.** A malformed condition raises `ConditionError`
  with a reason; the safe entry point turns that into "does not match" plus the reason
  (`conditions.py`, the wrapper around the evaluator).
- **A failed auto-assignment never fails the save**: upstream `msgprint`s
  `Auto assignment failed: {0}`; the old backend logs that text at warning level and the
  document saves (`assignment_rules.py`, the `ConditionError` handler).
- **Each mixin is one of the doors** in the root `CLAUDE.md` (rule 11): it uses the
  resource's own queryset, permission and field rules — never a lookup of its own.

## 5. Acceptance

- pytest: every test in the port list passing with its expected answers unchanged, on the
  test-only resources; new tests for each item in section 4 no old test covers; the
  permission checks as a matrix; the conditions evaluator and assignment engine on their
  own, with a stand-in document. The test-only resources include one that others point at by foreign key, by a
  doctype-and-name pair, from a child table and from the change history, so rename is
  tested against every kind of reference.
- **The `.http` blocks are proven by the units that opt in**, because the routes only exist
  once a real resource uses the mixins: the rename blocks of `05_contacts_organizations.http`
  with CONTACTS, the bulk blocks of `13_bulk_and_misc.http` and `11_permissions_matrix.http`
  with the resources they touch. Each such unit's gate lists them.

## 6. Questions for the owner — after the spec check, before the first build brief

Claude proposes an answer to each, the owner settles it, and it goes into `AS_BUILT.md`:

- **How a model declares the references rename must follow.** Foreign keys can be found
  automatically; doctype-and-name pairs (`reference_doctype` / `reference_name`) must be
  declared.
- **How a resource opts in** — the mixin names, and what each needs from the ViewSet.
- **How a saving model calls the assignment engine and SLA** — a direct call from its
  service, without either app importing the other's models.
