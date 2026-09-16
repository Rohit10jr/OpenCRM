# FOUNDATION — the project, the core layer, authentication and the doctype map

**Status: Provisional — awaiting owner review, 2026-09-16.** Nothing it depends on is
missing: it is the first unit. It stays Provisional until the owner has reviewed it and
settled Open question O2 (below).

**One agent, not a fan-out.** Everything here is a convention the other twelve units copy.
Two agents would produce two conventions. **Paths are from the repository root.**

---

## 1. Scope

The `PORT_MAP.md` rows under **FOUNDATION**:

- **Doctypes:** `User` (app `accounts`), `Version` (app `core`, withheld — no route)
- **Method paths (11):** `login`, `logout`, `token/refresh`, `frappe.auth.get_logged_user`,
  and `frappe.client.get`, `get_list`, `insert`, `set_value`, `delete`,
  `get_single_value`, `get_doc_permissions`
- **Routes:** `/api/resource/<DocType>` and `/api/resource/<DocType>/<name>`
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
  each with an empty `urls.py`, `doctypes.py` (`DOCTYPES = {}`) and `tasks.py`.
- **`config/urls.py`**, including every app's `urls.py`.
- **`documents/doctypes.py`**, assembling the map from the thirteen `doctypes.py` modules
  in one literal import list.
- **The Celery beat schedule**, assembled the same way from a `BEAT_SCHEDULE` in each app.

A later unit then only ever edits files inside its own app.

### 1.3 The `core` app

Each item names the old implementation in `backend/` to read first.

| Piece | What it does | Old implementation |
|---|---|---|
| Exceptions and the error body | Every class in `API_CONTRACT.md` section 5, the body builder, and the DRF `EXCEPTION_HANDLER` — including the mapping of DRF, Django, SimpleJWT and database exceptions | `frappe_core/exceptions.py`, `security.py:52-61` |
| Renderers | `{"message": …}`, `{"data": …}`, and sibling keys beside `message` | `frappe_core/renderers.py` |
| Parameters | Merge query and body, JSON-decode query values, drop `cmd`, drop surplus | `frappe_core/method_views.py:71-81`, `whitelist.py:75-92`, `query.py:47-59` |
| `MethodView` and `method_path()` | The base for every method endpoint: verbs, guest access, the 401, the envelope | `frappe_core/method_views.py`, `urls.py` |
| The base document model | Standard fields, the six naming strategies, `validate_name`, the series counter under a row lock, `force_insert` on create, email-field validation, `fetch_from` | `frappe_core/models.py`, `naming.py` |
| Change history | `Version`, tracked fields, and the daily `clear_old_versions` job. **Read `specs/VERSION_HISTORY.md` before touching retention** — the job's name invites a change that deletes the timeline | `frappe_core/versions.py`, `config/celery.py` |
| Filters | The grammar, every operator, case-insensitive `like`, `@me`, `is set`, tree operators — as a DRF filter backend that receives the user explicitly | `frappe_core/filters.py` |
| Ordering, grouping, fields, pagination | `order_by` clauses, `group_by` validation, `fields` selection, `limit_start` / `limit_page_length` with the 500 cap and `0` meaning no limit | `frappe_core/query.py` |
| Field access | Sensitive, restricted, read-only and encrypted, enforced for the response and all five field-naming parameters | `frappe_core/field_security.py`, `secrets.py` |
| Child tables | Inline read, wholesale replace on write, rows written before the parent's validation | `frappe_core/children.py`, `serializers.py:102-139` |
| `DocumentViewSet` | The base every doctype subclasses: list, retrieve, create, update, destroy with the contract's semantics — the create check against the payload, the destination re-check, `LinkExistsError` on a refused delete, one transaction per write | `frappe_core/views.py`, `serializers.py` |
| Row rules | The convention for a list rule (queryset narrowing) and an object rule (DRF permission class) | `frappe_core/permissions.py` |

### 1.4 The first part of `accounts`

- **`User`** as `AUTH_USER_MODEL` — it has to exist before the first migration. The
  primary key is the lowercased email; `Administrator` and `Guest` are real rows with
  unusable passwords; roles are groups (`Administrator`, `System Manager`,
  `Sales Manager`, `Sales User`); `enabled` is what login checks. Port the fields the CRM
  reads (`frappe_platform/models.py:99` onwards) and the seed migration
  (`frappe_platform/migrations/0002_*`).
- **`login`, `logout`, `token/refresh`, `frappe.auth.get_logged_user`** with their exact
  responses, refusals and the refresh-token rotation (`frappe_core/api/auth.py`).
- **The login lockout and the rate limiter**, per IP and per account
  (`frappe_core/security.py`, settings `LOGIN_MAX_CONSECUTIVE_ATTEMPTS=10`,
  `LOGIN_LOCK_INTERVAL_SECONDS=60`).

### 1.5 The first part of `documents`

- **The doctype map** (1.2).
- **`/api/resource/<DocType>` and `/api/resource/<DocType>/<name>`**, dispatching to the
  mapped ViewSet. Unknown, child-table and withheld doctypes answer the same 404
  (`frappe_core/views.py:70-82`, `urls.py:12-27` for names containing slashes).
