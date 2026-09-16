# Every document in this repo, and where it came from

`docs/internal/` had fourteen files and no index. This is that index, and it covers the whole
repo rather than just this folder, because the useful question is not *"what is in here"* but
*"which of these should I read, and can I trust it."*

## How to read the "Written by" column

**Every document here was written by Claude.** The split that matters is not authorship, it
is whether a human was in the loop while it was written:

* **Attended** — written in a session with the owner, before or between runs, to *steer* the
  work. These encode decisions.
* **Unattended** — written by an agent during a run, about its own work. These *report*, and
  they carry the agent's own confidence, including where it was wrong.

Inferred from the commit each file arrived in, which is recorded below and checkable.

**Precedence, which matters more than any of the above:** where a spec and `AS_BUILT.md`
disagree, `AS_BUILT.md` wins. Where a document and the Frappe source disagree, the source
wins.

---

## A. Day 1 — the planning set

Three commits. On 14 August this was the entire process.

| File | Written by | When | For |
|---|---|---|---|
| `readme.md` | Attended | 13 Aug | One line, until the *Getting in* section was added |
| `docs/PORT_PLAN.md` | Attended | 14 Aug | Source inventory, the frontend wire contract, settled architecture decisions |
| `CLAUDE.md` | Attended | 14 Aug | Standing rules for Claude. **Auto-loaded** |
| `AGENTS.md` | Attended | 14 Aug | Standing rules for Codex. **Auto-loaded**, written as a reviewer brief |
| `specs/README.md` | Attended | 14 Aug | Index of the phase specs and their status |
| `specs/PHASE_0_FOUNDATION.md` … `PHASE_7_INTEGRATIONS.md` | Attended | 14 Aug | **Eight specs written up front** — what each phase must build |
| `docs/internal/RUNBOOK.md` | Attended | 14 Aug | The first handoff. Covered phases 3–6; now a record of that run |
| `docs/internal/TASK.md` | Attended | 14 Aug | The entry point. Names the runbook to follow |
| `frontend/README.md` | — | 14 Aug | Came with the copied Vue app. Not ours |

## B. Written between phases, to set up the next one

Prep work, each its own commit or PR, none of it produced by a running agent.

| File | Written by | When | For |
|---|---|---|---|
| `specs/PHASE_8_AUTH_AND_DESK.md` | Attended | 15 Aug | Phase 8's spec, written early and **parked** until 0–7 finished |
| `specs/AS_BUILT.md` | Attended | 15 Aug | **What actually exists**, as against what the specs predicted. Created once the specs began rotting, and it beats them where they disagree |
| `docs/internal/RUNBOOK_PHASE_7.md` | Attended | 21 Aug | Phase 7's handoff — and where Step 0 and the nine "How to work here" rules were invented |
| `docs/internal/RUNBOOK_PHASE_8.md` | Attended | 23 Aug | Phase 8's handoff |
| `docs/WORKFLOW.md` | Attended | 25 Aug | All of the above, generalised into a reusable template for other projects |
| `docs/BACKEND_LAYOUT.md` | Attended | 9 Sep | What each `backend/` folder is for, and how a request travels through the three generic views. The orientation for someone who expected a normal Django layout |
| `docs/TESTING_GUIDE.md` | Attended | 10 Sep | The manual API walkthrough: what to test in what order, what each response should look like, and the gaps you will hit |
| `docs/http/*.http` | Attended | 10 Sep | The API test suite as VS Code REST Client files: click a block to see it, or replay a whole file with `backend/scripts/run_http.py`. `00_walkthrough` is the learning path; the numbered files cover every endpoint |
| `docs/ROUTES.md` | Attended | 9 Sep | **Generated** by `backend/scripts/generate_route_inventory.py` — every backend and frontend route in one place, with blank *Tested* columns. The checklist for the API walkthrough |

## C. Agent output — written during a run, about its own work

