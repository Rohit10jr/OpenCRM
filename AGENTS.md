# frappe_django_crm — agent brief for the rebuild

On this branch the work is **`backend_v2/`**: the same CRM rebuilt as a conventional
Django **REST API under `/api/v1/`**. Django 5.2 LTS, DRF, SimpleJWT, PostgreSQL 17,
Redis, Celery, Django Channels, django-treebeard. Python 3.13. Paths are from the
repository root.

| Folder | What it is | Your role |
|---|---|---|
| `backend/` | The first Django port. It copies Frappe's request layer, and it works | **The reference.** `backend_v2` must behave and answer exactly like it. Read-only; never import from it |
| `backend_v2/` | One app per area, DRF ViewSets and routers, serializers. Each new URL answers with the JSON of the old URL it replaces | **What you build or review** |
| `frontend/` | The Vue app, unchanged in this rebuild | Why responses and inputs must not change even though URLs do |

**A rebuild goes wrong in two silent ways:** something the old backend did is **lost**
(it blocked filtering on a password field; the new code forgets), or something is
**changed** (a `417` comes back as `400`, a message is reworded). The author's tests check
what the author believes, not what `backend/` does — so compare against the old code.

## What to read, and when

Your brief names what the task needs. Beyond it, read only the rows that match.

| Before you… | Read |
|---|---|
| write or review any route | **`backend_v2/docs/API_CONTRACT.md`** and the endpoint's row in **`backend_v2/docs/PORT_MAP.md`** (old file and line, protections, route map) |
| make anything answer differently | **`backend_v2/docs/PARITY_EXCEPTIONS.md`** |
| work on a unit | `backend_v2/specs/<UNIT>.md`, and `backend_v2/docs/REBUILD_PLAN.md` for the decisions (S1–S25) |
| extend what is built, or run tests | `backend_v2/docs/AS_BUILT.md` (recipes, traps, invariants) |
| port permissions or hidden fields | `specs/SECURITY_MODEL.md` |
| port something that looks odd | `specs/KNOWN_ISSUES.md`, `UPSTREAM_BUGS.md`: the old backend may have decided it |

These record decisions already made. If you think one is wrong, say so in your report;
do not work around it.

## Which source wins

1. **The old backend, `backend/`.** The route map says which old URL a route replaces;
   `PORT_MAP.md`'s **Old source** column gives its file and line, relative to `backend/`.
2. **Frappe's source, only where `backend/` does not answer:** CRM at
   `D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm` (working tree, tag
   `port-base`, v1.82.0) and the framework at
   `D:\02_Personal\01_OpenSource\02_FrameWorks\frappe` via `git show version-15:<path>`
   only. Never read `develop` in either.

**Never invent semantics.** If neither source answers, say so. Compare new code with old
code, not with the spec: the spec may share the author's misunderstanding.

## Hard rules

**For the rebuild:**

1. **New URL, same answer.** REST under `/api/v1/`, same status code, same JSON as the old
   endpoint. Dotted `/api/method/...` URLs and `/api/resource/` are not served. Any
   difference needs an **approved** `PARITY_EXCEPTIONS.md` entry; until then build the old
   behaviour and propose the entry.
2. **Same inputs.** Only three things change: the resource goes into the URL
   (`doctype="CRM Lead"` → `/api/v1/leads/`), the document name goes into the URL, and the
   HTTP method says what happens (`GET` reads, `POST` creates or runs an action, `PATCH`
   updates, `DELETE` deletes — **PUT is not served**). Anything else is a reshaped input
   and goes in the route map.
3. **No hidden routes.** Every URL written out in an app's `urls.py` and in the route map;
   no decorator, registry or import trick; nothing routed by doctype name.
4. **Fields are opt-in.** Each resource lists the fields that may be shown, filtered,
   sorted and searched. A field not on a list is not allowed there.
5. **Every way in has the same lock.** List, record, actions, list view, search, bulk
   actions and any other route reading a doctype apply the same permission and
   hidden-field rules. Guarding one and forgetting another is this project's most common
   bug.
6. **Pass the user along** as an argument, never from a global (`get_current_user()`).
7. **Never import from `backend/`**, and never edit outside `backend_v2/`.

**Carried over, because they are part of the contract:**

8. **Frappe's response shape stays for now:** `{"message": ...}` / `{"data": ...}` and
   Frappe's error body. JWT login and the WebSocket stay as they are.
9. **Copy error messages exactly**, word for word.
10. **Record names follow Frappe's six naming rules** (`CRM-LEAD-2026-00001`); three
    doctypes use plain numbers; a user's name is their lowercased email.
11. **Never use `_assign` for permissions.** Check the `ToDo` records.
12. **Text search ignores case.** Frappe's `like` maps to `ilike` / `icontains`.

## When building

A build task is a brief in `tasks/` (git-ignored): the branch, the unit, the `PORT_MAP.md`
rows, the old files and lines, the decisions taken, the tests that must pass. **Its
decisions are settled with the owner: build them, and if you think one is wrong, say so
rather than building something else.** Claude reviews and commits; the owner merges.

* **A spec-check brief comes first in each unit.** It is read-only: compare the unit's spec
  with `backend/` and report each claim that is stale or wrong, with the `backend/` file
  and function that shows it. Change nothing. Finding none is more often a sign of not
  looking than of none being there.
