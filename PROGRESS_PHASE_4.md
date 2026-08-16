# Phase 4 — PASS   [branch: phase-4-metadata]
Started: 2026-08-16   Finished: 2026-08-16   Commit: `1a7e5b6`

**Built:** The metadata layer. A generated **field-metadata source of truth**
(`frappe_core.field_meta`), which closed **C7**; the saved-view provider that fills
`get_data`'s last stub; the `CRM View Settings`, `CRM Fields Layout` and `CRM Form
Script` endpoints; and the kanban work that closed **C6**.

**Tests:** **1024 passing**, 31 skipped (all pre-existing), 0 failing. 72 new.
Nothing skipped or weakened in this phase.

| Criterion (`PHASE_4_METADATA.md` §4) | Covered by |
|---|---|
| Saved views persist per user and per doctype+view_type | `test_saved_view_persists_per_user_and_type` |
| `get_data` resolves columns through the full 4-step order | `test_step1_…` … `test_step4_…`, one per step |
| Kanban resolves columns from a Link target or Select options | `test_kanban_columns_from_a_link_target`, `…_from_select_options` |
| Form layouts render tabs/sections/columns matching upstream | `test_default_layout_builds_tabs_from_the_breaks`, `test_layout_expands_fieldnames_into_field_objects` |
| Filterable and group-by allowlists match the source exactly | `test_filterable_allowlist_matches_the_source_exactly`, `…group_by…` |
| `get_non_filterable_fields()` respected | parametrised over a real CRM doctype **and** the test doctype |
| Standard fields appear in filter dropdowns | `test_standard_fields_appear_in_the_filter_list` |
| One user's saved view is invisible to another | `test_one_users_saved_view_is_invisible_to_another` **and** `test_a_private_saved_view_is_invisible_through_the_generic_route` |
| Allowlists keyed on the Frappe fieldtype, not the Django type | `test_duration_is_group_by_able`, `test_long_text_is_filterable_but_not_group_by_able` |
| `get_data`'s response keys unchanged from phase 0 | `test_get_data_response_keys_are_unchanged_from_phase_0` |

## The thing the spec did not anticipate

**Everything here needed a field-metadata layer first.** `PHASE_4_METADATA.md` §3 asks
for allowlists keyed on the Frappe fieldtype and §2 asks for form layouts — and *neither
is recoverable from the Django models*. Phase 1 dropped the layout fieldtypes by design
and collapsed `Long Text`/`Small Text`/`Text Editor` onto `TextField`.

So the phase starts with `scripts/generate_field_meta.py`, which reads the DocType JSON
and writes `crm_app/data/doctype_meta.json` — 39 doctypes, 475 fields, with their real
Frappe fieldtypes, labels, options, `reqd`, `hidden` and **declaration order**.

Generated and committed rather than read at runtime, because the CRM source tree is a
development dependency: a deployed backend has no `crm/fcrm/doctype/` to read.
`test_generated_field_meta_is_current` regenerates and diffs, so it cannot rot silently.

**C7 is closed.** `FILTERABLE_FIELDTYPES` and `GROUP_BY_FIELDTYPES` are now
transcriptions of `crm/api/doc.py`'s lists. Concretely: `Duration` is group-by-able on
purpose rather than by accident, and `Long Text` / `Text Editor` are filterable but not
group-by-able — a distinction phase 0 could not express. Phase 3's `_resolved_fieldtype`
plaster is deleted.

**C6 is closed.** `get_records_based_on_order` (manual card ordering, two
permission-filtered queries) and `get_counts` (the four badge counts) are ported.

---

## Review — tier 1 (Codex, PowerShell 7)

Ran clean. Three findings, **all real, all fixed**. Two were the same mistake, and it is
worth naming because my own tests walked straight past it.

**High — private saved views were readable by anyone, via `/api/resource/CRM View
Settings`.** I tested `get_views` and I tested `get_data`, and both scoped correctly. But
the criterion is *"one user's saved view is invisible to another"*, not "invisible
through the two endpoints I wrote". `CRM View Settings` is a registered routable doctype,
and **a doctype with no permission hook is world-readable**, so the generic route
bypassed both endpoints entirely.

**High — `CRM Form Script` was writable by any authenticated user, same route.** This one
is an XSS boundary: `get_data` serves `form_script` to every client, which *executes* it.
A Sales User could have authored a script that ran in every colleague's browser. I had
gated the sibling `save_fields_layout` endpoint and assumed that was the boundary; the
generic route was the way around it.

Both fixed by registering real row-level rules
(`crm_app/permissions/metadata_docs.py`) — read follows the list rule, write is
admin-only, and `CRM Fields Layout` got the same treatment for consistency. Eleven
regression tests, all driving the **generic route** rather than the endpoints.

This changes the phase-2 invariant "exactly three doctypes have row rules". That test now
asserts the intended set of **six**, with the three additions named and justified, so an
*accidental* registration is still caught.

**Medium — the last phase-0 stub was still hard-coded.** `is_default` ignored
`load_default_columns` on a named view (`crm/api/doc.py:485-486`), which is how the
frontend chooses between "reset to default" and "save changes". Now read off the view.

### What I checked that the review did not

`test_every_filterable_field_is_actually_filterable` and its group-by twin. Moving the
allowlists off the Django model and onto the JSON is correct, but it creates a failure
mode that did not exist before: a field in the JSON that phase 1 never materialised
would now be *advertised* in the filter dropdown and then 417 when used. Every advertised
field on six doctypes is exercised against the real query layer.

---

## Decisions made without you

1. **Field metadata is generated and committed, not read at runtime.** A deployment has
   no CRM source tree. The freshness test is what makes this safe.
2. **`None` from a saved-view provider means "fall through".** `get_list_columns` was
   returning the provider's `None` straight to the caller, so a doctype with no saved
   view got *no columns* instead of the controller default. Fixed; it now matches
   `get_data`'s own contract.
3. **The saved-view provider is registered for every routable doctype**, not a
   hand-picked list — upstream's lookup is not doctype-specific, and a hand-picked list
   would silently exclude whichever doctype someone adds next.
4. **Three doctypes gained row-level rules that upstream does not register.** Upstream
   relies on DocType role permissions, which this port does not model, so "no hook" means
   "no protection". Recorded in `UPSTREAM_BUGS.md`.
5. **`get_counts` is not permission-filtered.** Upstream uses `frappe.db.count`, and the
   badge says "this card has 3 comments" — a viewer-dependent count would be stranger
   than an accurate one, and only a total is exposed, never content. Reproduced.
6. **Kanban manual ordering *is* permission-filtered.** Both queries go through
   `fetch_rows`, so a card someone dragged into place and later lost access to does not
   come back. Upstream's `get_records_based_on_order` uses `frappe.get_list`, which also
   filters — so this is faithful, not a divergence.

## Deviations from spec

- The field-metadata layer itself — the spec assumed the fieldtypes were available.
- Three extra permission hooks (decision 4).
- `GROUP_BY_STANDARD_FIELDS` drops upstream's duplicate `Created On` / `Modified On`
  entries (`crm/api/doc.py:143-154` lists both twice). A repeated entry in a dropdown is
  a rendering bug nothing depends on.

## Not ported — named, not hidden

- **`handle_perm_level_restrictions`** (`crm_fields_layout.py:146-170`). Frappe's
  per-field permission *levels* come from the DocType's `permissions` table, which this
  port does not model. **No CRM doctype sets a non-zero `permlevel`** — checked across
  all 39 JSONs — so the function would be a no-op on every field it could currently see.
  If a doctype ever sets one, this becomes a real gap.
- **`clear_old_versions`** (`crm_view_settings.py:311-319`) deletes old `Version` rows.
  `Version` is not modelled (see `PROGRESS_PHASE_3.md`), and it is a phase-5 scheduled
  job regardless.
- **`CRM Dashboard` layout editing.** `reset_to_default`, `get_dashboard` and `get_chart`
  landed in phase 3; there is no endpoint to *edit* a dashboard layout, and the spec's
  §2 mention of `CRM Dashboard` is satisfied by the chart definitions it already has.

## Concerns

- **The generic route is the recurring blind spot.** Two of three findings were the same
  shape: an endpoint carefully gated, and the doctype reachable another way. Every
  registered doctype is a public read/write surface unless a hook says otherwise. It
  would be worth a standing test that enumerates routable doctypes and asserts each is
  either row-ruled or *deliberately* world-readable — I did not write it, and phases 5-6
  will add more doctypes.
- **`field_meta` falls back to model introspection for the nine platform doctypes**
  (`User`, `Contact`, `ToDo`, …), which ship no JSON. That fallback is phase 0's old
  guess, so C7 is closed for the CRM doctypes and still approximate for the platform
  ones. It matters least where it is least accurate — the platform doctypes are barely
  filtered on — but it is not fully closed.
- **`get_default_layout` has no upstream fixture to diff against.** I ported the
  algorithm and tested its shape, but "matches upstream" is asserted structurally
  (tabs/sections/columns nest correctly), not against a real rendered layout. A visual
  check against the running frontend would be worth more than another unit test.
