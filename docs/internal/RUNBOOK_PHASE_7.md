# Unattended Run — Phase 7, Integrations

**You are running without a human available. Read this whole file before starting.**

This supersedes `RUNBOOK.md`, which covered the phases 3–6 run and is now a record of it.
The reviewer policy and gate below are the same; the commit rule is **not** — read §4.

---

## Scope

**Phase 7 only.** One branch, `phase-7-integrations`, cut from `main`.

| Integration | Source | ~LOC | Flag |
|---|---|---|---|
| **ERPNext** | `integrations/erpnext/`, `erpnext_crm_settings.py` | 1,300 | `ENABLE_ERPNEXT` |
| **Facebook lead sync** | `lead_syncing/`, `facebook_*` doctypes | 550 | `ENABLE_FACEBOOK_LEAD_SYNC` |
| **Twilio** | `integrations/twilio/`, `crm_twilio_settings` | 250 | `ENABLE_TWILIO` |
| **Exotel** | `integrations/exotel/`, `crm_exotel_settings` | 200 | `ENABLE_EXOTEL` |
| **WhatsApp** | `api/whatsapp.py` | 200 | `ENABLE_WHATSAPP` |

Every flag exists already in `config/settings/base.py`, all **off**.

## HARD STOP

**After phase 7's gate passes, STOP.** Do not start phase 8 — it ports nothing from
upstream, is new product work, and needs a human scope decision
(`specs/PHASE_8_AUTH_AND_DESK.md`).

## Two decisions the human has already made

Do not re-open these.

1. **ERPNext is an API client.** You are integrating with a *live ERPNext instance* over
   HTTP. You are **not** reimplementing ERPNext's models — that is explicitly out of
   scope. If the work seems to require porting `Item` or `Sales Order`, you have taken a
   wrong turn; log it and reduce scope.
2. **WhatsApp: port the endpoints, stub the provider.** It depends on `frappe_whatsapp`,
   a separate Frappe app not in this repo. Port `api/whatsapp.py`'s six endpoints and the
   message model behind a named seam, the way phase 5 did with `_reconcile_products`.
   **Do not vendor `frappe_whatsapp`.**

---

## Before you begin

Read, in order:

1. **`specs/AS_BUILT.md`** — what already exists. **Its security section is not optional
   for this phase**: you are adding credential-bearing doctypes, and it carries the
   checklist for that
2. `CLAUDE.md` — project rules and the reviewer policy
3. `specs/SECURITY_MODEL.md` — what protects a doctype and why, per doctype
4. `PORT_PLAN.md` — inventory, frontend contract, settled decisions
5. `specs/PHASE_7_INTEGRATIONS.md` — the spec
6. `specs/KNOWN_ISSUES.md` — problems that outlive a phase; check before re-diagnosing

### What is already built for you

Phase 5 left seams deliberately, so **do not create parallel machinery**:

| Already exists | Where |
|---|---|
| Six lead-sync tasks, registered, no-op behind the flag | `crm_app/tasks.py` |
| `run_product_reconciliation` and its `_reconcile_products` seam | `crm_app/tasks.py` |
| Twilio and Exotel settings doctypes, gated, credentials encrypted | `crm_app/models/telephony.py` |
| `CRM Call Log` and the shared call-log path | `crm_app/models/telephony.py` |
| Realtime publish, correct argument order | `crm_app.realtime.publish(event, message, user=...)` |
| Encryption at rest | `frappe_core.secrets`, `ENCRYPTED_FIELDS` |

Three realtime events are named and unported: `crm_customer_created`, `exotel_call`,
`whatsapp_message`. **`whatsapp_message` is a broadcast, not a doc-room event** —
`AS_BUILT.md` records that so you do not have to rediscover it.

---

## The rules that govern this phase

From `specs/PHASE_7_INTEGRATIONS.md` §3, and they are acceptance criteria, not advice:

- Every integration behind **its own flag, off by default**
- The CRM must be **fully functional with all five disabled** — no import-time coupling.
  A flag that is off must not import the provider's SDK
- **Never commit credentials.** Settings singletons hold encrypted fields
- Every outbound call gets **a timeout and a retry policy**. Phase 3 shipped a mail
  validation with no timeout and it hung the request for up to 130s — `UPSTREAM_BUGS` #15
- Failures **degrade gracefully**: an unreachable provider must never break lead or deal
  CRUD
- Webhooks: **verify signatures**, dedupe by provider message ID, respond fast and process
  async

**On signature verification:** the spec says do not skip it because it is inconvenient in
dev. It means it. An unsigned webhook endpoint is an unauthenticated write path into the
CRM from the public internet.

### Adding a doctype

Two tests will fail on you, deliberately. Neither decides for you; both refuse to let you
skip deciding.

* **`tests/test_route_surface.py`** — registering a doctype publishes it. Record what
  protects it: a row rule, reviewed-and-open with a reason, or not-yet-reviewed with the
  question.
