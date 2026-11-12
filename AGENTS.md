# frappe_django_crm — agent brief

Porting **Frappe CRM** (Python/Frappe framework) to **Django + DRF**, keeping the
existing Vue frontend. Django + DRF + SimpleJWT, PostgreSQL 17, Redis, Celery, Django
Channels, django-treebeard. Python 3.13.

## What to read, and when

Your brief names what the task needs. Beyond it, read only the rows that match your
change. What these files record is settled; if you think a decision is wrong, say so in
your report rather than working around it. Where `specs/AS_BUILT.md` and a phase spec
disagree, `AS_BUILT.md` wins: the specs were written before the code.

| Before you… | Read |
|---|---|
| change any backend behaviour | the section of **`specs/AS_BUILT.md`** for that area |
| touch a permission rule or what fields a user can see | **`specs/SECURITY_MODEL.md`** — required |
| add or register a doctype | the doctype checklist in `specs/AS_BUILT.md`, and `specs/UNROUTED_DOCTYPES.md` |
| change the frontend, or what it sends and receives | `PORT_PLAN.md` §3 and `frontend/JWT_PATCH.md` |
| diagnose something that looks broken | `specs/KNOWN_ISSUES.md`, then `UPSTREAM_BUGS.md` |
| change what a phase built, when `AS_BUILT.md` does not say why | that phase's spec, through `docs/history/SPECS_README.md` |
| work on an upstream bug | its entry in `UPSTREAM_BUGS.md` |

## Upstream source: which copy, and when

| Copy | Path | Read | Use it to |
|---|---|---|---|
| **CRM, the port's base** | `D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm` | the working tree (tag `port-base`) | see what the port should do |
| **Framework** | `D:\02_Personal\01_OpenSource\02_FrameWorks\frappe` | `git show version-15:<path>` only | explain what the CRM code does not: save, rename, delete, permissions, Data Import |
| **CRM, the owner's fork** | `D:\02_Personal\01_OpenSource\03_Applications\CRM\frappe_crm` | `upstream/develop` | upstream bug work only, when a brief says so |

* **The port's base is frozen.** `port-base` (`6583bfcdc`) is upstream v1.82.0
  (`48cb3ccce`, 26 Aug 2026) plus the owner's Docker docs, which change no CRM code.
  Never switch its branch or pull.
* **The framework checkout is on `develop`.** Never read its working tree and never
  `git checkout` there: a `develop` data file and permission row got into this port that
  way (`docs/FINDINGS.md` 90). `develop` is v16 pre-release; the fork is the only place
  it is right, and port code is never copied from it.
* **Never invent semantics.** Much of what a document does on save, rename or delete is
  in the framework, not the CRM app. If the CRM source cannot explain a behaviour, look
  there before concluding the port is right or wrong.

## Hard rules

1. The frontend wire protocol (`PORT_PLAN.md` §3) is a fixed external contract. JWT
   auth, the WebSocket transport and the boot-values call (`frontend/JWT_PATCH.md`) are
   the only three sanctioned deviations.
2. String primary keys per the six `autoname` strategies in
   `docs/history/PHASE_0_FOUNDATION.md` §2 — three doctypes are genuinely autoincrement.
3. `_assign` is a denormalised cache of `ToDo` records. Never use it for access control.
4. Preserve `frappe.throw` and `msgprint` text verbatim — it is user-facing copy.
5. Postgres, not MariaDB: map Frappe's `like` to `ilike`/`icontains`.
6. **Registering a doctype publishes it** through `/api/resource/`: every field readable,
   filterable and writable unless a rule says otherwise. Upstream leans on DocType role
   permissions, which this port does not model, so "upstream registers no hook" means
   "upstream had a layer we lack". A new doctype needs a permission rule
   (`crm_app/permissions/`), entries in `tests/test_permissions.py` and
   `tests/test_route_surface.py`, a row in `specs/SECURITY_MODEL.md`, and `docs/ROUTES.md`
   regenerated with `backend/scripts/generate_route_inventory.py`; `specs/AS_BUILT.md`
   has the full list and the credential checklist.
