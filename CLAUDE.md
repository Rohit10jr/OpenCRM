# frappe_django_crm

Frappe CRM moved from the Frappe framework to **Django + DRF**, keeping the Vue frontend.
**Paths are from the repository root.** This is the one `CLAUDE.md` for the whole
repository; Codex's reviewer brief is `AGENTS.md`.

## What is in this repository

| Folder | What it is |
|---|---|
| `backend/` | **The first Django version.** It copies Frappe's way of handling requests (RPC-style URLs such as `/api/method/crm.api.doc.get_data`, a doctype registry, generic routes). It works, and the owner still fixes it as testing finds problems |
| `backend_v2/` | **The rebuild — the main work on this branch.** The same CRM as a normal Django **REST API under `/api/v1/`**. Every new URL answers with exactly the same JSON as the old URL it replaces |
| `frontend/` | The Vue app. Not changed during the rebuild. Later it will switch to `backend_v2` by changing only which URL and HTTP method each call uses |

**Find out which folder your task is in, then follow the section for it** — "Working on
`backend_v2/`" or "Working on `backend/`" below. The rules in "Every task" apply to both.

---

## Every task

### Rules

1. **Work on a branch, never directly on `main`.**
2. **One commit per meaningful change, never one per phase.** An earlier run was told
   "one commit per phase" and produced single commits of 25,000 lines — impossible to
   review, bisect or revert. Commit when a coherent piece of work is done and the tests
   pass; a dozen commits in one piece of work is normal. Each must stand alone, with a
   message saying what changed and **why**.
3. **Stage by path — never `git add -A` or `git add .`** The owner keeps uncommitted work
   in the tree (under `frontend/`, in `docs/TESTING_GUIDE.md` and elsewhere), and it must
   never be swept into a commit.
4. **No two agents working at the same time edit the same file.** Split work along app or
   module lines.
5. **Copy error messages exactly.** A `frappe.throw` message is text users see — copy it
   word for word from its source. The frontend reads some of them.
6. **Never invent semantics — never guess how something should behave.** Find the answer
   in the source (each section below says where to look), or write the open question in
   your report.
7. **Security is the standing exception to "match the original".** Upstream Frappe
   protects most doctypes with DocType role permissions, a layer these backends do not
   have. So "upstream registers no permission hook" means "upstream had protection we do
   not" — not "no protection needed". Five findings came from reading it the wrong way.
   `specs/SECURITY_MODEL.md` has the detail per doctype.
8. **The owner runs the tests.** In a session with the owner, do not run pytest or the
   `.http` suite unless asked. An unattended run's runbook says what its gate runs.

### The Frappe source

When you do need upstream Frappe, both repositories are readable:

```
CRM app    D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm    (main)
framework  D:\02_Personal\01_OpenSource\02_FrameWorks\frappe           (version-15)
```

These two belong together: the Frappe CRM project's own automated tests run CRM `main`
against framework `version-15`. **Do not read `develop`** — it is the unreleased version 16
and behaves differently. A lot of what happens when a document is saved, renamed or
deleted lives in the framework, not the CRM app. If something looks impossible, suspect a
framework mechanism you have not found before suspecting your own code.

### Keep shell commands short

**A long command cannot be security-scanned, so it goes to a human for approval — which
stalls an unattended run indefinitely.** This has already cost a run. It is not about what
the command does; the harness refuses to approve text it could not read, so no permission
rule can pre-approve it. The only fix is to keep commands short.

Long *content* belongs in a file. The command that uses it stays tiny.

1. **Commit from a file, never inline.** Write the message with the Write tool, then
   `git commit -F .git/COMMIT_MSG` — about 35 characters, however long the message. Do
   **not** use `git commit -m "$(cat <<'EOF' … EOF)"`: that puts the whole message, often
   2,000 characters, into the command.
2. **Never inline a script.** Write `scratch/patch.py`, then run
   `python scratch/patch.py`. No `python - <<'PY' … PY`.
3. **Never write file contents through the shell.** No `cat > file <<'EOF'`. Use the Write
   and Edit tools — nothing gets scanned.
4. **Keep any single command under ~400 characters.** A backstop for what 1–3 miss. If a
   command is getting long, part of it belongs in a file.

