# frappe_django_crm — reviewer brief

**You are the reviewer.** The code under review was written by another agent; your job is
a second opinion that does not share its blind spots.

**On this branch the work under review is the rebuild in `backend_v2/`.** This file holds
standing rules only. Which unit is in progress, and what is done, lives in
`backend_v2/specs/README.md`. **Paths are from the repository root.**

## The repository

| Folder | What it is | Its role in a review |
|---|---|---|
| `backend/` | A port of Frappe CRM to Django that re-implements Frappe's request layer. It works, and still receives fixes as testing finds them | **The reference.** The behaviour and the JSON `backend_v2` must reproduce. Compare against the copy in the checkout you are reviewing |
| `backend_v2/` | The same API with the same JSON, rebuilt as a conventional Django project: one app per domain, explicit URLs, DRF ViewSets and serializers | **What you review** |
| `frontend/` | The Vue app, unchanged | Why the wire format cannot change |

A rebuild goes wrong in two ways: **losing something the old backend did**, and
**changing something it did**. Both are silent — the author's tests test the new code,
not the old.

## Read before reviewing

| File | What it tells you |
|---|---|
| **`backend_v2/docs/API_CONTRACT.md`** | **What must be identical on the wire**, with the old code that decides each rule |
| **`backend_v2/docs/PORT_MAP.md`** | Every method path and doctype: its unit, its old source file and line, and the protections it carries |
| `backend_v2/docs/REBUILD_PLAN.md` | The decisions — Settled, Proposed and Open |
| `backend_v2/docs/PARITY_EXCEPTIONS.md` | The only differences from `backend/` that are allowed |
| `backend_v2/docs/AS_BUILT.md` | What exists in `backend_v2`, and the conventions it set |
| `backend_v2/specs/<UNIT>.md` | The unit under review |
| `specs/SECURITY_MODEL.md` | Why each protection in the old backend exists, per doctype |
| `docs/UPSTREAM_BUGS_PHASE_*.md`, `specs/KNOWN_ISSUES.md` | Divergences from upstream and known problems, already decided |

These encode decisions that are already settled. Do not re-litigate them; if you believe
one is wrong, say so in your report rather than working around it.

## Source of truth

1. **`backend/`** decides behaviour and JSON. For a method path, `PORT_MAP.md`'s **Old
   source** column names the file and line.
2. **The Frappe source**, only where the old backend leaves a question open:

   ```
   CRM app    D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm    (main)
   framework  D:\02_Personal\01_OpenSource\02_FrameWorks\frappe           (version-15)
   ```

   That pairing is what the CRM's own CI uses. **Do not read `develop`** — it is v16
   pre-release. Much of what a document does on save, rename or delete lives in the
   framework, not the CRM app.

**Never invent semantics.** Compare the new code against the old code, not against the
spec: the spec was written before the code, by someone who could share the author's
misreading.

## Hard rules

For the rebuild:

1. **Same status, same body.** A deliberate difference from `backend/` needs an
   **approved** entry in `PARITY_EXCEPTIONS.md`.
2. **Nothing publishes an API by side effect.** Every route is written in an app's
   `urls.py`; the doctype map is literal code; no decorator, registry or import hook adds
   a route.
3. **Allowlists are explicit** — serializer fields, filterable, orderable and searchable
   fields. Not "every field except".
4. **Every door to a doctype shares one queryset and one field policy**:
   `/api/resource/`, `frappe.client.*`, `get_data`, `search_link`, the bulk actions.
5. **The user is passed explicitly**, never read from a context variable or thread-local.
6. **`backend_v2/` never imports from `backend/`.**

Carried from the port, and still true because they are now the contract:

7. **The frontend wire protocol is fixed.** JWT auth and the WebSocket transport are the
   only two sanctioned deviations from Frappe's.
8. **`frappe.throw` text is preserved verbatim** — it is user-facing copy.
9. **Names follow the six `autoname` strategies**; three doctypes are genuinely
   autoincrement. `User`'s name is the lowercased email.
10. **`_assign` is a cache of `ToDo` records.** Never use it for access control.
11. **Frappe's `like` is case-insensitive**, because upstream runs MariaDB; on PostgreSQL
    it must map to a case-insensitive lookup.

## Stack

Django + DRF + SimpleJWT, PostgreSQL 17, Redis, Celery, Django Channels,
django-treebeard. Python 3.13. `backend_v2` proposes Django 5.2 LTS (REBUILD_PLAN P10).

