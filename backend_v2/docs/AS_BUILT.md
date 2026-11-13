# As built — what `backend_v2` actually contains

**Status: FOUNDATION skeleton, account identity, and authentication built (2026-11-13).**

This file describes the code that exists, not the code that is planned. **Where it and a
spec disagree, this file wins**: specs are written before the code and go stale; this
file is written after the code and is kept true. **Where this file and the code disagree,
the code wins**, and this file is corrected in the same commit.

Each unit updates it before its gate: what it added, and the recipes the next unit
needs. **Paths are from the repository root.**

---

## 1. What exists

The Django project skeleton is in place with separate base, local and test settings.
It installs the ten top-level apps in the settled order, includes each app's URLconf
explicitly under `/api/v1/`, and exposes Django admin under `/admin/`.

`core` now supplies the Frappe exception classes and error body, the DRF exception
handler, the `{"message": ...}` / `{"data": ...}` envelope renderer, merged input
parsing, surplus-input binding, and `FrappeAPIView` for endpoints that are not resources.
It also supplies the default authenticated permission and the registry-free `DOCTYPE`
and `IS_CHILD_TABLE` model metadata readers. Authentication backends are deliberately
limited to `accounts.authentication.VersionedJWTAuthentication`; guest views opt out of
the default permission, while authentication still runs when they carry a token.

The four authentication routes are explicit in `accounts/urls.py`: login and refresh
are guest POST endpoints, logout is an authenticated POST endpoint, and `auth/me` is an
authenticated GET endpoint. Each accepts the route both with and without its trailing
slash. Login preserves the old input aliases, response shape, case-insensitive account
lookup, disabled-user wording and paired IP/account lockout. Refresh tokens rotate and
are recorded in SimpleJWT's blacklist tables; logout blacklists a supplied refresh token
without revoking other sessions.

Every issued token carries the user's `token_version`. Authentication and refresh both
refuse a stale version, while a missing claim counts as version zero for tokens issued
before this mechanism existed. `accounts.authentication.bump_token_version()` uses an
`F()` update and reloads the user. `User.save()` calls it on every save while the user is
disabled, preventing old tokens from becoming valid again after re-enabling; password
change and reset triggers remain ACCOUNTS' responsibility.

`core.security` resolves the request IP from `REMOTE_ADDR`, consulting
`X-Forwarded-For` only for the configured trusted proxy count. It stores consecutive
login failures in the configured cache, separately for IP and account, and provides a
request-aware rate-limit decorator for the later password endpoints. Login itself uses
the lockout tracker, not the flat rate limiter.

Celery loads one explicit `BEAT_SCHEDULE` from each app and refuses duplicate schedule
keys. Channels sends HTTP to Django and exposes `ws/realtime`; until NOTIFICATIONS adds
the real consumer, every WebSocket connection is closed without acceptance using code
4001.

`accounts.User` is the custom `AUTH_USER_MODEL`. Its string primary key is normalized to
a stripped, lowercased email except for the literal `Administrator` and `Guest` rows. It
stores its own `creation` and `modified` timestamps, exposes `enabled` as Django's
`is_active`, and derives CRM roles from Django groups; the literal Administrator always
also has the Administrator role. `UserManager.create_superuser` grants System Manager,
because CRM authority does not come from Django's `is_superuser` flag.

Django admin exposes `accounts.User` only for enabling and disabling. Identity fields are
read-only, the Administrator and Guest flags are also read-only, adding and deleting are
disabled, and there are no bulk actions.

The first account migrations create `User`, the four role groups, and the two built-in
users. Both built-ins start with unusable passwords; Administrator belongs to the
Administrator and System Manager groups. The model declares its sensitive, read-only,
email and attachment fields, but later FOUNDATION briefs add their enforcement and email
validation. The authentication routes above are the only application API routes built
so far.

## 2. Recipes

These are the sections FOUNDATION must write, because every later unit follows them.
Until then they are headings only; do not guess their contents from
`backend_v2/docs/REBUILD_PLAN.md`, which describes intent, not the result.

### Adding a resource

*Not written yet — FOUNDATION.* Model, serializer, ViewSet with its allowlists, its
registration on the app's router under `/api/v1/`, the recorded access decision, and the
tests the guard tests will demand.

### Adding an action or an endpoint

For an endpoint that is not a resource, subclass `core.views.FrappeAPIView`, implement
only the allowed HTTP methods, and write its route explicitly in its app's `urls.py` and
in the route map. `self.get_inputs(request)` merges query and body inputs, JSON-decodes
query values when possible, lets the body win, and drops `cmd`; the view then reads only
the keys it knows. Return `Response(payload)` or `self.envelope(payload)`: successful
responses use `{"message": payload}` with status 200. Return `WithResponseKeys` when
keys such as `docs` must sit beside `message`.

Apply a flat endpoint limit directly to a view method with
`@rate_limit(limit=..., seconds=...)`. For a per-input bucket, pass `key="email"` or a
callable taking the merged input dictionary, plus `normalise` when equivalent spellings
must share a bucket. The decorator resolves the request from the view-method arguments;
named and callable keys receive the same query-plus-body inputs as the view, with the
body winning and `cmd` removed.