Chained commands count as one command. Prefer several short calls over one long chain.

### Traps on this machine

Each of these has already cost time:

- **A background `runserver` outlives the shell that started it** on Windows, keeps the
  port, and keeps serving the code it started with. Before starting one, check
  `netstat -ano | findstr :8000` (or `:8001`) and end any stale process.
- **Never run two pytest invocations at once.** They share the test database, and the
  second one's teardown deletes it under the first.
- **Never edit a module the dev server has loaded while a `.http` replay is running** —
  the reload restarts the server in the middle of the file.
- **`docs/http/01_auth.http` and `09_users_and_invitations.http` both use up
  `change_password` attempts** (five per five minutes): never replay both in one window.
  **`99_lockout.http` locks logins from this machine for 60 seconds** — run it last.
- **Every `.http` file writes to the server's database.** It creates and deletes
  `ZZ`-prefixed rows, and switches two FCRM Settings flags and back.
- **`backend/scripts/run_http.py --mark` writes into `docs/ROUTES.md`.** Use `--mark` only
  when recording a test run of `backend/`, never from rebuild work.
- **No Celery worker runs by default.** Anything that queues work — bulk delete above ten
  documents, bulk update from twenty, an email sent without `now` — does nothing until one
  is started.

---

## Working on `backend_v2/` — the rebuild

### What it is

`backend/` works, but it rebuilds Frappe's request layer inside Django, with RPC-style
URLs. `backend_v2/` is a **REST API under `/api/v1/`**, written the way a Django developer
expects — one app per area, ViewSets and routers, serializers, permission classes — and
**every route answers with the same body as the old URL it replaces**. Inputs keep their
names and formats; only the URL and the HTTP method change. Why, and every decision so
far: `backend_v2/docs/REBUILD_PLAN.md`.

### Read these first

| File | In one line |
|---|---|
| **`backend_v2/docs/REBUILD_PLAN.md`** | **Why we are rebuilding, and every decision** — Settled, Proposed and Open. Read first |
| **`backend_v2/docs/API_CONTRACT.md`** | **Required before writing any route.** What every response must look like, what may change, and the old code behind each rule |
| `backend_v2/docs/PORT_MAP.md` | Every old endpoint and doctype: where it goes, its old file and line, the protections it must keep, its status — and, once written, the route map (old URL → new URL) |
| `backend_v2/docs/AS_BUILT.md` | What has actually been built, and the recipes for extending it |
| `backend_v2/specs/README.md` | The pieces of work (units), their order, and their status |
| `backend_v2/specs/<UNIT>.md` | Your unit: what to build, what must not be lost, how it is accepted |
| `backend_v2/docs/PARITY_EXCEPTIONS.md` | **Required before changing any behaviour.** The only places the new backend may answer differently |

### Which source wins

- **About what exists:** the code in `backend_v2/`, then `AS_BUILT.md`, then the unit spec,
  then `REBUILD_PLAN.md`. A spec is a plan written before the code, and goes stale.
- **About what a route must do:** the old backend in `backend/` first. The **Old source**
  column in `PORT_MAP.md` gives the exact file and line of each old endpoint. The Frappe
  source only when the old backend leaves a question open.
- **Decisions already taken** by the old backend, with their reasons, live in
  `specs/SECURITY_MODEL.md`, `specs/UNROUTED_DOCTYPES.md`, `specs/VERSION_HISTORY.md`,
  `specs/KNOWN_ISSUES.md`, `docs/UPSTREAM_BUGS_PHASE_*.md` and `docs/FINDINGS.md`. **Read
  them; do not decide them again.** A change goes through `PARITY_EXCEPTIONS.md`.
- **The acceptance suite** is `docs/http/*.http`. Its requests use the old URLs, so against
  `backend_v2` each one goes through the route map (REBUILD_PLAN section 6) — never
  straight to port 8001.

### Hard rules

1. **Do not edit anything outside `backend_v2/`** unless the owner asks. For rebuild work,
   `backend/`, `frontend/`, and the root `docs/` and `specs/` are read-only, and nothing in
   `backend_v2/` imports from `backend/`.