* **One brief is one commit.** Build exactly what it asks, touching only the files the
  change needs, and leave the changes in the working tree. Your sandbox cannot write
  `.git`: never run `git add`, `git commit` or `git push`.
* **Write the commit message** to `tasks/COMMIT_MSG`, overwriting it. The subject says what
  changed; the body says **why**, cites the `backend/` `path:line` it matches, and lists
  the files the commit should contain. No attribution line.
* **Tests:** run the `backend_v2` test files you touched and their neighbours, singly —
  the command is in `backend_v2/docs/AS_BUILT.md` §3 once FOUNDATION writes it, and in
  the brief until then. Not the full suite unless the brief
  asks; never the `.http` suite, a dev server, or anything in `backend/`. A test must not
  reach the network: stub the outbound call.
* **Port old tests before writing new ones** (REBUILD_PLAN S14). Where `backend/tests/` has
  a test for the behaviour, port it — new URLs, methods and imports, the same expected
  answers. Write a new test only where none exists, and then expect what `backend/` does,
  not what you think it should do. A ported test's expected answer changes only with an
  approved `PARITY_EXCEPTIONS.md` entry.
* **A migration that writes data uses the historical model** (`apps.get_model`).
* **Records:** the unit's status in `backend_v2/specs/README.md`, what you built in
  `backend_v2/docs/AS_BUILT.md`, a `proposed` entry in `PARITY_EXCEPTIONS.md` for any
  difference you think is needed, and the route map row.
* **Decisions are not yours to edit:** never change `backend_v2/docs/REBUILD_PLAN.md`,
  `backend_v2/docs/API_CONTRACT.md`, or the status of any `PARITY_EXCEPTIONS.md` entry.
  Propose a change in your report; the owner decides.
* **Never** print or edit `.env` files, send anything to an outside service, open a pull
  request, delete branches, or change files outside this repository.

**Your report:** the files changed or added; that `tasks/COMMIT_MSG` is written; the test
commands you ran with their last lines of output, quoted; every difference from `backend/`
and why; anything in the brief you did not do, with the reason.

## When reviewing

Review by reading only, against `backend/`. Be specific — file and line. Say plainly when
something is right; do not manufacture findings. Work through these in order:

1. **Same answer as before:** status code, keys, value types, messages word for word.
   Usual slips: a price that should be the string `"1000.000000"` returned as `1000.0`
   (in `backend/` one record gives the string and a list the number); `400` instead of
   `417`; `201` instead of `200` on create; `403` and `404` mixed up; an input reshaped
   without a route-map entry.
2. **Protections carried over:** every item in the doctype's `PORT_MAP.md` row — the rule
   on the list **and** single records; hidden, manager-only, read-only and encrypted fields
   in responses **and** in `fields`, `filters`, `or_filters`, `order_by`, `group_by`; on
   create the check sees what is being created, not an empty object; moving a comment or
   file onto another record is checked against that record.
3. **Every way in** has the same protection (hard rule 5).
4. **Nothing hidden or automatic:** every URL written out, every field list explicit.
5. **Normal Django style:** user passed along, logic in models or services, migrations that
   work on an empty database, tests that would fail if the code were broken. A test
   written new where `backend/tests/` already has one is a finding (S14).
6. **Unapproved changes:** a difference from `backend/` without an approved
   `PARITY_EXCEPTIONS.md` entry is a finding, **even if it is better.**

**What has gone wrong here before.** In the old backend: one endpoint guarded while
another doing the same job was not (six times); a secret hidden from responses but still
filterable, so `like` recovered a real email password one character at a time; a secret
hidden but stored in plain text, another encrypted but served; a permission check on an
empty object at create, or on the pre-edit record at update; a rule on the list but not
the record, or the reverse. **A rebuild adds:** a protection that lived in shared code
(`backend/frappe_core/query.py`, `field_security.py`, `views.py`) and vanishes when only
the endpoint is ported; tests that check the author's expectation, not `backend/`;
messages copied almost right; a record that matches while the same record in a list does
not.

**Public paths** — webhooks and guest endpoints — are reachable from the internet. A
webhook must verify the provider's signature from the real request. A guest endpoint
(login, refresh, forgot and reset password, invitations) gives nothing away, uses keys
once, and counts every password check toward the lockout.

**How to report:**

* **If you cannot read this repository, say so and stop.** Make the first line
  `REVIEW NOT PERFORMED` and the reason. Do not ask for files to be pasted or review from
  memory.
* **Do not run anything** in a review, and never say a test passes or fails. Name the test
  or `.http` block that would settle a finding.
* **One block per finding, most severe first:** Severity (high, medium, low); Where
  (`backend_v2/` `path:line`); Claim (one or two sentences); Evidence (the `backend/`
  `path:line`, and Frappe's where it matters); Recorded (`PARITY_EXCEPTIONS.md`,
  `KNOWN_ISSUES.md` or `UPSTREAM_BUGS.md`, or `new`).
* **Do not report:** differences with an approved exception; a new URL, method or reshaped
  input the route map records; values that differ between servers (names, timestamps,
  tokens); style preferences.
* Where unsure, say so and name what would settle it. End with a one-line verdict.
