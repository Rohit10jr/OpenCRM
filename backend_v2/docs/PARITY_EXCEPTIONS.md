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

- **Status:** approved by the owner (20 Nov 2026); first decided by the supervisor (`temp`
  A-21 D-B, DECISIONS, 18 Nov 2026); built as described
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

### PE-8. CRM Invitation is created and changed through the resource by System Manager or Administrator

- **Status:** approved by the owner (20 Nov 2026), rewriting the supervisor's first
  decision (`temp` A-24, DECISIONS 27, 18 Nov 2026; set-once `temp` A-50); built with
  this text (`temp` A-48 2b)
- **Where:** `POST /api/v1/invitations/` and `PATCH /api/v1/invitations/<name>/` (old
  `/api/resource/CRM Invitation`). No `.http` block found
- **Old backend:** the manager pair may create and change an invitation through the
  resource, every field writable, and a row created there has no key
  (`backend/crm_app/permissions/platform_docs.py:403-407`)
- **backend_v2:** System Manager or Administrator create and change an invitation
  through the resource. A create checks, in upstream's order, the address (417 "<email>
  is not a valid Email Address") and then the role (403 "Cannot invite for this role"
  unless it is Sales User, Sales Manager or System Manager). Upstream's role-profile check
  on an existing user (`validate_existing_user`) is not carried: there is no role
  profile here. `email` and `role` are written on create and then set once: a change
  answers 417 "Value cannot be changed for <strong>Email</strong>" (or Role), upstream's
  text; the same value sent back is accepted. On create the server sets `key` (the same
  generator `invite_by_email` uses), `status` "Pending" and `invited_by` (the caller), and
  the invitation mail goes out; `status`, `invited_by`, `email_sent_at` and `accepted_at`
  are never written through the resource. A Sales Manager lists, reads and deletes
  invitations and invites through `invite_by_email`, which also sets `invited_by` to the
  caller (the old backend leaves it empty there)
- **Why:** `invite_by_email` holds the role checks; the resource is for an
  administrator's scripts. Upstream sets `key`, `invited_by` and `status` in
  `before_insert` (`crm/fcrm/doctype/crm_invitation/crm_invitation.py`) and refuses a
  changed set-once field (`frappe/model/document.py:697-721`)
- **Recorded by:** ACCOUNTS, 18 Nov 2026

### PE-9. The User document's `assignmentruleuser_set` is always empty

- **Status:** approved by the owner (20 Nov 2026); first decided by the supervisor (`temp`
  A-26, DECISIONS 29, 18 Nov 2026); built as described
- **Where:** `GET` and `PATCH /api/v1/users/<name>/`, the `assignmentruleuser_set` key.
  Seen in `docs/http/09_users_and_invitations.http` 2.3-2.6, 6.2, 6.4 and
  `00_walkthrough.http` 4.9
- **Old backend:** emits the rows and accepts them (`backend/frappe_core/children.py:38-51`,
  `backend/frappe_core/serializers.py:76-77,188-192`)
- **backend_v2:** the User document's `assignmentruleuser_set` is always empty and is not
  written through User. ASSIGNMENTS decides the read side and whether the key leaves the
  User document
- **Why:** Assignment Rule is ASSIGNMENTS' model, not yet built; no `frontend/src` file
  reads the key
- **Recorded by:** ACCOUNTS, 18 Nov 2026

### PE-10. `get_exchange_rate` accepts only a known date and currency shape

- **Status:** approved by the owner (20 Nov 2026), widening the supervisor's first
  decision (`temp` A-30, DECISIONS 33, 18 Nov 2026); built in `c072147`, `9aa9a82`; the
  currency rule below is to be built (`temp` A-48 3d). Until then a currency is exactly
  three ASCII letters
- **Where:** `GET /api/v1/exchange-rate/` (old `crm.api.exchange_rate.get_exchange_rate`)
- `date` is `latest` or an ISO date (ASCII digits, a real calendar date); a currency is
  ASCII letters and digits, 2 to 5 characters. The old backend passes both through. A
  lowercase code is used as given, as the old backend uses it, and cached under its own
  key.
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-11. A settings record has no list route

