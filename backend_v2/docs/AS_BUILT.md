# As built — what `backend_v2` actually contains

**Status: empty. Nothing has been built yet (2026-09-16).**

This file describes the code that exists, not the code that is planned. **Where it and a
spec disagree, this file wins**: specs are written before the code and go stale; this
file is written after the code and is kept true. **Where this file and the code disagree,
the code wins**, and this file is corrected in the same commit.

Each unit updates it before its gate: what it added, and the recipes the next unit
needs. **Paths are from the repository root.**

---

## 1. What exists

*Nothing yet.* FOUNDATION writes the first entries: the project skeleton, the `core` app,
authentication, and the base ViewSet every resource inherits.

## 2. Recipes

These are the sections FOUNDATION must write, because every later unit follows them.
Until then they are headings only; do not guess their contents from
`backend_v2/docs/REBUILD_PLAN.md`, which describes intent, not the result.

### Adding a resource

*Not written yet — FOUNDATION.* Model, serializer, ViewSet with its allowlists, its
registration on the app's router under `/api/v1/`, the recorded access decision, and the
tests the guard tests will demand.

### Adding an action or an endpoint

*Not written yet — FOUNDATION.* An `@action` on a resource's ViewSet, or a view on
`core`'s base view for an endpoint that is not a resource; its route in the app's
`urls.py`; guest access; the envelope of the old path it replaces; and its row in the
route map.

### Carrying a document name with slashes in a route

*Not written yet — FOUNDATION.* Names like `R/GA` are legal; how the lookup allows them
without swallowing an action segment.

### Declaring field access

*Not written yet — FOUNDATION.* Sensitive, restricted, read-only, encrypted: where each is
declared and what enforces it.

### Writing a row rule

*Not written yet — FOUNDATION.* The list rule, the object rule, and the destination
re-check for rows that point at another document.

### Raising an error

*Not written yet — FOUNDATION.* The exception classes and how a message reaches the
client verbatim.

### Background work and live events

*Not written yet — FOUNDATION wires Celery and Channels; NOTIFICATIONS writes the
recipe.*

## 3. Running it

*Not written yet — FOUNDATION.* Virtualenv, `.env`, database creation, migrations, seed
data, the server on port 8001, pytest, running a file from `backend_v2/http/`, the body
diff.

### Traps — read before starting a server or running tests

Each of these has already cost time on this machine:

1. **An old server keeps running.** On Windows, a `runserver` started in the background
   keeps going after its terminal is closed. It holds the port and serves the **old
   code**. Before starting one, check `netstat -ano | findstr :8001` (and `:8000` for the
   old backend) and stop any old process.
2. **Never run pytest twice at once.** Both runs share one test database; when the first
   finishes, it deletes the database under the second.
3. **Don't edit code during a `.http` run.** The server restarts on the change, and the
   rest of the file fails.
4. **Some `.http` files use up limited attempts.** `01_auth.http` and
   `09_users_and_invitations.http` both use "change password", allowed 5 times per 5
   minutes — don't run both close together. `99_lockout.http` locks logins from this
   machine for 60 seconds — run it last.
5. **`.http` files change the database.** They create and delete `ZZ`-prefixed test
   records, and switch two FCRM Settings flags and back.
6. **Queued work needs a Celery worker.** Bulk delete of more than 10 records, bulk update
   of 20 or more, and emails sent without `now` go to a queue. With no worker running,
   nothing happens — it is not a bug.

## 4. Invariants that will bite you

*None recorded yet.* The old backend's list, which is likely to apply here too, is
`specs/AS_BUILT.md` section 4 — `lead_owner` is the access column, names may contain
slashes, "assigned" has two definitions, underscore caches never bump `modified`.
