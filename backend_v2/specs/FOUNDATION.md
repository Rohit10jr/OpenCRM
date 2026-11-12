# FOUNDATION — the project, the core layer, the base ViewSet and authentication

**Status: Provisional — awaiting owner review.** It is the first unit, so nothing it
depends on is missing; it becomes Ready once the owner has reviewed it and answered
section 6. Everything here is a convention every later unit copies. **Paths are from the
repository root.**

---

## 1. Scope

The `PORT_MAP.md` rows under **FOUNDATION**:

- **Doctypes:** `User` (app `accounts`), `Version` (app `core`, withheld — no route)
- **Old paths (12):** `login`, `logout`, `token/refresh`, `frappe.auth.get_logged_user`,
  and the generic document calls `frappe.client.get`, `get_list`, `get_value`, `insert`,
  `set_value`, `delete`, `get_single_value`, `get_doc_permissions`. The first four become
  routes under `/api/v1/auth/`; the eight generic calls become **the base ViewSet's CRUD**, which every
  resource inherits (their per-resource routes are each unit's to prove).
- **Other models:** the naming-series counter, SimpleJWT's token blacklist

Plus the things no row describes, because every row needs them:

### 1.1 The project skeleton

- `backend_v2/manage.py`, `config/settings/{base,local,test}.py` reading
  **`backend_v2/.env`** (django-environ), `backend_v2/.env.example`, a pinned
  `requirements.txt` (REBUILD_PLAN S17), `pytest.ini` and a root `conftest.py`.
- The runtime separation of REBUILD_PLAN section 7: database `opencrm_v2`, test database
  `test_opencrm_v2`, Redis databases 4–7, port 8001.
- `config/asgi.py` and `config/routing.py` with Channels wired and the WebSocket route
  present but served by a placeholder until NOTIFICATIONS; `config/celery.py` with the
  Celery app.

### 1.2 Every shared file, finished before any parallel work

Later units run in parallel and must never edit the same file (root `CLAUDE.md`). So this
unit writes, completely:

- **All ten apps**, created under `backend_v2/apps/` and listed in `INSTALLED_APPS`,
  each with an empty `urls.py` (its router, with nothing registered yet) and `tasks.py`.
- **`config/urls.py`**, including every app's `urls.py` under `/api/v1/`.
- **The Celery beat schedule**, assembled from a `BEAT_SCHEDULE` in each app, imported by
  name in one literal list.

A later unit then only ever edits files inside its own app.

### 1.3 The `core` app

Each item names the old implementation in `backend/` to read first.

| Piece | What it does | Old implementation |
|---|---|---|
| Exceptions and the error body | Every class in `API_CONTRACT.md` section 5, the body builder, and the DRF `EXCEPTION_HANDLER` — including the mapping of DRF, Django, SimpleJWT and database exceptions | `frappe_core/exceptions.py`, and the exception mapping in `frappe_core/security.py` |
| Renderers | `{"message": …}`, `{"data": …}`, and sibling keys beside `message`; each route applies the envelope of the old path it replaces | `frappe_core/renderers.py` |
| Input parsing | Merge query and body, JSON-decode query values, drop `cmd` and surplus inputs | the input handling in `frappe_core/method_views.py`, `whitelist.py` and `query.py` |
| The base view for non-resource endpoints | Guest access, the 401 for a missing token (`Not permitted`, as method paths answered), input parsing, the envelope | `frappe_core/method_views.py` |
| The base document model | Standard fields, the six naming strategies, `validate_name`, the series counter under a row lock, `force_insert` on create, email-field validation, `fetch_from` | `frappe_core/models.py`, `naming.py` |
| Change history | `Version`, tracked fields, and the daily `clear_old_versions` job. **Read `specs/VERSION_HISTORY.md` before touching retention** — the job's name invites a change that deletes the timeline | `frappe_core/versions.py`, `config/celery.py` |
| Filters | The grammar, every operator, case-insensitive `like`, `@me`, `is set`, tree operators — as a DRF filter backend that receives the user explicitly. Frappe's format, kept for now (REBUILD_PLAN S23) | `frappe_core/filters.py` |
| Ordering, grouping, fields, pagination | `order_by` clauses, `group_by` validation, `fields` selection, `limit_start` / `limit_page_length` with the 500 cap and `0` meaning no limit (S23) | `frappe_core/query.py` |
| Field access | Sensitive, restricted, read-only and encrypted, enforced for the response and all five field-naming parameters | `frappe_core/field_security.py`, `secrets.py` |
| Child tables | Inline read, wholesale replace on write, rows written before the parent's validation | `frappe_core/children.py`, and the child-row handling in `frappe_core/serializers.py` |
| `DocumentViewSet` | The base every resource subclasses and registers on its app's router: list, retrieve, create, partial update, destroy, with the contract's semantics — the create check against the payload, the destination re-check, `LinkExistsError` on a refused delete, the duplicate-name refusal, one transaction per write | `frappe_core/views.py`, `serializers.py`, `crm_app/api/client.py` |
| Row rules | The convention for a list rule (queryset narrowing) and an object rule (DRF permission class) | `frappe_core/permissions.py` |

### 1.4 The first part of `accounts`

- **`User`** as `AUTH_USER_MODEL` — it has to exist before the first migration. The
  primary key is the lowercased email; `Administrator` and `Guest` are real rows with
  unusable passwords; roles are groups (`Administrator`, `System Manager`,
  `Sales Manager`, `Sales User`); `enabled` is what login checks. Port the fields the CRM
  reads (`frappe_platform/models.py:99` onwards) and the seed migration
  (`frappe_platform/migrations/0002_*`).
- **Login, logout, token refresh and the logged-in user**, as routes under
  `/api/v1/auth/`, with the exact responses, refusals and refresh-token rotation of the
  old paths (`frappe_core/api/auth.py`).
- **`User.token_version`**, never on the wire: every token carries it, refresh and
  authentication refuse a token whose version is stale, and logging out of all sessions
  bumps it, so an access token already issued stops working at once
  (`frappe_core/authentication.py`, `tests/test_token_version.py`; KNOWN_ISSUES §6, fixed).
- **The login lockout and the rate limiter**, per IP and per account
  (`frappe_core/security.py`, settings `LOGIN_MAX_CONSECUTIVE_ATTEMPTS=10`,
  `LOGIN_LOCK_INTERVAL_SECONDS=60`).

### 1.5 The route naming rules

The rules are settled — REBUILD_PLAN S25. This unit **builds them into the base classes**
so every later unit gets them for free, and records how in `AS_BUILT.md`:

- **PATCH only** — the base ViewSet switches off DRF's default PUT.
- **Singletons** — a base for settings records that have no name in the URL (`GET` and
  `PATCH` only).
- **Optional trailing slash** on every route.
- **Names with slashes** — `R/GA` must be reachable, with action routes matched before
  the record route, so `/api/v1/organizations/R/GA/` is the record and not an action
  called `GA`.
- **Requests with no old equivalent** — an unknown URL, a method a route does not allow:
  their Frappe-shaped error bodies (`API_CONTRACT.md` section 5).

### 1.6 Tooling

- **Test-only resources**, installed only under test settings, so the generic layer is
  tested without any CRM model: one per naming strategy, a child table, a singleton, a
  tree, one with sensitive and restricted fields, one that points at another document.
  The old equivalent is `backend/tests_support/`.
- **Guard tests**, rebuilt for a project without a registry:
  1. every registered ViewSet has a recorded access decision — ruled, open with a reason,
     or withheld — and a resource declaring a secret must be ruled;
  2. every credential-shaped field name (`*_token`, `*_secret`, `password`, `api_key`,
     `auth`) is declared, or excused in writing;
  3. no view reads a resource's model through `Model.objects` instead of its ViewSet's
     queryset;
  4. every route the route map marks `built` resolves, and no route is served that the map
     does not list.

  Old equivalents: `tests/test_route_surface.py`, `test_credential_fields.py`,
  `test_phase3_endpoints.py`. **Show each guard failing on a deliberately broken case**
  before trusting it.
- **Two management commands for development data** (REBUILD_PLAN S20):
  - `manage.py seed_dev_data` — ports the old backend's `seed_defaults` (data and rules in
    `backend/crm_app/setup.py`: statuses, industries, lead sources, lost reasons, field
    layouts, quick filters, the user menu, form scripts, the manager dashboard) and, as
    `seed_e2e_users` does, the users the `.http` suite and browser tests log in as, with
    passwords from `backend_v2/.env`. A flag adds upstream's demo records
    from `crm/demo/`. Running it twice must not create duplicates.
  - `manage.py clear_dev_data` — removes exactly what the seed added, and nothing else.
  - This unit builds both commands, but seeds only the data its own models can hold (the
    users and roles). Each later unit adds its own defaults to the commands as its models
    appear — statuses with SALES, industries with CONTACTS, and so on.
  - Check that the old backend's demo database holds the same reference rows, so the two
    backends can be compared, and record any gap in the progress report.