- **Status:** approved by the owner (20 Nov 2026); first decided by the supervisor (`temp`
  A-30, DECISIONS 35, 18 Nov 2026); built in `ff874c1`, with the `.http` generator's
  handling in `e0656cd`
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

### PE-12b. Three `user_settings` crashes answer as errors

- **Status:** approved — decided by the supervisor on the owner's behalf (`temp` A-35,
  A-36, 18 Nov 2026; it only replaces a crash); built in `d46ab53`, `d8a85a7`
- **Where:** `GET` and `POST /api/v1/user-settings/` (old
  `frappe.model.utils.user_settings.get` and `.save`)
- **Old backend:** a `user_settings` string that is not JSON, and a `doctype` longer than
  140 characters on a save, probably raise unhandled
  (`backend/crm_app/api/user_settings.py:37-56`, the 140-character key column; not run);
  a missing `doctype` raises on the missing argument (`whitelist.py:75-92`)
- **backend_v2:** each answers 417 with a fixed sentence: "User settings must be valid
  JSON", "DocType name is too long" (on a save only; a read of a longer name answers
  `"{}"`, as `backend/`), "DocType is required"
- **Why:** replaces a crash with an error
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-14. A withheld doctype is not found by the metadata calls

- **Status:** approved by the owner (20 Nov 2026); first decided by the supervisor (`temp`
  A-35, DECISIONS 42, 18 Nov 2026); built in `f6e6822`, `94d5c15`
- **Where:** `GET /api/v1/meta/doctype/`, `meta/fields/`, `meta/sort-options/`,
  `meta/filterable-fields/`, `meta/group-by-fields/` (old `getdoctype`, `get_fields`,
  `sort_options`, `get_filterable_fields`, `get_group_by_fields`), for a withheld doctype
  (Version now; ToDo and Data Import Log when built); and, with CONFIGURATION milestone 6,
  the layout calls (`get_fields_layout`, `get_sidepanel_sections`,
  `save_fields_layout`) and the quick-filter calls (`get_quick_filters`,
  `update_quick_filters`); with milestone 7, the default rows and columns the saved-view
  calls merge (`list_definition_for`), which are empty for such a doctype
- **Old backend:** answers any registered doctype (`crm_app/api/form_load.py:177`,
  `crm_app/api/doc.py:90,346`, `frappe_core/metadata.py:117,154`)
- **backend_v2:** a withheld doctype answers 404 "DocType X not found" on every call that
  validates a doctype, as `API_CONTRACT.md:209` says
- **Why:** a doctype that is not served has no screen to describe. Upstream answers these
  calls for any doctype and lists every field (`frappe/desk/form/load.py:65-86`,
  `crm/api/doc.py`); the old backend does the same
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-15. A child table answers `getdoctype` and the layout read and save only

- **Status:** approved by the owner (20 Nov 2026); first decided by the supervisor (`temp`
  A-35, DECISIONS 42, 18 Nov 2026); `getdoctype`'s half built in `f6e6822`, `94d5c15`; the
  layout calls come with CONFIGURATION milestone 6
