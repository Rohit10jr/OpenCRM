# backend_v2 — the CRM API rebuilt as a conventional Django project

**This file overrides the repository-root `CLAUDE.md` for all work in `backend_v2/`.** The
root file governs `backend/`, the Frappe-style port. Some of its rules still apply here and
are listed below under "Inherited"; the rest do not. **Start sessions for this work from
`backend_v2/`**, so this file is loaded from the first message.

**Paths are from the repository root.**

## What this is

`backend/` works, but it rebuilds Frappe's request layer on top of Django. `backend_v2/`
serves **the same API with the same JSON**, written the way a Django developer expects:
one app per domain, explicit URLs, ViewSets, serializers, permission classes. The
frontend does not change. Why, and every decision taken so far:
`backend_v2/docs/REBUILD_PLAN.md`.

## Read these first

| File | What it is |
|---|---|
| **`backend_v2/docs/REBUILD_PLAN.md`** | **Why, the decisions (Settled / Proposed / Open), the apps, the generic layer.** Read first |
| **`backend_v2/docs/API_CONTRACT.md`** | **Required before writing any endpoint.** What must be identical on the wire, with the old code that decides each rule |
| `backend_v2/docs/PORT_MAP.md` | Every old method path and doctype, its unit, the protections it carries, and its status |
| `backend_v2/docs/AS_BUILT.md` | What `backend_v2` actually contains, and the recipes for extending it |
| `backend_v2/specs/README.md` | The units, their order and dependencies, and their status |
| `backend_v2/specs/<UNIT>.md` | Your unit's spec |
| `backend_v2/docs/PARITY_EXCEPTIONS.md` | **Required before changing any behaviour.** The only place the parity rule may be broken |

## Precedence

- **About what exists:** the code in `backend_v2/`, then `AS_BUILT.md`, then the unit
  spec, then `REBUILD_PLAN.md`. A spec is a plan written before the code; it goes stale.
- **About what an endpoint must do:** the old backend in `backend/`, then the Frappe
  source (below). **Never invent semantics** — find the answer, or flag the question in
  your report.
- **About the rules:** this file, then the root `CLAUDE.md`.

## Sources

| Source | Use it for |
|---|---|
| `backend/` — **read-only** | The behaviour and the JSON to reproduce. `PORT_MAP.md`'s **Old source** column names the file for each method path |
| `docs/http/*.http` | The acceptance suite. Replayed against `backend_v2`, it is how parity is shown |
| Frappe CRM `D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm` (`main`) and the framework `D:\02_Personal\01_OpenSource\02_FrameWorks\frappe` (`version-15`, never `develop`) | Only when the old backend leaves a question open |
| `specs/SECURITY_MODEL.md`, `specs/UNROUTED_DOCTYPES.md`, `specs/VERSION_HISTORY.md`, `specs/KNOWN_ISSUES.md`, `docs/UPSTREAM_BUGS_PHASE_*.md`, `docs/FINDINGS.md` | Decisions the old backend already took, with their reasons. **Read them; do not re-decide them.** A change goes through `PARITY_EXCEPTIONS.md` |

## Hard rules

1. **Nothing outside `backend_v2/` is edited** unless the owner asks. `backend/`,
   `frontend/`, and the root `docs/` and `specs/` are read-only for this work, and
   nothing in `backend_v2/` imports from `backend/`.
2. **Same status, same body.** `API_CONTRACT.md` is the contract. A deliberate difference
   is an entry in `PARITY_EXCEPTIONS.md`, written and approved before the code.
3. **Nothing publishes an API by side effect.** Every route is written in an app's
   `urls.py`. The doctype map is literal code: `documents.doctypes` imports each app's
   `doctypes.py` by name. No decorator, import hook or registry adds a route.
4. **Allowlists are explicit**: serializer fields, filterable, orderable and searchable
   fields. A new column is invisible until it is listed. For parity, the first lists hold
   exactly what the old backend exposes.
