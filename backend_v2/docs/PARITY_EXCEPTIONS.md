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

- **Status:** approved — owner, 17 Nov 2026 (proposed 16 Nov 2026)
- **Where:** the rename mixin (`frappe.client.rename_doc` →
  `POST /api/v1/<resource>/<name>/rename/`), on any resource another model names through a
  `TEXT_LINK_FIELDS` column. No `.http` block found
- **Old backend:** repoints Django foreign keys, polymorphic child parents and seven
  hard-coded doctype/name pairs (`backend/frappe_core/rename.py:30-38, 48-80`), but never
  a Link held in a plain text column (`frappe_core/links.py:1-19` says such columns exist;
  rename never calls it). After a rename those columns keep the old name, which now names
  nothing
- **backend_v2:** also rewrites every declared `TEXT_LINK_FIELDS` column that names the
  old name, in the same transaction (`backend_v2/core/rename.py:_repoint_text_links`)
- **Why:** a dangling reference users can see (the old name shown, the link broken). The
  per-model declarations make it a small change. It changes what users see, so only the
  owner approves it. The gap is the port's, not Frappe's: upstream's `rename_doc` repoints
  every Link field, all of them text columns (`git show
  version-15:frappe/model/rename_doc.py`, `:171-172` and `update_link_field_values` `:412`)
- **Recorded by:** SHARED_ACTIONS, 16 Nov 2026

### PE-6. Both queued bulk workers refuse a missing or disabled requester

- **Status:** approved — owner, 17 Nov 2026 (proposed 16 Nov 2026)
- **Where:** the queued halves of bulk update (`core.bulk_update_docs`, 20–500 documents)
  and bulk delete (`core.delete_bulk_docs`, more than ten). No `.http` block found
- **Old backend:** neither worker checks `enabled`: each binds the requesting user and
  re-checks the row rules as that user (`backend/crm_app/bulk_update.py:111-134`,
  `backend/crm_app/tasks.py:321-345`). A user disabled after queuing still has the job run
- **backend_v2:** both workers refuse a requester who is missing or disabled; bulk update
  fails every document; bulk delete refuses the batch as it refuses a missing requester
  and deletes nothing. When the batch names at least one existing document the job raises
  `PermissionError` (`No permission to delete <DocType> <name>`); an empty or
  already-deleted batch returns `"success"`, as for any requester
  (`backend_v2/core/mixins/bulk_delete.py:authorize_bulk_delete`)
  (`backend_v2/core/tasks.py`, `bulk_update_docs` and `delete_bulk_docs`)
- **Why:** a queued job outlives its request; disabling an account should revoke what it
  queued. Other users can see the difference (records not updated or deleted), so only
  the owner approves it. Upstream has the same gap: its worker only sets the user
  (`frappe.set_user`), with no `enabled` check
- **Recorded by:** SHARED_ACTIONS, 16 Nov 2026

### PE-7. `name` cannot be changed through the User resource

- **Status:** proposed — decided by the supervisor on the owner's behalf and flagged for
  the owner (`temp` A-21 D-B, DECISIONS, 18 Nov 2026); built as described
- **Where:** `PATCH /api/v1/users/<name>/` (old `PUT /api/resource/User/<name>`) with a
  `name` in the body. No `.http` block found
- **Old backend:** accepts `name` as a writable field on update (`backend/frappe_platform/
  models.py:131`, an editable primary key; `backend/frappe_core/serializers.py:243-283`)
- **backend_v2:** a sent `name` is ignored on update, as other read-only fields are; the
  record keeps its name
- **Why:** no caller changes a User's name through the resource (the profile screens only
  post back the session user's own document), and Frappe v15 refuses it
  (`frappe/model/document.py:850-859`, `check_if_latest`). Renaming a record is
  `rename_doc`, which `User` does not serve here
- **Recorded by:** ACCOUNTS, 18 Nov 2026

### PE-8. CRM Invitation is created by `invite_by_email` alone

- **Status:** proposed — decided by the supervisor on the owner's behalf and flagged for
  the owner (`temp` A-24, DECISIONS 27, 18 Nov 2026); built as described
- **Where:** `POST /api/v1/invitations/` and `PATCH /api/v1/invitations/<name>/` (old
  `/api/resource/CRM Invitation`). No `.http` block found
- **Old backend:** the manager pair may create and change an invitation through the
  resource (`backend/crm_app/permissions/platform_docs.py:403-407`)
- **backend_v2:** CRM Invitation cannot be created or changed through its resource;
  invitations are created by `invite_by_email` alone. Listing, reading and deleting stay
  with the manager pair