- **Where:** the metadata calls above, for a child table (CRM Dropdown Item, User Email,
  and later units' rows). Seen in `docs/http/07` 9.2, 9.3
- **Old backend:** answers every metadata call for a child table
- **backend_v2:** `getdoctype` answers a child table (`Grid.vue:545`,
  `stores/meta.js:9-17`), and so will milestone 6's `get_fields_layout` and
  `save_fields_layout` (the grid row editor); `get_sidepanel_sections`, the quick-filter
  calls, `get_fields`,
  `sort_options`, `get_filterable_fields` and `get_group_by_fields` answer 404, as
  `API_CONTRACT.md:210` says. With milestone 7, the saved-view calls merge no default
  rows or columns for a child table (`list_definition_for`)
- **Why:** the grids call `getdoctype` for their rows; no screen calls the other four for a
  child. Upstream answers these calls for any doctype and lists every field
  (`frappe/desk/form/load.py:65-86`, `crm/api/doc.py`); the old backend does the same
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-16. Metadata answers list only the fields the caller may read

- **Status:** approved by the owner (20 Nov 2026); first decided by the supervisor (`temp`
  A-35, DECISIONS 43, 18 Nov 2026); built in `f6e6822`, `94d5c15`
- **Where:** `getdoctype`'s fields, `meta/fields/`, `meta/filterable-fields/`,
  `meta/group-by-fields/`, `meta/sort-options/`; with milestone 6, the layout and
  quick-filter calls (the Required Fields section and the default layout included); with
  milestone 7, a saved kanban's default columns (a `column_field` the caller may not
  read gives none); and with milestone 8, `get_data`'s `fields` block (built in
  `717fdd3`)
- **Old backend:** lists every field name
- **backend_v2:** metadata answers list only the fields the caller may read. The fields
  that remain keep their original `idx`; gaps are allowed
- **Why:** the answer describes what the caller's own documents contain. Upstream answers
  these calls for any doctype and lists every field (`frappe/desk/form/load.py:65-86`,
  `crm/api/doc.py`); the old backend does the same
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-12c. A broken layout or quick-filter entry is refused or skipped

- **Status:** approved — decided by the supervisor on the owner's behalf (`temp` A-37,
  A-38, 18 Nov 2026; it only replaces a crash); built in `17241b1`, `90fa788`, `816bcb7`,
  `20e7989`
- **Where:** `save_fields_layout` and the CRM Fields Layout resource's create and PATCH;
  `get_fields_layout` and `get_sidepanel_sections` on a stored layout; `get_quick_filters`
- **Old backend:** a `layout` that is not valid JSON is stored, and that layout then
  fails `layout/` and `sidepanel-sections/` for every viewer
  (`backend/crm_app/api/fields_layout.py:123,220`). A quick-filter `json` entry that is
  a list or a dict fails the call for every later caller; a number entry is skipped
  (`backend/crm_app/api/doc.py:173-177`). A stored `json` that is a dict, or a string
  that parses to one, has its keys read as fieldnames (`:170-177`)
- **backend_v2:** a layout that is not valid JSON, or is nested too deep to read, is 417
  "Layout must be valid JSON" on save and on read. A quick-filter entry that is not a
  string is skipped, and a stored `json` that is not a list (or a string that does not
  parse to one) counts as no entries
- **Why:** replaces a crash with an error; the screen only ever stores a list of
  fieldnames
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-17. CRM Form Script is written by System Manager or Administrator

- **Status:** approved by the owner (20 Nov 2026); first decided by the supervisor (`temp`
  A-37, A-38, DECISIONS 45, 18 Nov 2026); built in `17241b1`
- **Where:** `POST`, `PATCH` and `DELETE /api/v1/form-scripts/...` (old
  `/api/resource/CRM Form Script`)
- **Old backend:** System Manager, Sales Manager or Administrator create, change and
  delete a form script (`backend/crm_app/permissions/metadata_docs.py:99-113`)
- **backend_v2:** System Manager or Administrator create, change and delete a form
  script; everyone lists and reads one, as before
- **Why:** upstream's role table gives write to System Manager alone
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-18. A layout's field lists hold fieldnames

- **Status:** approved by the owner (20 Nov 2026); first decided by the supervisor (`temp`
  A-37, A-38, DECISIONS 46, 18 Nov 2026); built in `17241b1`, `8c04d80`
- **Where:** `save_fields_layout`, the CRM Fields Layout resource's create and PATCH,
  `get_fields_layout`, `get_sidepanel_sections`
- **Old backend:** an entry of a layout's field list that is not a fieldname is stored,
  and passed through on read (`backend/crm_app/api/fields_layout.py:156-158,232-234`)
- **backend_v2:** a layout's field lists hold fieldnames; anything else is refused on
  save (417 "A layout's field lists hold fieldnames only") and left out on read
