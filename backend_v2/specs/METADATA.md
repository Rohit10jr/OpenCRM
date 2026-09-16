# METADATA — the list engine, saved views, field layouts and field metadata

**Status: Provisional, 2026-09-16.** Written before FOUNDATION exists: the scope is right,
the details are guesses. **Rewrite against `backend_v2/docs/AS_BUILT.md` before running.**
Paths are from the repository root.

## 1. Scope

App `metadata`. **The keystone unit**: six screens render from `get_data`, and it is where
the filter grammar, `@me`, saved views and column resolution meet. The `PORT_MAP.md` rows
under **METADATA**:

- **Doctypes:** CRM View Settings (integer key), CRM Fields Layout, CRM Form Script,
  CRM Global Settings; and the per-user list settings model
- **Method paths (22):** `crm.api.doc.get_data`; the field and filter helpers
  (`get_fields`, `get_filterable_fields`, `get_group_by_fields`, `get_quick_filters`,
  `update_quick_filters`, `sort_options`); `crm.api.views.get_views`; the eight
  `crm_view_settings.*` calls; the three `crm_fields_layout.*` calls;
  `frappe.desk.form.load.getdoctype`; `frappe.model.utils.user_settings.get` and `save`

## 2. Depends on

FOUNDATION. It is built **before** the CRM doctypes exist, so it is tested against the
test-only doctypes. Each CRM app later supplies its own list definition — default
columns and rows, kanban settings, fields that cannot be filtered — through whatever
convention this unit sets and records in `AS_BUILT.md`.

## 3. Read in `backend/` first

- `frappe_core/api/doc.py` — `get_data` itself
- `crm_app/api/doc.py`, `api/views.py`, `api/view_settings.py`, `api/fields_layout.py`,
  `api/form_load.py`, `api/user_settings.py`, `api/form_script.py`
- `frappe_core/metadata.py`, `frappe_core/field_meta.py`, `crm_app/metadata_hooks.py`
- `crm_app/data/doctype_meta.json` and `backend/scripts/generate_field_meta.py`, which
  builds it from the upstream DocType JSON
- `crm_app/models/metadata.py`, `crm_app/permissions/metadata_docs.py`
- `docs/PORT_PLAN.md` section 4, trap 2 — views and layouts are runtime data, not code
- Tests: `test_get_data.py`, `test_phase4_metadata.py`, `test_form_load.py`,
  `test_list_definitions.py`, `test_kanban_counts.py`

## 4. Must not be lost

- **`get_data`'s response shape**, and every key in it even when its value is empty.
- **It reads through the doctype's own queryset and field policy.** It is one of the
  doors in `backend_v2/CLAUDE.md` hard rule 5.
- **Kanban counts do not leak** rows the caller cannot read.
- **A public view is readable by everyone and deletable only by its owner.** The list
  rule and the object rule differ here on purpose.
- **A kanban column per user is built from every user**, as upstream builds it without a
  permission check; that is why `User` reads stay open.
- **`getdoctype` puts `docs` and `user_settings` beside `message`.** frappe-ui returns the
  whole body when `docs` is present.
- **The field metadata file is generated, and a test fails if it goes stale.**

## 5. Acceptance

- pytest on test-only doctypes for the engine; each saved-view permission shown failing
  without its rule.
- `docs/http/07_views_and_metadata.http` turns green only once SLA exists; this unit's
  gate names the blocks it owns.
- The body diff over those blocks.

## 6. Open questions

- Where a CRM app declares its list definition: on its ViewSet, or a small list
  definition class beside it. To settle in FOUNDATION's conventions, or here.
