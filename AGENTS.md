# frappe_django_crm — agent brief

Porting **Frappe CRM** (Python/Frappe framework) to **Django + DRF**, keeping the
existing Vue frontend.

This file holds standing rules only. Which phase the port is in, and what has shipped,
lives in `specs/README.md` — read it there rather than trusting anything dated in here.

## Read before working

| File | What it is |
|---|---|
| **`specs/AS_BUILT.md`** | **What already exists. Read this first.** Where it and a phase spec disagree, it wins — the specs were written before the code. Its security section lists the mechanisms a doctype can use |
| `PORT_PLAN.md` | Source inventory, frontend contract, settled architecture decisions |
| `specs/SECURITY_MODEL.md` | Per-doctype comparison with upstream, and the 11 places we deliberately differ |
| `specs/README.md` | Index of the phase specs, and the current status of each |
| `specs/PHASE_<N>_*.md` | The spec for the phase you were asked about |

These encode decisions that are already settled. Do not re-litigate them; if you
believe one is wrong, say so in your report rather than working around it.

## Source of truth

Two repositories, both readable:

```
CRM app    D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm    (main)
framework  D:\02_Personal\01_OpenSource\02_FrameWorks\frappe           (version-15)
```

That pairing is what the CRM's own CI uses. **Do not read `develop`** — it is v16
pre-release, and a finding checked against it can be wrong for the version this port
follows.

Read them whenever behaviour is unclear. **Never invent semantics.** Much of what a
document does on save, rename or delete is not in the CRM app at all but in the
framework — if the CRM source cannot explain a behaviour, look there before concluding
the port is right or wrong.

## Hard rules

1. The frontend wire protocol (`PORT_PLAN.md` §3) is a fixed external contract. JWT
   auth and the WebSocket transport are the only two sanctioned deviations.
2. String primary keys per the six `autoname` strategies in
   `specs/PHASE_0_FOUNDATION.md` §2 — three doctypes are genuinely autoincrement.
3. `_assign` is a denormalised cache of `ToDo` records. Never use it for access control.
4. Preserve `frappe.throw` message text verbatim — it is user-facing copy.
5. Postgres, not MariaDB: map Frappe's `like` to `ilike`/`icontains`.
6. **Registering a doctype publishes it.** Every field is readable, filterable and
   writable through the generic `/api/resource/` route unless a rule says otherwise.
   Upstream leans on DocType role permissions, which this port does not model — so
   "upstream registers no hook" means "upstream had a layer we lack", not "no protection
   needed".

## Stack

Django + DRF + SimpleJWT, PostgreSQL 17, Redis, Celery, Django Channels,
django-treebeard. Python 3.13.

## When reviewing

Reviews here are a second opinion on code another agent wrote. Prioritise, in order:
correctness against the Frappe source, permission/security correctness, and adherence to
the spec. Be specific — cite file and line. Say plainly when something is right; do not
manufacture findings.

### What has actually gone wrong here before

Worth knowing, because these are the shapes that survived the author's own tests:

* **The endpoint was gated and the generic route was not.** Five findings across four
  phases. An agent tests the endpoint it just wrote; `/api/resource/<doctype>` does the
  same job beside it, unguarded.
* **A value was hidden from responses and left filterable.** Hiding output is not
  protection — a filter turns the row count into an oracle, and `like` narrows a value one
  character per request. A real SMTP password was recovered this way.
* **A credential was hidden from the wire and stored in plain text**, and separately, one
  was encrypted but not hidden — served as ciphertext and still filterable. The two
  declarations are independent.
* **A permission check ran against the wrong object** — an empty instance on create, and
  the pre-edit instance on update, so a row could be *moved* onto a document the caller
  cannot write.
* **A rule was written against the read path only.** `permission_query_conditions` guards
  the list; `has_permission` guards the document. Setting one and not the other leaves the
  other route open.

### Public paths get the most scrutiny

An endpoint that needs no login — an `allow_guest` method, or a webhook — is reachable
from the public internet. Treat each one as an attack surface in its own right:

* **A webhook must verify its signature.** Without it, the webhook is an unauthenticated
  write path. This is a requirement, not a nicety.
* **A guest method gets the same scrutiny**, however harmless it looks.

### How to report

**If you cannot read this repository, say so and stop.** Make the first line of your
output `REVIEW NOT PERFORMED`, followed by the reason — a sandbox error, a path you could
not open. Do not ask for files to be pasted, and do not review from the prompt or from
memory. Reviews that silently did not happen have been accepted here before.

**Do not report test results you did not produce.** Reviews run read-only. Say a test
passes or fails only if you ran it, and quote the output.

**One block per finding, most severe first:**

* **Severity** — high, medium or low
* **Where** — `path:line` in this repo
* **Claim** — what is wrong, in one or two sentences
* **Evidence** — the upstream `path:line` you compared against, CRM app or framework
* **Recorded** — if the repo's docs already write this up, where; otherwise `new`

Where you are unsure, say so and name what would settle it. End with a one-line verdict.
