# TASK — Start Here

Read `docs/internal/RUNBOOK_PHASE_7.md` and follow it exactly. Where anything in this file
conflicts with it, the runbook wins.

```
Repo:   D:\02_Personal\01_OpenSource\03_Applications\CRM\frappe_django_crm
Branch: cut phase-7-integrations from main
Main:   phases 0-6 complete and merged. ~1,290 backend tests + 152 frontend, all passing
```

## Read first, in this order

1. **`specs/AS_BUILT.md`** — what already exists. Read this before writing any code, and
   **read its security section**: this phase adds credential-bearing doctypes and that
   section carries the checklist
2. `CLAUDE.md` — project rules and the reviewer policy
3. `specs/SECURITY_MODEL.md` — what protects each doctype, and why we differ from upstream
4. `PORT_PLAN.md` — inventory, frontend contract, settled decisions
5. `specs/PHASE_7_INTEGRATIONS.md` — the spec
6. `specs/KNOWN_ISSUES.md` — problems that outlive a phase

`AS_BUILT.md` is first for a reason: six phases built a framework layer, and the single
biggest time-waster available to you is rewriting part of it. Phase 5 in particular left
named seams for this phase to fill — `_reconcile_products`, six registered lead-sync tasks,
the Twilio and Exotel settings doctypes with their credentials already encrypted.

## What to run

**Phase 7 only.** Five integrations, each behind its own flag, all off by default:

| Integration | Flag | ~LOC |
|---|---|---|
| ERPNext | `ENABLE_ERPNEXT` | 1,300 |
| Facebook lead sync | `ENABLE_FACEBOOK_LEAD_SYNC` | 550 |
| Twilio | `ENABLE_TWILIO` | 250 |
| Exotel | `ENABLE_EXOTEL` | 200 |
| WhatsApp | `ENABLE_WHATSAPP` | 200 |

Progress file: `docs/internal/PROGRESS_PHASE_7.md`.

**Stop after phase 7's gate passes.** Phase 8 needs a human scope decision.

## Two decisions already made — do not re-open

1. **ERPNext is an API client** against a live instance. You are not reimplementing
   ERPNext's models; that is out of scope.
2. **WhatsApp: port the endpoints, stub the provider.** Do not vendor `frappe_whatsapp`.

## Commits — the thing that went wrong last time

**One commit per meaningful change.** The previous run was told "one commit per phase" and
produced single commits of 25,000 lines, which cannot be reviewed, bisected or reverted.

Commit when a coherent piece of work is complete and the suite is green — an integration's
model layer, its API client, its webhook handler, a bug fix, a docs update. **A dozen or
more commits for this phase is correct.**

Each commit stands alone: suite green at that commit, and a message saying what changed and
**why**. Write the message to a file and `git commit -F` — a long inline message stalls the
run (`CLAUDE.md`, shell rules).

## The gate, per phase

1. Full suite green, nothing weakened, **and green with all five flags off with no
   integration module imported**
2. Migrations clean, applying from empty
3. Independent review — Codex on PowerShell 7, then 5.1, then a fresh Claude subagent.
   **State which tier you used.** `codex exec` exits 0 even when it ran nothing
4. Commits as above

Fail twice on the same gate → write up what happened and **stop**. A clean stop with three
integrations landed beats five unverified ones.

## Two obligations while you work

- **Record every divergence** in `UPSTREAM_BUGS_PHASE_3-6.md`, continuing from #21
- **Keep `specs/AS_BUILT.md` current** as you add framework helpers — it is what the next
  phase reads first, and it was two phases stale before this run

## What the human will read first

`docs/internal/PROGRESS_PHASE_7.md`. Make it scannable, and **write down what you are
unsure about**. The phase-4 review found eight security holes by pulling threads that
phase's progress file left dangling — the file was useful *because* it admitted what it had
not checked.
