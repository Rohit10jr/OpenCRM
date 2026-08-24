# Conversion run 1 — three hours, hard stop

**You are running unattended against a clock.** Read this whole file before starting.

## Start here

You are working in the worktree
`D:\02_Personal\01_OpenSource\03_Applications\CRM\frappe_django_crm_react`, on branch
**`react-conversion`**. Run everything from this directory. Never `cd` to the sibling
repository, and never work on `main`.

**Do not re-plan this run.** The order of work below is fixed and chosen by dependency, not
preference. Do not reorder it, do not skip ahead to easier screens, and do not substitute
your own scope. If you think something in here is wrong, note it in the report and follow it
anyway — the run is only comparable if it is run as written.

**Set the clock before anything else** (next section). Stopping mid-plan with an honest
report is the successful outcome. Running over without one is not.

Then read the three files under "Read first" and start.

## What this run is

Convert the Vue frontend to React, screen by screen, **getting as far as three hours
allows**. This is not a spike with a two-screen scope — the target is the full conversion
and you will not reach it. That is expected and is not a failure.

**What is actually being measured is velocity and cost.** How far does three focused hours
get, and what does each screen cost once the engine exists? A run that converts four screens
properly is worth more than one that half-converts twenty, because the second teaches
nothing about the remaining 300 files.

**The deliverable is working code plus an honest ledger.** Both matter. Code nobody ran is
not progress, and a report that calls it progress makes the next decision on bad numbers.

---

## The clock — set it first, obey it

**Before anything else**, stamp the start:

```bash
date +%s > /tmp/run_start
```

**After every commit**, check elapsed minutes:

```bash
echo $(( ($(date +%s) - $(cat /tmp/run_start)) / 60 ))
```

| Elapsed | What happens |
|---|---|
| **150 min** | Stop starting anything new. Finish and commit what is in your hands |
| **160 min** | Stop coding entirely. Begin the report |
| **180 min** | Hard stop, committed and pushed |

**Do not run over.** A run that stops mid-file at 2:50 with a good report beats one that
stops at 3:20 with none. If a piece of work will obviously not fit in the remaining time,
do not start it — write it down as next-up instead.

---

## Read first — twenty minutes, not more

| File | Why |
|---|---|
| `docs/react-spike/FINDINGS.md` | What the Vue app is, measured. The `ViewControls` finding shapes the whole order below |
| `docs/react-spike/SPIKE_PLAN.md` | Stack, what to port vs. rewrite, the acceptance test |
| `CLAUDE.md` | Hard rules, shell-command rules, reviewer policy |

Skip `specs/PHASE_*` and `docs/internal/*` entirely — backend-port history, ~6,000 lines,
none of it applies. `CLAUDE.md` says which one exception matters.

---

## Setup — budget fifteen minutes

Nothing is installed in this worktree; `.venv`, `node_modules` and `.env` are all
gitignored. **No `.env` is needed** — every database setting has a working default
(`backend/config/settings/base.py:91`).

**Backend.** Do not build a venv; the sibling worktree has one with identical requirements:

```bash
../frappe_django_crm/backend/.venv/Scripts/python.exe backend/manage.py migrate
../frappe_django_crm/backend/.venv/Scripts/python.exe backend/manage.py runserver
```

Run it from *this* directory so it uses this worktree's code. Postgres must be up on
`localhost:5432`, database `opencrm`, user `postgres`. **If the backend will not start
within fifteen minutes, stop trying** — record it in the report as the run's first finding
and continue converting without runtime verification, labelling every screen `written`
rather than `verified` (see the ledger below). Do not spend an hour on infrastructure.

**Frontend.** `frontend-react/` beside `frontend/`, Vite + React + TypeScript. Install only
what the order below actually reaches.

**You do not need `frontend/node_modules`.** You are not touching the Vue app, and
`git diff --stat main -- frontend/` proves it for free.

---

## The order of work — this part is not yours to choose

Everything depends on the engine, so the engine comes first even though it shows nothing on
screen for the first hour. `ViewControls.vue` is 1,365 lines shared by **seven** pages;
build it once, properly, or every screen after the first pays again.

