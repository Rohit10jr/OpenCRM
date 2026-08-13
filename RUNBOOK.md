# Unattended Run — Phases 0 to 2 Only

**You are running without a human available. Read this whole file before starting.**

## HARD STOP

Run **phase 0, then phase 1, then phase 2. Then STOP.**

**Do not start phase 3.** Do not start phases 4–7. When phase 2's gate passes, write
your final report and halt, even if you have time and capacity left.

Phase 2 is the security boundary — row-level permissions. It needs human review before
anything builds on it. Phase 3's spec is provisional and will have been revised by you,
unreviewed. Stopping here is the correct outcome, not a failure.

---

## Before you begin

Read, in this order:

1. `CLAUDE.md` — project rules
2. `PORT_PLAN.md` — inventory, frontend contract, settled decisions
3. `specs/README.md` — spec index and status
4. `specs/PHASE_0_FOUNDATION.md` — your first task

Environment is already prepared. Do not reconfigure it:

- Branch `phase-0-foundation`, scaffold committed at `04b4d44`
- PostgreSQL 17 running, database `opencrm`, credentials in `.env` (gitignored)
- Redis reachable on 6379
- `frontend/` holds the real Vue frontend (52,449 LOC) — your acceptance reference
- Frappe source: `D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm`

Backend goes in `backend/`. Create the venv there.

---

## The loop

For each phase in **0, 1, 2**:

```
1. Read specs/PHASE_<N>_*.md in full
2. Implement it
3. Write tests for its acceptance criteria — real tests, not assertions of intent
4. Run the gate (below)
5. Gate passes  → commit, log to PROGRESS.md, next phase
   Gate fails   → fix, re-run gate (ONCE)
   Fails twice  → STOP. Log and halt.
```

**Phases run strictly in sequence.** Never begin a phase before the previous gate has
passed. Within phase 1 you may fan out by cluster; never two agents in one file.

---

## The gate

All four must pass. No exceptions, no "close enough".

### 1. Tests pass

```powershell
cd backend
pytest -q
```

Must exit 0. Every acceptance criterion in the phase spec must have a corresponding
test. A criterion with no test does not count as met.

### 2. Migrations are clean and apply from empty

```powershell
python manage.py makemigrations --check --dry-run   # no unmade model changes
python manage.py migrate                            # applies to opencrm
```

`pytest-django` builds and drops `test_opencrm` on every run, which proves migrations
apply from empty. If it doesn't, fix it before proceeding.

### 3. Codex review — independent second opinion

Run from the repo root. Read-only, so Codex cannot touch your files:

**Phase 0:**
```powershell
codex exec -s read-only "Review backend/ against specs/PHASE_0_FOUNDATION.md and the Frappe source at D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm. Focus on: does the filter-grammar translator match Frappe semantics (especially 'like' being case-insensitive on Postgres); are all six autoname strategies correct; does get_data return the right shape; is the ToDo/_assign relationship correct. Report concrete defects with file:line. Do not suggest style changes."
```

**Phase 1:**
```powershell
codex exec -s read-only "Review the Django models in backend/ against the DocType JSON in D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm\fcrm\doctype and specs/PHASE_1_MODELS.md. Check: missing or wrong fields vs the JSON, layout fieldtypes (Section/Column/Tab Break) wrongly made into columns, wrong Link targets, child tables exposed as standalone routes, lifecycle hooks not ported from the .py controllers. Report file:line."
```

**Phase 2:**
```powershell
codex exec -s read-only "Security review. Compare backend/ permission code against D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm\permissions\org_hierarchy.py and specs/PHASE_2_PERMISSIONS.md. Verify the rule evaluation ORDER matches exactly, that ToDo (not _assign) backs assignment checks, that cancelled ToDos grant no access, and that list filtering and has_permission agree in every case. Try to find a way to see a row you shouldn't via filters, fields, order_by or group_by. Report file:line."
```

**Act on the findings.** Fix real defects. Where you disagree with Codex, record the
disagreement and your reasoning in `PROGRESS.md` — do not silently ignore it.

### 4. Commit

One commit per phase. Message states the phase and what landed.

---

## Fail-stop

**If a gate fails twice on the same phase, STOP.**

Write to `PROGRESS.md`: what failed, the actual error, what you tried, and your best
read of the cause. Then halt.

Do not work around a failing gate. Do not skip to the next phase. Do not disable or
weaken a test to make it pass — that is the worst possible outcome, because it hides
the failure rather than reporting it.

A clean stop after phase 1 is far more useful than three phases of unverified code.

---

## PROGRESS.md

Create it at the repo root and append after every phase, pass or fail. This is what
gets read first on return, so make it scannable.

```markdown
## Phase <N> — <PASS | FAILED | STOPPED>
Started: <time>   Finished: <time>   Commit: <sha>

**Built:** 2-3 lines on what actually landed.

**Tests:** <count> passing. Any acceptance criterion NOT covered by a test, named.

**Codex findings:** what it raised, what you fixed, what you disputed and why.

**Decisions made without you:** every judgment call taken in the user's absence —
especially the two open spec questions (SLA compute timing, error-envelope shape).
State what you chose and the evidence.

**Deviations from spec:** anything built differently, and why.

**Concerns:** what you are unsure about. Be honest — this is the most valuable section.
```

---

## Judgment calls

You will hit ambiguity. In order of preference:

1. **Read the Frappe source.** It is the source of truth and it is right there.
2. **Read the frontend.** `frontend/src/stores/`, `src/data/document.js`,
   `src/composables/document.js` show what the API is expected to return.
3. **Choose the option that matches upstream behaviour**, implement it, and log the
   decision in `PROGRESS.md`.

Never invent semantics to make something easier. Never widen scope beyond the phase
spec. If a choice would be expensive to reverse and the evidence is genuinely
ambiguous, prefer to **stop and ask** over guessing — log it and halt.

Two questions are already known-open and need answering from source:
- SLA computed on write or on a schedule? (`specs/PHASE_5_ASYNC.md` §4)
- The exact error-envelope shape the frontend parses (`specs/PHASE_0_FOUNDATION.md` §6c)

---

## One extra phase-0 task

Phase 0 owns the provisional specs. After phase 0's gate passes, revise
`specs/PHASE_3_ENDPOINTS.md` through `PHASE_6_REALTIME.md` to match what you actually
built.

**Leave their status as PROVISIONAL.** Your revision is itself unreviewed. Note at the
top of each: "Revised by phase-0 agent, pending human review."

---

## Final report

When phase 2's gate passes — or when you stop early — write a closing entry in
`PROGRESS.md`:

- Which phases completed and their commit SHAs
- Total tests passing
- Every decision made without the user, gathered in one place
- What phase 3 should tackle first
- Anything you would want a human to look at before the port continues

Then stop. Do not start phase 3.
