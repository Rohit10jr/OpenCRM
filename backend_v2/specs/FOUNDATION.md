# FOUNDATION — the project, the core layer, the base ViewSet and authentication

**Status: Ready** — spec-checked and reviewed by the owner, 12 Nov 2026. Section 6 is
fully settled (13 Nov 2026). Everything here is a convention every later unit copies. **Paths are from the
repository root.**

---

## 1. Scope

The `PORT_MAP.md` rows under **FOUNDATION**:

- **Doctypes:** `User` (app `accounts`), `Version` (app `core`, withheld — no route)
- **Old paths (12):** `login`, `logout`, `token/refresh`, `frappe.auth.get_logged_user`,
  and the generic document calls `frappe.client.get`, `get_list`, `get_value`, `insert`,
  `set_value`, `delete`, `get_single_value`, `get_doc_permissions`. The first four become
  routes under `/api/v1/auth/`. The eight generic calls become **routes on the base
  classes**, which every resource inherits (their per-resource routes are each unit's to
  prove). Five are plain CRUD; three are not, and get small routes of their own (section
  6, Q8):

  | Old call | What it answers (`crm_app/api/client.py`) | Base route |
  |---|---|---|
  | `get_list` | rows | `GET <resource>/` |
  | `get` by `name` | one document | `GET <resource>/<name>/` |
  | `get` by `filters` | the first permitted match; 404 if none; 417 `name or filters is required` | **not served: no caller** (PE-3) |
  | `insert` | the created document | `POST <resource>/` |
  | `set_value` | the updated document; `fieldname` is a field name plus `value`, or a dict | `PATCH <resource>/<name>/` with the fields in the body |
  | `delete` | `null`, after the dynamic-link check | `DELETE <resource>/<name>/` |
  | `get_value` | `{}`, a dict, a scalar, a list or `None`, by `fieldname` and `as_dict` | `GET <resource>/value/` |
  | `get_single_value` | a scalar or `None`, with the singleton's field and object checks | `GET <settings>/value/` |
  | `get_doc_permissions` | `{"permissions": {...}}`, an empty map for a missing row | `GET <resource>/<name>/permissions/` |

  Old inputs keep their names on the three new routes (S7). `set_value` and `delete` on
  an editable child row (`CLIENT_EDITABLE`: Contact Email and Contact Phone only, edited
  by `useContactFields.ts`) answer through the parent; CONTACTS builds them (section 6).
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

### 1.2 Every shared file, written once

Units are built one at a time (`specs/README.md`), but the files every unit would touch
are still written here, completely, so no later unit reopens them:

- **All ten apps**, at the top level of `backend_v2/` (imported as `core`, `accounts`, …;
  section 6, Q7) and listed in `INSTALLED_APPS`, each with an empty `urls.py` (its
  router, with nothing registered yet) and `tasks.py`.
- **`config/urls.py`**, including every app's `urls.py` under `/api/v1/`.
- **The Celery beat schedule**, assembled from a `BEAT_SCHEDULE` in each app, imported by
  name in one literal list.

A later unit edits its own app's files. Where apps are shared by several units —
`core` (FOUNDATION, SHARED_ACTIONS, DATA_IMPORT) and `accounts` (FOUNDATION, ACCOUNTS) —
each unit's spec names the files it adds.

### 1.3 The `core` app

Each item names the old implementation in `backend/` to read first.

