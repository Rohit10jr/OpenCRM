# Unattended Run — Phases 3 to 6

**You are running without a human available. Read this whole file before starting.**

## Scope

Phases **3, 4, 5, 6**, in that order, on one new branch:

```powershell
git checkout -b phases-3-to-6
```

Phases 0-2 are **complete, reviewed and merged** on `phase-0-foundation` — 813 tests
passing. Do not revisit them; if you believe one is wrong, log it rather than reopening it.

## HARD STOP

**After phase 6's gate passes, STOP.** Do not start phase 7 (integrations, deferred
behind flags) or phase 8 (parked — it ports nothing and needs a human scope decision).

## Order matters, and phase 3 is the big one

**3 → 4 → 5 → 6.** Roughly 50 endpoints in phase 3 against 12 in phase 4 and less again
after; the work is heavily front-loaded.

Phase 4 comes after 3 rather than before it this time — the reverse of the earlier plan —
because phase 0 already implemented `get_data`'s four-step column resolution and left
`_load_saved_view` as a registered provider hook. Phase 3's metadata endpoints read that
seam; they do not need phase 4 to have filled it.

**If the window runs out mid-phase, stop cleanly.** Phase 3 complete with 4-6 untouched
is a good outcome. Three phases done properly beats four half-done — that is what the
gate is for.

## Before you begin

Read, in order:

1. **`specs/AS_BUILT.md`** — what phases 0-2 actually built
2. `CLAUDE.md` — project rules and the reviewer policy
3. `PORT_PLAN.md` — inventory, frontend contract, settled decisions
4. `specs/PHASE_3_ENDPOINTS.md` — your first task

**Read `specs/AS_BUILT.md` first — before `CLAUDE.md`, before your phase spec.** It
records what phases 0-2 actually built, as opposed to what the specs predicted. The
largest available time-waster is rewriting part of the framework layer that already
exists. Where a phase spec and `AS_BUILT.md` disagree, `AS_BUILT.md` wins.

Environment is prepared. Do not reconfigure it:

- Branch `phase-0-foundation`, phases 0-2 complete at 813 tests passing
- PostgreSQL 17 running, database `opencrm`, credentials in `.env` (gitignored)
- Redis reachable on 6379
- `frontend/` holds the real Vue frontend (52,449 LOC) — your acceptance reference
- Frappe **CRM app**: `D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm` (`main`)
- Frappe **framework**: `D:\02_Personal\01_OpenSource\02_FrameWorks\frappe` (`version-15`)
  — unavailable during phases 0-2, and several defects were only findable in it. The
  pairing `main` + `version-15` is what the CRM's own CI uses; do not read `develop`.
  — unavailable during phases 0-2; several defects were only findable in it

Backend goes in `backend/`. Create the venv there.

---

## The loop

For each phase in **3, 4, 5, 6**:

```
1. Read specs/PHASE_<N>_*.md in full
2. Implement it
3. Write tests for its acceptance criteria — real tests, not assertions of intent
4. Run the gate (below)
5. Gate passes  → commit, log to PROGRESS.md, next phase
   Gate fails   → fix, re-run gate (ONCE)
   Fails twice  → STOP. Log and halt.
```

Phases run strictly in sequence. Within a phase you may fan out by module or cluster;
**never two agents in one file**. Phase 3's five module groups (`specs/PHASE_3_ENDPOINTS.md`
§2) are the natural split.

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

### 3. Independent review — three tiers, tried in order

The point of this step is a reviewer that **does not share your blind spots**. Try the
tiers in order and stop at the first that genuinely works. **Record which tier you used
in `PROGRESS.md`** — a phase reviewed at tier 3 has had a weaker check than one reviewed
at tier 1, and the reader must be able to tell.

| Tier | Reviewer | Strength |
|---|---|---|
| **1** | Codex via PowerShell 7 | **Preferred** — different model, reads the repo itself |
| **2** | Codex via PowerShell 5.1 | Same reviewer, fallback shell |
| **3** | Claude subagent | **Degraded** — same model and same spec |