* **`tests/test_credential_fields.py`** — a field whose name looks like a credential must
  be declared in `SENSITIVE_FIELDS`, `ENCRYPTED_FIELDS` or `RESTRICTED_FIELDS`, or excused
  in writing.

The checklist is in `specs/AS_BUILT.md`. Follow it in order; it is five steps and it exists
because this project has already shipped a plaintext SMTP password and an API key on a
world-readable record.

---

## The loop

Work in fan-out where the work is independent. The five integrations barely touch each
other — Twilio and Exotel share the call-log path and nothing else. **Never two agents in
one file.**

Blocked on one integration? Move to another. Do not serialise on a parkable question.

**Never wait on an external service.** No integration test may require a live ERPNext,
Twilio account or Meta app. Stub at the seam and test the control flow — that is what
`_reconcile_products` is for.

---

## The gate

Same four steps as the phases 3–6 run. §4 has changed.

### 1. Tests pass

Full suite, green, no skips added. **Nothing weakened to make it pass** — that is the
worst possible outcome, because it hides the failure instead of reporting it.

With **all five flags off**, the suite must pass and no integration module may be
imported. Assert that, do not assume it.

### 2. Migrations clean and applying from empty

`makemigrations --check --dry-run` reports nothing outstanding, and the full migration set
applies to an empty database.

### 3. Independent review — three tiers, tried in order

**Unchanged from `RUNBOOK.md` §3.** Codex on PowerShell 7, then PowerShell 5.1, then a
fresh Claude subagent. `CLAUDE.md` carries the policy and the failure signatures that mean
a review did not actually happen.

**`codex exec` exits 0 even when it ran nothing.** If the output contains
`CreateProcessAsUserW failed`, `windows sandbox: runner failed`, `SpawnChild`, or Codex
asks you to paste files — the review did not happen. Escalate a tier.

Act on the findings. Where you disagree, record the disagreement and your reasoning in the
progress file — never silently ignore it. **State the tier used.**

### 4. Commits — one per meaningful change, NOT one per phase

**This is the rule that changed.** The phases 3–6 runbook said "one commit per phase", and
the result was single commits of 25,000 lines that are impossible to review, bisect or
revert.

**Commit when a coherent piece of work is complete and the suite is green.** Roughly:

- one integration's model layer
- one integration's API client
- one integration's webhook handler
- the shared call-log path
- a bug fix found during review
- a docs update

That is a dozen or more commits for this phase, and that is correct.

**Each commit must stand alone:** the suite green at that commit, and a message saying
what changed and *why* — the reasoning, not a restatement of the diff. Where you diverged
from upstream, the commit message is where the reason lives.

**Do not** batch unrelated changes because they happened in the same session. **Do not**
leave the suite red between commits. If a change is too large to describe in a sentence,
it is too large to be one commit.

Follow `CLAUDE.md`'s shell rules: write the message to a file, then `git commit -F`. A
long inline commit message stalls an unattended run.

---

## Fail-stop

**If the gate fails twice, STOP.**

Write to `PROGRESS_PHASE_7.md`: what failed, the actual error, what you tried, your best
read of the cause. Then halt.

Do not work around a failing gate. Do not skip ahead. **Do not disable or weaken a test.**

A clean stop with three integrations landed is far more useful than five unverified ones.

---

## `PROGRESS_PHASE_7.md`

At `docs/internal/PROGRESS_PHASE_7.md`, on the phase branch. Written when the phase ends —
pass, fail or stop. This is what gets read first on return, so make it scannable.

Follow the format the earlier phase files use. The sections that have proved to matter:

- **What was built**, and the acceptance criteria with what covers each
- **Decisions made without you** — anything a human would want to have been asked about
- **Deviations from spec**, with the reason
- **Not ported — named, not hidden.** A gap you record is a decision; a gap you omit is a
  bug someone finds later
- **Concerns** — what you would look at first if you had another hour

**Write what you are unsure about.** The phase-4 review found eight security holes by
pulling threads the phase's own progress file left dangling. That file was useful
*because* it admitted what it had not checked.

---

## Judgment calls

### When upstream is wrong

It sometimes is — **21 cases** are recorded in `UPSTREAM_BUGS_PHASE_*.md`. Diverge only on
bugs nothing can observe, and reproduce user-visible ones. Check whether anything actually
reads the field before deciding, and record the choice.

**Security is the standing exception.** Upstream protects most doctypes with DocType role
permissions, a layer this port does not model, so "upstream registers no hook" means
"upstream had protection we do not". Five findings came from reading a missing hook as a
missing requirement.

### When something looks impossible

Suspect a missing framework mechanism before suspecting your own code. `fetch_from` was
never ported and the symptom was "converted deals have a contact but no email" — it looked
like a conversion bug for an hour.

---

## Two standing obligations

1. **Record every divergence** in `UPSTREAM_BUGS_PHASE_3-6.md` (continue the numbering
   from 21) with the file:line evidence and our stance.
2. **Update `specs/AS_BUILT.md`** as you add framework-level helpers. It is what the next
   phase reads first, and it was two phases stale before this run — an agent reading it
   would have stored a page token in plain text.