2. **New URL, same answer.** Every route is REST, under `/api/v1/`, and answers exactly
   like the old URL it replaces: same status code, same JSON (`API_CONTRACT.md`). No
   RPC-style dotted URL and no generic `/api/resource/` route is served. A deliberate
   difference is an entry in `PARITY_EXCEPTIONS.md`, approved before the code.
3. **Same inputs.** Only the resource and the document name move into the URL, and the HTTP
   method says what happens. Any other change to a request is a reshaped input, and goes in
   the route map.
4. **No hidden routes.** Every URL is written out in an app's `urls.py` (its router or an
   explicit path) and listed in the route map. No decorator, registry or import trick adds
   one, and nothing is routed by doctype name.
5. **Fields are opt-in.** Each resource lists exactly which fields may be shown, filtered,
   sorted and searched. A new column stays invisible until it is added. For parity, the
   first lists hold exactly what the old backend exposes.
6. **Every way in has the same lock.** A doctype is not `built` until every protection in
   its `PORT_MAP.md` row is enforced and tested — the permission rule on the list **and**
   on single records, and each hidden, manager-only, read-only or encrypted field in
   responses and in `fields`, `filters`, `or_filters`, `order_by` and `group_by`. Its
   list, single-record and action routes, its list view, its search, the bulk actions and
   any other route that reads it all go through the same queryset and field rules.
7. **Pass the user along.** Code gets the user as an argument (`request.user` →
   `create_lead(data, user=...)`), never from a hidden global (REBUILD_PLAN P9).
8. **Normal Django placement.** Business logic in model methods or `services.py`, not in
   views. A signal only where a direct call cannot reach.

### Running it beside the old backend

Ports, databases, Redis databases and `.env` locations: REBUILD_PLAN section 7 —
`backend/` on port 8000, `backend_v2/` on port 8001, each with its own database, Redis
databases, `.env` and virtualenv.

---

## Working on `backend/` — fixes to the old port

The old backend is the rebuild's reference, so **a fix here changes what `backend_v2`
must reproduce**. Record each one in `docs/FINDINGS.md`. It reaches the rebuild branch once
it is merged into `main` and `main` is merged into that branch.

### Read these first

| File | In one line |
|---|---|
| **`specs/AS_BUILT.md`** | **What the old backend actually contains.** Read first; where it and a phase spec disagree, it wins |
| `docs/PORT_PLAN.md` | The original plan: source inventory, the frontend's wire protocol, the decisions settled at the start |
| **`specs/SECURITY_MODEL.md`** | **Required before touching any permission rule or field-visibility setting.** How each doctype is protected, and the four field tools |
| `specs/UNROUTED_DOCTYPES.md` | Doctypes withheld from `/api/resource/`, and why |
| `specs/VERSION_HISTORY.md` | What change history is kept and pruned. **Read before touching `clear_old_versions`** — its name invites a change that deletes the timeline |
| `specs/KNOWN_ISSUES.md` | Problems already known — check before investigating something from scratch |
| `docs/FINDINGS.md` | Bugs found by the `.http` suite, and their status |
| `specs/README.md`, `specs/PHASE_<N>_*.md` | The original phase specs — history now, useful for why something was built |

### Where to look

**The Frappe source first** (see "The Frappe source" above) — the old backend copies it.

**When upstream Frappe is wrong** — and it sometimes is: **39 cases** are recorded across
the `docs/UPSTREAM_BUGS_PHASE_*.md` files (1–9 and 36–38 in the `0-2` file, 10–35 and 39 in
the `3-6` file, which despite its name now covers everything since phase 3). Copy a bug
the user can see; fix one nothing can observe. Check whether anything actually reads the
field before deciding, and record the choice there.

### Hard rules

1. **The frontend's wire protocol is fixed** — the RPC-style URLs, the envelopes, the error
   format (`docs/PORT_PLAN.md` §3). JWT login and the WebSocket are the only two
   deviations from Frappe's.
2. **Registering a doctype publishes it.** Every field becomes readable, filterable and
   writable through `/api/resource/` unless something says otherwise. Before adding one,
   follow the checklist in `specs/AS_BUILT.md` — two tests (`test_route_surface.py`,
   `test_credential_fields.py`) will fail on you otherwise, by design.

---

## Stack