**Tier 3 is a real fallback, not an equivalent one** — but be precise about why. A fresh
subagent gets only the task prompt, so it is **not** carrying the writer's context. The
weakness is that it shares the writer's **model** (same priors, same failure modes) and
its **inputs** (the same spec — and when `PHASE_0_FOUNDATION.md` wrongly said `field:`
PKs are "slugified", only Codex caught it, by reading the Frappe source instead).

Since the weakness is model correlation, isolating context further does not help;
`claude -p` buys nothing over a fresh subagent. Only a different model does. Across
phases 0–2 Codex found 20 real defects precisely because it is one.

If you land on tier 3, say so plainly in `PROGRESS.md` and treat the phase as less
verified — less *diversely* covered, not less competently reviewed.

#### Tier 1 — Codex on PowerShell 7 (default)

`pwsh` resolves to `C:\Users\New\pwsh7\pwsh.exe`. Run from the repo root, read-only so
Codex cannot touch your files. Use the per-phase prompts below.

**Phase 3:**
```powershell
codex exec -s read-only "Review the API endpoints in backend/ against crm/api/*.py at D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm and specs/PHASE_3_ENDPOINTS.md. Verify every dotted path and parameter name matches source exactly, responses are wrapped in {'message': ...}, frappe.throw messages are preserved verbatim, and no endpoint bypasses the phase-2 permission layer by using Model.objects directly instead of query.fetch_rows. Check that any endpoint creating a lead or deal sets lead_owner/deal_owner, or the record is invisible to its creator. Pay special attention to bulk operations being permission-checked per item. Report file:line."
```

**Phase 4:**
```powershell
codex exec -s read-only "Review the metadata layer in backend/ against specs/PHASE_4_METADATA.md and the Frappe source at D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm. Verify the 4-step column resolution order in get_data is preserved (phase 0 already implemented it - check it was extended, not rewritten); that filterable and group-by allowlists are keyed on the Frappe fieldtype rather than the Django internal type; that get_non_filterable_fields() is honoured; and that one user's saved view is invisible to another. Report file:line."
```

**Phase 5:**
```powershell
codex exec -s read-only "Review the Celery tasks and beat schedule in backend/ against specs/PHASE_5_ASYNC.md and crm/hooks.py at D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm. Verify the beat entries match hooks.py scheduler_events exactly; that NO SLA sweep job exists (upstream computes SLA on write only); that deferred lead-sync tasks are registered but no-op behind a flag; that bulk delete permission-checks each item inside the task rather than only at request time; and that cache writes use a bare UPDATE rather than save(), so modified is not re-stamped. Report file:line."
```

**Phase 6:**
```powershell
codex exec -s read-only "Review the Channels realtime layer in backend/ against specs/PHASE_6_REALTIME.md. Verify unauthenticated WebSocket connects are rejected; that joining a document group runs the phase-2 permission check rather than trusting the client; that event names and payloads match the publish sites in crm/ at D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm; and that nothing in the app breaks when Channels is switched off. Report file:line."
```

#### Detecting a failed review — do not trust the exit code

**`codex exec` exits 0 even when it ran nothing.** A spawn failure is reported to the
model, not to the process. Any check on `$LASTEXITCODE` alone will record a review that
never happened — this is exactly how phases 0–2 were reviewed blind.

Treat the review as **FAILED** if the output contains any of:

```
CreateProcessAsUserW failed
windows sandbox: runner failed
SpawnChild
I couldn't complete the review
```

or if Codex asks you to paste files in. A review where Codex could not read the repo is
not a review. Escalate to the next tier rather than accepting it.

**Also treat it as FAILED if it does not return within ~10 minutes.** A broad prompt over
a large repo can run indefinitely — it reads far more than you expect. Two options, in
order: re-run once with a **narrower** prompt (name the specific files and the specific
claims to check, rather than asking it to go find things), and if that also times out,
escalate a tier. Record the timeout in `PROGRESS.md` the same way as any other failure —
a review that never returned is not a review that passed.

#### Tier 2 — Codex on PowerShell 5.1

