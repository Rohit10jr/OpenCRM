# Conversion run 2 — three hours, and one go/no-go

**You are running unattended against a clock.** Read this whole file before starting.

Supersedes `RUNBOOK_CONVERSION.md` for the run itself. **Its rules, its clock discipline and
its three-state ledger still apply** — read them there; they are not repeated here.

## Start here

Worktree `D:\02_Personal\01_OpenSource\03_Applications\CRM\frappe_django_crm_react`, branch
**`react-conversion-2`**, cut from `react-conversion`. Run everything from this directory.
Never `cd` to the sibling repository, and never work on `main`.

**Do not re-plan this run.** The order below is fixed and chosen by dependency. Do not
reorder it, do not skip ahead, and do not substitute your own scope. If you think something
here is wrong, note it in the report and follow it anyway — run 2 is only comparable to run 1
if it is run the same way.

**Three hours again, deliberately**, so the two runs can be compared directly rather than
adjusted for.

Then read "Read first" and start.

---

## Read first — twenty minutes

| File | Why |
|---|---|
| `docs/react-spike/CONVERSION_RUN_1.md` | **What run 1 built, measured, and got wrong.** §4 is your queue, §6 is your inheritance, §7 will save you an hour |
| `CLAUDE.md` | Hard rules, shell rules, reviewer policy |
| `frontend-react/src/list/` | The engine you are about to build on. Read it before extending it |

Skip `specs/PHASE_*` and `docs/internal/*` — backend-port history.

**Read `CONVERSION_RUN_1.md` §7 before touching the environment.** It contains three walls
run 1 hit and the way past each. Hitting them again is pure loss.

---

## Setup — budget ten minutes, not fifteen

Run 1 already established all of this. It is cheaper this time and there is no excuse for an
hour.

* **`.env` is required**, despite what `RUNBOOK_CONVERSION.md` said. Postgres rejects the
  empty-password default with `fe_sendauth: no password supplied`. Copy the sibling
  worktree's gitignored `.env`.
* **Backend:** reuse the sibling venv — `../frappe_django_crm/backend/.venv/Scripts/python.exe
  backend/manage.py runserver`, run from *this* directory so it serves this worktree's code.
* **Frontend:** `frontend-react/` already has its `package.json`, its Vite config with
  explicit `host` and `strictPort`, and the verification harness. `npm install`, then
  `npm run dev`.
* **`npm run verify` is the browser harness** and it already passes 15 steps. Run it once
  before writing anything. **If it does not pass on the code you inherited, stop and report
  that** — it means something regressed between runs and everything you build today sits on
  it.

---

## The gate this run exists for

Run 1 converted seven list screens for 3,421 lines because they shared one engine. Its own
recommendation was conditional, and this is the condition:

> **The Deal record screen is the honest test of whether the 2:1 ratio survives a screen with
> no shared engine behind it.**

So piece 1 is not just the first task. It is a **measurement**, and it decides whether the
rest of the run happens.

### How to decide, mechanically

When the Deal record screen is `verified`, write down its line count and its wall clock.
Then:

| Outcome | What it means | What you do |
|---|---|---|
| **≤ ~450 lines, ≤ ~35 min** | Record screens are cheap too; the estimate holds | **Continue** with the order below |
| **~450–900 lines** | Real per-screen work, but tractable | **Continue**, and say plainly in the report that the 20–30 hour estimate should move up |
| **≳ 900 lines, or ≳ 75 min** | It cost what Deals-plus-engine cost, and there are ~20 more record and settings screens | **Stop building.** Spend the remaining time on the report and recommend **outcome B — core flows only** |

**Do not soften this because the run feels productive.** The whole value of run 1 was that it
produced a number nobody had to argue about. The third row is a legitimate and useful result;
recording it honestly is worth more than four more screens.

---

## The order of work

| # | Piece | Notes |
|---|---|---|
| 1 | **Deal record screen** | `frontend/src/pages/Deal.vue` + its side panel and activity tabs. **This is the gate.** Build it properly; a stripped version measures nothing |
| 2 | **Row click → record screen** | The engine already has `onRowClick` and no page passes it, because there was nowhere to go. One line per page |
| 3 | **Saved views — read path** | The largest known gap. Vue resolves the view client-side and sends its `filters`, `order_by`, `columns`, `rows`, `kanban_columns` (`ViewControls.vue:459`); we send only `custom_view_name`. Match Vue |
| 4 | **Saved views — write path** | `CRM View Settings`. This is also what kanban drag-ordering needs, which is why it comes before modals |
| 5 | **Create/edit modals** | `DealModal`, `LeadModal`. Until these exist the `Create` button means nothing |
| 6 | **`socket.js`** | **Port it, do not reinvent it.** The phase-6 reconnect logic — backoff, jitter, re-subscribe — is ours, was hard-won, and is tested. `CLAUDE.md` rule 6 |
| 7 | **Contact and Organization record screens** | The second and third data points on the ratio from piece 1 |
| 8 | **Settings** | Only if the clock allows. Do not start one you cannot finish |

