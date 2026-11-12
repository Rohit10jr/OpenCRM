# Parity exceptions — where `backend_v2` answers differently on purpose

The rebuild's rule is **same status, same body** as `backend/`
(`backend_v2/docs/API_CONTRACT.md`). This file is the only place that rule may be broken,
and every break is written here **before** the code that makes it. A difference found in
testing that has no entry here is a bug in `backend_v2`, not an exception.

**Paths are from the repository root.**

## What earns an entry

- **An old-backend defect not worth copying**, such as a request that answers 500. A 500
  is never part of the contract, but replacing it with a proper error is still a change a
  client can see.
- **A decision the old backend deferred** and the owner has now taken.
- **A default that differs between library versions** (a newer DRF, SimpleJWT or Channels
  release than the old backend pins, S17) where matching the old output would mean
  fighting the framework.

Not an entry:

- **A value that legitimately differs between two servers** (generated names, timestamps,
  tokens). The body diff normalises those, and `API_CONTRACT.md` lists them.
- **The new URL, HTTP method and reshaped inputs of a route.** Those change by design
  (REBUILD_PLAN S6, S7) and are recorded in the route map in `PORT_MAP.md`. An entry here
  is for a difference in what comes back — status, body, behaviour — not in how it is
  asked for.

## How an entry is written

**Who does what:**

1. **The building agent proposes.** When it finds something it thinks should answer
   differently from the old backend, it adds an entry under **Register** below, with status
   `proposed`.
2. **It keeps building the parity version** — the old behaviour — in the meantime, never the
   change.
3. **The owner is told**: Codex says so in its report on the brief, and Claude raises it
   with the owner before committing.
4. **Only the owner approves or rejects.** The code changes only once the entry says
   `approved`.

Each entry has this shape:

```
### PE-<n>. <one-line summary>

- **Status:** proposed | approved | rejected — only the owner approves
- **Where:** the method path or doctype, and the `.http` block that shows it
- **Old backend:** what it answers today, with the file and line that decides it
- **backend_v2:** what it will answer instead
- **Why:** the reason, and what a client could notice
- **Recorded by:** unit and date
```

An `approved` entry changes the expectation. The `.http` block that shows the difference
is named, its REST copy in `backend_v2/http/` expects the new answer, and the body
comparison skips that block.

---

## Register

### PE-1. A method a route does not allow answers 405, not 403

- **Status:** approved — owner, 12 Nov 2026 (`specs/FOUNDATION.md` section 6, Q11)
- **Where:** every route; shown by `docs/http/01_auth.http` 1.12 (`GET login`)
- **Old backend:** 403 `PermissionError`, `Method <path> does not accept <VERB>`
  (`backend/frappe_core/method_views.py:46-50`) — wording that belonged to its RPC
  dispatch
- **backend_v2:** 405 with an `Allow` header, in the Frappe error shape; the exact body
  goes into `AS_BUILT.md` when built. An unknown URL is 404, also in the Frappe shape
- **Why:** the old answer described a dispatch `backend_v2` does not have. No client
  sends these requests, and S19 moves towards DRF's shapes anyway
- **Recorded by:** FOUNDATION, 12 Nov 2026

### PE-2. A tree operator on a field that is not a tree: new wording

- **Status:** proposed
- **Where:** every list route; any filter using `descendants of`, `ancestors of` or their
  variants on a field whose target is not a tree. No `.http` block found
- **Old backend:** 400 `ValidationError`, title `Invalid Filter`, message
  `No tree resolver registered for '<DocType or field>'; phase 2 registers these via
  filters.register_tree_resolver()` (`backend/frappe_core/filters.py:_tree_op`)
- **backend_v2:** the same status, `exc_type` and title, with a message that names no
  internals: `'<field>' is not a tree field`
- **Why:** the old text names a registry function and a build phase; `backend_v2` has
  neither (S11). Only the message changes
- **Recorded by:** FOUNDATION, 12 Nov 2026

---

## Candidates — not exceptions yet

One candidate from `specs/KNOWN_ISSUES.md` §7, for ACTIVITIES: `assign_to.remove_multiple`
clears every assignee, where upstream's limit of 5 leaves the sixth. Keeping it is parity
with the old backend, and matching upstream would bring its limit back, so probably no
entry. Confirm against `backend/` before proposing one.