- **Why:** every editor saves fieldnames, and the field's properties come from the
  doctype's own metadata
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-19. A saved view's owner and flags are set by the dedicated calls

- **Status:** approved by the owner (20 Nov 2026); first decided by the supervisor (`temp`
  A-39, DECISIONS 49, 18 Nov 2026); built in `c590ac3`
- **Where:** `POST` and `PATCH /api/v1/view-settings/...` (old
  `/api/resource/CRM View Settings`)
- **Old backend:** accepts `user`, `public`, `is_standard` and `is_default` as written
  (`backend/crm_app/permissions/metadata_docs.py:84-91`)
- **backend_v2:** on the resource, a saved view's `user`, `public`, `is_standard` and
  `is_default` are set by the dedicated calls only, and a created view belongs to the
  caller
- **Why:** the screen sets these through the dedicated calls alone
  (`ViewControls.vue:984-1290`, `ViewModal.vue:121-130`)
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-20. `public` acts on a view the caller may read

- **Status:** approved by the owner (20 Nov 2026); first decided by the supervisor (`temp`
  A-39, DECISIONS 50, 18 Nov 2026); built in `f7c4ea5`
- **Where:** `POST /api/v1/view-settings/<name>/public/` (old
  `crm.fcrm.doctype.crm_view_settings.crm_view_settings.public`)
- **Old backend:** checks the caller's role only
  (`backend/crm_app/api/view_settings.py:204-229`)
- **backend_v2:** `public` acts on a view the caller may read: the role check (403 "Not
  permitted"), then 404 for a missing view, then the read rule (403 "Not permitted")
- **Why:** the screen offers it on the views the caller sees
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-21. `set_as_default` and the kanban column refresh act on views the caller may use

- **Status:** approved by the owner (20 Nov 2026); first decided by the supervisor (`temp`
  A-39, DECISIONS 51, 18 Nov 2026); built in `f7c4ea5`
- **Where:** `POST /api/v1/view-settings/set-as-default/` and
  `POST /api/v1/view-settings/<name>/kanban-columns/` (old `set_as_default` and
  `fetch_and_update_kanban_columns`); and, with CONFIGURATION milestone 8, the named
  view's `load_default_columns` that `<resource>/list-view/` reads (old `get_data`,
  `backend/frappe_core/api/doc.py:176-186,343-348`): a view the caller may not read
  counts as missing
- **Old backend:** checks neither (`backend/crm_app/api/view_settings.py:246-270,318-347`)
- **backend_v2:** `set_as_default` with a name acts on the caller's own view (403 "Not
  permitted" otherwise, 404 for a missing one), and `fetch_and_update_kanban_columns` on
  a view the caller may read, saving only where the caller may write it
- **Why:** the screen offers "Set As Default" on the caller's own standard views only
  (`ViewControls.vue:1112-1116`, `:1141-1146`, `:1225-1233`), and "Reload Columns" on
  every board the caller sees (`KanbanView.vue:166-171`)
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-12d. Saved-view crashes answer as errors

- **Status:** approved — decided by the supervisor on the owner's behalf (`temp` A-39,
  18 Nov 2026; extended by A-43, 19 Nov 2026; it only replaces a crash); built in
  `c590ac3`, `b744875`, `f7c4ea5`, `8f5c569`, `85374af`
- **Where:** `create-view/`, `standard-view/`, `update-view/`, `set-as-default/` and
  `<name>/kanban-columns/` under `/api/v1/view-settings/`, the resource's create and
  PATCH, and `GET /api/v1/views/`
- **Old backend:** `create` or `create_or_update_standard_view` without a `doctype`
  raises building the route name (`backend/crm_app/api/view_settings.py:56-62`);
  `get_views` without a `doctype` raises on the missing argument
  (`backend/crm_app/api/views.py:13`, `frappe_core/whitelist.py:75-92`); `update`
  and `set_as_default` with a name that is not an integer raise in `filter(pk=…)`
  (`:176`, `:261`); a view that is not an object, `rows` or `columns` that is not a
  list, a row that is not a fieldname, a `doctype` or `type` that is not text, and
  `create` with no `label` raise (`:109-135`, `:150-167`); the kanban refresh raises on a
  stored `kanban_columns` that is not a list of objects (`:339-343`); a JSON column
  written through the resource that is not valid JSON is stored as written
