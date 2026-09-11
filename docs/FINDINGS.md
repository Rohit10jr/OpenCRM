# Findings from the API test suite

Defects the `docs/http/*.http` files turned up, one entry each. **Expected** is what
upstream Frappe does, read from its source; **Actual** is what this port answered. A
finding stays here until it is fixed or a decision records that the port diverges on
purpose, in which case the block's expectation is changed and the entry says so.

The block reference (`02 / 6.9`) is the file and block that reproduces it; run that file
through `backend/scripts/run_http.py` and the failing line is the reproduction.

| # | Block | Severity | Summary | Status |
|---|---|---|---|---|
| 1 | 02 / 6.9 | medium | A filter on a field the doctype does not have answers **500** | open |
| 2 | 02 / 10.9, 10.10 | high | A document without a name, or a name containing `<`, answers **500** | open |
| 3 | 02 / 10.11 | medium | Deleting a row another row links to answers **409 DuplicateEntryError** with Django's internal wording | open |
| 4 | 02 / 10.4, 10.5 | low | Serializer validation answers **400**, the port's own validation answers **417**, both as `ValidationError` | open |
| 5 | 01 / 1.11 | medium | An email typed in a different case cannot log in; upstream accepts `Ada@Example.com` | open |
| 6 | 01 / 1.4 | low | A malformed bearer token answers `exc_type: InvalidToken`, not `AuthenticationError` | open |

---

## 1. Unknown field in a filter → 500

**Block:** `02_resource_grammar.http` 6.9 — `filters=[["no_such_field","=","x"]]`

**Expected:** a 4xx with `exc_type: ValidationError`. The port's own contract
(`AS_BUILT.md` §4: "unknown row/field names raise, they are not dropped") and the comment
in `frappe_core/exceptions.py` on `FilterError` both say a malformed filter is a client
error, and `fields=` and `order_by=` already answer 417 for the same mistake.

**Actual:** 500. `filters.resolve_field_path` returns the name unchanged when the model
has no such field, `Q(no_such_field="x")` reaches the ORM, and Django raises `FieldError`,
which nothing catches. With `DEBUG=True` the body is the HTML debug page.

**Where:** `frappe_core/filters.py:build_q` — validate `fieldname` against
`concrete_field_names(model)` before building the `Q`, raising `FilterError`.

**Upstream, for the record:** `frappe/model/db_query.py:prepare_filter_condition` does
not validate the field either; the unknown column reaches MariaDB and the request fails
with a database error. So upstream is also a 500 here. The 4xx expectation is the port's
own contract, not a fidelity requirement, and it is the better behaviour: a typo in a
saved view's filter should not read as a server crash.

## 2. Naming validation errors → 500

**Blocks:** `02_resource_grammar.http` 10.9 (no `organization_name`) and 10.10 (name
`ZZ <script>`)

**Expected:** 417 with Frappe's own messages, `No Name Specified for CRM Organization`
and `Name cannot contain special characters like <>`. Both are `frappe.throw` calls
upstream (`frappe/model/naming.py:validate_name`), and the frontend displays
`messages[0]`.

**Actual:** 500. `frappe_core/naming.py` raises its own `NameError_`, which is not a
`FrappeError`, so `frappe_exception_handler` returns `None` and Django's 500 handler
takes over. The message text is right; it never reaches the client.

**Where:** make `NameError_` subclass `frappe_core.exceptions.ValidationError`, or map it
in the handler. **User-visible:** the Organization form's "Save" with an empty name shows
a generic failure instead of the message written for it.

## 3. Deleting a linked row → 409 with Django's wording

**Block:** `02_resource_grammar.http` 10.11 — `DELETE CRM Industry/ZZ Grammar Industry`
while an organization links to it

**Expected:** 417, `exc_type: LinkExistsError`, message
`Cannot delete or cancel because CRM Industry ZZ Grammar Industry is linked with CRM
Organization ZZ Grammar Alpha` (`frappe/model/delete_doc.py:check_if_doc_is_linked`).
The frontend shows that message.

**Actual:** 409, `exc_type: DuplicateEntryError`, message *"Cannot delete some instances
of model 'CRMIndustry' because they are referenced through protected foreign keys:
'CRMOrganization.industry'."* — Django's `ProtectedError` is a subclass of
`IntegrityError`, and the handler maps every `IntegrityError` to "Duplicate".

**Where:** `frappe_core/exceptions.py` — catch `ProtectedError` before `IntegrityError`
and render it as `LinkExistsError` (417) with the Frappe sentence. The referencing rows
are in `exc.protected_objects`.

## 4. Two status codes for one exc_type

**Blocks:** `02_resource_grammar.http` 10.4 (bad Select value) and 10.5 (Link to a
missing row)

**Expected:** 417. Every validation failure upstream is `frappe.exceptions.ValidationError`
with `http_status_code = 417`, and the port's own `ValidationError` uses 417.

**Actual:** 400. DRF's serializer raises its own `ValidationError`; the handler relabels
`exc_type` to `ValidationError` but keeps DRF's 400. So the same `exc_type` arrives as
400 from the serializer and 417 from model or filter code. The frontend branches on
`exc_type`, not the number, so nothing breaks; it is an inconsistency, and the reason the
suite keeps 417 as the expectation is that `PORT_PLAN.md` §3 fixes the wire protocol.

**Where:** `frappe_core/exceptions.py`, the `drf_exceptions.APIException` branch — use 417
when the mapped `exc_type` is `ValidationError`.

## 5. Login is case-sensitive on the email

**Block:** `01_auth.http` 1.11 — `{"usr": "ADA@EXAMPLE.COM", "pwd": <correct>}`

**Expected:** 200. Upstream's `User.find_by_credentials` (`user.py`) looks the name up
with `frappe.db.get_value`, and MariaDB's default collation compares case-insensitively,
so any casing of the address logs in. The User primary key is stored lowercased
(`frappe_platform/models.py:226`) for exactly that reason.

**Actual:** 401 `Invalid login credentials`. `frappe_core/api/auth.py:login` lowercases
the name only for the lockout tracker key and passes the raw value to
`authenticate()`, which does an exact match on `name`.

**Where:** `login` — resolve the account case-insensitively before authenticating.
Not a blanket `.lower()`: the built-in `Administrator` is stored with its capital, so the
lookup should be `name__iexact` (or try exact, then lowercased). **User-visible:** anyone
whose mail client capitalises their address gets "Invalid login credentials" for a
correct password.

## 6. A malformed bearer token is not an `AuthenticationError`

**Block:** `01_auth.http` 1.4 — `Authorization: Bearer this-is-not-a-token`

**Expected:** 401 with `exc_type: AuthenticationError`, which is what every other
authentication failure in the port answers and what `frontend/src/stores/users.js:34`
branches on.

**Actual:** 401 with `exc_type: InvalidToken` and SimpleJWT's wording *"Given token not
valid for any token type"*. The handler maps `drf_exceptions.AuthenticationFailed` by
exact type; SimpleJWT's `InvalidToken` is a subclass and falls through to its own class
name.

**Where:** `frappe_core/exceptions.py` — match with `isinstance` rather than the exact
type, or add `InvalidToken` to the map. The status is already right, so the frontend's
refresh-on-401 works; only the label and message differ.
