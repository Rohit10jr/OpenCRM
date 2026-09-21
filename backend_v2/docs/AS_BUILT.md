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
data, the server on port 8001, pytest, replaying an `.http` file, the body diff.

## 4. Invariants that will bite you

*None recorded yet.* The old backend's list, which is likely to apply here too, is
`specs/AS_BUILT.md` section 4 — `lead_owner` is the access column, names may contain
slashes, "assigned" has two definitions, underscore caches never bump `modified`.