- **backend_v2:** no `doctype`, or one that is not text, is 417 "DocType is required";
  a name that is not an integer is 404 "CRM View Settings X not found"; a view that is
  not an object is 417 "View must be an object"; `rows` or `columns` that is not a list
  is 417 "Rows must be a list" or "Columns must be a list"; a row that is not a
  fieldname is 417 "Rows must be fieldnames"; a `type` that is not text is 417 "Type
  must be text"; `create` with no `label` is 417 "Label is required"; in the kanban
  refresh, a stored `kanban_columns` that is not a list counts as none and an entry that
  is not an object is skipped; a resource write of `filters`, `columns`, `rows`,
  `kanban_columns` or `kanban_fields` that is not valid JSON is 417 "<Label> must be
  valid JSON" (for example "Kanban Columns must be valid JSON")
- **Why:** replaces a crash with an error
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-22. `get_data` is served for the resources that opt in to a list view

- **Status:** approved by the owner (20 Nov 2026); first decided by the supervisor (`temp`
  A-40, 18 Nov 2026); built in `717fdd3`, `f743a80`
- **Where:** `GET` and `POST /api/v1/<resource>/list-view/` (old `crm.api.doc.get_data`)
- **Old backend:** answers `get_data` for any registered doctype, and builds the column
  list whether or not the link target is served (`backend/frappe_core/api/doc.py:229`,
  `:438-443`)
- **backend_v2:** `get_data` is served for the resources that opt in to a list view; a
  child table, a withheld doctype and a settings record have none, and the URL answers
  the generic 404. A kanban column list is built from a link target only where that
  target is itself served
- **Why:** each list screen has its own resource; no screen lists a child table, a
  withheld doctype or a settings record
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-23. A list view takes at most `MAX_PAGE_LENGTH` kanban columns

- **Status:** proposed — decided by the supervisor on the owner's behalf and flagged for
  the owner (`temp` A-40, 18 Nov 2026); built in `f743a80`
- **Where:** `GET` and `POST /api/v1/<resource>/list-view/` with `kanban_columns`
- **Old backend:** accepts any number of sent columns
  (`backend/frappe_core/api/doc.py:484-526`)
- **backend_v2:** a sent `kanban_columns` list longer than `MAX_PAGE_LENGTH` is 417 "At
  most 500 kanban columns". A
  column's `page_length` of 0 still means no limit, and `page_length=0` every row, as
  before
- **Why:** the same limit as a list page's length
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-12e. List-view crashes answer as errors

- **Status:** approved — decided by the supervisor on the owner's behalf (`temp` A-40,
  18 Nov 2026; narrowed and extended by A-44, 19 Nov 2026; it only replaces a crash);
  built in `7daa881`, `f743a80`, `45a97a5`
- **Where:** `GET` and `POST /api/v1/<resource>/list-view/` (old `crm.api.doc.get_data`)
- **Old backend:** raises on: a `columns` entry that is not an object in a list or
  group-by view (`backend/frappe_core/api/doc.py:296-303`); a `kanban_columns` entry
  that is not an object in a kanban view (`:485-524`); a `rows` or `kanban_fields`
  entry that is a list or an object (`:396`, `:460-462`); a column's `order` that is
  neither a list nor a string (`:519-524`, `:540`); a `title_field` or `group_by_field` that is
  not text; group-by values of mixed types (`:615-623`); a `custom_view_name` that is
  not an integer (`filter(pk=…)`, `:176-186`)
