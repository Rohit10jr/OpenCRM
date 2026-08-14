# TASK — Start Here

Read `RUNBOOK.md` at the repo root and follow it exactly. It is the authoritative
instruction set for this run — where anything in this file conflicts with it, the
runbook wins.

```
Repo:   D:\02_Personal\01_OpenSource\03_Applications\CRM\frappe_django_crm
Branch: phase-0-foundation (checked out, scaffold committed at d82461b)
```

## Read first, in this order

1. `CLAUDE.md` — project rules
2. `PORT_PLAN.md` — inventory, frontend contract, settled decisions
3. `specs/README.md` — spec index and status
4. `specs/PHASE_0_FOUNDATION.md` — your first task

## What to run

- Phases **0, 1, 2** on the current branch, strictly in sequence.
- Then, **only if phase 2 finished clean** per the runbook's precondition gate:
  `git checkout -b phase-3-4-provisional`, then run phase **4**, then phase **3**.
- Then **STOP**. Do not start phase 5, 6 or 7.

## The gate — every phase, before the next begins

1. `pytest` exits 0, with a real test for every acceptance criterion in the spec
2. Migrations apply cleanly to `opencrm`
3. Codex reviews it read-only (exact prompts are in `RUNBOOK.md`)
4. Commit, and append to `PROGRESS.md`

## Rules

- **Gate fails twice on the same phase → STOP.** Write why to `PROGRESS.md`, halt.
- **Never disable or weaken a test to make a gate pass.**
- **Never invent Frappe semantics.** The source at
  `D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm` is the truth; the copied
  `frontend/` shows what the API must return.
- **Log every judgment call** you make in my absence to `PROGRESS.md`, especially the
  two known-open questions (SLA compute timing, error-envelope shape).
- **Report Codex's findings honestly**, including where you disagree with it.

## Environment

Already set up — Postgres (`opencrm`), Redis, `.env`, the frontend. **Do not
reconfigure it.** Backend goes in `backend/`.

---

I'm away for a few hours. Stopping cleanly at phase 2 with an honest `PROGRESS.md` is a
good outcome. Four phases of unverified code is not.
