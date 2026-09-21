# DOCUMENTS — bulk actions, rename, linked documents, link search

**Status: Provisional, 2026-09-16.** Written before FOUNDATION exists: the scope is right,
the details are guesses. **Rewrite against `backend_v2/docs/AS_BUILT.md` before running.**
Paths are from the repository root.

## 1. Scope

The generic operations every resource offers, after FOUNDATION built the base ViewSet's
CRUD. In the old backend each of these took a doctype as data; in `backend_v2` they become
per-resource routes (`/api/v1/leads/bulk-delete/`, `/api/v1/leads/search/`, …), and
**whether they are mixins every ViewSet inherits or endpoints in this app that look the
resource up is REBUILD_PLAN O7**, settled with the route map. They act on most doctypes,
so they come once most doctypes exist. The `PORT_MAP.md` rows under **DOCUMENTS**:

- **Method paths (6):** `crm.api.doc.delete_bulk_docs`,
  `crm.api.doc.get_linked_docs_of_document`, `crm.api.doc.remove_linked_doc_reference`,
  `frappe.client.rename_doc`,
  `frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs`,
  `frappe.desk.search.search_link`
- **No doctypes of its own.**

## 2. Depends on

SALES and ACTIVITIES — the doctypes these operations are exercised on, and the comments,
files and assignments a rename must repoint.

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
  history entry that named the document is repointed, and unique columns other than the
  key are handled so the rename does not collide with itself. The first port inserted a
  copy and deleted the original, which **deleted a renamed contact's email and phone rows
  and its deal links** (finding 13). `merge` raises rather than being silently ignored.
  Every refusal is `validate_rename`'s wording, each a 417.
- **Bulk delete checks permission on every document** before deleting any, in a bounded
  number of queries. **Above ten documents it is queued on Celery** and answers
  `"success"`. `Items are required` / `Items must be a list` are its refusals.
- **Bulk update runs inline below 20 documents and returns the failures, is queued from
  20 to 500, and is refused above 500** with upstream's sentence: `Bulk operations only
  support up to 500 documents.`
- **`search_link` goes through the doctype's queryset and field policy**, and **accepts
  `ignore_user_permissions` and ignores it**: honouring it would let an autocomplete list
  rows the caller cannot see. It answers `[{"value", "description"}]`.
- **Each of these is one of the doors** in `backend_v2/CLAUDE.md` hard rule 5.

## 5. Acceptance

- pytest for each item in section 4, the permission checks as a matrix.
- `docs/http/13_bulk_and_misc.http` and `11_permissions_matrix.http` in full; the rename
  blocks of `05_contacts_organizations.http`; the deal blocks of `04_deals.http` that
  depend on these calls.
- The body diff over the same blocks.

## 6. Open questions

None yet.