7. **Keep every difference from upstream visible**, in any file copied from upstream (all
   of `frontend/`, and backend code porting a named upstream function): the owner's later
   rewrite needs the full list. Never delete upstream code you replace — keep it in a
   comment prefixed `Upstream:`, with a line on why and the finding or `UPSTREAM_BUGS.md`
   entry. Mark code upstream lacks `Port only:`. Record frontend differences in
   `frontend/JWT_PATCH.md` ("Other frontend patches") and behaviour differences in the
   finding and `UPSTREAM_BUGS.md`.

## When building

A build task is a brief in `tasks/` (git-ignored): the branch, the upstream files, the
decisions already taken, the tests that must pass. **Its decisions are settled with the
owner: build them, and if you think one is wrong, say so rather than building something
else.** Claude reviews and commits; the owner merges.

* **One brief is one commit.** Build exactly what it asks, touching only the files the
  change needs, and leave the changes in the working tree. Your sandbox cannot write
  `.git`: never run `git add`, `git commit` or `git push`.
* **Write the commit message** to `tasks/COMMIT_MSG`, overwriting it. The subject says what
  changed; the body says **why**, cites the upstream `path:line` it follows, and lists
  the files the commit should contain. No attribution line.
* **Tests:** in `backend/`, run single files with `.venv/Scripts/python.exe -m pytest -q
  -p no:cacheprovider tests/<file>.py` — the files you touched and their neighbours. Not
  the full suite unless the brief asks, never the http suite or Playwright, never a dev
  server. A test must not reach the network: stub the outbound call, as
  `tests/test_exchange_rate.py` does.
* **A migration that writes data uses the historical model** (`apps.get_model`), so a
  later column cannot break a fresh `migrate`.
* **Records:** the finding the brief names in `docs/FINDINGS.md` (index row and entry),
  `UPSTREAM_BUGS.md` for any upstream defect you reproduce or diverge from, and
  `specs/KNOWN_ISSUES.md` for anything left unfinished.
* Leave `frontend/auto-imports.d.ts` alone; it is never committed.
* **Never** print or edit `.env` or `docs/http/.env`, send anything to an outside
  service, open a pull request, delete branches, or change files outside this repository.

**Your report:** the files changed or added; that `tasks/COMMIT_MSG` is written; the test
commands you ran with their last lines of output, quoted; every divergence from upstream
and why; and anything in the brief you did not do, with the reason.

## When reviewing

A review is a second opinion on code another agent wrote. Prioritise correctness against
the Frappe source, then permissions and security, then the spec. Cite file and line. Say
plainly when something is right; do not manufacture findings.

**What has gone wrong here before** — shapes that survived the author's own tests:

* **The endpoint was gated and the generic route was not** (five findings in four
  phases): `/api/resource/<doctype>` does the same job beside it, unguarded.
* **A value hidden from responses was left filterable.** A filter turns the row count into
  an oracle, and `like` narrows a value one character per request; a real SMTP password
  was recovered this way.
* **Hiding and encrypting a credential are independent.** One was hidden but stored in
  plain text; another encrypted but not hidden, so served as ciphertext and filterable.
* **A permission check ran against the wrong object:** an empty instance on create, the
  pre-edit instance on update, so a row could be moved onto a document the caller cannot
  write.
* **A rule covered one path only.** `permission_query_conditions` guards the list,
  `has_permission` the document; set both.
* **Public paths** — an `allow_guest` method or a webhook — are reachable from the
  internet. A webhook must verify its signature; a guest method gets the same scrutiny,
  however harmless it looks.

**How to report:**

* **If you cannot read this repository, say so and stop.** Make the first line
  `REVIEW NOT PERFORMED` and the reason. Do not ask for files to be pasted or review from
  memory: reviews that silently did not happen have been accepted here before.
* **Report only test results you produced**, with the output quoted. Reviews run
  read-only.
* **One block per finding, most severe first:** Severity (high, medium, low); Where
  (`path:line`); Claim (one or two sentences); Evidence (the upstream `path:line`
  compared against); Recorded (where the repo already writes it up, or `new`).
* Where unsure, say so and name what would settle it. End with a one-line verdict.
