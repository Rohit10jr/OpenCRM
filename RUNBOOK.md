# Unattended Run — Phases 0 to 4

**You are running without a human available. Read this whole file before starting.**

## Scope and the branch split

Two branches. This split is deliberate: it keeps reviewed work separate from work built
on unreviewed foundations, so phases 3–4 can be discarded wholesale without touching
phases 0–2.

| Branch | Phases | Why |
|---|---|---|
| `phase-0-foundation` (current) | **0 → 1 → 2** | The contract, the models, the security boundary |
| `phase-3-4-provisional` (you create it) | **4 → 3** | Built on specs revised but not reviewed |

Order on the second branch is **4 then 3**, not 3 then 4. Several of phase 3's Group A
endpoints (`get_filterable_fields`, `get_quick_filters`, `update_quick_filters`,
`get_views`) read and write the metadata layer phase 4 builds. Building them first means
building against stubs and then revising.

## HARD STOP

**After phase 3's gate passes, STOP.** Do not start phase 5, 6 or 7. Write your final
report and halt, even with time and capacity left.

---

## Gate before leaving `phase-0-foundation`

Phases 3–4 may **only** begin if phase 2 finished genuinely clean. Do not proceed if
any of these is true:

- Phase 2's gate needed a second attempt
- Codex's phase-2 security review raised anything you disputed rather than fixed
- Any phase-2 acceptance criterion lacks a real test
- You made a judgment call on permission semantics you are not confident about

If any apply: **stop at phase 2.** Log why in `PROGRESS.md`. Phases 3–4 built on a
shaky permission layer are worse than no phases 3–4, because they make the eventual fix
more expensive.

Permissions are the one thing where "probably right" is not good enough.

---

## Before you begin

Read, in order:

1. `CLAUDE.md` — project rules
2. `PORT_PLAN.md` — inventory, frontend contract, settled decisions
3. `specs/README.md` — spec index and status
4. `specs/PHASE_0_FOUNDATION.md` — your first task

Environment is prepared. Do not reconfigure it:

- Branch `phase-0-foundation`, scaffold committed
- PostgreSQL 17 running, database `opencrm`, credentials in `.env` (gitignored)
- Redis reachable on 6379
- `frontend/` holds the real Vue frontend (52,449 LOC) — your acceptance reference
- Frappe source: `D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm`

Backend goes in `backend/`. Create the venv there.

---

## The loop

For each phase in **0, 1, 2** — then, if the gate above allows, **4, 3**:

```
1. Read specs/PHASE_<N>_*.md in full
2. Implement it
3. Write tests for its acceptance criteria — real tests, not assertions of intent
4. Run the gate (below)
5. Gate passes  → commit, log to PROGRESS.md, next phase
   Gate fails   → fix, re-run gate (ONCE)
   Fails twice  → STOP. Log and halt.
```

Phases run strictly in sequence. Within phase 1 you may fan out by cluster; never two
agents in one file.

After phase 2 passes and the gate above allows:

```powershell
git checkout -b phase-3-4-provisional
```

Then continue the same loop with phase 4, then phase 3.

---

## The gate

All four must pass. No exceptions, no "close enough".

### 1. Tests pass

```powershell
cd backend
pytest -q
```

Must exit 0. Every acceptance criterion in the phase spec needs a corresponding test.
A criterion with no test does not count as met.

### 2. Migrations clean and applying from empty

```powershell
python manage.py makemigrations --check --dry-run
python manage.py migrate
```

`pytest-django` builds and drops `test_opencrm` each run, proving migrations apply from
empty. If it doesn't, fix that before proceeding.

### 3. Codex review — independent second opinion

Run from the repo root, read-only so Codex cannot touch your files.

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

**Phase 4:**
```powershell
codex exec -s read-only "Review the metadata layer in backend/ against specs/PHASE_4_METADATA.md and the Frappe source at D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm. Verify the 4-step column resolution order in api/doc.py:get_data is reproduced exactly; that filterable and group-by fieldtype allowlists match source; that get_non_filterable_fields() is honoured; that one user's saved view is invisible to another. Report file:line."
```

**Phase 3:**
```powershell
codex exec -s read-only "Review the API endpoints in backend/ against crm/api/*.py at D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm and specs/PHASE_3_ENDPOINTS.md. Verify every dotted path and parameter name matches source exactly, responses are wrapped in {'message': ...}, frappe.throw messages are preserved verbatim, and no endpoint bypasses the phase-2 permission layer. Pay special attention to bulk operations being permission-checked per item. Report file:line."
```

**Act on the findings.** Fix real defects. Where you disagree, record the disagreement
and your reasoning in `PROGRESS.md` — never silently ignore it.

### 4. Commit

One commit per phase, stating the phase and what landed.

---

## Fail-stop

**If a gate fails twice on the same phase, STOP.**

Write to `PROGRESS.md`: what failed, the actual error, what you tried, your best read of
the cause. Then halt.

Do not work around a failing gate. Do not skip ahead. **Do not disable or weaken a test
to make it pass** — that is the worst possible outcome, because it hides the failure
instead of reporting it.

A clean stop after phase 1 is far more useful than four phases of unverified code.

---

## PROGRESS.md

Create it at the repo root, append after every phase, pass or fail. This gets read first
on return — make it scannable.

```markdown
## Phase <N> — <PASS | FAILED | STOPPED>   [branch: <name>]
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
3. **Choose the option matching upstream behaviour**, implement it, log the decision.

Never invent semantics to make something easier. Never widen scope beyond the phase
spec. If a choice would be expensive to reverse and the evidence is genuinely
ambiguous, prefer to stop and ask over guessing — log it and halt.

Two known-open questions to answer from source:
- SLA computed on write or on a schedule? (`specs/PHASE_5_ASYNC.md` §4)
- The exact error-envelope shape the frontend parses (`specs/PHASE_0_FOUNDATION.md` §6c)

---

## One extra phase-0 task

Phase 0 owns the provisional specs. After phase 0's gate passes, revise
`specs/PHASE_3_ENDPOINTS.md` through `PHASE_6_REALTIME.md` to match what you built.

**Leave their status as PROVISIONAL** — your revision is itself unreviewed. Note at the
top of each: "Revised by phase-0 agent, pending human review."

---

## Final report

When phase 3's gate passes — or whenever you stop early — write a closing entry in
`PROGRESS.md`:

- Which phases completed, on which branch, with commit SHAs
- Total tests passing per branch
- Every decision made without the user, gathered in one place
- Whether `phase-3-4-provisional` is worth keeping or should be redone after review
- What phase 5 should tackle first
- Anything you want a human to look at before the port continues

Then stop.
