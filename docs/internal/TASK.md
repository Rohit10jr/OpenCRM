# TASK — Start Here

Read `docs/internal/RUNBOOK_PHASE_8.md` and follow it exactly. Where anything in this file
conflicts with it, the runbook wins.

```
Repo:   D:\02_Personal\01_OpenSource\03_Applications\CRM\frappe_django_crm
Branch: cut phase-8-auth from phase-8-prep-2  (NOT from main, and NOT from
        phase-8-prep - only prep-2 carries the two settled flag decisions, and
        it is deliberately unmerged)
Main:   phases 0-7 complete and merged. ~1,574 backend tests + 152 frontend, all passing
```

## Step 0 comes before any code

The runbook opens with **Step 0: read the recorded reasoning, then write
`docs/internal/ORIENTATION_PHASE_8.md`** saying what you understood — including **what you
think is stale or wrong** in what you read.

Do not skip it, and do not treat it as paperwork. Six phases of decisions are written down
in this repo, and the two most expensive bugs of the last review both came from an agent
(and later, a human) trusting a sentence that had quietly stopped being true. The section
where you disagree with the documents is the one most likely to be worth reading.

The runbook also carries **"How to work here"** — seven rules, each one a bug that
shipped. Read them before starting, not after your first review round.

## Read first, in this order

1. **`specs/AS_BUILT.md`** — what already exists. Read this before writing any code, and
   **read its security section**: this phase adds credential-bearing doctypes and that
   section carries the checklist
2. `CLAUDE.md` — project rules and the reviewer policy
3. `specs/SECURITY_MODEL.md` — what protects each doctype, and why we differ from upstream
4. `PORT_PLAN.md` — inventory, frontend contract, settled decisions
5. `specs/PHASE_8_AUTH_AND_DESK.md` — the spec
6. `specs/KNOWN_ISSUES.md` — problems that outlive a phase

`AS_BUILT.md` is first for a reason: seven phases built a framework layer, and the single
biggest time-waster available to you is rewriting part of it. For this phase specifically,
**the auth backend already exists** — login, logout, token refresh, `get_logged_user` and
`change_password` all shipped in phase 0. What is missing is the pages, plus endpoints for
password reset and invite acceptance.

## What to run

**Phase 8, scope A only.** Four screens and the endpoints behind them:

| # | Screen | Backend |
|---|---|---|
| 1 | Login | exists |
| 2 | Forgot password | new — port `user.py:1044` |
| 3 | Set / reset password | new — port `user.py:828` and `:945` |
| 4 | Invite acceptance | new — `crm.api.accept_invitation` |

Not in scope: Desk-linked record editors, or any generic admin UI.

Progress file: `docs/internal/PROGRESS_PHASE_8.md`.

**This is the last phase.** Stop when the gate passes.

## The decisions are made — do not re-open

All of them are in `specs/PHASE_8_AUTH_AND_DESK.md`. The short form:

1. **Pages live inside the Vue app.** The redirect out of the SPA at `router.js:222` is
   the bug, not the contract.
2. **Reset links last 1 hour**; invitations keep their 3 days. Two clocks, deliberately.
3. **`test_password_strength` is not ported** — validate in the browser, enforce the real
   minimum server-side via Django's validators.
4. **JWT, not a session** — `update_password` returns a token pair.

**And one correction you should know about**: the spec used to say there was no upstream to
be faithful to. That was wrong. `frappe/www/` and `user.py` carry the whole auth flow —
key generation, expiry, single-use, and two deliberately-chosen failure messages. Match
them. Only the markup is new.

## Commits — the thing that went wrong last time

**One commit per meaningful change.** The previous run was told "one commit per phase" and
produced single commits of 25,000 lines, which cannot be reviewed, bisected or reverted.

Commit when a coherent piece of work is complete and the suite is green — an integration's
model layer, its API client, its webhook handler, a bug fix, a docs update. **A dozen or
more commits for this phase is correct.**

Each commit stands alone: suite green at that commit, and a message saying what changed and
**why**. Write the message to a file and `git commit -F` — a long inline message stalls the
run (`CLAUDE.md`, shell rules).

## The gate

1. Full suite green, nothing weakened
2. Migrations clean, applying from empty
3. Independent review — Codex on PowerShell 7, then 5.1, then a fresh Claude subagent.
   **State which tier you used.** `codex exec` exits 0 even when it ran nothing
4. Commits as above
5. **Walk the flow yourself, and say how.** Invite an address, read the link out of the
   outbox, redeem it, set a password, log in with it. Phase 7 shipped a Twilio signature
   check that was correct, tested and unreachable in production; a green unit suite over a
   flow nobody walked is the same failure.

Fail twice on the same gate → write up what happened and **stop**. Login working and
password reset half-built, honestly reported, beats four screens nobody has walked.

## Two obligations while you work

- **Record every divergence** in `UPSTREAM_BUGS_PHASE_3-6.md`, continuing from #33.
  It is tracked in git now, so a reviewer can see it
- **Keep `specs/AS_BUILT.md` current** as you add framework helpers — it is what the next
  phase reads first, and it was two phases stale before this run

## What the human will read first

`docs/internal/PROGRESS_PHASE_7.md`. Make it scannable, and **write down what you are
unsure about**. The phase-4 review found eight security holes by pulling threads that
phase's progress file left dangling — the file was useful *because* it admitted what it had
not checked.
