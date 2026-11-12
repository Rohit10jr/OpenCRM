# DATA_IMPORT — CSV import of new records, and the import template

**Status: Provisional** — the scope is right, the details are guesses. **Rewrite against
`backend_v2/docs/AS_BUILT.md` before building.** Paths are from the repository root.

## 1. Scope

Lives in `core`, as `core/data_import/`. The `PORT_MAP.md` rows under **DATA_IMPORT**:

- **Doctypes:** Data Import (routed, System Manager only), Data Import Log (withheld — no
  route; `specs/UNROUTED_DOCTYPES.md`)
- **Method paths (4):** `frappe.core.doctype.data_import.data_import.get_preview_from_template`,
  `get_import_logs`, `form_start_import`, `download_template`

What the old backend supports, and so what parity means here: **CSV upload, inserting new
records only**, into the six importable doctypes — CRM Lead, CRM Deal, Contact, CRM
Organization, CRM Task, CRM Call Log (`IMPORTABLE_DOCTYPES` in
`backend/crm_app/data_import/documents.py`). Google Sheets and "Update existing records"
are refused clearly; failed rows cannot be downloaded (`specs/KNOWN_ISSUES.md` §8).

## 2. Depends on

SALES, CONTACTS and ACTIVITIES: each row is written through its doctype's normal create
path, so every importable doctype must exist with its rules. It comes last, beside
INTEGRATIONS.

## 3. Read in `backend/` first

- `crm_app/data_import/` — `importer.py` (parsing, header matching, previews, without
  writing), `run.py` (the import job), `validation.py` (save validation),
  `documents.py` (which doctypes, and how a row is written), `exporter.py` (the template)
- `crm_app/api/data_import.py`, `crm_app/permissions/data_import.py`, the Data Import
  models in `frappe_platform/models.py`
- The version-15 originals, which the old backend follows name for name:
  `git show version-15:frappe/core/doctype/data_import/importer.py`, `exporter.py`,
  `data_import.py`
- `specs/KNOWN_ISSUES.md` §8; `UPSTREAM_BUGS.md` 68 and 76 and the other Data Import
  entries
- **Tests to port** (REBUILD_PLAN S14): `test_data_import_doctypes.py`,
  `test_data_import_run.py`, `test_data_import_template.py`,
  `test_data_import_validation.py`. To read and write again: `test_data_import_parsing.py`.
  The spec check confirms the list.

## 4. Must not be lost

- **System Manager only**, on the doctype and through every door — including the generic
  document calls, which can reach the withheld log too. Not the target doctype's upstream
  `import` right, which no CRM role holds (`UPSTREAM_BUGS.md` 68).
- **Each row goes through the importable doctype's own create path**, so an imported row
  obeys exactly the rules of one made by hand; one transaction per document, a failure
  logged against its row, never aborting the import.
- **Starting an import is claimed atomically** (`job_claimed_at`, one conditional update),
  and a redelivered job never runs twice; rows already logged are skipped on retry.
- **Every message, warning and status follows version-15**, verbatim; the old backend's
  recorded divergences are kept — each marked `Port only:` in `crm_app/data_import/`:
  a UTF-8 byte-order mark is stripped (Excel's "CSV UTF-8" adds one, and upstream then
  loses the first column); a short row is a warning, not a crash; a contact's first email
  and phone become primary when the file does not say; a mapped contact email or phone
  goes to the child table; an ID column is skipped with a warning, since this is
  insert-only; the preview reads only the stored file, never a path from the request.
- **Assignment rules apply to imported rows**, as in version-15: its `apply` skips only
  patches, installs and the setup wizard, and only `update_due_date` skips imports
  (`frappe/automation/doctype/assignment_rule/assignment_rule.py`). The old backend
  matches; do not add an import skip.
- **Live progress** reaches the screen through the realtime events NOTIFICATIONS
  publishes (`data_import_refresh`).

## 5. Acceptance

- pytest: every test in the port list passing with its expected answers unchanged, and
  new tests for each item in section 4 no old test covers.
- The Playwright import test (`frontend/tests/e2e/data-import.spec.js`) passes against
  `backend_v2` once the frontend moves (REBUILD_PLAN S22); until then, the body diff over
  the four method paths with a fixed CSV.

## 6. Open questions

None.
