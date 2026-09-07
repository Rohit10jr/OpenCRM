# The React branches, and what to read for each

Six branches, each cut from the one before it. **`react-conversion-5` contains all of them** —
so to see the finished state you only need that one. Read the others when you want to know
*why* something is the way it is.

Every branch left `frontend/` and `backend/` byte-identical to `main`. That is the whole
point of the arrangement: the Vue app keeps working, and the experiment is reversible by
deleting a directory.

| Branch | Adds | Size | On origin |
|---|---|---|---|
| `react-spike` | Survey and plan, no code | 6 files | **no — local only** |
| `react-conversion` | Scaffold + 7 list screens | 52 files, ~8,900 lines | yes |
| `react-conversion-2` | Record screens, saved views | 34 files, ~3,400 | yes |
| `react-conversion-3` | Comments, assignment, kanban drag | 15 files, ~1,300 | yes |
| `react-conversion-4` | Unit tests, assignee picker | 13 files, ~2,100 | yes |
| `react-conversion-5` | Everything else — 23 commits | 72 files, ~8,000 | yes |

---

## `react-spike` — measure before building

No React code at all. It answered "what is the Vue app, actually" — 326 files, ~47,300
lines, counted rather than estimated — and fixed the stack and the acceptance test before
anyone wrote a line.

**Read:** `FINDINGS.md`, then `SPIKE_PLAN.md`. These two are still the reading list for
anyone new; nothing later replaces them.

⚠️ **Not pushed.** It exists only in this checkout. Push it or it is one `git gc` from gone.

---

## `react-conversion` — the scaffold and the list engine

Vite, TypeScript, Tailwind, TanStack Router and Query, shadcn primitives, the axios client
and the ported JWT layer, then **one list engine driving all seven list screens**.

That last part is the branch's argument. Vue has a shared `ViewControls.vue` (1,365 lines)
*plus* a per-page `Deals.vue` / `Leads.vue` (~560 lines each) repeating row-parsing, empty
states and kanban wiring. Here a page passes a doctype and a title.

**Read, in order:**
1. `frontend-react/src/api/client.ts` — the wire protocol, and where `{data}` vs `{message}` is handled
2. `frontend-react/src/auth/tokens.ts` — ported, not rewritten; the refresh-once-on-401 path is load-bearing
3. `frontend-react/src/list/useListView.ts` — the engine's state
4. `frontend-react/src/pages/Deals.tsx` — 58 lines against Vue's ~560, and that is the point
5. `docs/react-spike/CONVERSION_RUN_1.md`

---

## `react-conversion-2` — records, and URL state

The Deal record screen — the gate run 1 asked for — then Contact, Organization and Lead for
almost nothing each, because `RecordScreen` is shared the same way `ListView` is.

Two decisions worth knowing:
* **Filters and sort moved into the URL.** A filtered list can be linked, survives a reload,
  and is still there after opening a record and pressing back.
* **The side panel is metadata-driven.** `get_sidepanel_sections` returns the layout with
  each field expanded, so the panel renders any doctype with no per-doctype code.

**Read:**
1. `frontend-react/src/record/RecordScreen.tsx` — how tabs and the panel compose
2. `frontend-react/src/record/SidePanel.tsx` + `FieldInput.tsx` — metadata in, inputs out
3. `frontend-react/src/list/useViews.ts` — saved views, both halves
4. `docs/react-spike/CONVERSION_RUN_2.md`

---

## `react-conversion-3` — the interactions

Comments, assignment, bulk delete, kanban drag-and-drop, and server-side search on link
fields (which had been listing 100 rows and filtering client-side).

Also where `VUE_DIVERGENCES.md` starts being useful — sort and filter menus switched to the
curated endpoints, because building them from `get_data`'s `fields` offered every field on
the doctype including ones that filter badly.

**Read:**
1. `frontend-react/src/list/useFieldOptions.ts` — why there are three field endpoints
2. `frontend-react/src/record/LinkCombobox.tsx` — search, not a dropdown
3. `docs/react-spike/VUE_DIVERGENCES.md`
4. `docs/react-spike/CONVERSION_RUN_3.md`

---

## `react-conversion-4` — the small careful one

One hour, three commits. **33 unit tests** over the pure functions, and a searchable
assignee picker.

The tests are the part worth copying: each was checked to *fail on the bug it pins*.
Reverting `likeWrap` to `return value` turns two of them red. A test that cannot fail is
decoration.

**Read:** `frontend-react/src/lib/format.test.ts` and the two beside it, then
`docs/react-spike/CONVERSION_RUN_4.md`.

---

## `react-conversion-5` — breadth, and a reversed policy

The big one. 23 commits: 16 settings screens, dashboard, notifications, data import, a live
call panel, every remaining record tab, kanban settings, persistent columns, rich text with
sanitising, and a responsive layout.

Two things separate it from the others:

* **The policy reversed.** Runs 1–4 refused to build UI for an unserved endpoint. Run 5
  builds it, wires it to the real path, lets it fail visibly, and names the missing path in
  a banner. `BACKEND_GAPS.md` is the register.
* **Nothing in it is verified.** It compiles and builds at every commit. No screen has been
  clicked. Runs 1–4 used `verified` to mean "opened in a browser"; stretching it here would
  make their claims worthless too.

It also corrected a two-run-old mistake: telephony, WhatsApp, ERPNext, the dashboard and
notifications were all *already served*. Runs 2 and 3 had written them off without looking.

**Read:**
1. `docs/react-spike/CONVERSION_RUN_5.md` — start here
2. `docs/react-spike/BACKEND_GAPS.md` — what is missing and what to do about it
3. `frontend-react/src/record/RecordScreen.tsx` — the busiest file
4. `frontend-react/src/telephony/callStatus.ts` — the one pure function worth reading twice

---

## If you only have twenty minutes

`CONVERSION_RUN_5.md` → `BACKEND_GAPS.md` → `git log --oneline main..react-conversion-5`.

The commit messages carry the reasoning. That is deliberate — CLAUDE.md rule 4 exists so
the log is readable instead of the code being re-derived.
