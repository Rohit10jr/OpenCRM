# frappe_django_crm — React worktree

**This worktree does one thing: convert the Vue frontend to React.** The Django backend is
finished and is a fixed contract here. Do not change it.

If you were expecting the backend port — phases 0–8, DocTypes, permissions, Celery — that
is the *sibling* worktree. See "What not to read" below before opening anything.

## Read these first

| File | What it is |
|---|---|
| **`docs/react-spike/FINDINGS.md`** | **What the Vue frontend actually is** — 326 files, ~47,300 lines, measured. Read first |
| **`docs/react-spike/SPIKE_PLAN.md`** | **Scope, stack, the gate, and what "done" means.** Read second |
| `PORT_PLAN.md` **§3** | *The frontend contract.* The wire protocol the React client must speak |
| `PORT_PLAN.md` **§6** | The API surface — 51 whitelisted endpoints |
| `specs/AS_BUILT.md` | What the backend actually serves |

That is the whole reading list. It is short on purpose.

## What not to read

`specs/PHASE_*.md`, `docs/internal/*` (progress, runbooks, TASK, final report),
`specs/SECURITY_MODEL.md`, `specs/UNROUTED_DOCTYPES.md`, `specs/VERSION_HISTORY.md`.

These are **backend-port history**, roughly 6,000 lines of it. They are correct and they
are kept deliberately — but nothing in them applies to writing React, and reading them
costs an afternoon. `docs/internal/TASK.md` and `RUNBOOK_PHASE_8.md` are live instructions
for a *different agent in a different worktree*; they are not addressed to you.

**One exception.** `UPSTREAM_BUGS_PHASE_0-2.md` and `UPSTREAM_BUGS_PHASE_3-6.md` hold the
upstream findings, and some cite Vue files by line — `Settings.vue:214-218`,
`UserEmailSettings.vue:139`, `LeadModal.vue:187`. Before rewriting a screen, grep these two
files for its name. Otherwise you will either replicate a known upstream bug without
knowing, or silently "fix" one we deliberately reproduce.

## Source of truth

Port from **`frontend/`** — this repo's Vue app. It is not stock: `auth/tokens.js`,
`auth/jwtRequest.js` and `socket.js` were written or rewritten for this port and are ours.

```
upstream Vue   D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\frontend\src
```

Read upstream only to understand *intent* where ours is unclear. Where the two differ,
**ours wins** — the difference is usually deliberate and recorded.

## Hard rules

1. **The backend is a fixed contract.** Nothing in `backend/` changes during this work. If
   it looks like it must, that is a finding to write down and report — the API is
   documented and something is probably being misread.
2. **The Vue app must keep working.** Do not edit `frontend/`. New code goes in
   `frontend-react/` beside it, speaking to the same API. That is what makes this
   reversible.
3. **Work on the branch your runbook names**, and never on `main`. Do not merge to `main`
   while this is still an experiment. Do not name a branch here — this file has already
   gone stale once by doing that, when the work moved from `react-spike` to
   `react-conversion` and the sentence stayed behind.
4. **One commit per meaningful change, never one per screen.** The owner reads every
   commit — that is the point of the exercise, not overhead. A commit too large to review
   in a sitting has failed regardless of whether the code is right. Roughly: scaffold ·
   axios/auth · query layer · each shadcn primitive group · table · list engine · Deals ·
   kanban · then Leads.
5. **Conventional beats clever.** If there are two ways and one is what a React developer
   would expect, use that one even if the other is shorter. No custom state managers, no
   render props where a hook will do, no abstraction invented for a second caller that does
   not exist yet. Anything surprising is a defect even when it works — see the acceptance
   test in `SPIKE_PLAN.md`.
6. **Port faithfully vs. rewrite idiomatically.** `auth/tokens.js`, `auth/jwtRequest.js`
   and `socket.js` are ported — the refresh-once-on-401 path and the phase-6 reconnect
   logic (backoff, jitter, re-subscribe) are load-bearing and tested. **Do not reimplement
   them from memory.** Pinia stores, `createResource` and composables are rewritten —
   they are Vue answers to Vue problems.
7. **Do not tidy adjacent files.** The run you were given has a scope; stay inside it.
8. Comments explain **why**, not what. A comment earns its place by recording a decision
   or a trap.
9. **Update the document in the same commit as the code.** Every stale claim in this
   project was true when written — `AS_BUILT.md` went two phases stale, a docstring
   promised a three-line fix that would have deleted the timeline, a progress file said a
   plaster was removed while it was still serving three endpoints. Nobody wrote those to
   mislead; they changed the code and left the sentence behind. If your change makes a
   sentence somewhere false, fix the sentence in the same commit. It is the cheapest rule
   here and it has cost the most.
