# SHARED_ACTIONS — bulk actions, rename, linked documents, link search

**Status: Provisional.** Written 2026-09-16 as DOCUMENTS; renamed, moved to wave 2 and
folded into `core` on 2026-09-22 (REBUILD_PLAN S12, S24). Written before FOUNDATION
exists: the scope is right, the details are guesses. **Rewrite against
`backend_v2/docs/AS_BUILT.md` before running.** Paths are from the repository root.

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

The exact routes go into the route map with the rules of REBUILD_PLAN S25. The list view
(`get_data`) and field metadata are mixins too, but they belong to CONFIGURATION.

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
- `docs/FINDINGS.md` entry 13; `docs/UPSTREAM_BUGS_PHASE_3-6.md` #39
- The framework source for the originals: `frappe/model/rename_doc.py`,
  `frappe/model/delete_doc.py`, `frappe/desk/doctype/bulk_update/bulk_update.py`,
  `frappe/desk/search.py`
- Tests: `test_rename.py`, `test_delete_dependants.py`, `test_bulk_actions.py`

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
- **Each mixin is one of the doors** in the root `CLAUDE.md`, rebuild hard rule 6: it uses
  the resource's own queryset, permission and field rules — never a lookup of its own.

## 5. Acceptance

- pytest for each item in section 4 on the test-only resources, the permission checks as
  a matrix. The test-only resources include one that others point at by foreign key, by a
  doctype-and-name pair, from a child table and from the change history, so rename is
  tested against every kind of reference.
- **The `.http` blocks are proven by the units that opt in**, because the routes only exist
  once a real resource uses the mixins: the rename blocks of `05_contacts_organizations.http`
  with CONTACTS, the bulk blocks of `13_bulk_and_misc.http` and `11_permissions_matrix.http`
  with the resources they touch. Each such unit's gate lists them.

## 6. Decisions this unit takes, and records in `AS_BUILT.md`

- **How a model declares the references rename must follow.** Foreign keys can be found
  automatically; doctype-and-name pairs (`reference_doctype` / `reference_name`) must be
  declared.
- **How a resource opts in** — the mixin names, and what each needs from the ViewSet.

## 7. Open questions

None yet.