If tier 1 fails, retry the identical prompt with `pwsh` hidden, so Codex falls back to
`powershell.exe`:

```powershell
$orig = $env:PATH
$env:PATH = ($orig -split ';' | Where-Object { $_ -notlike '*WindowsApps*' -and $_ -notlike '*pwsh7*' }) -join ';'
codex exec -s read-only "<same prompt>"
$env:PATH = $orig
```

Apply the same failure detection. If it also fails, go to tier 3.

#### Tier 3 — Claude subagent (degraded)

Spawn a **fresh subagent** with the same per-phase prompt. Prefer this over
`claude -p`: no process startup, parallelisable, and the harness notifies on completion
rather than blocking on a call that might hang.

- **Never use a `fork` subagent for review.** A fork inherits the writer's full context
  — including the reasoning that produced the bug. Use a fresh agent with no
  conversation context.
- Give it the phase prompt verbatim, plus the repo path and the Frappe source path.
- Use `claude -p "<prompt>"` **only** if you are yourself a subagent and cannot spawn
  one, or if you want a hard context boundary. Verified working: Claude Code 2.1.232.

Because tier 3 shares your blind spots, add one instruction the other tiers don't need:
*"Assume the author was competent and the obvious things are right. Look for what a
reader who shares the author's assumptions would skip."*

**Act on the findings.** Fix real defects. Where you disagree, record the disagreement
and your reasoning in `PROGRESS.md` — never silently ignore it. **State the tier used.**

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

**Review — tier <1 | 2 | 3>:** which reviewer actually ran, and why that tier (if not 1,
what failed). Then: what it raised, what you fixed, what you disputed and why. If tier 3,
say plainly that this phase had a weaker check than a Codex-reviewed one.

**Decisions made without you:** every judgment call taken in the user's absence —
especially the two open spec questions (SLA compute timing, error-envelope shape).
State what you chose and the evidence.

**Deviations from spec:** anything built differently, and why.

**Concerns:** what you are unsure about. Be honest — this is the most valuable section.
```

---

## Judgment calls

You will hit ambiguity. In order of preference:

1. **Read the CRM source.** It is the source of truth and it is right there.
2. **Read the framework source.** New since phases 0–2, and it answers things the CRM
   app cannot — `fetch_from`, `validate_name`, `append_number_if_name_exists`, nested-set
   locking and the shared-docs query were all only findable there.
3. **Read the frontend.** `frontend/src/stores/`, `src/data/document.js`,
   `src/composables/document.js` show what the API is expected to return.
4. **Choose the option matching upstream behaviour**, implement it, log the decision.

Never invent semantics to make something easier. Never widen scope beyond the phase
spec. If a choice would be expensive to reverse and the evidence is genuinely
ambiguous, prefer to stop and ask over guessing — log it and halt.

### When upstream is wrong

It sometimes is — nine cases are catalogued in `UPSTREAM_BUGS.md`. The rule:

> **Diverge on bugs nothing can observe. Reproduce bugs that are user-visible.**

Before diverging, **check whether anything reads the field or behaviour**. A status-log
field was corrected because nothing reads it; an odd guard on expected deal value was
reproduced because users see the result. Record either choice in the code with the source
line, and add an entry to `UPSTREAM_BUGS.md`.

### When something looks impossible

Suspect a missing framework mechanism before suspecting your own code. `fetch_from` was
never ported, and the symptom — "converted deals have a contact but no email" — looked
like a conversion bug for an hour. Check the framework source for the feature before
working around it.

---

## Two standing obligations

**Keep `specs/AS_BUILT.md` current.** It is what stops the next agent rewriting your
work. When you add a helper other phases will call, add the row. When a phase spec turns
out to be wrong about what exists, fix `AS_BUILT.md` first.

**Flip your spec's status when the gate passes.** Specs 3-6 are marked *PROVISIONAL —
revised by phase-0 agent, pending human review*. Once a phase is built, tested and
reviewed, replace that header with what is actually true of it. A spec still claiming to
be provisional after its phase shipped is worse than no status at all.

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