Every view is authenticated by default. A guest endpoint declares
`permission_classes = [AllowAny]`; JWT authentication still runs first when the request
carries a token. No view binds a user into ambient state: pass `request.user` to any
service that needs it. Write both slash forms with one explicit `re_path`, using a final
`/?$`; do not rely on `APPEND_SLASH`, because POST bodies must not be redirected.

Resource actions and their ViewSet base are not built yet.

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

Raise a class from `core.exceptions`, or call `throw(message, exc=ValidationError)`.
Messages are copied verbatim into the scalar `message`, the plain-string `messages`
list, and the double-encoded `_server_messages` list. The available classes and statuses
are:

| Class | Status | Title |
|---|---:|---|
| `ValidationError` | 417 | Message |
| `MandatoryError` | 417 | Message |
| `InvalidEmailAddressError` | 417 | Message |
| `OutgoingEmailError` | 417 | Message |
| `LinkValidationError` | 417 | Message |
| `LinkExistsError` | 417 | Message |
| `PermissionError` | 403 | Not Permitted |
| `SecurityException` | 403 | Message |
| `DoesNotExistError` | 404 | Not Found |
| `AuthenticationError` | 401 | Message |
| `DuplicateEntryError` | 409 | Message (`Duplicate` for a database integrity error) |
| `NameError` | 409 | Message |
| `RateLimitExceededError` | 429 | Message |

`FilterError`, a `ValueError`, is rendered as status 400, `ValidationError`, title
`Invalid Filter`. DRF validation errors become 417 and nested field messages are
flattened. `Http404` and missing Django objects become `DoesNotExistError`; protected
and restricted deletes become `LinkExistsError` before the broader integrity-error
mapping is considered. DRF response headers such as `Retry-After`, `WWW-Authenticate`
and `Allow` are preserved. An exception the handler does not recognize remains a plain
500.

A wrong method has this body (shown for `GET`) and an `Allow` header:

```json
{"exception":"frappe.exceptions.MethodNotAllowed: Method \"GET\" not allowed.","exc_type":"MethodNotAllowed","_server_messages":"[\"{\\\"message\\\": \\\"Method \\\\\\\"GET\\\\\\\" not allowed.\\\", \\\"title\\\": \\\"Message\\\"}\"]","message":"Method \"GET\" not allowed.","messages":["Method \"GET\" not allowed."]}
```

`core.views.frappe_not_found` decides the response for an unknown non-admin URL. A
final catch-all in `config.urls` makes it apply under `/api/v1/` and elsewhere even
when `DEBUG=True`; `handler404` uses the same function for `Http404` resolution when
`DEBUG=False`. Django admin keeps its own 404 pages. The body is:

This 404 holds for every HTTP method, including unsafe requests without a CSRF token.

```json
{"exception":"frappe.exceptions.DoesNotExistError: Not found.","exc_type":"DoesNotExistError","_server_messages":"[\"{\\\"message\\\": \\\"Not found.\\\", \\\"title\\\": \\\"Not Found\\\"}\"]","message":"Not found.","messages":["Not found."]}
```

### Background work and live events

*Not written yet — FOUNDATION wires Celery and Channels; NOTIFICATIONS writes the
recipe.*

## 3. Running it

From the repository root on Windows, create the isolated Python 3.13 environment and
install the exact pinned dependencies:

```powershell
py -3.13 -m venv backend_v2\.venv
backend_v2\.venv\Scripts\python.exe -m pip install -r backend_v2\requirements.txt
```

Settings read only `backend_v2/.env`; it is optional because the skeleton has defaults.
Use `backend_v2/.env.example` when local overrides are needed. Do not reuse the root
`.env`. From `backend_v2/`, check the project or run one test file with:

```powershell
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe -m pytest tests/test_skeleton.py
```

Apply schema and seed migrations to the configured `opencrm_v2` database from the same
directory with:

```powershell
.venv\Scripts\python.exe manage.py migrate
```

This also creates SimpleJWT's `token_blacklist` tables. JWT and auth-security settings
may be overridden with `JWT_ACCESS_TOKEN_LIFETIME_MINUTES`,
`JWT_REFRESH_TOKEN_LIFETIME_DAYS`, `TRUSTED_PROXY_COUNT`,
`LOGIN_MAX_CONSECUTIVE_ATTEMPTS`, and `LOGIN_LOCK_INTERVAL_SECONDS`; their defaults are
5 minutes, 7 days, 0 proxies, 10 failures, and 60 seconds respectively.

Database creation, migrations, seed data, the server on port 8001, the `.http` suite and
the parity body diff are added by later FOUNDATION briefs.

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

User admin bulk actions must stay disabled: Django applies them with `QuerySet.update()`,
which skips `User.save()` and therefore skips disabled-user token revocation.

The old backend's list, which is likely to apply here too, is
`specs/AS_BUILT.md` section 4 — `lead_owner` is the access column, names may contain
slashes, "assigned" has two definitions, underscore caches never bump `modified`.