- **The seven `frappe.client.*` paths** above, each delegating to the mapped ViewSet
  (`crm_app/api/client.py`).

### 1.6 Tooling

- **Test-only doctypes**, installed only under test settings, so the generic layer is
  tested without any CRM model: one per naming strategy, a child table, a singleton, a
  tree, one with sensitive and restricted fields, one that points at another document.
  The old equivalent is `backend/tests_support/`.
- **Guard tests**, rebuilt for a project without a registry:
  1. every doctype in the map has a recorded access decision — ruled, open with a
     reason, or withheld — and a doctype declaring a secret must be ruled;
  2. every credential-shaped field name (`*_token`, `*_secret`, `password`, `api_key`,
     `auth`) is declared, or excused in writing;
  3. no view reads a mapped doctype through `Model.objects` instead of its ViewSet's
     queryset;
  4. every method path `PORT_MAP.md` marks `built` resolves.

  Old equivalents: `tests/test_route_surface.py`, `test_credential_fields.py`,
  `test_phase3_endpoints.py`. **Show each guard failing on a deliberately broken case**
  before trusting it.
- **Seed data** for the dev database: at least what `docs/http/01_auth.http` needs. How
  much more, and from where, is O2.
- **`backend_v2/scripts/parity_diff.py`**: replays a `.http` file against two hosts, each
  run keeping its own captured variables, and compares status and body per block after
  normalising tokens, timestamps and generated names. **It writes its own `.http` parser**
  — nothing in `backend_v2/` imports from `backend/`. The normalisation rules are written
  into `AS_BUILT.md`.

### 1.7 Documentation

`backend_v2/docs/AS_BUILT.md` sections 1–3, every recipe, before the gate.

## 2. Depends on

Nothing.

## 3. Read in `backend/` first

Everything in the tables above, then these tests, which pin behaviour that cost real time
to get right: `tests/test_filters.py`, `test_field_security.py`, `test_naming.py`,
`test_name_validation.py`, `test_name_lookup.py`, `test_envelope.py`,
`test_resource_api.py`, `test_child_rows.py`, `test_auth.py`, `test_security.py`,
`test_hardening.py`, `test_versions.py`, `test_version_retention.py`.

Also `frappe_core/registry.py` and `frappe_core/session.py`, to understand what this unit
replaces rather than to copy them.

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
- **Names:** validated on every insert; stored verbatim; slashes allowed in the URL;
  a name an integer key cannot hold is a 404, not a 500; creating over an existing
  string key is a `DuplicateEntryError`, never a silent overwrite (`models.py:277-286`).
- **Errors:** DRF's `ValidationError` is 417, not 400; SimpleJWT's `InvalidToken` is
  `AuthenticationError`; a refused delete is `LinkExistsError`, checked before
  `IntegrityError`; a malformed filter is a 400, not a 500; an unknown doctype on a method
  is a 404.
- **Login:** the exact spelling of the name first, then case-insensitive; the password is
  checked before "User disabled or missing" is said; both trackers count every failure.
- **Refresh rotation is done by hand**, because the path and envelope are custom and
  SimpleJWT's settings alone do not apply to a hand-written view (`auth.py:146-180`).
- **`logout` requires a token**; it is not a guest endpoint.
- **Decimals are strings in a document and numbers in a list row** (`API_CONTRACT.md`
  section 6).

## 5. Acceptance — the gate

1. `manage.py check` is clean, and migrations apply from empty on `opencrm_v2`.
2. pytest is green in `backend_v2/`: the generic layer on the test-only doctypes, and
   authentication. **Each test that guards a protection is shown failing without it.**
3. Against `backend_v2` on port 8001, the `docs/http/01_auth.http` blocks for `login`,
   `logout`, `token/refresh` and `get_logged_user` pass. The file's other blocks belong to
   ACCOUNTS; the progress report lists them by number.
4. `parity_diff.py` over those blocks is clean, or each difference has a proposed entry
   in `PARITY_EXCEPTIONS.md`.
5. The four guard tests exist, and each has been seen to fail.
6. `AS_BUILT.md` sections 1–3 are written; `PORT_MAP.md` rows are marked; this table's
   status in `specs/README.md` is flipped.
7. Independent review at the highest tier that works (root `CLAUDE.md`), stated in the
   progress report.

## 6. Decisions this unit takes, and records in its progress report

- **Where field-access declarations live** — on the ViewSet, the serializer or the model.
  The plan leans towards the ViewSet, with encryption as a model field type.
- **How a tree operator finds its tree without a registry** — for example, the filter
  backend asking the related model for a method it defines.
- **The body diff's normalisation rules.**
- **How the old backend's per-request role cache is replaced** once there is no ambient
  user (`frappe_core/field_security.py:138-154`).

## 7. Open questions — for the owner, before this spec is Ready

- **O2 — baseline data.** A `seed_dev_data` command written from what the `.http` files
  assume, or reference rows exported from the old backend through its API. It decides how
  much of 1.6's seeding happens here.
- **P3 — keep `/api/resource/`.** This spec assumes yes. If the owner drops it, 1.5 and
  the `.http` suite both change.
- **P10 — Django 5.2.** This spec assumes yes.
