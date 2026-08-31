# Conversion run 3 — the queue, and what the backend will not let us build

Branch `react-conversion-3`, cut from `react-conversion-2`. Eight commits, ~141 working
minutes.

**No runbook was written for this run.** The instruction was to work run 2's next-up list in
order, or pick what I was confident about, and to record any bug found in the Vue app or the
backend. So the first twelve minutes went on checking what the backend actually serves — and
that check changed the plan.

---

## 1. The headline: run 2's two top priorities are backend-blocked

Run 2's report made building the email composer *the condition* on run 3. It cannot be met.

| Run 2 said | Reality |
|---|---|
| **1. Email composer** | `frappe.core.doctype.communication.email.make` is **not whitelisted**. A composer would 404 on Send |
| **2. Attachments** | Frappe's `upload_file` is **not whitelisted**, and `config/urls.py` routes only `/api/resource/*` and `/api/method/*` — there is no upload route at all |

Both checked against `frappe_core.whitelist.all_methods()`, not inferred from the Vue
source. `backend/` is fixed in this worktree, so both are recorded (divergence entries 7 and
8) with what would unblock them, and neither was built. **A Send button that 404s is worse
than no Send button**, and stubbing one would have been the exact failure mode this project
keeps having.

So the run took the rest of the queue plus everything else the whitelist does serve.

---

## 2. The ledger

`verified` = a real browser drove it · `renders` = builds and mounts · `written` = never run.

| Piece | State | Lines | Vue equivalent |
|---|---|---|---|
| Backend survey + divergence entries 7–9 | — | — | — |
| **Comments** on records (`CommentBox`, timeline rendering) | `verified` | 91 | `CommunicationArea.vue` 333 (its other half is blocked) |
| **Assign / unassign** (`AssignTo`) | `verified` | 123 | `AssignTo.vue` 99 |
| **Bulk delete** with select-all (`BulkActions`) | `verified` | 84 | `ListBulkActions.vue` 252 |
| **Searchable Link combobox** (`LinkCombobox`) | `verified` | 145 | `Controls/Link.vue` 204 |
| **Kanban cross-column drag** | `verified` | ~45 | part of `KanbanView.vue` |
| **Curated sort/filter menus** (`useFieldOptions`) | `verified` | 62 | part of `ViewControls.vue` |
| Codex fixes (4) + tab-body lookup | `verified` | — | — |
| **Total application code, cumulative** | | **6,287** | |
| *of which written this run* | | **~590** | |

**Harness: 31 steps at the start of the run, 35 at the end, all green, zero console errors,
and — new this run — stable across consecutive runs.** `frontend/` and `backend/` are
byte-identical to `main`. All 15 dotted paths the React source calls resolve.

---

## 3. What this run actually cost

~590 lines of React against ~890 lines of the Vue components it replaces — **1.5:1**, worse
than run 2's headline 2.4:1 and almost exactly the *discounted* 1.5:1 run 2 said to plan
against. That is the number holding up under a third measurement, which is worth more than
the flattering one.

**The estimate does not move.** Run 2 said 15–25 hours with 13 as a floor. Nothing here
argues either way: these were small, well-defined, individually-served features, and they
cost what small features cost. The two things that *would* have moved it — email and
attachments — are the two that could not be built.

**What has changed is the risk profile.** Run 2 named five unmeasured subsystems. Two of
them turn out not to be conversion work at all; they are backend work that must happen
first. Anyone planning the remainder should treat "port the frontend" and "the backend
serves what the frontend needs" as two projects, because on this evidence they are.

---

## 4. Bugs and gaps found — Vue app and backend

Recorded as asked. All are in `VUE_DIVERGENCES.md` so they survive this report.

**Backend (reported, not touched):**

1. **`communication.email.make` not whitelisted** — blocks the entire email feature.
2. **`upload_file` not whitelisted, and no upload route exists** — blocks attachments.
3. **`sort_options` and `get_filterable_fields` return duplicate `fieldname`s.** `name`
   appears in the standard fields and again in the doctype's own, and the server does not
   merge them. React warned about duplicate keys and could drop one; `useFieldOptions`
   dedupes client-side. *The server merging them would be the better fix.*
4. Carried from run 2 and still true: `get_deal_contacts` and `crm_deal.create_deal` are
   unserved, so the Deal contacts sub-panel cannot be built and creation goes through
   `/api/resource`.

**Vue app:** nothing new. Run 3 read `CommunicationArea.vue`, `AssignTo.vue`, `Link.vue`,
`ListBulkActions.vue` and `KanbanView.vue` and found no defect in any of them — the
divergences below are ours, not theirs.

**Ours, deliberate, and one that must not be "fixed":**

5. **Comments are plain text here and HTML in Vue** (entry 10). The *rendering* half must
   stay text: a comment written in the Vue client is HTML authored by another user, so
   `dangerouslySetInnerHTML` would be stored XSS with a Vue-shaped delivery mechanism. The
   visible cost is that a Vue-written comment shows its tags. The fix is a sanitiser plus
   the editor, never an unescape.

---

## 5. Codex findings