10. **Never disable or weaken a test to make it pass.** That is the worst available
    outcome, because it hides the failure instead of reporting it. The same applies to
    lowering a bar to clear it — a screen marked `verified` that was not clicked, a
    coverage claim narrowed after the fact. If something will not pass, say so and stop;
    an honest failure is a result, and a fabricated pass poisons every decision made from
    it.

## Stack

Fixed, because familiarity is the entire purpose of this work:

| Layer | Choice |
|---|---|
| Framework | React 18 + TypeScript |
| Routing | TanStack Router |
| Data | TanStack Query + axios |
| Components | shadcn/ui |
| Styling | Tailwind (already in the Vue app; the config ports) |
| Table | TanStack Table |
| Toast | sonner (replaces `frappe-ui` `toast`, ~30 sites) |
| Rich text | TipTap React bindings (the Vue `TextEditor` is a TipTap wrapper) |
| Build | Vite |

## Two things that are free — use them

* **`test_every_frontend_dotted_path_resolves`** in `backend/tests/test_phase3_endpoints.py`
  reads frontend source and fails if it calls an API path nothing serves. Point it at
  `frontend-react/` and the contract stays enforced for nothing.
* **The Vue app's own vitest suite** (`cd frontend && yarn test:run`) proves you have not
  broken it.

## This is a worktree

The sibling directory `frappe_django_crm/` holds another agent working on phase 8. **Shared
git history, separate working trees** — neither disturbs the other, but:

* Run everything from *this* directory. Never `cd` to the sibling.
* **Never bare `git stash` / `git stash pop`** — the stash stack is shared and you could
  pop their work. Use a WIP commit instead.

## Keep shell commands short

**A long command cannot be security-scanned, so it escalates to human review — which
stalls an unattended run indefinitely.** This has already cost a run on this project. No
permission rule can pre-approve it; the harness simply refuses to approve text it could not
read. The only fix is short commands.

Long *content* belongs in a file. The command that uses it stays tiny.

1. **Commit from a file, never inline.** Write the message with the Write tool, then
   `git commit -F .git/COMMIT_MSG`. Not `git commit -m "$(cat <<'EOF' … EOF)"`.
2. **Never inline a script.** Write `scratch/patch.py`, then `python scratch/patch.py`.
   No `python - <<'PY' … PY`.
3. **Never write file contents through the shell.** No `cat > file <<'EOF'`. Use Write and
   Edit — nothing gets scanned.
4. **Keep any single command under ~400 characters.** Chained commands count as one.
   Prefer several short calls over one long chain.

---

# Reviewer policy — three tiers

You write the code; something that does **not** share your blind spots reviews it. Try
these in order, stop at the first that genuinely works, and always say which tier you used.

| Tier | Reviewer | Notes |
|---|---|---|
| **1** | Codex via PowerShell 7 | Preferred — different model, reads the repo itself |
| **2** | Codex via PowerShell 5.1 | Same reviewer, fallback shell |
| **3** | Claude subagent | **Degraded** — same model, correlated blind spots |

## Tier 1 — Codex (default)

codex-cli on PATH as `codex`, auth configured. The interactive TUI needs a live terminal,
so you cannot drive it — use `codex exec`. Codex reads the repo itself; point it at paths,
do not paste code.

```powershell
codex exec -s read-only "<review request>"   # review, cannot touch files
codex exec resume --last "<follow-up>"       # continue the same session
```

**Never trust the exit code.** `codex exec` exits 0 even when it ran nothing. If the output
contains `CreateProcessAsUserW failed`, `windows sandbox: runner failed`, `SpawnChild`, or
Codex asks you to paste files — **the review did not happen.** Escalate a tier. A run that
does not return in ~10 minutes is also a failure: retry once with a narrower prompt naming
exact files and claims, then escalate.

## Tier 3 — Claude subagent

Spawn a **fresh** subagent, not a `fork` — a fork inherits the reasoning that produced the
bug, which is the opposite of a second opinion. It is still degraded, because the weakness
is *model correlation*, not context: same priors, same failure modes. Isolating context
further buys nothing; only a different model does.

It is weak at finding *different* bugs, not at finding bugs. Compensate by pointing it at
the Vue source rather than at your own plan, and by adding: *"Assume the author was
competent and the obvious things are right. Look for what a reader who shares the author's
assumptions would skip."*

## Always

Blocking, ~1–2 min per call — batch reviews rather than pinging after every edit. Report
findings, including where you disagree. **Do not auto-apply them.**
