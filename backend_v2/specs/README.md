# Unit specs — index, order and status

**This table is the one home of unit status.** Per-row status (each method path and
doctype) lives in `backend_v2/docs/PORT_MAP.md`. **Paths are from the repository root.**

A **unit** is one piece of the rebuild with its own gate and pull request: usually one
Django app, built as a series of briefs. Units are named for what they build, never
numbered — the order below can change without renaming anything.

## Status values

| Status | Meaning |
|---|---|
| **Provisional** | Written before the code it depends on exists. Its scope is right; its details are guesses. **Rewrite it against `AS_BUILT.md` before building it** |
| **Ready** | Rewritten against what exists, spec-checked, and reviewed by the supervising session (with Codex/agy); the owner gets a summary in `temp\SPEC_REVIEWS.md` and may overturn it (owner, 17 Nov 2026). Its briefs can be written |
| **Running** | Its briefs are being built by Claude and reviewed |
| **Done** | Gate passed. `AS_BUILT.md` updated, `PORT_MAP.md` rows marked, the unit's pull request merged with its progress report |

Flip the status in this table in the same commit that changes the fact. A spec whose
status is wrong is worse than no status at all.

## Units

| Unit | Spec | Apps | Depends on | Status |
|---|---|---|---|---|
| FOUNDATION | [`FOUNDATION.md`](FOUNDATION.md) | `core`, and the first part of `accounts` | — | **Done** — gate passed 16 Nov 2026 (PRs #64, #65, #66) |
| ACCOUNTS | [`ACCOUNTS.md`](ACCOUNTS.md) | `accounts` | FOUNDATION, SHARED_ACTIONS | Running — gate passed 18 Nov 2026 (PRs #74, #75, #76, `temp` A-23, A-24, A-26); **Done** once they merge |
| CONFIGURATION | [`CONFIGURATION.md`](CONFIGURATION.md) | `configuration` | FOUNDATION, SHARED_ACTIONS, ACCOUNTS | Running — spec Ready for all eight milestones (`temp` A-27, A-28, A-30, A-33, A-35, A-37, A-39, A-40); milestones 1 (Desk plumbing), 2 (reference data and boot), 3 (FCRM Settings, exchange rate), 4 (Email Account), 5 (field metadata), 6 (layouts, form scripts, quick filters), 7 (saved views) and 8 (the list engine) built; the real resources opt in to the list view with SALES, ACTIVITIES and CONTACTS |
| SHARED_ACTIONS | [`SHARED_ACTIONS.md`](SHARED_ACTIONS.md) | `core` (the mixins in `core/mixins/`, the conditions evaluator) | FOUNDATION | **Done** — gate passed 16 Nov 2026 (PRs #67, #68; #67 landed via #71) |
| CONTACTS | [`CONTACTS.md`](CONTACTS.md) | `contacts` | ACCOUNTS, SHARED_ACTIONS, CONFIGURATION | Running — spec Ready (`temp` A-41, A-42); milestones 0 (the shared actions' remove contact and linked delete) and 1 (Salutation, Gender, CRM Industry) built; CRM Organization waits for the owner (DECISIONS 56) |
| NOTIFICATIONS | [`NOTIFICATIONS.md`](NOTIFICATIONS.md) | `notifications` | ACCOUNTS | Provisional |
| ASSIGNMENTS | [`ASSIGNMENTS.md`](ASSIGNMENTS.md) | `activities` (ToDo, Assignment Rule, the engine), `core` (`render_template`) | ACCOUNTS, NOTIFICATIONS, SHARED_ACTIONS | Provisional |
| SALES | [`SALES.md`](SALES.md) | `sales` | ACCOUNTS, CONFIGURATION, SHARED_ACTIONS, CONTACTS, ASSIGNMENTS, SLA | Provisional |
| ACTIVITIES | [`ACTIVITIES.md`](ACTIVITIES.md) | `activities` | SALES, NOTIFICATIONS, SHARED_ACTIONS, ASSIGNMENTS | Provisional |
| DASHBOARD | [`DASHBOARD.md`](DASHBOARD.md) | `dashboard` | SALES | Provisional |
| SLA | [`SLA.md`](SLA.md) | `sla` | FOUNDATION, SHARED_ACTIONS | Provisional |
| INTEGRATIONS | [`INTEGRATIONS.md`](INTEGRATIONS.md) | `integrations` | SALES, ACTIVITIES | Provisional |
| DATA_IMPORT | [`DATA_IMPORT.md`](DATA_IMPORT.md) | `core` (`core/data_import/`) | SALES, CONTACTS, ACTIVITIES | Provisional |

**Units and apps are a starting point, not final** (REBUILD_PLAN section 4). Work may be
merged, split or moved with a proper reason — raised in the spec check before the code,
**flagged to the owner when decided**, and recorded in the progress report after — and
this table, `PORT_MAP.md` and REBUILD_PLAN section 4 are updated with it.

### Build order

One unit at a time, one brief at a time: this machine runs one heavy job at a time, so
nothing is built in parallel. Each unit depends only on units above it.

| # | Unit | Why here |
|---|---|---|
| 1 | FOUNDATION | It sets the conventions every other unit copies, and writes every shared file |
| 2 | SHARED_ACTIONS | The mixins every resource opts in to, and the conditions evaluator that SLA and the assignment engine call |
| 3 | ACCOUNTS | `User`'s rules, roles and the sales hierarchy, which most later rules read |
| 4 | CONFIGURATION | The list engine and settings every screen reads |
| 5 | CONTACTS | Needs ACCOUNTS, and opts in to the rename mixin |
| 6 | NOTIFICATIONS | Comments, assignments and WhatsApp messages all create notifications, so it comes before them |
| 7 | ASSIGNMENTS | ToDo, the Assignment Rule doctype and the engine that SALES calls on save; it needs NOTIFICATIONS (a ToDo notifies its assignee). Split out of SHARED_ACTIONS on 16 Nov 2026 (A-7): the engine cannot run without these models |
| 8 | SLA | Saving a lead or deal calls it, so it comes before SALES |
| 9 | SALES | The largest unit. Lead and Deal reference nearly everything above |
| 10 | ACTIVITIES | Hangs off leads and deals; adds the assignment-rule routes on the models from ASSIGNMENTS |
| 11 | DASHBOARD | Counts and sums over leads and deals |
| 12 | INTEGRATIONS | Off by default; the phone providers need the call logs from ACTIVITIES |
| 13 | DATA_IMPORT | Writes Leads, Deals, Contacts, Organizations, Tasks and Call Logs through their normal create path, so it needs all of them |

**Resource units opt in to the mixins** (REBUILD_PLAN S24): each adds the shared-action
and list-view mixins it needs to its own ViewSets, and its gate proves those routes on
its own records.

**When a spec names a file in `docs/http/`**, the unit runs its REST copy in
`backend_v2/http/` (REBUILD_PLAN S9), and the body comparison checks it against the
original. **When a file turns green** is tabled in `PORT_MAP.md`: a file passes in full
only once every unit it touches is done. A unit's gate names the blocks it owns; blocks
waiting on a later unit are listed in its progress report, not hidden.

## How a unit is run

```
spec (Provisional)
        ──►  spec check            the supervising session, read-only with Codex/agy,
                                   checks the spec against backend/ and reports what is
                                   stale or wrong
        ──►  rewrite               the rebuild session rewrites the spec against AS_BUILT
                                   and the findings
        ──►  spec review (Ready)   the supervising session reviews the rewrite; the owner
                                   gets a summary in temp\SPEC_REVIEWS.md
        ──►  briefs in tasks/      one per commit plan, written by Claude from the spec
        ──►  Claude builds each brief, reviews it against backend/ and commits; the
             supervisor reads each commit's diff
        ──►  gate: tests, ruff, the unit's .http blocks, the body diff, review
        ──►  pull request          its description is the unit's progress report
```

**Claude builds; the supervising session reviews with Codex or agy** (root `CLAUDE.md`,
"Building and reviewing"; owner, 17 Nov 2026). Briefs are git-ignored.

**The spec check comes first because specs go stale.** In the old backend, the check
before each phase found four or five false claims in its spec; finding none is more
likely a sign of not looking. Each finding is fixed in the spec, or settled with the
owner, before the first build brief.

**If the gate fails twice, stop** and report to the owner — unless the second failure's
cause is confirmed and its fix is small and plainly right; then make a third attempt and
report it (root `CLAUDE.md`, "Building and reviewing"). A unit with a known hole,
honestly reported, costs less than every later unit built on one believed sound.

**The progress report is the unit's pull request description:** what was built, by app;
the tests and the commands run; each gate item with its result; the review tier, findings,
and what was applied or declined; decisions taken without the owner; deviations from the
spec; what is not done and the unit it now belongs to; `.http` blocks left for a later
unit; and **concerns** — what was not checked. Concerns are read first; a thin list is a
warning sign.

## What every spec contains

1. **Scope** — the app, and the `PORT_MAP.md` rows the unit owns
2. **Depends on** — what must exist first
3. **Read in `backend/` first** — the old implementation, the tests to read and write
   again, and **the tests to port** (REBUILD_PLAN S14)
4. **Must not be lost** — protections and behaviours with a history
5. **Acceptance** — the ported tests passing with their expected answers unchanged, new
   tests where none existed, `.http` files or blocks, the body diff
6. **Questions for the owner** — answered after the spec check, before the spec becomes
   Ready; the builder builds what is decided and decides nothing itself