---

## Carry-over from run 1 §6 — fix in passing, do not make a pass

Run 1 listed nine weaknesses honestly. **Three become real this run**; the rest stay recorded
until something forces them.

1. **`userCell(fieldname)` helper.** Deals and Leads each carry a near-identical fifteen-line
   `cellOverrides` entry for their owner column. Run 1 left it duplicated on purpose — *"two
   is not yet a pattern; note it before writing the third."* **The record screens are the
   third.** Extract it now.
2. **Filters belong in the URL.** They are page state today, so they vanish on reload and
   cannot be linked. Piece 2 makes this worse: navigating to a record and back loses the
   filter. TanStack Router already validates search params. Fix it as part of piece 2.
3. **Split `ViewControls.tsx`.** 340 lines doing three jobs. If piece 3 or 4 has you editing
   it, pull `FilterEditor` out first. If they do not, leave it.

**Leave alone unless they block you:** the `Cell.tsx` key-based special cases, the single
573 kB chunk, currency precision, `useListView`'s fifteen return values.

---

## Rules

Unchanged from `RUNBOOK_CONVERSION.md` §Rules. The three that were tested hardest last time:

1. **`backend/` does not change.** If it looks like it must, that is a finding for the report.
   Run 1 found one — `test_every_frontend_dotted_path_resolves` cannot be pointed at the React
   tree — and correctly reported it instead of editing.
2. **`frontend/` does not change.** `git diff --stat main -- frontend/` must stay empty.
3. **One commit per meaningful change.** Run 1 produced fourteen for 3,421 lines and they were
   reviewable. Match that.

Plus, short shell commands; never a bare `git stash` (the stack is shared with the sibling
worktree).

---

## Codex — two checkpoints

Same tier ladder as `CLAUDE.md`. **Never trust the exit code** — `CreateProcessAsUserW
failed`, `windows sandbox: runner failed`, `SpawnChild`, or a request to paste files all mean
the review did not happen. Run 1 also had one call **hang with no output for 20 minutes**;
kill it at ten and re-issue it narrower, naming the exact files.

* **After piece 1 (the record screen).** Ask specifically for behaviour parity against
  `frontend/src/pages/Deal.vue`, cited by line — and whether anything in it should have been
  shared with the list engine rather than written again.
* **After piece 4 (saved views, both halves).** The highest-risk piece in the run: it is a
  read path and a write path against `CRM View Settings`, and run 1's largest gap. Ask
  whether the parameters sent match `ViewControls.vue:459` exactly.

Fix what is real and cheap. Record what is real and expensive.

---

## Verification

**A screen counts as working when a real browser has driven it.** The harness exists —
`npm run verify`, 15 steps, non-zero exit on a failed step or a console error.

**Extend it; do not replace it, and do not let it rot.** Every piece above adds steps: open a
record from a row click, switch a saved view and assert the columns changed, create a deal
through the modal. A harness that still asserts run 1's fifteen steps at the end of run 2 is
a harness that stopped covering the product.

Two things run 1 learned the hard way:

* **Plain HTTP does not open** in the Chrome behind the automation tools here — not
  localhost, not the LAN IP, not `http://neverssl.com`. HTTPS does. It is a browser policy,
  not the app. Run 1 lost ten minutes on this before switching to headless Chromium via
  puppeteer, which is what the harness uses. **Do not re-litigate it. Use the harness.**
* **A comment claiming a bug was avoided is not evidence it was avoided.** `session.tsx`
  carried exactly such a comment while shipping the stale-guard bug the browser pass then
  caught. Assert it in the harness or do not claim it.

Time-box per screen: ten minutes fighting the browser, then mark it `renders`, say why, move
on.

---

## The report — `docs/react-spike/CONVERSION_RUN_2.md`

Last twenty minutes. Same three states, unblurred: **`verified`** (a browser drove it),
**`renders`** (builds and mounts), **`written`** (never run).

Include, in this order:

1. **The gate answer, first and plainly.** The record screen's lines and minutes, which row of
   the table above it landed in, and what follows. This is the single thing the run exists to
   produce — it goes at the top, not in a conclusion.
2. **The ledger** — one row per piece: name, state, lines, wall clock.
3. **How the ratio moved.** Run 1 measured 2.06:1 across the list slice. Recompute over what
   run 2 replaced, and say whether the remaining estimate — 20–30 hours, 11 as a floor —
   should move, and in which direction.
4. **Next-up, in order**, so run 3 can start cold.
5. **Codex findings** — raised, fixed, disputed, with reasons.
6. **Where the code is weak.** Run 1's §6 is the standard; an empty or shorter section will be
   read as a shallower review, not cleaner code. Say which of run 1's nine you fixed, which
   you inherited unchanged, and which got worse.
7. **What surprised you.**

**Do not round up, do not describe unrun code as working, and do not present a partial
conversion as nearly done.** Run 1's `written` column was empty and its numbers were exact.
That is the bar.