- **backend_v2:** each of these is 417 with a fixed sentence ("Columns must be objects",
  "Kanban columns must be objects", "Rows must be fieldnames", "Kanban fields must be
  fieldnames", "A column's order must be a list", "Title field must be a fieldname",
  "Group by field must be a fieldname"), except that group-by values of mixed types are
  sorted by their text and a `custom_view_name` that is not an integer counts as no
  view. A null in a manual `order` names no card. Where the old code does not crash it
  is kept: the kanban lists are read only in a kanban view and `columns` only in a list
  or group-by view, a number or null in `rows` is "Unknown field 5 for X", and a string
  `order` is read as its characters
- **Why:** replaces a crash with an error
- **Recorded by:** CONFIGURATION, 18 Nov 2026

### PE-24. Rename is served where upstream allows a rename

- **Status:** approved by the owner (20 Nov 2026), rewriting the supervisor's first
  decision (`temp` A-41, A-42, DECISIONS 58 and, for the child-row caches, 60; 19 Nov
  2026; rewritten by `temp` A-48 3c); to be built, for the resources already built
  first and for later units as they are built
- **Where:** `POST /api/v1/<resource>/<name>/rename/` (old `frappe.client.rename_doc`);
  and the Contact Email and Contact Phone row routes,
  `PATCH /api/v1/contacts/<name>/email-ids/<row>/` and `.../phone-nos/<row>/` (old
  `frappe.client.set_value` on the row)
- **Old backend:** the rename call accepts any doctype
  (`backend/crm_app/api/client.py:462-495`); the row edit writes the underscore caches
  of the row (`:421-446`)
- **backend_v2:** rename is served for the doctypes upstream marks `allow_rename`, and
  needs the write rule. Not served: Gender, CRM Task, CRM View Settings, CRM Global
  Settings, CRM Sales Hierarchy. A child-row write never writes the underscore caches
- **Why:** upstream refuses a rename where `allow_rename` is off
  (`frappe/model/rename_doc.py:379-380`); the caches are written by their own calls
  (`API_CONTRACT.md:240`)
- **Recorded by:** CONTACTS, 19 Nov 2026

### PE-25. "Remove contact" clears the document's own contact field and table

- **Status:** approved by the owner (20 Nov 2026); first decided by the supervisor (`temp`
  A-42, DECISIONS 59, 19 Nov 2026); built in `c1490cd`
- **Where:** `POST /api/v1/<resource>/<name>/linked-documents/` with `remove_contact`,
  and `POST /api/v1/<resource>/bulk-delete/` on a resource that removes contacts (old
  `remove_linked_doc_reference` and `delete_bulk_docs`)
- **Old backend:** clears whatever the document exposes under that name
  (`backend/crm_app/api/doc.py:579-586`)
- **backend_v2:** "remove contact" clears the document's own `contact` field and its
  `contacts` table, the one its resource declares
- **Why:** the screen removes a contact from the deal it is unlinked from
- **Recorded by:** CONTACTS, 19 Nov 2026

### PE-26. Deleting a linked document needs its delete rule

- **Status:** approved by the owner (20 Nov 2026); first decided by the supervisor (`temp`
  A-42, A-45, DECISIONS 59, 19 Nov 2026); built in `c1490cd`, `a39108f`
- **Where:** `POST /api/v1/<resource>/<name>/linked-documents/` with `delete`, and
  `POST /api/v1/<resource>/bulk-delete/` with `delete_linked`
- **Old backend:** checks the write rule. Upstream's unlink answers 403 and rolls the
  request back when a linked document may not be deleted; its bulk delete leaves the
  item in place
- **backend_v2:** the unlink action's delete and bulk delete's `delete_linked` delete
  only the linked documents the caller may delete; one the caller may not delete is
  skipped, like every other refusal in those loops, and its link is still cleared
- **Why:** the linked delete asks what the record route asks
- **Recorded by:** CONTACTS, 19 Nov 2026

### PE-27. Email Account is System Manager's and Administrator's

- **Status:** approved by the owner (20 Nov 2026; `temp` A-48 2a); built with this entry
- **Where:** `/api/v1/email-accounts/...` (list, create, read, PATCH, delete, rename)
  and `POST /api/v1/email-accounts/setup/` (old `/api/resource/Email Account`,
  `crm.api.settings.create_email_account`)
