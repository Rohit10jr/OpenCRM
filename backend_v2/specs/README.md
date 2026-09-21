# Unit specs — index, order and status

**This table is the one home of unit status.** Per-row status (each method path and
doctype) lives in `backend_v2/docs/PORT_MAP.md`. **Paths are from the repository root.**

A **unit** is one handoff: usually one Django app, sized so an agent can finish it and
pass its gate in one run. Units are named for what they build, never numbered — the order
below can change without renaming anything.

## Status values

| Status | Meaning |
|---|---|
| **Provisional** | Written before the code it depends on exists. Its scope is right; its details are guesses. **Rewrite it against `AS_BUILT.md` before running it** |
| **Ready** | Rewritten against what exists, and reviewed by the owner. Can be handed to an agent |
| **Running** | A run is in progress. Its runbook is in `backend_v2/docs/runs/` |
| **Done** | Gate passed. `AS_BUILT.md` updated, `PORT_MAP.md` rows marked, progress report written |

Flip the status in this table in the same commit that changes the fact. A spec whose
status is wrong is worse than no status at all.

## Units

| Unit | Spec | Apps | Depends on | Status |
|---|---|---|---|---|
| FOUNDATION | [`FOUNDATION.md`](FOUNDATION.md) | `core`, and the first parts of `accounts` and `documents` | — | **Provisional — awaiting owner review** |
| ACCOUNTS | [`ACCOUNTS.md`](ACCOUNTS.md) | `accounts` | FOUNDATION | Provisional |
| SETTINGS | [`SETTINGS.md`](SETTINGS.md) | `crm_settings` | FOUNDATION | Provisional |
| METADATA | [`METADATA.md`](METADATA.md) | `metadata` | FOUNDATION | Provisional |
| CONTACTS | [`CONTACTS.md`](CONTACTS.md) | `contacts` | ACCOUNTS | Provisional |
| NOTIFICATIONS | [`NOTIFICATIONS.md`](NOTIFICATIONS.md) | `notifications` | ACCOUNTS | Provisional |
| SALES | [`SALES.md`](SALES.md) | `sales` | ACCOUNTS, SETTINGS, METADATA, CONTACTS | Provisional |
| ACTIVITIES | [`ACTIVITIES.md`](ACTIVITIES.md) | `activities` | SALES, NOTIFICATIONS | Provisional |
| DASHBOARD | [`DASHBOARD.md`](DASHBOARD.md) | `dashboard` | SALES | Provisional |
| SLA | [`SLA.md`](SLA.md) | `sla` | SALES | Provisional |
| DOCUMENTS | [`DOCUMENTS.md`](DOCUMENTS.md) | the rest of `documents` | SALES, ACTIVITIES | Provisional |
| TELEPHONY | [`TELEPHONY.md`](TELEPHONY.md) | `telephony` | SALES, ACTIVITIES | Provisional |
| INTEGRATIONS | [`INTEGRATIONS.md`](INTEGRATIONS.md) | `integrations` | SALES, ACTIVITIES, TELEPHONY | Provisional |

### What can run at the same time

Units in one wave depend only on earlier waves and own different apps, so they never
edit the same file.

| Wave | Units | Why this grouping |
|---|---|---|
| 1 | FOUNDATION | **One agent.** It sets the conventions every other unit copies, and writes every shared file — splitting it produces competing designs to reconcile |
| 2 | ACCOUNTS, SETTINGS, METADATA | Each needs only FOUNDATION |
| 3 | CONTACTS, NOTIFICATIONS | Each needs `User` and the roles from ACCOUNTS. Notifications come this early because comments, assignments and WhatsApp messages all create them |
| 4 | SALES | The largest unit. Lead and Deal reference nearly everything before them |
| 5 | ACTIVITIES, DASHBOARD, SLA | Each hangs off leads and deals |
| 6 | DOCUMENTS, TELEPHONY | Bulk actions, rename and linked documents need every doctype they act on; calls log notes and tasks |
| 7 | INTEGRATIONS | Off by default, and last for that reason |

The `.http` files use the old paths; against `backend_v2` they are sent through the route
map (REBUILD_PLAN section 6). **When a file turns green** is tabled in `PORT_MAP.md`: a file passes in full
only once every unit it touches is done. A unit's gate names the blocks it owns; blocks
waiting on a later unit are listed in its progress report, not hidden.

## How a unit is run

```
spec (Provisional)  ──►  rewrite against AS_BUILT, owner review (Ready)
        ──►  RUNBOOK_<UNIT>.md    written for this run: scope, gate, fail-stop
        ──►  ORIENTATION_<UNIT>.md  written by the agent BEFORE any code:
                                     what it understood, what looks stale or wrong
        ──►  work, one commit per meaningful change
        ──►  gate: tests, the unit's .http blocks, the body diff, review
        ──►  PROGRESS_<UNIT>.md   written by the agent AFTER the gate
```

Runbooks, orientations and progress reports live in `backend_v2/docs/runs/`. They are
records of one run, never edited afterwards, and kept apart from the living documents.

## What every spec contains

1. **Scope** — the app, and the `PORT_MAP.md` rows the unit owns
2. **Depends on** — what must exist first
3. **Read in `backend/` first** — the old implementation and its tests
4. **Must not be lost** — protections and behaviours with a history
5. **Acceptance** — pytest areas, `.http` files or blocks, the body diff
6. **Open questions** — for the owner, answered before the spec becomes Ready
