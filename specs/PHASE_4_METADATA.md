# Phase 4 — Metadata Layer

> **PROVISIONAL** — flip this header to Authoritative when your gate passes.
>
> **Read `specs/AS_BUILT.md` first.** It lists what phases 0-2 actually built; where it
> and this spec disagree, it wins.

**Fan out.** Runs *after* phase 3, not before it — phase 0 already built `get_data`'s
four-step resolution and left `_load_saved_view` as a registered provider, so phase 3's
metadata endpoints read that seam without needing this phase filled in first.

### This phase owns C7

`frappe_core/metadata.py` keys its filterable and group-by allowlists on **Django
internal types** (`FILTERABLE_INTERNAL_TYPES`, `GROUP_BY_INTERNAL_TYPES`), which is lossy
both ways: `Long Text`/`Small Text`/`Text Editor` all collapse to `TextField`, and
`Duration`/`Rating` are indistinguishable from `IntegerField`/`FloatField`. So `Duration`
is currently group-by-able only by accident.

Phase 1 records each field's original Frappe fieldtype — filter on **that** and delete the
internal-type sets. `metadata._frappe_fieldtype` already exists as the resolver.

### And C6, partly

`get_data`'s kanban branch is structural: column resolution from a Link target or Select
options works, but `get_records_based_on_order` (per-column manual ordering) and
`getCounts` (the email/comment/task/note badge counts) are absent. The counts need the
`Comment` and `ToDo` models, both of which are ported.

Source: `crm_view_settings` (328 LOC, 8 endpoints), `crm_fields_layout` (259 LOC, 3),
`crm_form_script`, `crm_dashboard`, and `api/doc.py:get_data`.

---

## 1. Why this phase exists

This is **trap 2** from `PORT_PLAN.md` §4. Users define their own list views, columns,
filters, and form layouts **at runtime**. That means the app needs metadata *tables*
alongside the hard-coded models. Teams that hard-code everything hit a wall here and
restructure.

Concretely, `get_data` cannot return the right columns without this layer — phase 0
stubs it to controller defaults, and this phase makes it real.

---

## 2. Components

### `CRM View Settings`
Per-user, per-doctype saved views. Verified lookup key from `get_data`:

```python
{"dt": doctype, "type": view_type or "list", "is_standard": 1, "user": session_user}
```

Stores `columns` and `rows` as JSON. `view_type` ∈ `list`, `kanban`, `group_by`.
Also supports non-standard (named) views the user creates and switches between.
A daily job clears old versions (`clear_old_versions`) — that's phase 5.

### `CRM Fields Layout`
Form layout: tabs → sections → columns → fields. PK is `format:{dt}-{type}`.
This is where the **layout fieldtypes deliberately skipped in phase 1**
(`Section Break`, `Column Break`, `Tab Break`) come back — as layout data, not
model columns.

### Column resolution order
Reimplement exactly as `get_data` does it:

1. Explicit `columns`/`rows` passed by the caller → custom view, use as-is
2. Else the user's saved `CRM View Settings` for this doctype+type
3. Else the controller's `default_list_data()`
4. Else `[name, modified]`

Then: every column key must also appear in `rows`; hidden fields are dropped; the
`group_by_field` is appended to `rows` if missing.

> **Already built.** Phase 0 implemented all four steps in
> `backend/frappe_core/api/doc.py:get_data`, in upstream's order, plus the two fixups
> (`_liked_by` width `10rem`→`50px`, hidden-column removal). Step 2 is the only stub —
> see §2a. Covered by `backend/tests/test_get_data.py`.

---

## 2a. The seam phase 0 left for you

**Do not edit `get_data`.** Step 2 is a registered provider, not a code change:

```python
from frappe_core import registry

def saved_view(doctype, user, view_type):
    """Return {"columns": [...], "rows": [...]} or None to fall through."""
    ...

registry.register_metadata_hooks(
    "CRM Lead",
    list_columns_provider=saved_view,
    filterable_fields_provider=...,   # optional; overrides the phase-0 default
)
```

Contract, all asserted in `backend/tests/test_hooks.py`:

