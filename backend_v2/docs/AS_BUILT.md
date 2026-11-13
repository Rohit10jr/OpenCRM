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

`core.models.BaseDocument` supplies the standard document fields, server timestamps,
user foreign keys, fetch-from, email and text-Link validation, and the create lifecycle.
Its seven naming strategies live in `core.naming`; naming-series counters are incremented
under a row lock. `AutoIncrementDocument` replaces the string primary key with an integer
one. Model metadata is declared as ordinary inherited class attributes, without a
metaclass. `tests_support`, installed only by the test settings, contains small models
covering every naming strategy and the generic-layer cases later FOUNDATION briefs use.

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
email and attachment fields. `core.field_access` now reads every field-access declaration
from the model and applies the global `password` and `last_login` sensitivity rule. User
roles are cached only on that `User` instance and can be cleared explicitly or by
`refresh_from_db()`.

`core.fields` supplies encrypted character and text fields. They encrypt before every
database write and remain ciphertext on the instance; `core.secrets` retains the old
prefix, pass-through migration behavior, key failures and changed-key wording. The
authentication routes above are the only application API routes built so far.

## 2. Recipes

These are the sections FOUNDATION must write, because every later unit follows them.
Until then they are headings only; do not guess their contents from
`backend_v2/docs/REBUILD_PLAN.md`, which describes intent, not the result.

### Adding a resource

Start the model by subclassing `BaseDocument`, or `AutoIncrementDocument` for a genuine
integer name. Declare `DOCTYPE` and `NAME_STRATEGY` as class attributes. The other
model declarations are `IS_CHILD_TABLE`, `IS_SINGLE`, `FETCH_FROM`, `EMAIL_FIELDS`, and
`TEXT_LINK_FIELDS`; the last maps a text column to `(app_label.Model, label)`. A field
that deliberately keeps a deleted target's name as audit data is also named in
`ALLOW_DANGLING_LINK_FIELDS`. Later FOUNDATION briefs add the serializer, ViewSet,
allowlists, router registration and recorded access decision.

Creating through Django's ordinary `objects.create()` is intentionally unsupported,
because it cannot supply the required actor. Use `Model(...).save(user=user)`, or
`Model.objects.create_for_user(user=user, ...)`. Updates likewise call
`save(user=user)`. A request passes `request.user`; seeds and scheduled jobs pass
`accounts.roles.ADMINISTRATOR`; an enqueued job passes the user who enqueued it.
Passing `None` or an empty string raises `TypeError` with
`` `user` is required to save a document ``.

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

Declare access rules as model class attributes. `SENSITIVE_FIELDS` are never readable;
`password` and `last_login` are sensitive on every model without being declared.
`RESTRICTED_FIELDS` are readable only by `System Manager`, `Sales Manager`, and the
literal `Administrator`, unless `RESTRICTED_FIELDS_ROLES` replaces those two role names.
`READONLY_FIELDS` are readable but silently ignored on generic writes.
`PRIVILEGED_WRITE_FIELDS` are readable by everyone but writable only by the restricted
roles, unless `PRIVILEGED_WRITE_ROLES` replaces them. Anonymous callers are never
privileged. Pass the `User` instance to `hidden_from(model, user)`,
`is_hidden(model, field, user)`, and `unwritable_by(model, user)`; none reads ambient
request state.

Declare stored credentials with `core.fields.EncryptedCharField` or
`EncryptedTextField`, and also list the field in `SENSITIVE_FIELDS`. Encryption uses only
`FIELD_ENCRYPTION_KEY`; a missing key refuses the write. Read plaintext explicitly with
`document.get_password("fieldname")`. `core.field_access.encrypted_fields(model)` derives
the encrypted names from field types for the credential guard—there is no second list to
maintain. ViewSet allowlists for fields shown, filtered, sorted and searched arrive in
brief 08 and may narrow these declarations, never widen them.

`User.get_roles()` memoises on that instance. Call `user.clear_roles_cache()` after a
test changes group membership in place; `user.refresh_from_db()` clears it automatically.

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

An unsaved document always issues an INSERT (`force_insert=True`). A caller-supplied
name that is already taken therefore raises an integrity error instead of silently
updating the existing row. Names are stored as Frappe supplies them (trimmed where
Frappe trims, never slugified), and only `<` and `>` are forbidden. Every document save
requires the acting `user`; there is no ambient current-user state or Guest fallback.

User admin bulk actions must stay disabled: Django applies them with `QuerySet.update()`,
which skips `User.save()` and therefore skips disabled-user token revocation.

The attribute of an encrypted field is ciphertext after save and after load. Code that
needs the credential must call `get_password()`; direct attribute access is deliberately
not useful.

The old backend's list, which is likely to apply here too, is
`specs/AS_BUILT.md` section 4 — `lead_owner` is the access column, names may contain
slashes, "assigned" has two definitions, underscore caches never bump `modified`.
