# As built — what `backend_v2` actually contains

**Status: FOUNDATION skeleton and account identity built (2026-11-13).**

This file describes the code that exists, not the code that is planned. **Where it and a
spec disagree, this file wins**: specs are written before the code and go stale; this
file is written after the code and is kept true. **Where this file and the code disagree,
the code wins**, and this file is corrected in the same commit.

Each unit updates it before its gate: what it added, and the recipes the next unit
needs. **Paths are from the repository root.**

---

## 1. What exists

The Django project skeleton is in place with separate base, local and test settings.
It installs the ten top-level apps in the settled order, includes each app's currently
empty URLconf explicitly under `/api/v1/`, and exposes Django admin under `/admin/`.

`core` now supplies the Frappe exception classes and error body, the DRF exception
handler, the `{"message": ...}` / `{"data": ...}` envelope renderer, merged input
parsing, surplus-input binding, and `FrappeAPIView` for endpoints that are not resources.
It also supplies the default authenticated permission and the registry-free `DOCTYPE`
and `IS_CHILD_TABLE` model metadata readers. Authentication backends are deliberately
empty until FOUNDATION brief 04; guest views opt out of the default permission.

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

The first account migrations create `User`, the four role groups, and the two built-in
users. Both built-ins start with unusable passwords; Administrator belongs to the
Administrator and System Manager groups. The model declares its sensitive, read-only,
email and attachment fields, but later FOUNDATION briefs add their enforcement and email
validation. There are no application API routes yet.

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

Every view is authenticated by default. A guest endpoint declares
`permission_classes = [AllowAny]`; authentication still runs first once FOUNDATION adds
JWT authentication. No view binds a user into ambient state: pass `request.user` to any
service that needs it.

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

An unknown non-admin URL, under `/api/v1/` or elsewhere, has this body:

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

*None recorded yet.* The old backend's list, which is likely to apply here too, is
`specs/AS_BUILT.md` section 4 — `lead_owner` is the access column, names may contain
slashes, "assigned" has two definitions, underscore caches never bump `modified`.