Django + DRF + SimpleJWT, PostgreSQL 17, Redis, Celery, Django Channels,
django-treebeard (nested-set trees). Python 3.13. `backend_v2` proposes Django 5.2 LTS
(REBUILD_PLAN P10).

---

# Reviewer policy — three tiers

You write the code; something that does **not** share your blind spots reviews it. Try
these in order, stop at the first that genuinely works, and always tell the owner which
tier you used. **Every reviewer's brief is the root `AGENTS.md`.**

| Tier | Reviewer | Notes |
|---|---|---|
| **1** | Codex via PowerShell 7 | Preferred — a different model, and it reads the repo itself |
| **2** | Codex via PowerShell 5.1 | Same reviewer, fallback shell |
| **3** | Claude subagent | **Weaker** — same model, so it tends to share your blind spots |

Full procedure: `docs/internal/RUNBOOK_PHASE_7.md` §3.

## Tier 1 — Codex (default)

- codex-cli 0.147.0, on PATH as `codex`. Auth is already configured.
- The interactive screen needs a live terminal, so you **cannot** drive it. Use
  `codex exec` — headless: prompt in, report out.
- Codex reads the repo itself, and loads `AGENTS.md` wherever it is run from. Point it at
  paths; do not paste code in.
- Codex **reviews by reading only** — `AGENTS.md` tells it not to run tests. The owner runs
  them.

```powershell
codex exec -s read-only "<review request>"   # review, cannot touch files
codex exec review                            # built-in review subcommand
codex exec resume --last "<follow-up>"       # continue the same Codex session
codex exec --approve-for-me "<task>"         # only if the owner asks Codex to make edits
```

## Never trust the exit code

**`codex exec` exits 0 even when it ran nothing.** If the output contains
`REVIEW NOT PERFORMED`, `CreateProcessAsUserW failed`, `windows sandbox: runner failed` or
`SpawnChild`, or Codex asks you to paste files, the review **did not happen**. Go down a
tier; do not accept it. The first phases were reviewed blind this way.

**Give a run up to 40 minutes; do not kill it at 10.** A review that names files and
claims takes anywhere from one to thirty minutes, and a run that is still reading the right
files has not failed. At the 20-minute mark, look at its output so far and tell the owner
where it is. Only a run past 40 minutes, or one that has wandered into unrelated files,
counts as failed: re-run once with a narrower prompt — name the exact files and the exact
claims to check instead of asking it to go looking — then go down a tier if that times out
too.

## Tier 3 — Claude subagent

Spawn a **fresh** subagent, not a `fork`. A fresh subagent receives only the task prompt —
no conversation history — so it is genuinely separate. A `fork` inherits your whole context,
including the reasoning that produced the bug, which is the opposite of a second opinion.
Point it at `AGENTS.md` as its brief.

**Why tier 3 is still weaker.** The problem is *not* shared context; a fresh subagent has
none. It is:

1. **Same model** — same habits and same mistakes. If this model misreads a Frappe idiom
   once, a second copy reading the same code will likely misread it the same way.
2. **Same inputs** — writer and reviewer read the same spec. When a spec once wrongly said
   `field:` names are "slugified", both would have inherited the error. Codex caught it only
   by going to the Frappe source instead.

Because the weakness is the shared model, **separating context further does not help** —
`claude -p` buys nothing over a fresh subagent. Only a different model does. Use
`claude -p` only if you are yourself a subagent and cannot spawn one.

Tier 3 is weak at finding *different* bugs, not at finding bugs. In phase 0 the writing
agent re-read its own work after Codex signed off and found two real defects Codex missed,
including the most serious one of the phase. Same-model review has real value; it just
covers less new ground.

**Make up for it** by pointing tier 3 at the source rather than the spec wherever they
could disagree — the old code in `backend/` for rebuild work, the Frappe source for the old
port — and by adding: *"Assume the author was competent and the obvious things are right.
Look for what a reader who shares the author's assumptions would skip."*

## Always

- A review blocks for minutes. Batch reviews rather than asking after every edit.
- Each `codex exec` starts fresh — use `resume --last` for follow-up rounds.
- Report findings to the owner, including where you disagree. Do not apply them without
  being asked.
