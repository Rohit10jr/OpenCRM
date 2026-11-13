# Unit specs — index, order and status

**This table is the one home of unit status.** Per-row status (each method path and
doctype) lives in `backend_v2/docs/PORT_MAP.md`. **Paths are from the repository root.**

A **unit** is one piece of the rebuild with its own gate and pull request: usually one
Django app, built as a series of Codex briefs. Units are named for what they build, never
numbered — the order below can change without renaming anything.

## Status values

| Status | Meaning |
|---|---|
| **Provisional** | Written before the code it depends on exists. Its scope is right; its details are guesses. **Rewrite it against `AS_BUILT.md` before building it** |
| **Ready** | Rewritten against what exists, spec-checked, and reviewed by the owner. Its briefs can be written |
| **Running** | Its briefs are being built by Codex and reviewed |
| **Done** | Gate passed. `AS_BUILT.md` updated, `PORT_MAP.md` rows marked, the unit's pull request merged with its progress report |

Flip the status in this table in the same commit that changes the fact. A spec whose
status is wrong is worse than no status at all.

## Units

| Unit | Spec | Apps | Depends on | Status |
|---|---|---|---|---|
| FOUNDATION | [`FOUNDATION.md`](FOUNDATION.md) | `core`, and the first part of `accounts` | — | **Running** — briefs in progress |
| ACCOUNTS | [`ACCOUNTS.md`](ACCOUNTS.md) | `accounts` | FOUNDATION | Provisional |
| CONFIGURATION | [`CONFIGURATION.md`](CONFIGURATION.md) | `configuration` | FOUNDATION | Provisional |
| SHARED_ACTIONS | [`SHARED_ACTIONS.md`](SHARED_ACTIONS.md) | `core` (the mixins in `core/mixins/`, the conditions evaluator, the assignment engine) | FOUNDATION | Provisional |
| CONTACTS | [`CONTACTS.md`](CONTACTS.md) | `contacts` | ACCOUNTS, SHARED_ACTIONS | Provisional |
| NOTIFICATIONS | [`NOTIFICATIONS.md`](NOTIFICATIONS.md) | `notifications` | ACCOUNTS | Provisional |
| SALES | [`SALES.md`](SALES.md) | `sales` | ACCOUNTS, CONFIGURATION, SHARED_ACTIONS, CONTACTS, SLA | Provisional |
| ACTIVITIES | [`ACTIVITIES.md`](ACTIVITIES.md) | `activities` | SALES, NOTIFICATIONS, SHARED_ACTIONS | Provisional |
| DASHBOARD | [`DASHBOARD.md`](DASHBOARD.md) | `dashboard` | SALES | Provisional |
| SLA | [`SLA.md`](SLA.md) | `sla` | FOUNDATION, SHARED_ACTIONS | Provisional |
| INTEGRATIONS | [`INTEGRATIONS.md`](INTEGRATIONS.md) | `integrations` | SALES, ACTIVITIES | Provisional |
| DATA_IMPORT | [`DATA_IMPORT.md`](DATA_IMPORT.md) | `core` (`core/data_import/`) | SALES, CONTACTS, ACTIVITIES | Provisional |

**Units and apps are a starting point, not final** (REBUILD_PLAN section 4). Work may be
merged, split or moved with a proper reason — raised in the spec check before the code
and recorded in the progress report after — and this table, `PORT_MAP.md` and
REBUILD_PLAN section 4 are updated with it.

### Build order

One unit at a time: Codex runs one brief at a time on this machine, so nothing is built
in parallel. Each unit depends only on units above it.

| # | Unit | Why here |
|---|---|---|
| 1 | FOUNDATION | It sets the conventions every other unit copies, and writes every shared file |
| 2 | SHARED_ACTIONS | The mixins every resource opts in to, and the conditions evaluator and assignment engine that SLA and SALES call |
| 3 | ACCOUNTS | `User`'s rules, roles and the sales hierarchy, which most later rules read |
| 4 | CONFIGURATION | The list engine and settings every screen reads |
| 5 | CONTACTS | Needs ACCOUNTS, and opts in to the rename mixin |
| 6 | NOTIFICATIONS | Comments, assignments and WhatsApp messages all create notifications, so it comes before them |
| 7 | SLA | Saving a lead or deal calls it, so it comes before SALES |
| 8 | SALES | The largest unit. Lead and Deal reference nearly everything above |
| 9 | ACTIVITIES | Hangs off leads and deals; builds the assignment rules on the engine from 2 |
| 10 | DASHBOARD | Counts and sums over leads and deals |
| 11 | INTEGRATIONS | Off by default; the phone providers need the call logs from ACTIVITIES |
| 12 | DATA_IMPORT | Writes Leads, Deals, Contacts, Organizations, Tasks and Call Logs through their normal create path, so it needs all of them |

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
spec (Provisional)  ──►  rewrite against AS_BUILT, owner review (Ready)
        ──►  spec check            the first brief: Codex, read-only, checks the spec
                                   against backend/ and reports what is stale or wrong
        ──►  briefs in tasks/      one per commit, written by Claude from the spec
        ──►  Codex builds each brief; Claude reviews against backend/ and commits
        ──►  gate: tests, the unit's .http blocks, the body diff, review
        ──►  pull request          its description is the unit's progress report
```

**Codex builds and Claude reviews** (root `CLAUDE.md` and `AGENTS.md`). Briefs are
git-ignored.

**The spec check comes first because specs go stale.** In the old backend, the check
before each phase found four or five false claims in its spec; finding none is more
likely a sign of not looking. Each finding is fixed in the spec, or settled with the
owner, before the first build brief.

**If the gate fails twice, stop** and report to the owner. A unit with a known hole,
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
   Ready; Codex builds what is decided and decides nothing itself