- The provider is called with `(doctype, user, view_type or "list")` — `view_type`
  already defaulted, so the `{"dt", "type", "is_standard": 1, "user"}` lookup key in §2
  maps straight onto the arguments.
- It is called **only when the caller passed no `columns`/`rows`**, matching upstream's
  `if not custom_view` guard. A custom view must not hit the database.
- Returning `None` falls through to `default_list_data()` — that is upstream's `elif`.
- A non-`None` return sets `is_default = False`.

Phase-0 stubs to replace, all marked `PHASE 4` in `frappe_core/api/doc.py`:

| Stub | Returns now | Owes |
|---|---|---|
| `_load_saved_view` | `None` unless a provider is registered | the CRM View Settings lookup |
| `_get_views` | `[]` | `crm/api/views.py:get_views` |
| `_get_form_script` | `None` | `crm_form_script.get_form_script` (also `list_script`) |
| `is_default` / `custom_view_name` | never re-reads the saved view | upstream reads `load_default_columns` off it |

The **response shape is already final** — every key upstream returns is present and
tested. Filling these in must not add or rename a key.

### `default_list_data()`
Each doctype controller defines its own default columns and rows. Port these as a
classmethod on each model. Phase-1 agents may have skipped them — check, and fill the
gaps here.

### `CRM Form Script`
User-authored **JavaScript** run client-side on forms. Store and serve it; do not try
to execute it server-side. Treat as untrusted content and note the XSS surface — it is
admin-authored upstream, so gate write access to admins.

### `CRM Dashboard`
Chart definitions backing `api/dashboard.py`. `get_chart` and `get_dashboard` accept a
date range and user filter.

---

## 3. Filterable / sortable field metadata

`doc.py` defines allowlists per capability, verified from source:

- **Filterable**: `Check, Data, Float, Int, Currency, Dynamic Link, Link, Long Text, Select, Small Text, Text Editor, Text, Duration, Rating, Date, Datetime`
- **Group-by**: `Check, Data, Float, Int, Currency, Dynamic Link, Link, Select, Duration, Date, Datetime` — narrower, no free text
- **Sortable**: any field that holds a value (excludes layout types)

Standard fields are appended to the filterable list and must be present:
`name, owner, modified_by, creation, modified, _user_tags, _liked_by, _comments, _assign`.

A controller may declare `get_non_filterable_fields()` to subtract from this. Honour it.

> **Phase-0 status.** `frappe_core/metadata.py` already implements
> `get_filterable_fields`, `get_group_by_fields` and the standard-field list, honours
> `get_non_filterable_fields()` (resolved off the model class, as upstream resolves it
> off the controller), and applies the two allowlists. **But it expresses them as
> Django internal types, not Frappe fieldtypes** — `FILTERABLE_INTERNAL_TYPES` /
> `GROUP_BY_INTERNAL_TYPES`. That mapping is lossy in both directions:
> `Long Text`/`Small Text`/`Text Editor` all collapse to `TextField`, and
> `Duration`/`Rating` are indistinguishable from `IntegerField`/`FloatField`.
>
> **Phase 4 owns fixing this.** Once phase 1 records each field's original Frappe
> fieldtype, filter on *that* and delete the internal-type sets. Until then the group-by
> list is slightly wrong: `Long Text`, `Small Text` and `Text Editor` are correctly
> excluded, but so is nothing else that maps to `TextField` — and `Duration`, which
> upstream *does* allow to group by, is currently included only because it shares
> `IntegerField`. Flagged in `PROGRESS.md`.

---

## 4. Acceptance criteria

- [ ] Saved views persist per user and per doctype+view_type
- [ ] `get_data` resolves columns through the full 4-step order
- [ ] Kanban resolves columns from a Link target or Select options
- [ ] Form layouts render tabs/sections/columns matching upstream
- [ ] Filterable and group-by allowlists match the source exactly
- [ ] `get_non_filterable_fields()` is respected
- [ ] Standard fields appear in filter dropdowns
- [ ] One user's saved view is invisible to another user
- [ ] Allowlists are keyed on the **Frappe fieldtype**, not the Django internal type
- [ ] `get_data`'s response keys are unchanged from phase 0 — the four `PHASE 4` stubs
      are filled in, nothing is added or renamed