| File | Written by | When | For |
|---|---|---|---|
| `docs/internal/PROGRESS.md` | Unattended | 14 Aug | Phases 0–2 |
| `frontend/JWT_PATCH.md` | Unattended | 14 Aug | The JWT changes made to the Vue app in phase 0 |
| `docs/internal/PROGRESS_PHASE_3.md` | Unattended | 16 Aug | The endpoint layer |
| `docs/internal/PROGRESS_PHASE_4.md` | Unattended | 16 Aug | The metadata layer |
| `docs/internal/PROGRESS_PHASE_5.md` | Unattended | 16 Aug | Celery, beat schedule, async signals |
| `docs/internal/PROGRESS_PHASE_6.md` | Unattended | 16 Aug | Channels realtime |
| `docs/internal/FINAL_REPORT.md` | Unattended | 16 Aug | **Across** phases 3–6 — the cross-phase view no single progress file can give. Its §4 names the defect class that recurred four times |
| `docs/internal/ORIENTATION_PHASE_7.md` | Unattended | 21 Aug | **Written before any code.** What I understood, and what I believe is stale. Found four false claims |
| `docs/internal/PROGRESS_PHASE_7.md` | Unattended | 22 Aug | The five integrations |
| `docs/internal/ORIENTATION_PHASE_8.md` | Unattended | 24 Aug | Same, for phase 8. Found five |
| `docs/internal/PROGRESS_PHASE_8.md` | Unattended | 24 Aug | The auth screens. **Its Concerns section is the honest list of what phase 8 did not check** |

Every progress file follows one template: built · tests · review tier · decisions taken
without you · deviations · not done · concerns. **Concerns is the section worth reading
first** — a review once found eight security holes by pulling threads one had left dangling.

## D. Agent byproducts — none of these were planned

Each exists because a review found something. Nobody sat down to write any of them.

| File | Written by | When | For |
|---|---|---|---|
| `specs/UNROUTED_DOCTYPES.md` | Unattended | 18 Aug | Doctypes withheld from `/api/resource/`, and the rule we would have written instead |
| `specs/SECURITY_MODEL.md` | Unattended | 19 Aug | Per-doctype protection, and the 11 places we deliberately differ from upstream |
| `specs/KNOWN_ISSUES.md` | Unattended | 20 Aug | Problems that outlive a phase — flaky tests, half-built features, accepted trades |
| `specs/VERSION_HISTORY.md` | Unattended | 20 Aug | What change history is recorded and pruned. **Read before touching `clear_old_versions`** — its name invites a change that deletes the timeline |
| `docs/UPSTREAM_BUGS_PHASE_0-2.md` | Unattended | written from 14 Aug, **tracked 23 Aug** | Defects found in **upstream Frappe** while porting, with our stance on each |
| `docs/UPSTREAM_BUGS_PHASE_3-6.md` | Unattended | written from 16 Aug, **tracked 23 Aug** | The same, continuing. **38 entries across both files**, one sequence |

> **Two things this group got wrong, both now fixed, both worth knowing.** The registers were
> **gitignored for six phases** — so an agent under a standing obligation to record every
> divergence was writing into a file no reviewer could see. And once tracked, the two files
> had *independently* numbered entries 10–13, so a cross-reference to "#12" meant two
> different bugs depending on which file you opened.

---

## If you are starting work here

Read in this order, and stop when you have what you need:

1. **`specs/AS_BUILT.md`** — what exists. The largest available time-waster is rebuilding it
2. **`CLAUDE.md`** — the rules, and the reviewer policy
3. **`docs/PORT_PLAN.md`** — the contract and the settled decisions
4. **Your phase's spec**, then **`specs/KNOWN_ISSUES.md`**

And if you are handing work to an agent rather than doing it yourself, read
**`docs/WORKFLOW.md`** — it is the shape all of the above turned out to have.

*(The `PROGRESS_*`, `TASK` and `RUNBOOK` files began at the repository root and were moved
here later; so did `PORT_PLAN.md` and the two `UPSTREAM_BUGS` files, into `docs/`.
`git log --follow` crosses both moves.)*