- **The REST copy of the `.http` suite** (REBUILD_PLAN S9): a script,
  `backend_v2/scripts/build_http_suite.py`, that reads the old `docs/http/` files and the
  route map and writes `backend_v2/http/` — same file names, requests and expected
  answers, with the new URLs, methods and reshaped inputs. This unit generates the blocks
  whose routes it builds (the auth routes); later units regenerate as they add routes.
- **`backend_v2/scripts/parity_diff.py`**: sends each old block to `backend/` and its REST
  copy to `backend_v2`, each run keeping its own captured variables, and compares status
  and body per block, ignoring what naturally differs (tokens, timestamps, generated
  names). The ignore rules go into `AS_BUILT.md`.
- **Both scripts write their own `.http` parser** — nothing in `backend_v2/` imports from
  `backend/`.

### 1.7 Documentation

`backend_v2/docs/AS_BUILT.md` sections 1–3, every recipe, and the route conventions,
before the gate.

## 2. Depends on

Nothing — except that its rows in the route map (the four auth routes) must be written
first (REBUILD_PLAN S8, S25).

## 3. Read in `backend/` first

Everything in the tables above, then these tests, which pin behaviour that cost real time
to get right: `tests/test_filters.py`, `test_naming.py`, `test_name_validation.py`,
`test_name_lookup.py`, `test_envelope.py`, `test_resource_api.py`, `test_auth.py`,
`test_hardening.py`, `test_versions.py`, `test_version_retention.py`. They test old
internals, so they are read and written again (REBUILD_PLAN S14).