| Piece | What it does | Old implementation |
|---|---|---|
| Exceptions and the error body | Every class in `API_CONTRACT.md` section 5, the body builder, and the DRF `EXCEPTION_HANDLER` — including the mapping of DRF, Django, SimpleJWT and database exceptions, and keeping the `Retry-After` and `WWW-Authenticate` headers | `frappe_core/exceptions.py` (classes, body, and the mapping and handler at `:179-369`); `RateLimitExceededError` and `SecurityException` are defined in `frappe_core/security.py` |
| Renderers | `{"message": …}`, `{"data": …}`, and sibling keys beside `message`; each route applies the envelope of the old path it replaces | `frappe_core/renderers.py` |
| Input parsing | Merge query and body, JSON-decode query values, drop `cmd` and surplus inputs | the input handling in `frappe_core/method_views.py`, `whitelist.py` and `query.py` |
| The base view for non-resource endpoints | Guest access, the 401 for a missing token (`Not permitted`, as method paths answered), input parsing, the envelope | `frappe_core/method_views.py` |
| The base document model | Standard fields, the seven naming strategies (`NamingSeries`, `FieldValue`, `Hash`, `Format`, `Prompt`, `AutoIncrement`, and `DataImportTimestamp`, which only Data Import uses), `validate_name`, the series counter under a row lock, `force_insert` on create, email-field validation, `fetch_from`, and `null` stored as `""` on a non-null text or select field | `frappe_core/models.py`, `naming.py`, `serializers.py:90-103` |
| Change history | `Version`, tracked fields, and the daily `clear_old_versions` job. **Read `specs/VERSION_HISTORY.md` before touching retention** — the job's name invites a change that deletes the timeline | `frappe_core/versions.py`; the job itself is `crm_app/tasks.py:clear_old_versions`, scheduled in `config/celery.py` |
| Filters | The grammar, every operator, case-insensitive `like`, `@me`, `is set`, tree operators — as a DRF filter backend that receives the user explicitly. Frappe's format, kept for now (REBUILD_PLAN S23) | `frappe_core/filters.py` |
| Ordering, grouping, fields, pagination | `order_by` clauses, `group_by` validation, `fields` selection, `limit_start` / `limit_page_length` with the 500 cap and `0` meaning no limit (S23) | `frappe_core/query.py` |
| Field access | Sensitive, restricted, read-only and encrypted, enforced for the response and all five field-naming parameters | `frappe_core/field_security.py`, `secrets.py` |
| Child tables | Inline read, wholesale replace on write. **The order differs by write:** on update the rows are written before the parent's validation; on create the parent is saved first, then the rows are written, then the parent is refreshed and saved again — all in one transaction | `frappe_core/children.py`, and `frappe_core/serializers.py:145-186` |
| `DocumentViewSet` | The base every resource subclasses and registers on its app's router: list, retrieve, create, partial update, destroy, and the three non-CRUD routes of section 1, with the contract's semantics — the create check against the payload, the destination re-check, the dynamic-link check before a delete, `LinkExistsError` on a refused delete, the duplicate-name refusal, one transaction per write, `doctype` on every serialized document and child row | `frappe_core/views.py`, `serializers.py`, `crm_app/api/client.py` |
| Row rules | The convention for a list rule (queryset narrowing) and an object rule (DRF permission class) | `frappe_core/permissions.py` |

### 1.4 The first part of `accounts`

**Who owns `User`** (section 6, Q9): FOUNDATION builds the model, its seed migration,
the four auth routes, the issuing and checking of `token_version`, and revocation whenever
a disabled user is saved. **ACCOUNTS** builds the `/api/v1/users/` routes, ports
`test_user_access.py`, and owns the password-change and password-reset revocation triggers.

- **`User`** as `AUTH_USER_MODEL` — it has to exist before the first migration. The
  primary key is the lowercased email (stripped); `Administrator` and `Guest` are real
  rows and keep their capitals; roles are groups (`Administrator`, `System Manager`,
  `Sales Manager`, `Sales User`); `enabled` is what login checks. The seed migration
  creates both built-ins with unusable passwords; **`Guest` stays unusable**, while
  `seed_dev_data` gives `Administrator` a password (section 1.6). Port the fields the CRM
  reads (`frappe_platform/models.py:99` onwards), the model's own field declarations
  (`:110-304`), and the seed migration
  (`frappe_platform/migrations/0002_seed_roles_and_users.py`).
