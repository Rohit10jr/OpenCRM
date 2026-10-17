# frappe_django_crm — agent brief

Porting **Frappe CRM** (Python/Frappe framework) to **Django + DRF**, keeping the
existing Vue frontend.

This file holds standing rules only. What has shipped lives in `specs/AS_BUILT.md`, and
the phase-by-phase record in `docs/history/SPECS_README.md` — read those rather than
trusting anything dated in here.

## Read before working

| File | What it is |
|---|---|
| **`specs/AS_BUILT.md`** | **What already exists. Read this first.** Where it and a phase spec disagree, it wins — the specs were written before the code. Its security section lists the mechanisms a doctype can use |
| `PORT_PLAN.md` | Source inventory, frontend contract, settled architecture decisions |
| `specs/SECURITY_MODEL.md` | Per-doctype comparison with upstream, and the 11 places we deliberately differ |
| `docs/history/SPECS_README.md` | Index of the per-phase specs, moved to history on 7 Oct 2026 |
| `docs/history/PHASE_<N>_*.md` | The spec of the phase that built what you are touching; the decisions in them still apply |

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
   auth, the WebSocket transport and the boot-values call (`frontend/JWT_PATCH.md`) are
   the only three sanctioned deviations.
2. String primary keys per the six `autoname` strategies in
   `docs/history/PHASE_0_FOUNDATION.md` §2 — three doctypes are genuinely autoincrement.
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

## When building

Some tasks ask you to write the code rather than review it. Claude plans the task and
reviews what you build; the owner merges. A build task comes as a brief, one Markdown
file in `tasks/` (git-ignored), naming the branch, the upstream files, the decisions
already taken and the tests that must pass. **The brief's decisions are settled with the
owner: build them, and if you think one is wrong, say so in your report rather than
building something else.**

### Reading upstream

**The framework checkout is on `develop`, not `version-15`.** Read every framework file
with `git show version-15:<path>` from `D:\02_Personal\01_OpenSource\02_FrameWorks\frappe`,
never the working tree, and never `git checkout` there. Reading the working tree is how
a `develop` data file, and a permission row only `develop` has, got into this port
(`docs/FINDINGS.md` 90). The CRM app is read from its working tree (`main`).

### Branch and commits: you write, Claude commits

Your sandbox (`workspace-write`) cannot write `.git`, so **you do not run `git add` or
`git commit`**, and never push. Claude checks out the branch before you start, and
commits after reviewing.

* **One brief is one commit.** Build exactly what the brief asks, with the tests that
  cover it green, and leave the changes in the working tree. A feature is several briefs.
* **Write the commit message** to `tasks/COMMIT_MSG` (overwrite it each time). The
  subject says what changed; the body says **why**, citing the upstream `path:line` it
  follows, and lists the files the commit should contain. End it with:

  ```
  Co-Authored-By: Codex <noreply@openai.com>
  ```

* Leave `frontend/auto-imports.d.ts` alone; Vite rewrites it, and it is never committed.
* Touch only the files the brief's change needs, so the commit stays one change.

### Tests

* Run single test files, in `backend/`: `.venv/Scripts/python.exe -m pytest -q
  -p no:cacheprovider tests/<file>.py`. Run the files the change touches and their
  neighbours before each commit.
* **The full suite is not yours to run** unless the brief asks: it takes 10 to 20 minutes
  on a 4 GB machine. **Never run the http suite or Playwright**; they need live servers
  and the demo passwords.
* One heavy process at a time. Do not start a dev server.
* A test must not reach the network. Stub the one outbound call, as
  `tests/test_exchange_rate.py` does.

### The checklists that bite

* **Registering a doctype publishes it** (hard rule 6). A new doctype needs a permission
  rule (`crm_app/permissions/`), an entry in `tests/test_permissions.py` and
  `tests/test_route_surface.py`, a row in `specs/SECURITY_MODEL.md`, and
  `docs/ROUTES.md` regenerated with `backend/scripts/generate_route_inventory.py`.
  `specs/AS_BUILT.md` has the full list, and the credential checklist.
* **A migration that writes data uses the historical model** (`apps.get_model`), not
  the live one, so a later column cannot break a fresh `migrate`.
* **Upstream's user-facing text is copied verbatim**, `frappe.throw` and `msgprint`
  messages included (hard rule 4).
* **Records.** Update the finding the brief names in `docs/FINDINGS.md` (its index row
  and its entry), `UPSTREAM_BUGS.md` for any upstream defect you reproduce or diverge
  from, and `specs/KNOWN_ISSUES.md` for anything you leave unfinished.

### Keep the difference from upstream visible

This port is not the final version: the owner plans a later, proper Django rewrite, and
will need to know exactly where the port differs from upstream. So, in any file copied
from upstream (the whole `frontend/`, and backend code that ports a named upstream
function):

* **Never delete upstream code you replace.** Keep it in a comment, prefixed
  `Upstream:`, beside the new code, with one or two lines saying why it changed and
  citing the finding or `UPSTREAM_BUGS.md` entry.
* **Mark code that upstream does not have** with `Port only:` and the same reference.
* **Record every frontend difference** in `frontend/JWT_PATCH.md`, "Other frontend
  patches", and every behaviour difference in the finding and `UPSTREAM_BUGS.md`.

### Never

* Print or edit `.env` or `docs/http/.env`; they hold real credentials.
* Send anything to an outside service, open a pull request, or delete branches.
* Change files outside this repository.

### Your report

End with: the files you changed or added; that `tasks/COMMIT_MSG` is written; the test
commands you ran and their last lines of output, quoted; every place you diverged from
upstream and why; and anything in the brief you did not do, with the reason.

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