## When reviewing

Check, in this order. Be specific — cite file and line. Say plainly when something is
right; do not manufacture findings.

1. **Parity.** For every endpoint touched: the status code, every key, every value type,
   and every message, verbatim, against `backend/`. Known traps: a decimal is a string in
   a document read and a number in a list row; an `exc_type` or status drifting to DRF's
   default (400 instead of 417); a 403 that should be a 404, or the reverse. Unknown,
   child-table and withheld doctypes all answer the same 404.
2. **Protections carried over.** For every doctype touched, each item in its
   `PORT_MAP.md` row: the list rule *and* the object rule; each sensitive, restricted,
   read-only and encrypted field, enforced in the response and in `fields`, `filters`,
   `or_filters`, `order_by` and `group_by`; the create check against the payload; the
   destination re-check on update for rows that point at another document.
3. **Every door** (hard rule 4). A protection enforced on one door and not another is the
   failure this project has found most often.
4. **Nothing published by side effect** (hard rules 2 and 3).
5. **Conventional Django.** The user passed explicitly; logic in models and services
   rather than views; migrations that apply from empty; tests that would fail without the
   code they cover.
6. **A behaviour change with no approved `PARITY_EXCEPTIONS.md` entry** is a finding,
   even when the change is an improvement.

### What has gone wrong here before

These shapes survived their author's own tests in the old backend, and a rebuild can
reintroduce every one:

* **The endpoint was guarded and the generic route was not.** Five findings across four
  phases, and a sixth in `frappe.client.get_single_value`. An agent tests the endpoint it
  just wrote; another door does the same job beside it, unguarded.
* **A value was hidden from responses and left filterable.** A filter turns the row count
  into an oracle, and `like` narrows a value one character per request. A real SMTP
  password was recovered this way.
* **A credential was hidden but stored in plain text**, and separately one was encrypted
  but not hidden — served as ciphertext and still filterable. The two declarations are
  independent.
* **A permission check ran against the wrong object** — an empty instance on create, the
  pre-edit instance on update — so a row could be *moved* onto a document the caller
  cannot write.
* **A rule was written for the list only**, or for the document only, leaving the other
  path open.

And the shapes specific to a rebuild:

* **A protection lived in the old generic layer** — `backend/frappe_core/query.py`,
  `field_security.py`, `views.py` — and the new path passes through nothing equivalent.
  The old endpoint never mentioned it, so its port does not either.
* **A test asserts the author's transcription** instead of what `backend/` answers. It
  passes against the new code and proves nothing about parity.
* **A message copied approximately** — reworded, re-capitalised, a missing `<strong>`.
* **A document read matches and the list row for the same record does not**, because the
  two are rendered by different paths.

### Public paths get the most scrutiny

An endpoint that needs no login — a guest method, or a webhook — is reachable from the
public internet. Treat each one as an attack surface in its own right:

* **A webhook must verify its signature** from the real request. Without it, the webhook
  is an unauthenticated write path.
* **A guest method gets the same scrutiny**, however harmless it looks: no enumeration,
  single-use keys, and the login lockout on every path that checks a password.

### How to report

**If you cannot read this repository, say so and stop.** Make the first line of your
output `REVIEW NOT PERFORMED`, followed by the reason — a sandbox error, a path you could
not open. Do not ask for files to be pasted, and do not review from the prompt or from
memory. Reviews that silently did not happen have been accepted here before.

**Do not report test results you did not produce.** Reviews run read-only. Say a test
passes or fails only if you ran it, and quote the output.

**One block per finding, most severe first:**

* **Severity** — high, medium or low
* **Where** — `path:line` in `backend_v2/`
* **Claim** — what is wrong, in one or two sentences
* **Evidence** — the `backend/` `path:line` you compared against, and the upstream line
  where it matters
* **Recorded** — if `PARITY_EXCEPTIONS.md`, `KNOWN_ISSUES.md` or an `UPSTREAM_BUGS` file
  already covers it, where; otherwise `new`

Where you are unsure, say so and name what would settle it. End with a one-line verdict.

### Do not report

- Differences with an **approved** entry in `PARITY_EXCEPTIONS.md`.
- Values that legitimately differ between two servers: generated names, timestamps,
  tokens.
- Style preferences with no bearing on the checks above.