- **Why:** the frontend only lists, deletes and calls `invite_by_email`
  (`InviteUserPage.vue:175-205`, `:86`), and `invite_by_email` holds the role checks
- **Recorded by:** ACCOUNTS, 18 Nov 2026

### PE-9. The User document's `assignmentruleuser_set` is always empty

- **Status:** proposed — decided by the supervisor on the owner's behalf and flagged for
  the owner (`temp` A-26, DECISIONS 29, 18 Nov 2026); built as described
- **Where:** `GET` and `PATCH /api/v1/users/<name>/`, the `assignmentruleuser_set` key.
  Seen in `docs/http/09_users_and_invitations.http` 2.3-2.6, 6.2, 6.4 and
  `00_walkthrough.http` 4.9
- **Old backend:** emits the rows and accepts them (`backend/frappe_core/children.py:38-51`,
  `backend/frappe_core/serializers.py:76-77,188-192`)
- **backend_v2:** the User document's `assignmentruleuser_set` is always empty and is not
  written through User; ASSIGNMENTS decides the read side
- **Why:** Assignment Rule is ASSIGNMENTS' model, not yet built; no `frontend/src` file
  reads the key
- **Recorded by:** ACCOUNTS, 18 Nov 2026

### PE-10. `get_exchange_rate` accepts only a known date and currency shape

- **Status:** proposed — decided by the supervisor on the owner's behalf and flagged for
  the owner (`temp` A-30, DECISIONS 33, 18 Nov 2026); built in `c072147`, `9aa9a82`
- **Where:** `GET /api/v1/exchange-rate/` (old `crm.api.exchange_rate.get_exchange_rate`)
- `get_exchange_rate` accepts `date` only as `latest` or an ISO date (ASCII digits, a real
  calendar date) and currencies only as three-letter codes (ASCII letters, either case);
  the old backend passes them through. A lowercase code is used as given, as the old
  backend uses it, and cached under its own key.
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-11. A settings record has no list route

- **Status:** proposed — decided by the supervisor on the owner's behalf and flagged for
  the owner (`temp` A-30, DECISIONS 35, 18 Nov 2026); built in `ff874c1`, with the
  `.http` generator's handling in `e0656cd`
- **Where:** `GET /api/v1/crm-settings/` (old `GET /api/resource/FCRM Settings` with
  `fields` or `filters`). Seen in `docs/http/12_settings_singletons.http` 1.3-1.5 and
  `backend/tests/test_settings_access.py` `test_the_key_cannot_be_probed_by_filtering`
- **Old backend:** answers list-shaped reads of a settings record
- **backend_v2:** a settings record has no list route. `GET crm-settings/` answers the
  record itself, ignoring `fields` and `filters`. In the `.http` copy, `12` 1.3-1.5 are
  marked `# @retired PE-11`: 1.3 is covered by 1.2, 1.4 by 1.11
  (`value/?field=access_key`), 1.5 by no other block; the filter test is not ported
- **Why:** the settled singleton routes (S25 (3)) serve one record at the resource root,
  with GET, PATCH and `value/`
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-12. Exchange-rate crashes and malformed answers answer as failed fetches

- **Status:** proposed — decided by the supervisor on the owner's behalf (`temp` A-30,
  DECISIONS 34, 18 Nov 2026; it only replaces a 500); built in `c072147`, `9aa9a82`
- **Where:** `GET /api/v1/exchange-rate/` (old `crm.api.exchange_rate.get_exchange_rate`)
- **Old backend:** a missing `from_currency` or `to_currency` raises TypeError in the
  dispatch (500); a transport error or malformed JSON from a paid provider is not caught
  (`backend/crm_app/api/exchange_rate.py:168-186`, 500); any JSON value a provider
  answers is cached and returned as the rate
- **backend_v2:** a missing currency answers `1`, as an empty one does (`:56`); the paid
  providers' failure falls through to the generic 417 sentence; a provider's answer
  counts only as a positive number, and anything else is a failed fetch (not cached, and
  a free provider falls back to the other)
- **Why:** each replaces a 500 with the answer the old code gives the neighbouring case
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-12a. A saved account without authentication sends without reading its password

- **Status:** approved — decided by the supervisor on the owner's behalf (`temp` A-34, 18
  Nov 2026; it only replaces an error); built in `8a2cbf1`
- **Where:** system and outgoing mail through a saved Email Account (`core.mail.open_backend`)
- **Old backend:** reads and decrypts the stored password for every saved account before
  sending (`backend/crm_app/communication.py:624`), so an account with
  `no_smtp_authentication` and a stored password could not send without an encryption key
- **backend_v2:** the password is decrypted only when the account authenticates
  (`smtp_settings`); an account with `no_smtp_authentication` sends without reading it