**Tests to port** — they call the API, so they move over with new URLs, methods and
imports and the same expected answers: `test_child_rows.py`, `test_field_security.py`,
`test_security.py`, `test_token_version.py`, `test_numeric_filter_values.py`,
`test_singleton_names.py`, `test_client_get_value.py`, `test_route_surface_review.py`,
`test_unrouted_doctypes.py`, and the generic-layer and auth tests of
`test_phase3_endpoints.py` (each later unit ports that file's tests for its own routes).
The spec check confirms the list.

Also `frappe_core/registry.py`, `whitelist.py` and `session.py`, to understand what this
unit replaces rather than to copy them.

## 4. Must not be lost

Each of these was a real defect in the old backend, found and fixed:

- **Every door to a doctype shares one queryset and one field policy.** Five findings
  across four phases were a guarded endpoint beside an unguarded generic route. A sixth
  was `frappe.client.get_single_value`, which checked sensitive fields and nothing else,
  so every manager-only settings row answered to any user — including the token that is
  the whole authentication on the Exotel webhook (`specs/SECURITY_MODEL.md`, "The second
  door the phase-7 review found").
- **A hidden field is refused in `filters`, `or_filters`, `order_by`, `group_by` and
  `fields`**, not only dropped from the response. A real SMTP password was recovered
  through a `like` filter before this rule existed.
- **Create is checked against an instance carrying the payload**, not an empty one; an
  **update that moves a row onto another document is re-checked there**.
- **Names:** validated on every insert; stored verbatim; slashes allowed; a name an
  integer key cannot hold is a 404, not a 500; creating over a taken name is a
  `DuplicateEntryError` with upstream's `already exists` sentence (finding 25), never a
  silent overwrite (the insert path in `frappe_core/models.py`).
- **Errors:** DRF's `ValidationError` is 417, not 400; SimpleJWT's `InvalidToken` is
  `AuthenticationError`; a refused delete is `LinkExistsError`, checked before
  `IntegrityError`; a malformed filter is a 400, not a 500; an input naming an unknown
  doctype is a 404.
- **Login:** the exact spelling of the name first, then case-insensitive; the password is
  checked before "User disabled or missing" is said; both trackers count every failure.
- **Refresh rotation is done by hand**, because the route and envelope are custom and
  SimpleJWT's settings alone do not apply to a hand-written view (`refresh_token` in
  `frappe_core/api/auth.py`).
- **`logout` requires a token**; it is not a guest endpoint.
- **Decimals are strings in a document and numbers in a list row** (`API_CONTRACT.md`
  section 6).

## 5. Acceptance — the gate

1. `manage.py check` is clean, and migrations apply from empty on `opencrm_v2`.
2. pytest is green in `backend_v2/`: **every test in section 3's port list, passing with
   its expected answers unchanged** (or changed only by an approved
   `PARITY_EXCEPTIONS.md` entry), plus new tests for the generic layer on the test-only
   resources where no old test exists. **Each test that guards a protection is shown
   failing without it.**
3. The login, logout, token refresh and logged-in-user blocks of
   `backend_v2/http/01_auth.http` get the same status and body from `backend_v2` (port
   8001) as their originals in `docs/http/01_auth.http` get from `backend/` —
   `parity_diff.py` clean, or each difference with a proposed entry in
   `PARITY_EXCEPTIONS.md`. The file's other blocks belong to ACCOUNTS; the progress report
   lists them by number.
4. The four guard tests exist, and each has been seen to fail.
5. `AS_BUILT.md` sections 1–3 and the route conventions are written; `PORT_MAP.md` rows
   are marked; this unit's status in `backend_v2/specs/README.md` is flipped.
6. Independent review at the highest tier that works (root `CLAUDE.md`), stated in the
   progress report.

## 6. Questions for the owner — after the spec check, before the first build brief

Codex builds what is decided; it does not decide (root `AGENTS.md`). Claude proposes an
answer to each, the owner settles it, and the answer goes into the briefs and then into
`AS_BUILT.md`:

- **Where field-access declarations live** — on the ViewSet, the serializer or the model.
  The plan leans towards the ViewSet, with encryption as a model field type.
- **How a tree operator finds its tree without a registry** — for example, the filter
  backend asking the related model for a method it defines.
- **How a route carries a document name containing slashes.**
- **What the body comparison ignores, and how the REST copy is generated.**
- **How the old backend's per-request role cache is replaced** once there is no ambient
  user (the role cache in `frappe_core/field_security.py`).
- **Where a CRM app declares its list definition** for `get_data` — on its ViewSet, or a
  small class beside it (moved here from CONFIGURATION, which builds the engine that
  reads it).
- **Whether the apps live in `backend_v2/apps/`** (imported as `apps.core`) or at the top
  level (imported as `core`); REBUILD_PLAN sections 4 and 5 disagree.

The one task left before the spec check: this unit's rows in the route map — the four
auth routes — written with the rules of REBUILD_PLAN S25.