| # | Piece | Notes |
|---|---|---|
| 1 | **Scaffold** | Vite, TS, Tailwind (the Vue app's config ports), TanStack Router skeleton |
| 2 | **axios + auth** | **Port** `frontend/src/auth/tokens.js` and `jwtRequest.js`. Refresh-once-on-401 is ours and is tested — do not reinvent it |
| 3 | **Query layer** | The `createResource` → `useQuery`/`useMutation` mapping. **~90 call sites ride on this**; get it wrong and everything downstream is wrong at once |
| 4 | **shadcn primitives** | Only what the screens below need: Button, Dropdown, Tooltip, Dialog, Avatar, Switch, Popover, Badge, Input. `toast` → sonner |
| 5 | **The list engine** | `crm.api.doc.get_data` — filters, sort, columns, pagination, saved views, quick filters. This is `ViewControls.vue`. **Shared by seven pages: write it shared, not Deals-shaped** |
| 6 | **Auth screens** | Login, ForgotPassword, UpdatePassword, AcceptInvitation. New in phase 8, ~425 lines, and they are how you log in to check anything else |
| 7 | **Deals** | List + table + kanban. The first screen; expect ~2,500 lines with the engine |
| 8 | **Leads** | **The number that matters.** Same engine, different page — expect ~600. If it is not dramatically cheaper, the engine was built wrong and that is the run's most important finding |
| 9 | **Then, in order** | Contacts · Organizations · Notes · Tasks · CallLogs — all seven share `ViewControls` |
| 10 | **Then** | Detail/record screens, then settings |

Get as far as the clock allows. **Do not skip ahead to easy screens to inflate the count** —
the order is by dependency, and a report showing "9 screens converted, none run" would be
worse than useless.

---

## Rules

1. **`backend/` does not change.** If it looks like it must, that is a finding for the
   report, not an edit. The API is a fixed, documented contract.
2. **`frontend/` does not change.** React goes in `frontend-react/`. The Vue app keeps
   working; that is what makes this reversible.
3. **One commit per meaningful change.** The owner reads every one. Roughly the ten rows
   above, several commits each. **Never one big commit** — an earlier run on this project
   produced a single 25,000-line commit and it was unreviewable.
4. **Conventional beats clever.** If there are two ways and one is what a React developer
   would expect, use that one even if the other is shorter. No custom state managers, no
   render props where a hook will do, no abstraction invented for a second caller that does
   not exist. **The owner is fluent in React and not in Vue, and the entire point of this
   work is that they can read the result.** Anything surprising is a defect even when it
   works.
5. **Comments explain why, not what.**
6. **Keep shell commands short** — see `CLAUDE.md`. A long command escalates to human
   review, and there is no human here. That alone can end the run.
7. **Never bare `git stash`** — the stash stack is shared with the sibling worktree.
8. Branch `react-conversion`. Never `main`.

---

## Codex — at checkpoints, not after every commit

Reviewer policy and the tier ladder are in `CLAUDE.md`. Each call blocks 1–2 minutes, so
**two checkpoints, not ten**:

* **After piece 3 (the query layer).** The highest-leverage review in the run — ~90 future
  call sites inherit whatever shape you chose. Ask specifically: does this reproduce
  `createResource`'s auto-fetch, refetch-on-change and cache semantics, or has it quietly
  changed them?
* **After piece 7 (Deals).** Ask for behaviour parity against `frontend/src/pages/Deals.vue`
  and `components/ViewControls.vue`, cited by line.

If a third obviously earns its keep and the clock allows, take it. **Never trust the exit
code** — if the output shows `CreateProcessAsUserW failed`, `windows sandbox: runner
failed`, `SpawnChild`, or Codex asks you to paste files, the review did not happen.
Escalate a tier rather than accepting it.

Report findings in the ledger. Fix what is real and cheap; record what is real and
expensive.

---

## Verification — the gate this project keeps failing

Phase 8 wrote an end-to-end script that drove real HTTP against a real database, passed
**26 of 26 steps**, and still shipped two bugs: an email linking to raw JSON, and a
password reset that bounced the user back to the login screen. Every backend test passed.
**Neither runs a browser.** That was the third occurrence of the same shape in two phases.

So: **a screen counts as working when it has been clicked in a browser.** You have Chrome
automation tools available — use them. Log in, load the list, apply a filter, sort, switch
to kanban, open a record.

Time-box it. If the browser pass is fighting you for more than ten minutes on a screen,
stop, mark that screen `renders` rather than `verified`, note why, and move on. **Do not
rabbit-hole.** An honest `renders` is worth more than an hour lost.

---

## The report — `docs/react-spike/CONVERSION_RUN_1.md`

Write it in the last twenty minutes. **This is the actual deliverable of the run**, because
the decision that follows is made from it.

**Every screen and module gets one of exactly three states. Do not blur them:**

| State | Means |
|---|---|
| **`verified`** | Clicked in a browser. It works |
| **`renders`** | Builds and mounts, not exercised end to end |
| **`written`** | Code exists, never run |

Include, precisely:

1. **The ledger** — one row per piece: name, state, lines, wall-clock minutes.
2. **The two numbers the run exists for** — cost of screen 1 (with the engine) and cost of
   screen 2 (without). State them even if screen 2 was not reached; say so plainly if not.
3. **Extrapolation, and the decision it feeds.** At the measured marginal cost, what does
   the remaining conversion total? Show the arithmetic.

   **Then answer the actual question this run exists to settle**, in one paragraph, plainly:

   > **Keep going at full-conversion pace, or fall back to the two-screen spike scope in
   > `SPIKE_PLAN.md`?**

   Those are the two live options. Full conversion is right if the engine held up, the
   marginal screen is genuinely cheap, and the code is readable at this pace. The spike is
   right if speed cost quality — if screens are stacking up in `written` state, if Deals had
   to be special-cased, or if you would not want the owner reading what you produced in
   hour three. Map it onto `SPIKE_PLAN.md`'s outcomes A / B / C and say which, and why.

   **Recommending the slower path is a legitimate and useful result.** You are not being
   scored on distance covered.
4. **What is next-up**, in order, so the run can be resumed cold.
5. **Codex findings** — what was raised, what was fixed, what was left and why.
6. **Where the code is weak.** Anything rushed for the clock, anything you would write
   differently with another hour, anything you copied when you should have shared. **An
   empty section here is not credible** and will be read as a shallow review rather than
   clean code.
7. **What surprised you.** The mapping that did not work, the thing that took four times
   its estimate. This is what the next run's plan is built from.

**Do not round up, do not describe unrun code as working, and do not present a partial
conversion as nearly done.** The number this run produces decides whether the remaining
~45,000 lines get attempted at all — an optimistic report buys a bad decision.

---

## When you are blocked

Try twice, differently. Then write it down and move to the next piece — do not burn the
clock on one wall. Unblocking the whole run is worth more than any single screen, and
"blocked on X, here is what I tried" is a legitimate and useful result.