- **Old backend:** every signed-in user lists and reads an Email Account; the manager
  pair creates, changes and deletes one, and calls `create_email_account`
  (`backend/crm_app/permissions/platform_docs.py:49-53,158-186`,
  `backend/crm_app/api/settings.py`)
- **backend_v2:** System Manager or Administrator list, read, create, change, rename and
  delete an Email Account and call `setup/`; any other caller gets an empty list, 403
  "No permission for Email Account <name>" on a record, and 403 "Not permitted" on
  `setup/`. A User's `user_emails` rows stay System Manager's to write
- **Why:** upstream's role table (`frappe/email/doctype/email_account/email_account.json`,
  v15): System Manager reads, writes, creates and deletes; Inbox User, a role this
  product does not have, reads
- **Recorded by:** A-48 group 2, 20 Nov 2026

### PE-28. The role actions do not take Administrator or Guest as their target

- **Status:** approved by the owner (20 Nov 2026; `temp` A-48 2c); built with this entry
- **Where:** `POST /api/v1/users/<name>/update-role/`, `POST /api/v1/users/add-existing/`
  and `POST /api/v1/users/<name>/remove-crm-roles/` (old `crm.api.user.update_user_role`,
  `add_existing_users`, `remove_crm_roles_from_user`)
- **Old backend:** applies no check on the target's name; the role rows of Administrator
  or Guest change like any other user's (`backend/crm_app/api/user.py:111-217`)
- **backend_v2:** 403 "Not permitted" when the target is Administrator or Guest. The
  check runs after every existing refusal and just before the roles change, so each
  answer upstream gives (such as "Only System Managers can modify other System Managers"
  for a Sales Manager acting on Administrator, who holds System Manager) is unchanged;
  `add-existing` applies it to each name in turn, as every other refusal in that loop
- **Why:** upstream's framework fixes those two accounts' roles whatever their role rows
  say: v15 `frappe/permissions.py:497-507` answers Guest with the Guest role and
  Administrator with every role, and `frappe/core/doctype/user/user.py:626-628` strips
  Guest's rows to Guest on save
- **Recorded by:** A-48 group 2, 21 Nov 2026

### PE-29. Contact, CRM Organization, CRM Industry and Address need a CRM role

- **Status:** approved by the owner (20 Nov 2026; `temp` A-48 2d, A-61 item 4); built
  with this entry for CRM Industry and Address; Contact and CRM Organization to be built
  with their milestones, and until then they are not served
- **Where:** `/api/v1/industries/...` and `/api/v1/addresses/...`: list, create, read,
  PATCH, delete, `value/`, `search/` and every other route that reads the list or the
  object rule (old `/api/resource/CRM Industry`, `/api/resource/Address`)
- **Old backend:** every signed-in user lists, reads, creates and changes them; CRM
  Industry registers no rule, Address deletes only for System Manager or Administrator
  (`backend/crm_app/permissions/platform_docs.py:424-434`; DECISIONS 58)
- **backend_v2:** Sales User, Sales Manager, System Manager or Administrator; a caller
  with none of these gets an empty list, 403 "No permission for <doctype> <name>" on a
  record, and 403 on create. Address delete stays System Manager's or Administrator's.
  Salutation and Gender keep their rule (everyone reads, System Manager writes)
- **Why:** upstream's role tables grant these doctypes to the CRM roles (a user with
  none keeps only the contacts they created; `backend_v2` grants nothing)
- **Recorded by:** A-48 group 2, 21 Nov 2026

---

## Candidates — not exceptions yet

One candidate from `specs/KNOWN_ISSUES.md` §7, for ACTIVITIES: `assign_to.remove_multiple`
clears every assignee, where upstream's limit of 5 leaves the sixth. Keeping it is parity
with the old backend, and matching upstream would bring its limit back, so probably no
entry. Confirm against `backend/` before proposing one.
