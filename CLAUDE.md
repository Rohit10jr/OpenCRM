# frappe_django_crm — the rebuild

Frappe CRM, already ported to Django, rebuilt as a conventional **Django REST API in
`backend_v2/`**. This branch (`django-rebuild`) is for that work. Paths are from the
repository root.

| Folder | What it is | For this work |
|---|---|---|
| `backend_v2/` | The same CRM as a REST API under `/api/v1/`: one app per area, ViewSets, routers, serializers. Every new URL answers with exactly the JSON of the old URL it replaces | **What we build** |
| `backend/` | The first Django port. It copies Frappe's request layer (RPC-style URLs, a doctype registry, generic routes), and it works | **The reference**, read-only here. The owner fixes it on its own branches; fixes reach this branch through `main` |
| `frontend/` | The Vue app | Not changed in the rebuild. It moves to `backend_v2` after the whole rebuild is done, by changing only URLs and HTTP methods (REBUILD_PLAN S4, S22) |

**The order of work.** First parity: `backend_v2` answers exactly like `backend/`. Then
`backend_v2/` is renamed `backend/` (S10). The upstream sync (the port's base was 1,083
commits behind upstream `main` on 3 Nov 2026) and translations are separate later stages, not part of parity
(`specs/KNOWN_ISSUES.md` §11; owner, 12 Nov 2026).

**Before the rebuild merges into `main`, split this file and `AGENTS.md`** (owner, 12 Nov
2026). They are written for the owner's machine and workflow — local paths, Codex builder
mode, the long-run rule — which does not belong in a public repository. The tracked files
become short and general: the project, the stack, how to run the tests, the contract
rules. Everything personal moves to gitignored local files: `CLAUDE.local.md` for Claude,
and for Codex whatever local override the installed codex-cli supports (check it then).

## What to read, and when

Nothing needs reading for a question, a docs edit or a git task. Before a change, read
the rows that match it. What these files record is settled; if you think a decision is
wrong, say so instead of working around it.

| Before you… | Read |
|---|---|
| start a unit of work | **`backend_v2/docs/REBUILD_PLAN.md`** (why, and decisions S1–S25), `backend_v2/specs/README.md` (units, order, status), then your `backend_v2/specs/<UNIT>.md` |
| write or change any route | **`backend_v2/docs/API_CONTRACT.md`** — required — and the endpoint's row in `backend_v2/docs/PORT_MAP.md` |
| make anything answer differently from `backend/` | **`backend_v2/docs/PARITY_EXCEPTIONS.md`** — required |
| extend what is already built | `backend_v2/docs/AS_BUILT.md` §2 (recipes) and §4 (invariants) |
| start a server or run tests | `backend_v2/docs/AS_BUILT.md` §3 (traps), and REBUILD_PLAN §7 for ports, databases and `.env` |
| port a doctype's permissions or hidden fields | its `PORT_MAP.md` row, and `specs/SECURITY_MODEL.md` |
| port `clear_old_versions` or change history | `specs/VERSION_HISTORY.md` — its name invites a change that deletes the timeline |
| port something that looks odd or broken | `specs/KNOWN_ISSUES.md`, `UPSTREAM_BUGS.md`, `docs/FINDINGS.md`: the old backend may have decided it already |
| need the old backend's internals | `specs/AS_BUILT.md` (the old one, at the root) |

## Which source wins

- **What a route must do:** the old backend in `backend/` first. `PORT_MAP.md`'s **Old
  source** column gives each old endpoint's file and line. Frappe's source only where the
  old backend leaves a question open (S13).
- **What exists:** the code in `backend_v2/`, then `backend_v2/docs/AS_BUILT.md`, then the
  unit spec, then `REBUILD_PLAN.md`. A spec is written before the code and goes stale: if
  a document describes the code differently, correct the document in the same commit —
  unless the code answers differently from `backend/`. Then the code is the bug.
- **Decisions the old backend already took** — `specs/SECURITY_MODEL.md`,
  `specs/UNROUTED_DOCTYPES.md`, `specs/KNOWN_ISSUES.md`, `UPSTREAM_BUGS.md` (83 upstream
  bugs, and whether each was copied or fixed), `docs/FINDINGS.md`. Read them; do not
  decide them again. A change goes through `PARITY_EXCEPTIONS.md`.
- **The acceptance suite** will be `backend_v2/http/`: a REST copy of `docs/http/`,
  generated from the route map (S9). The old files stay as they are.

## Upstream source: which copy, and when

Only when `backend/` leaves a question open.

| Copy | Path | Read |
|---|---|---|
| **CRM, the port's base** | `D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm` | the working tree (tag `port-base`, upstream v1.82.0). Never switch its branch or pull |
| **Framework** | `D:\02_Personal\01_OpenSource\02_FrameWorks\frappe` | `git show version-15:<path>` only; the checkout is on `develop` |

**Do not read `develop`** in either repository: it is v16 pre-release (`docs/FINDINGS.md`
90). **Never invent semantics** — match the source, or write the open question in your
report. Much of what happens on save, rename or delete is in the framework.

## Rules

**Working here**

1. **Work on `django-rebuild`** or a branch from it, never on `main`.
2. **`main` is merged into `django-rebuild` when the owner asks.** That is how the owner's
   fixes to `backend/` reach the reference here; until then this worktree's `backend/` may
   lag `main`. A brief names the `main` commit its reference was read at.