- **Why:** an account that sends no credentials has no use for them; this replaces an error
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-13. A settings record's `value/` refuses a field it does not list

- **Status:** approved — decided by the supervisor on the owner's behalf (`temp` A-31, 18
  Nov 2026); no client sends such a field; built in `ecbec60`
- **Where:** `GET /api/v1/<settings>/value/` (old `frappe.client.get_single_value`), for
  every `SingletonViewSet`. No `.http` block found
- **Old backend:** `field` is a required argument, and a field the record does not have
  answers `null` (`getattr(instance, field, None)`, `backend/crm_app/api/client.py:282-295`)
- **backend_v2:** a missing field, or one outside the resource's readable list, answers
  417 "Field ... is not readable"; a sensitive or restricted field is still 403; a link
  answers its stored name
- **Why:** in `backend_v2` a missing field and a link field were 500s; refusing anything
  outside the resource's readable list keeps the answer within the fields it lists
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-12b. Two `user_settings` crashes answer as errors

- **Status:** approved — decided by the supervisor on the owner's behalf (`temp` A-35, 18
  Nov 2026; it only replaces a crash); to be built in CONFIGURATION milestone 5
- **Where:** `POST /api/v1/user-settings/` (old `frappe.model.utils.user_settings.save`)
- **Old backend:** a `user_settings` string that is not JSON, and a `doctype` longer than
  140 characters, probably raise unhandled (`backend/crm_app/api/user_settings.py:37-56`,
  the 140-character key column); not run
- **backend_v2:** each answers 417 with a fixed sentence
- **Why:** replaces a crash with an error
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-14. A withheld doctype is not found by the metadata calls

- **Status:** proposed — decided by the supervisor on the owner's behalf and flagged for
  the owner (`temp` A-35, DECISIONS 42, 18 Nov 2026); to be built in CONFIGURATION
  milestone 5
- **Where:** `GET /api/v1/meta/doctype/`, `meta/fields/`, `meta/sort-options/`,
  `meta/filterable-fields/`, `meta/group-by-fields/` (old `getdoctype`, `get_fields`,
  `sort_options`, `get_filterable_fields`, `get_group_by_fields`), for a withheld doctype
  (Version now; ToDo and Data Import Log when built)
- **Old backend:** answers any registered doctype (`crm_app/api/form_load.py:177`,
  `crm_app/api/doc.py:90,346`, `frappe_core/metadata.py:117,154`)
- **backend_v2:** a withheld doctype answers 404 "DocType X not found" on every call that
  validates a doctype, as `API_CONTRACT.md:209` says
- **Why:** a doctype that is not served has no screen to describe
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-15. A child table answers `getdoctype` and the layout calls only

- **Status:** proposed — decided by the supervisor on the owner's behalf and flagged for
  the owner (`temp` A-35, DECISIONS 42, 18 Nov 2026); to be built in CONFIGURATION
  milestones 5 and 6
- **Where:** the metadata calls above, for a child table (CRM Dropdown Item, User Email,
  and later units' rows). Seen in `docs/http/07` 9.2, 9.3
- **Old backend:** answers every metadata call for a child table
- **backend_v2:** `getdoctype` answers a child table (`Grid.vue:545`,
  `stores/meta.js:9-17`), and so will milestone 6's layout calls; `get_fields`,
  `sort_options`, `get_filterable_fields` and `get_group_by_fields` answer 404.
  `API_CONTRACT.md:209` says 404 for every child table; the contract is the owner's to
  change and is not edited here
- **Why:** the grids call `getdoctype` for their rows; no screen calls the other four for a
  child
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-16. Metadata answers list only the fields the caller may read

- **Status:** proposed — decided by the supervisor on the owner's behalf and flagged for
  the owner (`temp` A-35, DECISIONS 43, 18 Nov 2026); to be built in CONFIGURATION
  milestone 5
- **Where:** `getdoctype`'s fields, `meta/fields/`, `meta/filterable-fields/`,
  `meta/group-by-fields/`, `meta/sort-options/`, and later `get_data`'s `fields` block
- **Old backend:** lists every field name
- **backend_v2:** metadata answers list only the fields the caller may read
- **Recorded by:** CONFIGURATION, 18 Nov 2026

---

## Candidates — not exceptions yet

One candidate from `specs/KNOWN_ISSUES.md` §7, for ACTIVITIES: `assign_to.remove_multiple`
clears every assignee, where upstream's limit of 5 leaves the sixth. Keeping it is parity
with the old backend, and matching upstream would bring its limit back, so probably no
entry. Confirm against `backend/` before proposing one.
