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

- **Status:** approved — owner, 12 Nov 2026
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

### PE-3. `frappe.client.get` by `filters` is not served

- **Status:** approved — owner, 13 Nov 2026
- **Where:** `frappe.client.get` called with `filters` instead of `name`;
  `docs/http/13_bulk_and_misc.http` 2.5–2.7
- **Old backend:** the first permitted document matching the filters; 404
  `<DocType> not found` when none matches; 417 `name or filters is required` when neither
  is given (`backend/crm_app/api/client.py:client_get`)
- **backend_v2:** no route. Reading by `name` is each resource's `GET <resource>/<name>/`;
  the three blocks have no REST copy
- **Why:** no caller. All three frontend callers pass `name` (`SlaPolicyView.vue`,
  `SlaPolicyList.vue`, `AssignmentRuleView.vue`), and no seeded form script calls it. A
  route nobody calls is code to read and secure for nothing (S5); it can be added if a
  caller appears
- **Recorded by:** FOUNDATION, 13 Nov 2026

### PE-4. A parent loop in a tree is refused on save, as upstream refuses it

- **Status:** approved — owner, 13 Nov 2026 (revised the same day: refuse the loop, as
  upstream does, instead of repairing the bounds afterwards)
- **Where:** every `TreeDocument` (CRM Sales Hierarchy, CRM Territory): a create or
  update that sets a node's parent to the node itself or to one of its descendants. The
  `descendants of` / `ancestors of` filters and the sales hierarchy's row rule read the
  bounds such a loop would corrupt. No `.http` block found
- **Old backend:** accepts the save. The rebuild then walks from roots only, so nodes in
  a rootless loop are never visited and **keep whatever `lft`/`rgt` they had before** —
  possibly overlapping another subtree's (`backend/crm_app/permissions/tree.py:
  _rebuild_locked`, `depth > len(nodes)` guard). The missing check is finding 95
  (`docs/FINDINGS.md`, branch `docs/finding-tree-loop`; not yet merged to main)
- **backend_v2:** the save is refused with upstream's answer —
  `NestedSetRecursionError` (a `ValidationError`, so 417, title `Message`), message
  **`Item cannot be added to its own descendants`** — when the node is the new parent or
  an ancestor of it (`frappe/utils/nestedset.py:validate_loop`, version-15 `:234-237`,
  called on insert at `:78` and on move at `:114`). The rebuild itself stays the old
  one, so no loop can form and none needs repairing
- **Why:** `lft`/`rgt` decide which rows a user can see (`tree.py:30-40`), so stale,
  overlapping bounds after a malformed reparent are a permission defect. Refusing the
  loop is upstream's own behaviour; repairing bounds after the fact (this entry's first
  version, briefly built in brief 07) would have kept accepting a corrupt hierarchy
- **Recorded by:** FOUNDATION, 13 Nov 2026

### PE-5. Rename also repoints Links stored as plain text

- **Status:** proposed — parked for the owner (`temp` A-9, 16 Nov 2026). The parity
  version (no repointing) is what is built until this says `approved`
- **Where:** the rename mixin (`frappe.client.rename_doc` →
  `POST /api/v1/<resource>/<name>/rename/`), on any resource another model names through a
  `TEXT_LINK_FIELDS` column. No `.http` block found
- **Old backend:** repoints Django foreign keys, polymorphic child parents and seven
  hard-coded doctype/name pairs (`backend/frappe_core/rename.py:30-38, 48-80`), but never
  a Link held in a plain text column (`frappe_core/links.py:1-19` says such columns exist;
  rename never calls it). After a rename those columns keep the old name, which now names
  nothing
- **backend_v2:** also rewrites every declared `TEXT_LINK_FIELDS` column that names the
  old name, in the same transaction
- **Why:** a dangling reference users can see (the old name shown, the link broken). The
  per-model declarations make it a small change. It changes what users see, so only the
  owner approves it
- **Recorded by:** SHARED_ACTIONS, 16 Nov 2026

---

## Candidates — not exceptions yet

One candidate from `specs/KNOWN_ISSUES.md` §7, for ACTIVITIES: `assign_to.remove_multiple`
clears every assignee, where upstream's limit of 5 leaves the sixth. Keeping it is parity
with the old backend, and matching upstream would bring its limit back, so probably no
entry. Confirm against `backend/` before proposing one.
