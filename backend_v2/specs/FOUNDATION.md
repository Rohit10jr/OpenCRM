# FOUNDATION — the project, the core layer, the base ViewSet and authentication

**Status: Provisional — awaiting owner review.** Written 2026-09-16; updated 2026-09-21 for
REST routes (REBUILD_PLAN S6–S8). Nothing it depends on is missing: it is the first unit.
It stays Provisional until the owner has reviewed it and settled the open questions in
section 7.

**One agent, not a fan-out.** Everything here is a convention the other twelve units copy.
Two agents would produce two conventions. **Paths are from the repository root.**

---

## 1. Scope

The `PORT_MAP.md` rows under **FOUNDATION**:

- **Doctypes:** `User` (app `accounts`), `Version` (app `core`, withheld — no route)
- **Old paths (11):** `login`, `logout`, `token/refresh`, `frappe.auth.get_logged_user`,
  and the generic document calls `frappe.client.get`, `get_list`, `insert`, `set_value`,
  `delete`, `get_single_value`, `get_doc_permissions`. The first four become routes under
  `/api/v1/auth/`; the seven generic calls become **the base ViewSet's CRUD**, which every
  resource inherits (their per-resource routes are each unit's to prove).
- **Other models:** the naming-series counter, SimpleJWT's token blacklist

Plus the things no row describes, because every row needs them:

### 1.1 The project skeleton

- `backend_v2/manage.py`, `config/settings/{base,local,test}.py` reading
  **`backend_v2/.env`** (django-environ), `backend_v2/.env.example`, a pinned
  `requirements.txt` (REBUILD_PLAN P10), `pytest.ini` and a root `conftest.py`.
- The runtime separation of REBUILD_PLAN section 7: database `opencrm_v2`, test database
  `test_opencrm_v2`, Redis databases 3–6, port 8001.
- `config/asgi.py` and `config/routing.py` with Channels wired and the WebSocket route
  present but served by a placeholder until NOTIFICATIONS; `config/celery.py` with the
  Celery app.

### 1.2 Every shared file, finished before any parallel work

Later units run in parallel and must never edit the same file (root `CLAUDE.md`). So this
unit writes, completely:

- **All thirteen apps**, created under `backend_v2/apps/` and listed in `INSTALLED_APPS`,
  each with an empty `urls.py` (its router, with nothing registered yet) and `tasks.py`.
- **`config/urls.py`**, including every app's `urls.py` under `/api/v1/`.
- **The Celery beat schedule**, assembled from a `BEAT_SCHEDULE` in each app, imported by
  name in one literal list.

A later unit then only ever edits files inside its own app.

### 1.3 The `core` app

Each item names the old implementation in `backend/` to read first.

| Piece | What it does | Old implementation |
|---|---|---|
| Exceptions and the error body | Every class in `API_CONTRACT.md` section 5, the body builder, and the DRF `EXCEPTION_HANDLER` — including the mapping of DRF, Django, SimpleJWT and database exceptions | `frappe_core/exceptions.py`, `security.py:52-61` |
| Renderers | `{"message": …}`, `{"data": …}`, and sibling keys beside `message`; each route applies the envelope of the old path it replaces | `frappe_core/renderers.py` |
| Input parsing | Merge query and body, JSON-decode query values, drop `cmd` and surplus inputs | `frappe_core/method_views.py:71-81`, `whitelist.py:75-92`, `query.py:47-59` |
| The base view for non-resource endpoints | Guest access, the 401 for a missing token (`Not permitted`, as method paths answered), input parsing, the envelope | `frappe_core/method_views.py` |
| The base document model | Standard fields, the six naming strategies, `validate_name`, the series counter under a row lock, `force_insert` on create, email-field validation, `fetch_from` | `frappe_core/models.py`, `naming.py` |
| Change history | `Version`, tracked fields, and the daily `clear_old_versions` job. **Read `specs/VERSION_HISTORY.md` before touching retention** — the job's name invites a change that deletes the timeline | `frappe_core/versions.py`, `config/celery.py` |
| Filters | The grammar, every operator, case-insensitive `like`, `@me`, `is set`, tree operators — as a DRF filter backend that receives the user explicitly. **Built as the working assumption of REBUILD_PLAN O5**; the design may change once discussed | `frappe_core/filters.py` |
| Ordering, grouping, fields, pagination | `order_by` clauses, `group_by` validation, `fields` selection, `limit_start` / `limit_page_length` with the 500 cap and `0` meaning no limit (also O5) | `frappe_core/query.py` |
| Field access | Sensitive, restricted, read-only and encrypted, enforced for the response and all five field-naming parameters | `frappe_core/field_security.py`, `secrets.py` |
| Child tables | Inline read, wholesale replace on write, rows written before the parent's validation | `frappe_core/children.py`, `serializers.py:102-139` |
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
- **The login lockout and the rate limiter**, per IP and per account
  (`frappe_core/security.py`, settings `LOGIN_MAX_CONSECUTIVE_ATTEMPTS=10`,
  `LOGIN_LOCK_INTERVAL_SECONDS=60`).

### 1.5 The route conventions

The conventions every unit follows when it designs its routes, recorded in `AS_BUILT.md`:

- **Resource naming** — plural, lower-case, hyphenated (`leads`, `call-logs`), and how a
  doctype name becomes one.
- **Actions** — `@action` on the ViewSet; hyphenated `url_path`; which verb for which kind
  of action.
- **Document names with slashes** — `R/GA` must be reachable, and
  `/api/v1/organizations/R/GA/` must not be read as an action called `GA`.
- **Requests with no old equivalent** — an unknown URL, a method a route does not allow:
  their Frappe-shaped error bodies (`API_CONTRACT.md` section 5).

The route map's contents are REBUILD_PLAN O6. This unit proposes the conventions; the
owner settles them with the map.

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
- **Seed data** for the dev database: at least what `docs/http/01_auth.http` needs. How
  much more, and from where, is O2.
- **`backend_v2/scripts/parity_diff.py`**: sends each block of a `.http` file to
  `backend/` as written, and to `backend_v2` translated through the route map — path,
  method and any reshaped input — each run keeping its own captured variables. It
  compares status and body per block after normalising tokens, timestamps and generated
  names. **It writes its own `.http` parser** — nothing in `backend_v2/` imports from
  `backend/`. The normalisation rules and the translation are written into `AS_BUILT.md`.

### 1.7 Documentation

`backend_v2/docs/AS_BUILT.md` sections 1–3, every recipe, and the route conventions,
before the gate.

## 2. Depends on

Nothing — except that its route rows need the route-map conventions settled (O6).

## 3. Read in `backend/` first

Everything in the tables above, then these tests, which pin behaviour that cost real time
to get right: `tests/test_filters.py`, `test_field_security.py`, `test_naming.py`,
`test_name_validation.py`, `test_name_lookup.py`, `test_envelope.py`,
`test_resource_api.py`, `test_child_rows.py`, `test_auth.py`, `test_security.py`,
`test_hardening.py`, `test_versions.py`, `test_version_retention.py`.

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
  silent overwrite (`models.py:277-286`).
- **Errors:** DRF's `ValidationError` is 417, not 400; SimpleJWT's `InvalidToken` is
  `AuthenticationError`; a refused delete is `LinkExistsError`, checked before
  `IntegrityError`; a malformed filter is a 400, not a 500; an input naming an unknown
  doctype is a 404.
- **Login:** the exact spelling of the name first, then case-insensitive; the password is
  checked before "User disabled or missing" is said; both trackers count every failure.
- **Refresh rotation is done by hand**, because the route and envelope are custom and
  SimpleJWT's settings alone do not apply to a hand-written view (`auth.py:146-180`).
- **`logout` requires a token**; it is not a guest endpoint.
- **Decimals are strings in a document and numbers in a list row** (`API_CONTRACT.md`
  section 6).

## 5. Acceptance — the gate

1. `manage.py check` is clean, and migrations apply from empty on `opencrm_v2`.
2. pytest is green in `backend_v2/`: the generic layer on the test-only resources, and
   authentication. **Each test that guards a protection is shown failing without it.**
3. The `docs/http/01_auth.http` blocks for login, logout, token refresh and the logged-in
   user, sent to `backend_v2` on port 8001 through the route map, get the same status and
   body as the originals get from `backend/` — `parity_diff.py` clean, or each difference
   with a proposed entry in `PARITY_EXCEPTIONS.md`. The file's other blocks belong to
   ACCOUNTS; the progress report lists them by number.
4. The four guard tests exist, and each has been seen to fail.
5. `AS_BUILT.md` sections 1–3 and the route conventions are written; `PORT_MAP.md` rows
   are marked; this unit's status in `specs/README.md` is flipped.
6. Independent review at the highest tier that works (root `CLAUDE.md`), stated in the
   progress report.

## 6. Decisions this unit takes, and records in its progress report

- **Where field-access declarations live** — on the ViewSet, the serializer or the model.
  The plan leans towards the ViewSet, with encryption as a model field type.
- **How a tree operator finds its tree without a registry** — for example, the filter
  backend asking the related model for a method it defines.
- **How a route carries a document name containing slashes.**
- **The body diff's normalisation rules, and how it translates a request.**
- **How the old backend's per-request role cache is replaced** once there is no ambient
  user (`frappe_core/field_security.py:138-154`).

## 7. Open questions — for the owner, before this spec is Ready

- **O2 — baseline data.** A `seed_dev_data` command written from what the `.http` files
  assume, or reference rows exported from the old backend through its API.
- **O5 — the filter, sort and pagination design.** This spec builds Frappe's grammar
  unchanged, as the working assumption.
- **O6 — the route map**, at least its conventions and the four auth routes.
- **O7 — where the generic operations live** (bulk actions, rename, link search, the
  list view). It decides whether the base ViewSet carries hooks for them.
- **P10 — Django 5.2.** This spec assumes yes.
