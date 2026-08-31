# Conversion run 4 — one hour on the sharpest gap

Branch `react-conversion-4`, cut from `react-conversion-3`. Two commits, 56 working minutes
against a one-hour budget.

A deliberately small run against run 3's next-up list: **item 1 (unit tests) and item 5
(searchable `AssignTo`)**. Items 2–3 (quick filters, notifications) were not started —
neither fits an hour with verification, and run 3's own rule is not to start what will not
finish.

---

## What landed

| Piece | State | Lines |
|---|---|---|
| **33 unit tests** + vitest config, `npm test` | `verified`¹ | 218 |
| `toLocalInput` moved to `lib/format.ts`; three functions exported for test | — | — |
| **Searchable assignee picker** | `verified` | ~30 |
| `scratch/seed_users.py` — eight CRM users, so assignment is testable | — | — |
| Three harness bugs fixed | `verified` | — |

¹ Verified in the strongest available sense: **the tests were checked to fail on the bug
they pin.** Reverting `likeWrap` to `return value` turns two of them red. A test that cannot
fail is decoration, and this project has shipped enough green-over-unrun to make that worth
proving rather than asserting.

`npm test` — 33 passed. `npm run verify` — 35 steps, green, zero console errors.
`frontend/` and `backend/` byte-identical to `main`.

---

## The tests, and why these functions

Run 3 called the absence of unit tests its sharpest gap, for a specific reason: the browser
harness is stateful, drives a real database, and run 3 spent more time on assertions that
had drifted than on the app. **The point of these is that a red harness now means "the app
broke" rather than "something moved".**

The four functions covered are the four defects that actually shipped or were caught late,
so each is pinned rather than remembered:

| Function | The bug it pins |
|---|---|
| `likeWrap` | Run 1 sent `like` values unwrapped; the backend read the absent wildcards as "no pattern", chose `iexact`, and the filter box returned nothing while looking like it worked |
| `viewParams` | A stored `"123"` is valid JSON and went into the request as `filters: 123` |
| `toLocalInput` | Datetime fields round-tripped UTC as if it were local time |
| `byFieldname` | `sort_options` returns `name` twice and the server does not merge them |

`toLocalInput`'s assertions are written against the *runner's* offset rather than a fixed
zone, so they hold in UTC too — where the bug is invisible.

`toLocalInput` moved out of `FieldInput.tsx` into `lib/format.ts` in the process. It is a
date utility like the two beside it, and **a pure function living in a component file is a
pure function nobody tests** — which is most of why it was not tested before.

---

## The assignee picker, and the fixture it needed

`AssignTo` rendered every CRM user in one unsearchable list — run 3's weakness 15, the same
defect the Link `<select>` had at a hundred rows with a smaller number.

**Filtered client-side, not through `search_link`.** `get_users` returns tens of users, not
thousands, and they are already fetched and cached for every avatar on screen. Searching the
server for a list we are holding would be a round trip to answer a question we can already
answer. The Link picker needs the server because Organizations are unbounded; this does not.
That asymmetry is deliberate and is commented where it lives.

**It could not be verified as-was.** The database had one CRM user, so the box never
rendered — the feature would have been `written`, not `verified`, and run 3's bar forbids
calling that done. `scratch/seed_users.py` adds eight, which also makes the pre-existing
assign/unassign assertions mean something: they had been toggling a list of one.

---

## What surprised me: the pattern from run 3 repeated immediately

Seeding those eight users exposed a real weakness in the harness step that had been passing
for a whole run. It clicked **"the first button"** in the picker — and with nine people,
position means nothing. After a reload the first entry is somebody else, so the *unassign*
half was assigning a second person. It had only ever passed because there was exactly one
user to click.

That is the third distinct instance of run 3's finding: **an assertion that reports on its
own fixtures rather than on the product.** It toggles a named person now.

Two smaller ones fixed alongside:

* A `waitForFunction` using `.every()`, which is vacuously true for an empty list and let
  the step proceed to click nothing.
* The timeline step asserting before the feed settled — `activitiesPending` follows
  `isFetching`, so the timeline shows "Loading activity…" through any refetch, and the
  assertion was racing a spinner.

**Every one of these was found by making the fixture more realistic, not by reading code.**
That is worth a line in the next run's plan: a fixture with one of something tests almost
nothing, and this database still has one organization list, one status per column, and one
saved view at a time.

---

## Where the code is weak

Run 3's list, unchanged except where noted:

| # | Item | Now |
|---|---|---|
| 7 | No unit tests | **Fixed for the pure functions.** Everything with a hook or a component in it is still untested — no jsdom, no render tests |
| 15 | `AssignTo` unsearchable | **Fixed** |
| 3, 6, 8, 9, 11, 12, 13, 16, 17, 18 | | **Unchanged** |

New:

19. **The tests cover pure functions only, and the honest coverage is narrow.** Nothing
    tests `useListView`'s parameter assembly, which is the highest-traffic logic in the app
    and is exactly the sort of thing that broke in run 2 (`order_by` sentinel) and run 3
    (saved-view precedence). That needs a hook test with a mocked query client, which is a
    bigger setup than this hour allowed.
20. **`scratch/seed_users.py`, `seed_deals.py`, `purge.py` and `reseed_deals.py` are all
    gitignored scratch.** The fixtures the harness depends on are now substantial and live
    nowhere a fresh checkout can find them. They should be one committed seed command.

---

## Next-up, in order

1. **Commit the seed scripts as one command** (weakness 20). The harness is only reproducible
   on this machine until that happens, and it is now load-bearing.
2. **Quick filters** (`get_quick_filters`, `update_quick_filters`) — served, unused, most
   visible missing piece of the toolbar.
3. **Notifications** (`get_notifications`, `mark_as_read`) — served, unused.
4. **A hook test setup** so `useListView`'s parameter assembly can be pinned (weakness 19).
5. **Split `ListView`** (run 3's weakness 17).
6. **Blocked, and still not frontend work:** email composer and attachment upload — see
   `VUE_DIVERGENCES.md` entries 7 and 8.
