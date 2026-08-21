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

**Start at Step 0 below** — it carries the reading list and the orientation file you write
before touching code. What follows here is the short version of why that matters.

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

## Step 0 — Understand what exists, and write down what you found

**Before writing any code.** Not a formality: an agent that skips this rebuilds a
framework layer that already exists, or trusts a document that has gone stale.

Read, in this order:

| # | File | What you are looking for |
|---|---|---|
| 1 | `specs/AS_BUILT.md` | What exists. **Its security section is mandatory for this phase** |
| 2 | `specs/SECURITY_MODEL.md` | What protects each doctype, and the 11 places we differ from upstream |
| 3 | `specs/UNROUTED_DOCTYPES.md` | Two routes withheld, and the rule we would write instead |
| 4 | `specs/VERSION_HISTORY.md` | What change history is recorded and pruned |
| 5 | `specs/KNOWN_ISSUES.md` | Problems that outlive a phase — check before re-diagnosing |
| 6 | `UPSTREAM_BUGS_PHASE_*.md` | 21 upstream defects and our stance on each |
| 7 | `PORT_PLAN.md` | Inventory, frontend contract, settled decisions |
| 8 | `docs/internal/PROGRESS_PHASE_3..6.md` | What each phase built, and its Review Resolution |
| 9 | `specs/PHASE_7_INTEGRATIONS.md` | Your task |

Then **write `docs/internal/ORIENTATION_PHASE_7.md`** before starting. Six sections:

1. **What exists that I must not rebuild.** Name the helpers and seams, with paths. Phase 5
   left `_reconcile_products`, six registered lead-sync tasks and two settings doctypes
   with credentials already encrypted, specifically for you.
2. **The mechanisms that protect a doctype**, in your own words, and when each applies. If
   you cannot explain why `SENSITIVE_FIELDS` and `ENCRYPTED_FIELDS` are both needed on a
   credential, re-read before continuing.
3. **What I believe is stale or wrong in these documents.** See the rule below — this is
   the section most likely to be genuinely useful.
4. **What I do not understand yet**, and what I will do about it.
5. **The risks I see in phase 7 specifically**, given what I have read.
6. **My plan**, integration by integration, with the order and why.

**Keep it under two pages.** It is a thinking exercise, not a deliverable. Its value is
that it forces you to notice the gap between what the docs say and what the code does —
which is exactly where this project's worst bugs have lived.

---

## How to work here — lessons this project paid for

These are not style preferences. Each one is a bug that shipped.

### Verify the premise before following an instruction

`clear_old_versions` carried a docstring saying *"the day `Version` lands, the body is
three lines."* `Version` landed. Following that instruction would have written a general
audit-table pruner and **silently deleted every timeline entry older than 14 days** —
upstream prunes only saved-view churn.

Another said *"no CRM doctype sets a non-zero `permlevel`, checked across all 39 JSONs."*
False: `CRM Twilio Settings` sets it on three credential fields.

**A document is evidence, not proof.** When an instruction tells you to do something,
check that the reason it gives is still true.

### A claim you write will be trusted

A progress file said *"phase 3's `_resolved_fieldtype` plaster is deleted."* It was not —
it is still serving three endpoints. Someone reading that file believes it.

Before you write "X is done", check that X is done. Before you write "nothing uses Y",
grep for Y.

### Verify a test fails without the thing it tests

A test asserting that a disabled user could not re-enable themselves **passed with the
mechanism removed** — the account was rejected at authentication, so the test never
reached the code it claimed to cover. Green for a reason unrelated to its own subject.

For anything load-bearing: remove the mechanism, confirm the test fails, put it back. It
takes a minute and it is the difference between a test and a decoration.

### Record what you did not check

The most useful sections of this project's documents are the honest ones. A smoke test
that passed is recorded beside a list of what it did not cover. The phase-4 review found
**eight** security holes by pulling threads a progress file left dangling — that file was
useful *because* it admitted its own gaps.

A gap you record is a decision. A gap you omit is a bug someone finds later.

### Investigate before applying a pattern

Three doctypes that all reference Leads and Deals got three different answers: `ToDo`'s
route was withheld, `Email Account` got a rule, and `CRM Task` was deliberately left open.
Deciding by resemblance would have got two of the three wrong.

Two questions settle it, and they are cheaper than designing a rule:

1. **Does anything actually call this route?** No → withhold it; a route that does not
   exist is a smaller surface than one that is guarded.
2. **Do the `frappe.client.*` endpoints share the check?** They resolve through
   `_get_checked`, so if they do, a row rule covers every door — and withholding the route
   would fix nothing.

### Measure rather than assert

"Connections are being reused" was verified by watching the Postgres backend PID across
six calls: six distinct before, one after. "The flaky test is rare" was verified by running
the suite six times and counting.

If a claim can be measured in five minutes, measure it.

### Do not widen scope silently

While fixing a flaky test, a real production problem surfaced — a database connection
opened per permission check. It was **recorded first and applied as its own decision**,
not folded into the flake fix. Tuning changes that arrive as a side effect of something
else are how nobody remembers deciding.

If you find something outside your task, write it in the progress file and either raise it
or do it deliberately. Never both silently.

### Update the document in the same commit as the code

Every stale claim in this project was true when written. `AS_BUILT.md` went two phases
stale; a docstring promised a three-line fix that would have deleted the timeline; a
progress file said a plaster was removed while it was still serving three endpoints.

Nobody wrote those to mislead. They changed the code and left the sentence behind.

If your change makes a sentence somewhere false, fix the sentence in the same commit. It
is the cheapest thing in this list and it has cost the most.

### When you disagree with a review finding

Record the disagreement and your reasoning in the progress file. Never silently ignore it,
and never apply a fix you believe is wrong to make a reviewer happy.

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