- **Login, logout, token refresh and the logged-in user**, as routes under
  `/api/v1/auth/`, with the exact responses, refusals and refresh-token rotation of the
  old paths (`frappe_core/api/auth.py`).
- **`User.token_version`**, never on the wire: every token carries it, and refresh and
  authentication refuse a token whose version is stale
  (`frappe_core/authentication.py:VersionedJWTAuthentication`, applied in `get_user` so
  the WebSocket consumer gets it too; `tests/test_token_version.py`; KNOWN_ISSUES §6,
  fixed). FOUNDATION also builds `bump_token_version` (`authentication.py:38-47`), the one
  function that revokes every token at once. **Ordinary logout does not bump it** — it
  only blacklists the refresh token handed in (`auth.py:logout`). FOUNDATION bumps it on
  every `User.save()` while disabled (`frappe_platform/models.py:280-288`); ACCOUNTS owns
  the password-change and password-reset callers.
- **Restricted Django admin for `User`** — it can change only `enabled`; names, email and
  full name are read-only, built-in users cannot be disabled, add and delete are refused,
  and bulk actions are off so `QuerySet.update()` cannot bypass token revocation
  (`frappe_platform/admin.py`).
- **The login lockout:** login uses the consecutive-failure tracker on two keys, the
  client IP and the normalised account (`frappe_core/security.py`, `auth.py:login`).
  Settings `LOGIN_MAX_CONSECUTIVE_ATTEMPTS` and `LOGIN_LOCK_INTERVAL_SECONDS` are read
  from the environment, **defaults 10 and 60** (`config/settings/base.py:203-204`). The
  tracker's storage is shared across processes (Redis), and the client IP is taken
  through `TRUSTED_PROXY_COUNT`, never from a blindly trusted `X-Forwarded-For`
  (`security.py:18-26`, `68-98`; `settings/base.py:184-210`).
- **The rate limiter** (`security.py:203-260`, per endpoint and IP, optionally per
  account) is built here as a reusable piece. **Login does not use it**, on purpose
  (`auth.py:47-55`: a hard cap there locks out an office behind one NAT address). ACCOUNTS
  proves it on the reset and update-password routes.

### 1.5 The route naming rules

The rules are settled — REBUILD_PLAN S25. This unit **builds them into the base classes**
so every later unit gets them for free, and records how in `AS_BUILT.md`:

- **PATCH only** — the base ViewSet switches off DRF's default PUT.
- **Singletons** — a base for settings records that have no name in the URL (`GET` and
  `PATCH` only).
- **Optional trailing slash** on every route.
- **Names with slashes** — `R/GA` must be reachable, with action routes matched before
  the record route, so `/api/v1/organizations/R/GA/` is the record and not an action
  called `GA`. How: section 6, Q3.
- **Requests with no old equivalent** — decided in section 6, Q11: a method a route does
  not allow answers **405** with an `Allow` header, and an unknown URL **404**, both in
  the Frappe error shape (`API_CONTRACT.md` section 5).

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
    `backend/crm_app/setup.py`, `after_install()` at `:556-575`: lead, deal and
    communication statuses, industries, lead sources, lost reasons, countries,
    languages, currencies, genders, salutations, dropdown items, field layouts, quick
    filters, the user menu, form scripts, the manager dashboard; pinned by
    `tests/test_seed_defaults.py:46-65`), and the users the `.http` suite and browser
    tests log in as, with passwords from `backend_v2/.env`. **`seed_e2e_users` creates only
    the first two of the four**, so the command goes further than it:

    | User | Role | Password from |
    |---|---|---|
    | `Administrator` | Administrator | `ADMIN_PWD` |
    | `ada@example.com` | Sales User | `SALES_PWD` |
    | `grace@example.com` | Sales Manager | `MANAGER_PWD` |
    | `alan@example.com` | Sales User | `SALES2_PWD` |

    (`seed_e2e_users.py:21-53`; the last two are logged in as by `docs/http/07`, `11`,
    `12` and `13`.) A flag adds upstream's demo records from `crm/demo/`. Running it twice
    must not create duplicates.
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

