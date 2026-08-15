# TASK — Start Here

Read `RUNBOOK.md` and follow it exactly. Where anything in this file conflicts with it,
the runbook wins.

```
Repo:   D:\02_Personal\01_OpenSource\03_Applications\CRM\frappe_django_crm
Branch: phase-0-foundation  (phases 0-2 complete, 813 tests passing)
```

## Read first, in this order

1. `specs/AS_BUILT.md` — **what already exists.** Read this before writing any code
2. `CLAUDE.md` — project rules and the reviewer policy
3. `PORT_PLAN.md` — inventory, frontend contract, settled decisions
4. `specs/PHASE_3_ENDPOINTS.md` — your first task

`AS_BUILT.md` is first for a reason: phases 0-2 built a framework layer, and the single
biggest time-waster available to you is rewriting part of it.

## What to run

**All four phases: 3, 4, 5, 6.** In that order, each on its own branch, each branching
from the previous phase's completed tip:

| Phase | Branch | Progress file |
|---|---|---|
| 3 | `phase-3-endpoints` | `PROGRESS_PHASE_3.md` |
| 4 | `phase-4-metadata` | `PROGRESS_PHASE_4.md` |
| 5 | `phase-5-async` | `PROGRESS_PHASE_5.md` |
| 6 | `phase-6-realtime` | `PROGRESS_PHASE_6.md` |

```powershell
git checkout -b phase-3-endpoints          # from phase-0-foundation
# ... phase 3, gate passes, commit ...
git checkout -b phase-4-metadata           # from phase-3-endpoints
```

Write each phase's report to **its own** `PROGRESS_PHASE_<N>.md`, in the same format the
existing `PROGRESS.md` uses. Do not append to `PROGRESS.md` — it is the phase 0-2 record.

After phase 6, **STOP**. Do not start phase 7 (integrations, deferred) or phase 8
(parked).

**All four are expected to land.** Phase 3 is the largest at ~50 endpoints, but 4, 5 and
6 are progressively smaller and the framework layer they build on already exists. Pace
accordingly — do not treat phase 3 as the whole job.

## Do not idle

The failure mode to avoid is stalling, not moving too fast.

- **Fan out within a phase.** Phase 3's five module groups are independent; phase 4's
  components likewise. Never two agents in one file, but several files at once is fine.
- **Blocked on one module? Move to another** and come back. Do not serialise on a
  question you can park.
- **Do not wait on anything external.** Nothing in phases 3-6 needs a running worker, a
  mail server or a browser (see the testing rule below).
- **Do not re-litigate settled decisions.** They are in `PORT_PLAN.md` §10 and
  `specs/AS_BUILT.md`. If you disagree, log it and keep moving.

## The gate — every phase, before the next begins

1. `pytest` exits 0, with a real test for every acceptance criterion
2. Migrations apply cleanly (`makemigrations --check` reports nothing)
3. A reviewer passes — tier 1 is Codex, and **it works now**; see `RUNBOOK.md` §3
4. Commit, write `PROGRESS_PHASE_<N>.md`, then branch for the next phase

## Tests that would need external services

**Never let a missing service block the gate.** Phases 5 and 6 look like they need
infrastructure; almost none of it is actually required, because the standard in-process
substitutes exist:

| Instead of | Use |
|---|---|
| A running Celery worker | `CELERY_TASK_ALWAYS_EAGER = True` — tasks run inline |
| A running Celery Beat | Assert the schedule off `app.conf.beat_schedule`; do not run it |
| Redis as a channel layer | `InMemoryChannelLayer` in test settings |
| A real WebSocket server | `channels.testing.WebsocketCommunicator` |
| An SMTP server | `locmem` email backend; assert `django.core.mail.outbox` |

So write the test properly first — reach for a skip only when the behaviour genuinely
cannot be exercised in-process (a real broker round-trip, a live third-party API).

When you do skip, **`pytest.mark.skip` with a reason naming what it would need**, and
list it in that phase's progress file. A silently missing test is the thing to avoid; an
explicitly skipped one with a reason is fine and does not block the gate.

## Rules

- **Gate fails twice on the same phase → STOP.** Write why to `PROGRESS_PHASE_<N>.md`,
  halt, and do not branch for the next phase.
- **Never disable or weaken a test to make a gate pass.**
- **A test that cannot fail is not a test.** Before trusting one, check it fails without
  the fix. This caught two vacuous tests in earlier phases.
- **Never invent Frappe semantics.** Both sources are readable now:
  - CRM app — `D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm` (`main`)
  - Framework — `D:\02_Personal\01_OpenSource\02_FrameWorks\frappe` (`version-15`)
- **Diverge only on bugs nothing can observe; reproduce user-visible ones.** Check
  whether anything reads the field before deciding, and record it in `UPSTREAM_BUGS.md`.
- **Log every judgment call** to that phase's `PROGRESS_PHASE_<N>.md`, with evidence.

## If something looks impossible

Suspect a missing framework mechanism before suspecting your own code. `fetch_from` was
never ported, and the symptom looked like a conversion bug for an hour. Check the
framework source for the feature before working around it.

---

I am away for about 4 hours, and I expect all four phases attempted. The gate is there to
keep the work honest, not to give you a reason to stop early — if a phase passes its gate,
branch and start the next one immediately.

The one thing I do not want is unverified code presented as finished. Everything else,
keep moving.