5. **A doctype is not `built` until every protection in its `PORT_MAP.md` row is
   enforced and tested**: the row rule on the list *and* on the object, and each declared
   field across all five field-naming parameters (`fields`, `filters`, `or_filters`,
   `order_by`, `group_by`) as well as the response. Every door to a doctype —
   `/api/resource/`, `frappe.client.*`, `get_data`, `search_link`, the bulk actions — goes
   through its ViewSet's queryset and field policy.
6. **The user is passed, never looked up from ambient state.** No context variable or
   thread-local "current user" (REBUILD_PLAN P9).
7. **Preserve message text verbatim.** Copy each sentence from `backend/`, which copied
   it from upstream. It is user-facing copy, and the frontend parses some of it.
8. **Conventional placement.** Business logic in model methods or `services.py`, not in
   views. A signal only where a direct call cannot reach.

## Inherited from the root `CLAUDE.md`, unchanged

- **Keep shell commands short** — commit messages from a file (`git commit -F`), scripts
  in files, file contents through the Write and Edit tools, nothing over ~400 characters.
- **Work on a branch.** **One commit per meaningful change**, each saying what and why.
- **No two concurrent agents edit the same file.** Units split on app lines; the shared
  files FOUNDATION writes (`config/urls.py`, `INSTALLED_APPS`, `documents/doctypes.py`,
  the Celery schedule) are finished before any parallel work starts.
- **The reviewer policy**: tier 1 Codex on PowerShell 7, tier 2 on PowerShell 5.1, tier 3
  a fresh Claude subagent; never trust `codex exec`'s exit code; give a run 40 minutes.
  Codex's brief is the repository-root `AGENTS.md`, written for this rebuild, so it loads
  wherever Codex is run from. **A tier-3 subagent gets the same brief**: point it at that
  file.
- **Security is the standing exception.** When the old backend protects something, the
  protection is carried over even where upstream Frappe registers no hook.

## Not inherited

- "Read `docs/PORT_PLAN.md` and your phase spec before starting": those describe
  `backend/`. Read the files in the table above instead.
- "Registering a doctype publishes it" and the old guard tests by name: `backend_v2` has
  no registry, and FOUNDATION writes its own guard tests.
- Per-bug decisions about upstream Frappe: the old backend already took them, and
  `docs/UPSTREAM_BUGS_PHASE_*.md` records each. Changing one is a parity exception.

## Running beside the old backend

Ports, databases, Redis databases and `.env` locations: `REBUILD_PLAN.md` section 7.
Traps that have already cost time on this machine:

- **A background `runserver` outlives the shell that started it** on Windows, keeps the
  port, and keeps serving the code it started with. Before starting one, check
  `netstat -ano | findstr :8001` and end any stale process.
- **Never run two pytest invocations at once.** They share the test database, and the
  second one's teardown drops it under the first.
- **Never edit a module the dev server imported while a replay is running**: the reload
  restarts the server mid-file.
- **`docs/http/01_auth.http` and `09_users_and_invitations.http` both spend
  `change_password` attempts** (five per five minutes): never replay both in one window.
  **`99_lockout.http` locks logins from this machine for 60 seconds**; run it last.
- **Every `.http` file writes to the server's database.** It creates and deletes
  `ZZ`-prefixed rows, and toggles two FCRM Settings flags and restores them.
- **Never pass `--mark` to `backend/scripts/run_http.py`** when replaying against
  `backend_v2`. It writes into `docs/ROUTES.md`, which describes the old backend.
- **No Celery worker runs by default.** Anything that enqueues — bulk delete above ten
  documents, bulk update from twenty, an email sent without `now` — does nothing until
  one is started.

## Tests

In a session with the owner, **the owner runs pytest and the `.http` suite** unless they
ask you to. An unattended run's runbook states what its gate runs.

## Committing

**Stage by path, never `git add -A` or `git add .`** The owner keeps uncommitted work in
the tree — under `frontend/`, in `docs/TESTING_GUIDE.md`, and elsewhere — and it must never
be swept into a commit.
