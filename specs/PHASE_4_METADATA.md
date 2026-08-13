# Phase 4 — Metadata Layer

> **PROVISIONAL** — the phase-0 agent must revise and flip to Authoritative.

**Fan out.** Needs phase 0 and phase 1 cluster 6.

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