3. **One commit per meaningful change.** One run once made 25,000-line commits that could
   not be reviewed or reverted. Each commit stands alone, with a message saying what
   changed and **why**.
4. **Stage by path** — never `git add -A` or `git add .`. The owner keeps uncommitted work
   in the tree, and `frontend/auto-imports.d.ts` is never committed.
5. **No two agents edit the same file at the same time.** Split work by app.

**Building `backend_v2`**

6. **Nothing outside `backend_v2/` is edited** unless the owner asks. `backend/`,
   `frontend/`, and the root `docs/` and `specs/` are read-only, and `backend_v2/` never
   imports from `backend/`.
7. **New URL, same answer.** Every route is REST, under `/api/v1/`, and answers exactly
   like the old URL: same status code, same JSON (`API_CONTRACT.md`). No dotted RPC URL,
   no generic `/api/resource/` route. **If something should answer differently:** add a
   `proposed` entry under **Register** in `PARITY_EXCEPTIONS.md`, keep building the old
   behaviour, tell the owner, and change the code only once the entry is `approved`. This
   replaces the old port's `Upstream:` / `Port only:` comments: every difference lives in
   that register.
8. **Same inputs.** Only the resource and the document name move into the URL, and the
   HTTP method says what happens. Any other change is a reshaped input and goes in the
   route map.
9. **No hidden routes.** Every URL is written out in an app's `urls.py` and listed in the
   route map. No decorator, registry or import trick; nothing routed by doctype name.
10. **Fields are opt-in.** Each resource lists the fields that may be shown, filtered,
   sorted and searched; a new column stays invisible until added. The first lists hold
   exactly what `backend/` exposes.
11. **Every way in has the same lock.** A doctype is not `built` until every protection in
   its `PORT_MAP.md` row is enforced and tested — the permission rule on the list **and**
   single records, and each hidden, manager-only, read-only or encrypted field in
   responses and in `fields`, `filters`, `or_filters`, `order_by` and `group_by` — on its
   list, record, action, list-view, search and bulk routes alike.
12. **Pass the user along** as an argument (`create_lead(data, user=...)`), never from a
   hidden global (S16).
13. **Normal Django placement.** Business logic in models or `services.py`, not views. A
   signal only where a direct call cannot reach.
14. **Copy error messages exactly**, word for word from `backend/`. Users see them and the
   frontend reads some.
15. **Security is the exception to "match the original".** Frappe protects most doctypes
   with a role permission table, which neither Django backend has, so "Frappe has no
   permission hook here" means "Frappe had protection we lack". `backend/` has since added
   those protections: **carry them over even where the Frappe source shows nothing.**
   Five security bugs came from this misreading; `specs/SECURITY_MODEL.md` has the detail.

## Tests

Codex runs the test files it touched, singly (`AGENTS.md` "When building"). Otherwise
Claude runs no tests unasked. **Before a pull request, ask the owner** whether they run
the full suite and the `.http` suite or Claude runs them; when Claude does, "Long runs"
below applies.

**Old API tests are ported, not rewritten** (S14, changed 12 Nov 2026): about 50 files in
`backend/tests/` call the API, and their expected answers come from the old backend, so a
misreading by the author cannot creep into both code and test. In review, a new test where
an old one exists is a finding, and so is a changed expectation without an approved
exception.

## Long runs: the test suite, Codex and subagents

When Claude runs the full suite, a Codex build or review, or a long subagent task, it runs
in the background with output to a log, and Claude reads the log. (Owner, 12 Nov 2026.)

* **Never stop a run abruptly**, and never on time alone.
* **Every 15 minutes, look and decide.** Read the log so far, tell the owner where it is,
  and judge whether it is still making progress.
* **45 minutes is the upper limit for that routine.** Past it, decide from the result and
  the evidence: what the run has done, whether it is still progressing, what stopping
  would lose. Stop only a run that is stuck or has wandered, and say why. A stuck Codex
  run is re-run once with a narrower prompt before escalating a tier.
* **Do not report a result the log does not contain.**

## Keep shell commands short

The rules are in the global `~/.claude/CLAUDE.md` ("Shell"). Here: commit messages in
`.git/COMMIT_MSG` (or `tasks/COMMIT_MSG` after a Codex build) and `git commit -F`;
scripts in the session scratchpad; PR bodies through `--body-file`.

## Stack

Django 5.2 LTS (S17) + DRF + SimpleJWT, PostgreSQL 17, Redis, Celery, Django Channels,
django-treebeard. Python 3.13. `backend/` runs on port 8000 and `backend_v2/` on 8001,
each with its own database, Redis databases, `.env` and virtualenv (S18, REBUILD_PLAN §7).

---

# Codex (see the codex skill)

**Builder mode (owner, 15 Oct 2026; confirmed for the rebuild 12 Nov 2026):** Codex
writes `backend_v2` from briefs in `tasks/`; Claude plans, reviews and commits, and does
not write feature code. Codex's side is `AGENTS.md` "When building".

- A brief names the unit and its spec, the `PORT_MAP.md` rows, the old backend's files
  and lines, the decisions already taken, the one change to make, and the tests.
- Run builds with `network_access=true`, so tests can reach PostgreSQL. Codex leaves its
  commit message in `tasks/COMMIT_MSG`.
- Review the diff against `backend/`, not against the spec: the spec and the author can
  share a misunderstanding. For a tier-3 review, point the subagent at `backend/` too.