Nothing. Its rows in the route map — the four auth routes — are written
(`PORT_MAP.md`, FOUNDATION; REBUILD_PLAN S8, S25).

## 3. Read in `backend/` first

Everything in the tables above, then the tests below. **A test is "port" when it sends a
request** (`APIClient`, `auth_api`, `api_as`, the `api` fixture) and "rewrite" when it
calls functions, models or reads source (REBUILD_PLAN S14). Classified by the spec check
of 12 Nov 2026 over all 119 files in `backend/tests/`.

**Port** — new URLs, methods and imports, the same expected answers: `test_auth.py`,
`test_hardening.py`, `test_envelope.py`, `test_resource_api.py`, `test_child_rows.py`,
`test_numeric_filter_values.py`, `test_singleton_names.py`,
`test_client_get_value.py`, `test_route_surface_review.py`, `test_wire_shapes.py`,
`test_document_doctype_key.py`, `test_null_as_blank.py`.

**Mixed — port the request tests, rewrite the rest.** The brief that takes a file names
its tests on each side:

| File | Port | Rewrite |
|---|---|---|
| `test_name_validation.py` | slash names reachable, updated, deleted, listed (`:128-177`) | the naming checks |
| `test_name_lookup.py` | invalid key, duplicate name, resource and method answers (`:27-78`) | `by_name` |
| `test_field_security.py` | the API cases at its end | the direct field, filter and query cases |
| `test_security.py` | login and change-password requests (change-password is ACCOUNTS') | tracker, middleware, limiter |
| `test_token_version.py` | the request cases | direct token and authentication calls |
| `test_unrouted_doctypes.py` | the API attacks | registry assertions, timeline internals |
| `test_phase3_endpoints.py` | the generic-client group (around `:1181-1330`) and the auth cases; each later unit ports its own | source scans, registry checks |
| `test_delete_link_check.py`, `test_delete_dependants.py` | the base-delete cases | — |
| `test_platform_models.py` | only the `User` and global field-security cases: their request tests | the same cases' direct tests; the rest of the file is not FOUNDATION's |
| `test_permissions.py` | only the base permission call sites: their request tests | the same cases' direct tests; the rest is not FOUNDATION's |
| `test_disable_user.py` | only the token-revocation cases | — (disabling itself is ACCOUNTS') |

**Rewrite** — read for the behaviour, write again against the new code:
`test_filters.py`, `test_naming.py`, `test_versions.py`, `test_version_retention.py`,
`test_route_surface.py`, `test_credential_fields.py`, `test_seed_defaults.py`,
`test_seed_e2e_users.py`, and the `User` normalisation cases of
`test_contact_naming.py`.

**Not FOUNDATION's:** `test_user_access.py` (ACCOUNTS, section 1.4).

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
- **The lockout cannot be bypassed:** its storage is shared across processes, and the
  client IP honours only `TRUSTED_PROXY_COUNT` proxies — a per-process cache or a trusted
  `X-Forwarded-For` defeats it (`frappe_core/security.py:18-26`, `68-98`).
- **`password` and `last_login` are sensitive on every model**, without a declaration
  (`frappe_core/field_security.py:28-35`).
- **A secret is hidden and encrypted, both** — hidden but stored in plain text, or
  encrypted but served, were each real defects
  (`tests/test_credential_fields.py:test_a_true_secret_is_both_hidden_and_encrypted`).
- **Every serialized document and child row carries `doctype`**
  (`frappe_core/serializers.py:105-130`; `test_document_doctype_key.py`).
- **`_assign`, `_liked_by` and `_comments` are JSON strings, not arrays**, in a document
  and in a list row alike (`serializers.py:122-124`, `query.py:266-279`;
  `test_wire_shapes.py`).
- **`null` sent for a non-null text or select field is stored as `""`** — the frontend
  clears fields that way (`serializers.py:90-103`; `test_null_as_blank.py`).
- **Delete checks dynamic links before removing a row**, not only the database's foreign
  keys (`frappe_core/views.py:234-239`, `crm_app/api/client.py:client_delete`;
  `test_delete_link_check.py`, FINDINGS 76).
- **Decimals are strings in a document and numbers in a list row** (`API_CONTRACT.md`
  section 6).

## 5. Acceptance — the gate

1. `manage.py check` is clean, and migrations apply from empty on `opencrm_v2`.
2. pytest is green in `backend_v2/`: **every test in section 3's port list, passing with
   its expected answers unchanged** (or changed only by an approved
   `PARITY_EXCEPTIONS.md` entry), plus new tests for the generic layer on the test-only
   resources where no old test exists. **Each test that guards a protection is shown
   failing without it.**
3. FOUNDATION's `.http` blocks get the same status and body from `backend_v2` (port
   8001) as their originals get from `backend/` — `parity_diff.py` clean, or each
   difference with a proposed entry in `PARITY_EXCEPTIONS.md`:

   | File | FOUNDATION's blocks | ACCOUNTS' blocks |
   |---|---|---|
   | `01_auth.http` | 1.1–1.11, 1.13, 2.1–2.10 | 2.12 (the fresh login that sets up the rest), 3.1–3.3, 4.1–4.11 (4.8, 4.9 and 4.11 log in, but test a password change), 5.1–5.3 |
   | `99_lockout.http` | 1.1–2.2 (login's IP and account tracker) | 3.1 (`update_password`) |

   **Blocks whose verb has no new route** are not translated (section 6, Q4): `01_auth`
   1.12 (`GET login`, old answer 403 `Method login does not accept GET`) and 2.11
   (`GET logout`, old answer 200). Each becomes a tagged negative case in
   `backend_v2/http/` expecting the new 405 (Q11), outside the body comparison. The old
   `POST get_logged_user` and `GET token/refresh` had no block; their 405s get one
   negative case each. The progress report lists ACCOUNTS' blocks by number.
4. The four guard tests exist, and each has been seen to fail.
5. `AS_BUILT.md` sections 1–3 and the route conventions are written; `PORT_MAP.md` rows
   are marked; this unit's status in `backend_v2/specs/README.md` is flipped.
6. Independent review at the highest tier that works (root `CLAUDE.md`), stated in the
   progress report.

## 6. Questions for the owner — after the spec check, before the first build brief

Codex builds what is decided; it does not decide (root `AGENTS.md`). Claude proposed an
answer to each after the spec check; **the owner settled Q1–Q11 on 12 Nov 2026**. The
answers go into the briefs and then into `AS_BUILT.md`.

| # | Question | Answer |
|---|---|---|
| Q1 | Where field-access declarations live | **On the model**, as class attributes — sensitive, restricted, read-only, encrypted — as `backend/` has them (`field_security.py:38-176`); encryption is a model field type. The ViewSet carries only the opt-in lists of fields shown, filtered, sorted and searched (rule 10). A rule on the ViewSet would leave a second ViewSet over the same model unprotected — the "second door" defect, six times in the old backend |
| Q2 | How a tree operator finds its tree without a registry | `core` provides an abstract `TreeDocument` base — **storing Frappe's `lft`/`rgt` nested set, not treebeard** (amended 13 Nov, below). The filter backend follows the field to `_meta.get_field(f).related_model` and checks `issubclass(..., TreeDocument)`; otherwise 400 `Invalid Filter`. The old refusal text names old internals (`No tree resolver registered for …`, `filters.py:_tree_op`), so the new wording needs a `proposed` entry in `PARITY_EXCEPTIONS.md` before it is built |
| Q3 | How a route carries a name with slashes | A small `core.routers.DocumentRouter` (a `SimpleRouter` subclass): the name matches `.+?`, the trailing slash is optional, and routes are registered collection actions → record actions → record. DRF's default order puts the record before record actions, which would read `R/GA/convert/` as a record. The old route is `(?P<name>.+?)` (`frappe_core/urls.py:12-26`). S25 (8)'s known limit stands |
| Q4 | What the body comparison ignores, and how the REST copy is generated | **Ignore:** one list of JSON paths in a file under `backend_v2/scripts/` — tokens, `creation`/`modified`, names from series, hash and autoincrement naming; an ignored value must still be present and of the same type. **Generate:** each block rewritten from the route map; a block whose verb has no new route becomes a tagged negative case, outside the comparison (section 5, item 3) |
| Q5 | How the per-request role cache is replaced | Cached on the user instance, as Django's `ModelBackend` does with `_perm_cache`. The user lives for one request and is passed along (S16); never a cross-request cache (old: `field_security.py:178-194`) |
| Q6 | Where an app declares its list definition for `get_data` | A small class in the app's `list_views.py`, named by the ViewSet's `list_view_class` attribute. Columns and kanban defaults are presentation, and the list-view mixin sits on the ViewSet (S24). (Old: static methods on the model, `registry.py:90-134`) |
| Q7 | `backend_v2/apps/` or top level | **Top level**, imported as `core`, `accounts`, …; REBUILD_PLAN section 4 corrected |
| Q8 | The `frappe.client` calls that are not CRUD | Each gets a small route on the base classes (section 1 table). `get` by `filters` is not served (PE-3); `set_value`/`delete` on a child row go to CONTACTS — below |
| Q9 | Who owns `User` | FOUNDATION: model, migration, auth routes, issuing and checking `token_version`, and revocation on every save while disabled. ACCOUNTS: `/api/v1/users/`, `test_user_access.py`, and password-change and password-reset revocation (section 1.4; amended by owner, 13 Nov 2026) |
| Q10 | The "parallel work" premise | Dropped; units are built one at a time. FOUNDATION still writes the shared files once (section 1.2) |
| Q11 | Requests with no old equivalent | A disallowed method is **405** with `Allow`; an unknown URL is **404**; both in the Frappe error shape (`API_CONTRACT.md` section 5). No client sends either; S19 moves towards DRF's shapes anyway |

**Settled after the first answers (owner, 12 Nov 2026):**

- **PE-2** (the tree-filter refusal's wording) is approved.
- **`set_value` and `delete` on a child row** are not on the base. Only Contact Email and
  Contact Phone opt in (`CLIENT_EDITABLE`, `frappe_platform/models.py:541`, `565`), for
  the contact page (`useContactFields.ts`; FINDINGS 67). **CONTACTS** gives those two
  rows nested routes under their contact, and updates `API_CONTRACT.md`'s "a child row is
  never reachable on its own" with that exception when it builds them.

**Settled after the overnight run (owner, 13 Nov 2026):**

- **`get` by `filters` is not served** (PE-3): no caller — the three frontend callers
  pass `name`, no seeded form script calls `get`; only `docs/http/13_bulk_and_misc.http`
  2.5–2.7 test it, and they get no REST copy.
- **Trees keep Frappe's nested set**, not treebeard (Q2 amended). `TreeDocument` carries
  `lft`/`rgt` and the parent link, which are on the wire, and ports the old rebuild with
  its locking (`backend/crm_app/permissions/tree.py`). The owner compared treebeard:
  `NS_Node` numbers every top-level node after the first wrongly, and `MP_Node` has no
  `lft`/`rgt`. Treebeard is out of the stack and `requirements.txt`.
- **`save()` requires the user** — no default. Seeds and background jobs pass one
  explicitly, matching Frappe version-15: **scheduled jobs run as `Administrator`** (the
  scheduler calls `frappe.connect()`, which sets Administrator,
  `frappe/__init__.py:298-299`), and **an enqueued job runs as the user who enqueued
  it** (`enqueue` captures `frappe.session.user`, `frappe/utils/background_jobs.py:145`;
  `execute_job` sets it, `:204`). A seed runs as `Administrator`, as upstream's install
  step does.