One checkpoint, narrow prompt, returned in under five minutes — the lesson from runs 1 and 2
held. Four findings, all real, all fixed:

| Finding | Why it mattered |
|---|---|
| `LinkCombobox` kept its debounced term across a close | Reopening within 250ms showed results for the *previous* search under an empty input |
| Clear control was `role="button"` inside a real `<button>` | Invalid interactive nesting; not keyboard-reachable as its own control, however well the click handler behaved |
| `BulkActions` left a stale selection on failure | Invites a second attempt at the same doomed list |
| `AssignTo` did not invalidate the activity feed | An assignment is a tracked change and appears in the timeline |

Codex cleared `CommentBox`'s Ctrl+Enter handling and I agree with the clearance.

---

## 6. Where the code is weak

Run 2's list, then what is new.

| # | From run 2 | Now |
|---|---|---|
| 3 | `Cell.tsx` special-cases by key, not fieldtype | **Unchanged** |
| 5 | Kanban read-only | **Half fixed** — cross-column drag works; within-column reordering does not |
| 6 | One chunk, no code splitting | **Worse.** More screens, still one chunk |
| 7 | No unit tests | **Unchanged, and now the sharpest gap** — see §7 |
| 8 | `useListView` returns 23 values | **Unchanged** |
| 9 | Currency ignores server precision | **Unchanged** |
| 4 (run 2's new list) | Link `<select>` capped at 100 | **Fixed** — searchable combobox |
| 10 | Tab bodies a five-branch ternary | **Fixed** — a lookup |
| 11 | `CreateModal` drops hidden Quick Entry sections | **Unchanged** |
| 12 | `UNMODELLED_LINK_TARGETS` will rot | **Unchanged** |
| 13 | Panel widths hardcoded, nothing responsive under ~1100px | **Unchanged** |
| 14 | `useRecord` fetches activities to fund one tab | **Better** — two tabs read it now |

New this run:

15. **`AssignTo` renders every CRM user in one unsearchable list.** Fine at five users, the
    same defect the Link `<select>` had at a hundred. `search_link` would serve it.
16. **`BulkActions` offers only delete**, and the confirmation says "linked documents are
    left alone" — true, because `delete_linked` is hardcoded false and nothing surfaces it.
17. **`ListView` is now doing five things** — URL binding, the list query, view mutations,
    the kanban move mutation, and selection. It is at the size `ViewControls.tsx` was when
    run 2 split it.
18. **`get_quick_filters` and `get_group_by_fields` are served and unused.** Quick filters
    are a row of one-click filters the React app has no equivalent of; group_by is
    hardcoded to `owner` rather than offering what the endpoint returns.

---

## 7. What surprised me

**The harness spent more of this run lying to me than the app did.** Six separate couplings,
every one of them mine, and each failed *far from its cause*:

* The bulk-delete step deleted "the first two rows" — the seeded fixtures three later steps
  filtered on. It destroyed its own preconditions and the failures appeared in unrelated
  assertions.
* Its creations had no email and accumulated across runs until they filled page one, at
  which point the filter steps could not find a row to filter on.
* The filter steps hardcoded a seeded value, so they broke when that value was deleted.
* One filter assertion read the first row's email, which was empty, so the filter was
  dropped entirely and it cheerfully reported "22 rows narrowed to 22".
* The timeline step asserted "at least one entry", which really asserted "row one is an old
  record".
* The assign step assumed the record started unassigned. The picker toggles, so a record
  left assigned turned the first click into an *un*assign — and it reported "did not survive
  a reload" **while the server log showed no `assign_to.add` at all**.

Every one of those looked like a product bug first. In each case I probed the API directly
before touching the app, and in each case the API was correct. **The most valuable habit of
this run was refusing to fix the app until the endpoint had been proved wrong**, and the
first hypothesis — that cancelling a ToDo blocks re-assigning the same user — was wrong;
acting on it would have "fixed" a bug that does not exist.

That is also the strongest argument yet for weakness 7. The browser harness is now 35 steps
and it is the only safety net, but a suite this stateful needs unit tests underneath it for
the pure functions (`toFilterDict`, `likeWrap`, `viewParams`, `toLocalInput`, `byFieldname`)
so that a red harness means "the app broke" rather than "something moved".

**The smaller surprise:** run 2 predicted the remaining work was in five lumpy subsystems.
It was half right. Two are lumpy; two do not exist yet on the server; and the fifth —
assign-to — turned out to be 123 lines because the endpoints were already there and nobody
had looked.

---

## 8. Next-up, in order

1. **Unit tests for the pure functions.** Cheapest thing on this list and it makes every
   later run's harness failures legible.
2. **Quick filters** (`get_quick_filters`, `update_quick_filters`) — served, unused, and the
   most visible missing piece of the list toolbar.
3. **Notifications** (`get_notifications`, `mark_as_read`) — served, unused, and the app has
   no notification chrome at all.
4. **Split `ListView`** before it grows again (weakness 17).
5. **A searchable `AssignTo`** (weakness 15), reusing `LinkCombobox`'s shape.
6. **Then, only if the backend moves:** email composer, attachments. Both are blocked on
   §4.1 and §4.2, and neither is frontend work until they are.
