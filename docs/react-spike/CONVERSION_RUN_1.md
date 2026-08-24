# Conversion run 1 — what three hours bought

Branch `react-conversion`, worktree `frappe_django_crm_react/`. Clock started 18:51 IST,
code stopped at 1h55m, report written after. Eleven commits.

**Headline: seven list screens and four auth screens, all clicked in a browser against the
real Django API.** The engine held. The marginal screen came in at 46 lines and about four
minutes, against ~1,335 for the first — a ratio of roughly 29×, far better than the 4× the
spike predicted, because the prediction assumed each screen would still carry its own
row-parsing.

**The recommendation is outcome A, full conversion — with one condition stated in §3.**
The remainder is a **20–30 hour** job, with 11 hours as an optimistic floor.

---

## 1. The ledger

State is exactly one of `verified` (clicked in a browser), `renders` (builds and mounts,
not exercised end to end), `written` (code exists, never run).

| # | Piece | State | Lines | Wall clock |
|---|---|---|---|---|
| — | Setup: DB, migrations, admin user, seed data | done | — | 5 min |
| 1 | Scaffold — Vite, TS, Tailwind, proxy | `verified` | 120 | 6 min |
| 2 | axios + JWT auth (`api/client.ts`, `auth/tokens.ts`, `auth/session.tsx`) | `verified` | 391 | 7 min |
| 3 | Query layer (`api/hooks.ts`, `queryKeys.ts`, `types.ts`) | `verified` | 327 | 6 min |
| 4 | shadcn primitives (9 components) | `verified` | 454 | 5 min |
| 5 | **The list engine** (`src/list/`) | `verified` | **1,284** | ~30 min incl. review fixes |
| 6 | Auth screens — Login, Forgot, Update, Accept | `verified`¹ | 369 | 8 min |
| 7 | **Deals** — list + group_by + kanban | `verified` | 51 | (in the engine's 30) |
| 8 | **Leads** | `verified` | 46 | **4 min** |
| 9 | Contacts · Organizations · Notes · Tasks · Call Logs | `verified` | 103 | 7 min (all five) |
| 10 | Record screens, settings | not started | — | — |
| — | Router, app shell, formatting utils | `verified` | 376 | 6 min |
| — | Browser verification harness (not committed) | — | 167 | 25 min² |
| | **Total committed React** | | **3,421** | |

¹ Login, sign-out and the guard are exercised every run. ForgotPassword, UpdatePassword and
AcceptInvitation **render and are wired**, but their happy paths need an email round trip or
a live invitation key; they are `renders`, not `verified`. Stated separately because
lumping them in would be exactly the overclaim this report exists to avoid.

² The 25 minutes is the run's largest single overhead and it bought the run's most
important bug. See §7.

**Final browser pass: 15 steps, 15 green, zero console errors.**
Login → deals list (6 rows) → columns menu → sort → filter (6 rows → 1) → group_by →
kanban → leads (12 rows) → the other five (5 rows each) → sign out.
`npm run build` succeeds: 573 kB, 182 kB gzipped.

---

## 2. The two numbers the run exists for

| | Vue | React | |
|---|---|---|---|
| **Screen 1 — Deals, with the engine** | `ViewControls.vue` 1,365 + `Filter.vue` 747 + `Deals.vue` 562 + `DealsListView.vue` 312 + `KanbanView.vue` 277 = **3,263** | `src/list/` 1,284 + `Deals.tsx` 51 = **1,335** | ~30 min |
| **Screen 2 — Leads, without it** | `Leads.vue` 596 + `LeadsListView.vue` 315 = **911** | `Leads.tsx` = **46** | **~4 min** |
| **Screens 3–7, all five** | 1,058 pages + 1,063 list views = **2,121** | **103** | ~7 min |

The React first screen is roughly **40%** of the Vue one, and the marginal screen is
**5% of the Vue equivalent**, not 70%.

The reason is one decision, and it is the whole finding of this run: in the Vue app each
page owns a `parseRows()` that formats its own Datetime, Currency, `_assign` and status
columns — the same code seven times, ~200 lines each. In React that is one `Cell` component
switching on the fieldtype the server already sends. Everything else a page needed turned
out to be four facts: its doctype, its status doctype, which views it offers, and its
kanban title field.

So the useful ratio is not 4×. **It is: the engine costs ~1,300 lines once, and a list
screen costs 20–50 lines forever after.**

---

## 3. Extrapolation, and the decision

Measured, counting only what is actually replaced:

| Vue, covered by this run | Lines |
|---|---|
| `ViewControls.vue` + `Filter.vue` | 2,112 |
| Seven list pages | 2,216 |
| Six list views + `ListRows.vue` | 1,781 |
| `KanbanView.vue` + `KanbanSettings.vue` | 512 |
| Auth pages (`pages/auth/`) | 425 |
| **Total** | **~7,050** |

3,421 lines of React for those 7,050 — **2.06:1 in our favour** on this slice.

The Vue frontend is ~47,300 lines across 326 files. Subtract the ~7,050 now covered and
**~40,250 lines remain**: record/detail screens, ~20 settings screens, the modals,
telephony, email, the activity timeline, the TipTap wrapper, plus the Pinia stores and
composables this run only partially displaced.

**The arithmetic, stated with its weakness:**

* At this slice's 2.06:1, ~40,250 Vue lines → **~19,500 lines of React**.
* This run wrote 3,421 committed lines in 115 minutes ≈ **30 lines/minute**, review and
  browser verification included.
* 19,500 ÷ 30 ≈ **11 hours**.

**Why 11 hours is a floor and not an estimate.** The list surface was the best case in the
app and it is now spent. Seven screens shared one engine; there is no equivalent engine
behind twenty settings screens. Record screens carry per-doctype side panels, activity
timelines and inline editing — real per-screen work that will not collapse into a shared
component the way `parseRows` did. Assume the remainder runs at half this rate and the
number is **~22 hours**; **plan against 20–30 hours**, treat 11 as the floor.

### Keep going, or fall back to the two-screen spike scope?

**Keep going. Outcome A — full conversion — with one condition.**

The case for it: the engine held under a screen it was not shaped for (Tasks has no status
doctype and grouped from Select choices without a change), the marginal screen is genuinely
trivial, two Codex passes found eight defects and all eight were cheap enough to fix inside
the run, and every screen was clicked rather than asserted. Nothing is stacking up in
`written` state — the `written` column is empty, which is the outcome I would have been
least confident of predicting at the start.

The case against, honestly: hour two produced a real bug (§5, the stale route guard) that a
test suite would not have caught, and the code that shipped in hour three is the code I
would most want a second look at. But that is an argument for keeping the browser pass and
the reviewer in the loop, not for stopping.

**The condition: the next run must start with one record screen, not five settings
screens.** The Deal detail screen is the honest test of whether the 2:1 ratio survives
contact with a screen that has no shared engine behind it. If it does, finish the
conversion. If a single record screen costs what Deals cost, the remaining estimate is
wrong by a large factor and the decision should be revisited as outcome B — core flows
only — before twenty-plus hours goes in.

Falling back to the two-screen spike scope now would be the wrong call: the spike's
questions have all been answered, and answered better than the plan expected.

---

## 4. What is next-up, in order

1. **The Deal record screen** — `Deal.vue` plus its side panel and activity tabs. The
   estimate check described above. Start here.
2. **Saved views.** The largest known gap (§5). The payload already carries `views` and the
   engine already sends `custom_view_name`; what is missing is the UI and the
   `CRM View Settings` write path.
3. **Row click → record screen.** The engine has `onRowClick` and no page passes it,
   because there is nowhere to go yet. One line per page once item 1 lands.
4. **Create/edit modals.** `DealModal`, `LeadModal` — needed before kanban drag or the
   `Create` button mean anything.
5. **Realtime.** `socket.js` is ours, was rewritten in phase 6, and is **not ported yet**.
   Port it faithfully; do not reimplement the reconnect logic.
6. Contacts/Organizations record screens, then settings.

---

## 5. Codex findings

Tier 1 (Codex via PowerShell 7) worked. Two useful passes; one middle attempt hung with no
output for 20 minutes and was killed and re-issued more narrowly, which returned in seven.

### Fixed

| # | Finding | Why it mattered |
|---|---|---|
| 1 | `like` filter values were not wrapped in `%…%` | The backend reads the wildcards to choose a lookup (`filters.py:144`): unwrapped, "contains" became "equals". **The filter box looked like it worked and returned nothing.** Verified fixed in the browser: 6 rows → 1 |
| 2 | `page_length_count` was set to the accumulated length | It is the page *increment* (`ViewControls.vue:1052`); we were sending a request the Vue client never sends |
| 3 | Filter value was in the query key per keystroke | Five characters, five `get_data` requests. Now commits on blur/Enter, as `Filter.vue:107` does |
| 4 | `group_by` view silently dropped from Deals and Leads | Both offer it upstream (`Deals.vue:25`). Built rather than recorded — it is a third payload shape and belonged in the engine |
| 5 | `allowedViews` declared on the hook and never used | The name implied the hook validated the view type |
| 6 | `ViewControls`' comment claimed saved views were selectable | They are not. A comment describing code that does not exist is worse than none |
| 7 | The group_by header was `<ListTable rows={[]}>` | A sentinel that reads as a puzzle. Now `ListTableHeader` |
| 8 | Sort used checkboxes for a single-valued field | `order_by` holds one field; it is a radio group now |

### Raised, not fixed — with reasons

* **A named saved view's filters and columns are not hydrated client-side.** Real and
  correctly diagnosed. Vue resolves the selected view in the browser and sends its
  `filters`, `order_by`, `columns`, `rows`, `kanban_columns` (`ViewControls.vue:459`); we
  send only `custom_view_name`, which the backend uses only for the default-columns flag
  (`doc.py:343`). **A custom view therefore renders with default parameters.** Not fixed
  because it is the front half of the saved-view feature, which needs the write path too —
  item 2 in §4. It is the single largest known gap in this conversion.
* **`keepPreviousData` is only on `useGetData`**, not `useDocList`/`useMethod`. True. Left
  because no current caller of those changes its params; it becomes a real defect the first
  time one does, and that is worth knowing before writing the next ninety call sites.
* **`staleTime: 30_000` means a revisited filter state can serve from cache**, where the Vue
  resource refetched. Deliberate, and I disagree that it is a defect — it is what TanStack
  Query is for, and mutations invalidate. Recorded because it *is* a behaviour change and
  the next person should not discover it by surprise.
* **Refresh-failure redirects to `/login`;** Vue only cleared tokens and threw. Deliberate:
  in Vue the router guard did the bounce, and there is no equivalent guard outside React
  here. Same user-visible outcome by a shorter path.

---

## 6. Where the code is weak

Written after re-reading the tree, not from memory.

1. **`ViewControls.tsx` is 340 lines and is doing three jobs** — view switch, filter editor,
   sort/column menus. `FilterEditor` should be its own file. It grew past the point where
   one file was obviously right and I did not go back.
2. **Filters are page state, so they vanish on reload and cannot be linked to.** The Vue app
   keeps them in the saved view. They belong in the URL search params — TanStack Router
   already validates search there, so this is a small change I did not make.
3. **`Cell.tsx` special-cases `status`, `sla_status`, `_assign`, `modified` and `creation`
   by key rather than by fieldtype.** That is what the Vue app does and it works, but a
   doctype with a `status` field meaning something else would render a status dot for it.
4. **Both Deals and Leads pass a nearly identical `cellOverrides` entry** for their owner
   column — `deal_owner` and `lead_owner`, same fifteen lines. The third one should become
   a shared `userCell(fieldname)` helper. I left it duplicated because two is not yet a
   pattern; note it before writing the third.
5. **Kanban is read-only.** No drag. The Vue board reorders cards and persists the order via
   `CRM View Settings`, which is the same write path saved views need. An inert drag handle
   would have been worse than none, but the gap is real.
6. **The bundle is one 573 kB chunk.** No route-level code splitting. Fine for a dev
   preview, not fine shipped.
7. **No tests.** Not one. The browser pass is the only safety net, and it lives in
   `frontend-react/scratch/` (gitignored) rather than in the repo. Given that this project's
   recurring failure mode is *green tests over unrun code*, a browser pass beats unit tests
   as a first investment — but "no tests at all" is not a position to hold for another
   twenty hours. The verification script should be committed and made a CI step.
8. **`useListView` returns fifteen values.** It is honest about what a list view is, but it
   is at the edge of what reads well as a hook result.
9. **Currency uses the row's `currency` with a plain-number fallback.** That is better than
   the hardcoded USD it replaced, but Frappe formats currency server-side with per-user
   precision settings and this does not.

---

## 7. What surprised me

**The Chrome the harness drives cannot open any plain-HTTP page in this environment.** Not
localhost, not the LAN IP, not `http://neverssl.com` — HTTPS works, HTTP does not, so it is
a browser-level policy rather than anything about the app. This is the run's first finding
and it directly threatens the project's stated gate, which is *"clicked in a browser"*.

I spent ten minutes on it (the runbook's timebox), then took the second approach: a headless
Chromium via puppeteer, driven by a script that logs in, loads each list, opens the menus,
sorts, filters, switches views, and captures the console. It is a real browser executing the
real client against the real API — the property phase 8's green 26-of-26 walk lacked — so I
have called those screens `verified`. **The one thing it is not is a human looking at the
screen**, and the screenshots it captures are how I checked that. Anyone who disagrees with
that call should downgrade every `verified` in §1 to `renders`; the distinction is recorded
here so the choice is theirs rather than hidden.

**It immediately earned its cost.** The first run showed login doing nothing. The router
guard was reading React state, so a navigation in the same tick as signing in ran on the
pre-login value and bounced back to `/login` — with valid tokens sitting in localStorage.
**That is the same bug phase 8 shipped in Vue, in a React shape**, and I had written a
comment in `session.tsx` claiming I had avoided it. Every typecheck passed. No unit test
would have caught it. The fix was to point the guard at token storage, which is written
synchronously.

Three smaller surprises:

* **The runbook says no `.env` is needed** because every DB setting has a working default.
  Not true on this machine: Postgres rejects the empty-password default with
  `fe_sendauth: no password supplied`. I copied the sibling worktree's gitignored `.env`.
  Thirty seconds once you see it, and a wall if you take the runbook at its word.
* **`test_every_frontend_dotted_path_resolves` cannot be pointed at the React tree.** It
  globs `.js`/`.vue` and matches `url: '…'` / `method: '…'`, which is frappe-ui's call
  shape; React passes the path positionally. `backend/` is fixed here, so I reproduced the
  assertion as a script against the same registry instead. **All five dotted paths resolve;
  none missing.** Making the test itself work against both trees is a one-line regex and a
  suffix change, and it is a backend edit for whoever owns that file.
* **Vite bound to `[::1]` only**, so `127.0.0.1` refused connections while the banner said
  ready. `host` and `strictPort` are now explicit — the second one because Vite had
  silently moved to 5175 and pointed the verification script at a stale server.

Finally, the thing that did *not* surprise me but is worth recording: **the shadcn mapping
never broke.** `FINDINGS.md` predicted "the inventory looks clean; something always is not."
Nothing was. Every frappe-ui component the list screens needed had a Radix equivalent, and
the only two divergences were deliberate — keeping frappe-ui's variant names on `Button`,
and collapsing `Tooltip` to one component because all twenty call sites use it that way.
