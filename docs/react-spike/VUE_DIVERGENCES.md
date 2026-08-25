# Where the React client differs from the Vue one

**Every place `frontend-react/` behaves differently from `frontend/`, and why.** The backend
port keeps `UPSTREAM_BUGS_PHASE_*.md` for the same reason and it earned its place there: when
something behaves oddly, the first question is *"is that a port bug, or did we mean that?"*
and this file is where the answer lives.

**Numbering is one sequence.** Continue from the highest number here, never from the number a
runbook happens to quote.

## What belongs here

* **A deliberate behaviour change.** React does something the Vue client did not, and we
  chose it. Record what a user would notice.
* **A Vue bug we did not reproduce.** State how you know it is a bug, and check nothing reads
  the behaviour before diverging.
* **A Vue bug we *did* reproduce**, because a user sees the result and matching it matters
  more than fixing it.
* **A gap** — Vue does something we have not built yet. Not a divergence forever, but it is
  one today, and an unrecorded gap reads as a bug to the next person.

## What does not belong here

Per-run narrative. The runs' own reports (`CONVERSION_RUN_<N>.md`) carry what happened, what
Codex raised, and where the code was weak. **This file carries only what is still true**, so
it can be read on its own without reading every report that preceded it.

> **A note on where these come from.** Entries 1–4 were raised by Codex during run 1 and
> recorded only inside `CONVERSION_RUN_1.md` §5. That is a per-run document, so by run 3 they
> would have been invisible without re-reading an old report. Lifted here so they survive.

---

## 1. A named saved view renders with default parameters

**Where:** `frontend-react/src/list/` vs `frontend/src/components/ViewControls.vue:459`

**Vue** resolves the selected view in the browser and sends its `filters`, `order_by`,
`columns`, `rows` and `kanban_columns` with the request. **React** sends only
`custom_view_name`, which the backend uses solely for a default-columns flag
(`frappe_core/api/doc.py:343`).

So selecting a saved view gives you the *default* list, not the saved one.

**Us:** *Gap, not a decision.* This is the front half of the saved-view feature; the write
path against `CRM View Settings` is missing too. It is **the single largest known gap** in
the conversion and is item 3–4 in run 2's order. Remove this entry when both halves land.

## 2. A revisited filter state can serve from cache

**Where:** `frontend-react/src/api/hooks.ts` — `staleTime: 30_000`

Vue's `createResource` refetched on every parameter change. TanStack Query serves a cached
result for 30 seconds when the same key comes back — so filtering to X, back to Y, then to X
again inside half a minute shows the first X response rather than a fresh one.

**Us:** *Diverge, deliberately.* It is what the library is for, mutations invalidate, and the
window is short. Recorded because it **is** a user-visible behaviour change and the next
person should not find it by surprise and "fix" it.

**If it ever bites:** the symptom is stale rows after someone else edits a record, within 30
seconds, on a filter you have already visited. That is the trade, not a bug.

## 3. `keepPreviousData` is on `useGetData` only

**Where:** `frontend-react/src/api/hooks.ts` — not on `useDocList` or `useMethod`

Changing parameters on those two blanks the list to a loading state instead of holding the
previous rows.

**Us:** *Gap, currently inert.* No caller of either changes its params today, so nothing shows
it. **It becomes a real defect the first time one does** — which is worth knowing before the
next ninety call sites get written, rather than after.

## 4. A failed token refresh redirects; Vue only cleared and threw

**Where:** `frontend-react/src/api/client.ts` vs `frontend/src/auth/jwtRequest.js`

Vue cleared the tokens and let the error propagate; its router guard then bounced the user to
Login on the next navigation. React redirects to `/login` from the interceptor.

**Us:** *Diverge, deliberately.* Same user-visible outcome by a shorter path — there is no
equivalent always-mounted guard here. Recorded because the *mechanism* differs, and anyone
tracing "why did I end up at Login" should find this rather than reverse-engineer it.

## 5. Kanban is read-only

**Where:** `frontend-react/src/list/` vs `frontend/src/components/Kanban/KanbanView.vue`

The Vue board reorders cards by drag and persists the order through `CRM View Settings`.
React renders the board and does not.

**Us:** *Gap.* It needs the same write path as saved views (entry 1), which is why the two are
adjacent in run 2's order. An inert drag handle would have been worse than none.

## 6. Currency is formatted client-side from the row's own currency field

**Where:** `frontend-react/src/list/Cell.tsx`

Frappe formats currency server-side with per-user precision settings. React reads the row's
`currency` and falls back to a plain number.

**Us:** *Diverge, knowingly incomplete.* Better than the hardcoded USD it replaced, and wrong
for any user whose precision settings differ from the default. Fix it when a real user has
non-default precision, not before.
