# API contract — what must stay identical on the wire

**Status: Draft, 2026-09-16.** Written from the old backend's code, not from memory. Every
rule names the file that decides it today, so a disagreement can be settled by reading
the source rather than this page. **Paths are from the repository root.**

**The rule of this document:** `backend_v2` answers every request with the same status
code and the same JSON body as `backend/` does. Where this page and the old backend
disagree, **the old backend wins** and this page is corrected. A deliberate difference
needs an entry in `backend_v2/docs/PARITY_EXCEPTIONS.md` *before* it is written.

"Same body" means: the same keys, the same nesting, the same value types, and the same
values wherever a value is deterministic. Generated names, timestamps and tokens
legitimately differ between two servers; everything else does not.

---

## 1. URLs

| Pattern | Serves | Decided in |
|---|---|---|
| `/api/method/<dotted.path>` | Every method call the frontend makes | `backend/frappe_core/urls.py:21-26` |
| `/api/resource/<DocType>` | List (GET), create (POST) | same |
| `/api/resource/<DocType>/<name>` | Read (GET), update (PUT), delete (DELETE) | same |
| `ws/realtime?token=<access token>` | The WebSocket | `backend/config/routing.py` |

- **A trailing slash is optional** on every HTTP route above.
- **A method path is not always dotted.** `login`, `logout` and `token/refresh` are
  method paths too, and `token/refresh` contains a slash.
- **A doctype contains spaces** (`CRM Lead`), sent percent-encoded.
- **A document name may contain slashes** (`R/GA` is a legal Organization name) and is
  matched as a path, not a segment. Names reject only `<` and `>`.
- **There is no PATCH.** PUT is a partial update.
- **The complete list of method paths is `backend_v2/docs/PORT_MAP.md`.** No other path
  is served, and a path is served under exactly the spelling listed there.

## 2. Authentication

JWT bearer tokens replace Frappe's `sid` cookie — the one sanctioned deviation from
Frappe's protocol, and already shipped in the frontend. `backend/frappe_core/api/auth.py`.

| Request | Response `message` |
|---|---|
| `POST login` with `usr`, `pwd` (also accepts `username`/`email`, `password`) | `{"access", "refresh", "message": "Logged In", "home_page": "/crm", "full_name", "user"}` |
| `POST token/refresh` with `refresh` (also `refresh_token`) | `{"access", "refresh"}` — the refresh token **rotates**, the old one is blacklisted |
| `POST`/`GET logout` with `refresh` | `{"message": "Logged Out"}` — always succeeds; blacklists the refresh token if given |
| `GET frappe.auth.get_logged_user` | the user's name, e.g. `"ada@example.com"` |

- Header: `Authorization: Bearer <access>`. Access tokens live **5 minutes**, refresh
  tokens **7 days** (both from env: `JWT_ACCESS_TOKEN_LIFETIME_MINUTES`,
  `JWT_REFRESH_TOKEN_LIFETIME_DAYS`).
- `update_password` returns **the same shape as `login`** (`auth.py:108-124`,
  `issue_tokens`). The set-password page logs the user straight in with it.
- Login is case-insensitive on the name, exact spelling first (`auth.py:75-81`).
- Login refusals, all `AuthenticationError` 401 unless noted:

| Case | Message |
|---|---|
| `usr` or `pwd` missing | `Both usr and pwd are required` — **ValidationError 417** |
| Wrong password, or unknown user | `Invalid login credentials` |
| Right password on a disabled account | `User disabled or missing` |
| IP or account locked | `Your account has been locked and will resume after 60 seconds` — **SecurityException 403** |

- **Anywhere a password is checked, the lockout tracker applies** — `login` and the
  old-password path of `update_password` alike (`specs/SECURITY_MODEL.md`, "The lockout
  is not login's private business").

## 3. Parameters

`backend/frappe_core/method_views.py:71-81`, `backend/frappe_core/whitelist.py:75-92`.

- **Query string and body are merged**; a body key wins over a query key.
- **Every query-string value is JSON-decoded if it parses**, and kept as a string if it
  does not. `filters=[["status","=","Open"]]` and a native JSON array in the body are the
  same thing; `order_by=modified desc` stays a string.
- **`cmd` is dropped.** It is Frappe's legacy method selector.
- **Surplus parameters are dropped**, unless the endpoint accepts arbitrary keywords. An
  unexpected cache-buster must never cause an error.
- Verbs: each method path accepts a fixed set, listed in `PORT_MAP.md`. Most accept GET
  and POST.

## 4. Success envelopes

`backend/frappe_core/renderers.py`.

| Route | Body | Status |
|---|---|---|
| `/api/method/*` | `{"message": <payload>}` | 200 |
| `/api/resource/*` GET | `{"data": <document or list>}` | 200 |
| `/api/resource/*` POST | `{"data": <created document>}` | **201** |
| `/api/resource/*` PUT | `{"data": <updated document>}` | 200 |
| `/api/resource/*` DELETE | `{"data": null}` | 200 |

**One method puts keys beside `message`:** `frappe.desk.form.load.getdoctype` answers
`{"message": null, "docs": [...], "user_settings": ...}` (`renderers.py:34-45`). frappe-ui
hands the whole body to the caller whenever `docs` is present, so the sibling keys are
load-bearing.

## 5. Errors

`backend/frappe_core/exceptions.py`. **The frontend branches on this shape**, so it is
contract, not style — see the consumers listed at the top of that file.

### The body

```json
{
  "exception": "frappe.exceptions.ValidationError: <first message>",
  "exc_type": "ValidationError",
  "_server_messages": "[\"{\\\"message\\\": \\\"<msg>\\\", \\\"title\\\": \\\"Message\\\"}\"]",
  "message": "<first message>",
  "messages": ["<first message>", "..."]
}
```

- `_server_messages` is **a JSON string containing JSON strings**, each
  `{"message", "title"}`. `FilesUploader.vue:215` double-parses it.
- `messages` is a **list of plain strings**; the frontend reads `messages[0]`.
- Every message after the first is something upstream would have shown before the
  throw — a document missing three mandatory fields reports all three.
- **`frappe.throw` text is preserved verbatim.** It is user-facing copy.

### Status and `exc_type`

| `exc_type` | Status | Title | Raised for |
|---|---|---|---|
| `ValidationError` | 417 | Message | Any `frappe.throw`; serializer validation (DRF's 400 becomes 417) |
| `MandatoryError` | 417 | Message | A required field is missing |
| `InvalidEmailAddressError` | 417 | Message | `<value> is not a valid Email Address` |
| `LinkValidationError` | 417 | Message | `Could not find <Label>: <name>` |
| `LinkExistsError` | 417 | Message | Delete refused by a reference: `Cannot delete or cancel because <DocType> <name> is linked with <DocType> <name>` |
| `OutgoingEmailError` | 417 | Message | No email account to send through |
| `PermissionError` | 403 | Not Permitted | Row or action refused |
| `SecurityException` | 403 | Message | Login locked out |
| `DoesNotExistError` | 404 | Not Found | Unknown document, doctype or method |
| `AuthenticationError` | 401 | Message | No token, bad token, bad credentials |
| `DuplicateEntryError` | 409 | Duplicate | A unique constraint (the database message is passed through) |
| `NameError` | 409 | Message | A name containing `<` or `>`, equal to the doctype, or `New <DocType>` |
| `RateLimitExceededError` | 429 | Message | `You hit the rate limit because of too many requests. Please try after sometime.` |
| `ValidationError` | **400** | **Invalid Filter** | Any filter that cannot be applied (section 7) |

- A 429 keeps its `Retry-After` header; a 401 keeps `WWW-Authenticate`
  (`exceptions.py:361-366`).
- **An unhandled exception is a plain 500**, not a Frappe body. That is not a contract to
  preserve; it is a defect wherever it happens.

### Fixed sentences the frontend or the suite relies on

| Situation | Status | Message |
|---|---|---|
| Unknown method path | 404 | `Method <path> not found` |
| Method called with a verb it does not accept | 403 | `Method <path> does not accept <VERB>` |
| Non-guest method called with no token | 401 | `Not permitted` |
| Resource route called with no token | 401 | `Authentication credentials were not provided.` |
| Any route called with an invalid or expired token — guest methods included, because authentication runs first | 401 | SimpleJWT's sentence, taken from its `detail` |
| Unknown doctype, child table, or withheld doctype | 404 | `DocType <DocType> not found` — **identical for all three** |
| Document not found | 404 | `<DocType> <name> not found` |
| Document read/write/delete refused | 403 | `No permission for <DocType> <name>` |
| Create refused | 403 | `Not permitted to create <DocType>` |
| Update that would move a row onto a document the caller cannot write | 403 | `Not permitted to move <DocType> there` |

A name the primary key cannot hold (letters for an integer-keyed doctype such as
CRM Task) is **not found**, never a 500 (`backend/frappe_core/query.py:32-44`).

## 6. Documents on the wire

### Standard fields

Every document carries these (`backend/frappe_core/models.py:113-156`):

| Field | Type on the wire | Note |
|---|---|---|
| `name` | string, or integer for the three autoincrement doctypes | The primary key. Autoincrement: CRM Task, CRM View Settings, CRM Product Sync Issue |
| `owner`, `modified_by` | string | A user's name |
| `creation`, `modified` | datetime string | See "Values" below |
| `idx` | integer | Row position |
| `docstatus` | integer | Always 0 in this product |
| `_assign`, `_liked_by`, `_comments` | JSON list | Caches. **Never writable** by a client |
| `_user_tags` | string | Cache. **Never writable** by a client |

`owner`, `modified_by`, `creation` and `modified` are stamped by the server and are
read-only (`backend/frappe_core/serializers.py:31-40`).

### Names

The name each doctype gets on create is listed in `PORT_MAP.md` (Naming column). Six
strategies: `NamingSeries('CRM-LEAD-.YYYY.-')` → `CRM-LEAD-2026-00001` (five digits),
`FieldValue('x')` → the field's value **verbatim** (no slugifying), `Hash(10)` → ten
random characters, `Format('{dt}-{type}')`, `Prompt()` → the client supplies `name`,
`AutoIncrement()` → integer. `backend/frappe_core/naming.py`.

**`User`'s name is the lowercased email.** `Administrator` and `Guest` are the two
exceptions, and keep their capitals.

### Links and child tables

- **A Link field is its target's name as a plain string** — never a nested object.
- **Child tables are inline**: a list of row objects under the parent's field.
- **A write replaces a child table wholesale** — the rows sent are the rows kept.
- **A child row is never reachable on its own**; it has no route.

### Values — the traps

Rendered by DRF with default settings, which produces two surprises that must be
reproduced exactly:

| Value | In a document read (`frappe.client.get`, `/api/resource/<dt>/<name>`) | In a list row (`get_list`, `/api/resource/<dt>`, `get_data`) |
|---|---|---|
| **Decimal** column (e.g. `annual_revenue`, `total`) | **string**, padded to the column's decimal places: `"1000.000000"` for six | **number**: `1000.0` |
| Datetime | `"2026-09-16T10:00:00.123456Z"` | same |
| Date | `"2026-09-16"` | same |

The decimal difference exists because document reads go through a serializer
(`COERCE_DECIMAL_TO_STRING` defaults to true) and list rows are `.values()` dicts that
DRF's JSON encoder turns into floats. **It is part of the contract until a parity
exception says otherwise.**

### Field visibility

The four declarations, per doctype, are in `PORT_MAP.md` (Declared fields column).
`backend/frappe_core/field_security.py`.

| Declaration | Read | Write | Applies at |
|---|---|---|---|
| Sensitive (`S`) | **nobody** | nobody | Serializer output, `fields=`, `filters=`, `or_filters=`, `order_by=`, `group_by=` |
| Restricted (`R`) | System Manager, Sales Manager, `Administrator` | — | The same five, **per request** |
| Read-only (`RO`) | everybody | **nobody** — silently ignored | Serializer input |
| Encrypted (`E`) | not on the wire (always paired with `S`) | — | Storage |

`password` and `last_login` are sensitive on every model. **All five field-naming
parameters must agree**; a hidden field that can still be filtered or sorted leaks its
value one request at a time. That is how a real SMTP password was recovered from the
old backend before this rule existed.

## 7. List queries

`backend/frappe_core/query.py`, `backend/frappe_core/filters.py`. Shared by
`/api/resource/<DocType>`, `frappe.client.get_list` and `crm.api.doc.get_data`, **so the
three cannot disagree**, and a caller cannot pick the laxer route.

### Parameters

| Parameter | Default | Rules |
|---|---|---|
| `fields` | every readable concrete field | `["*"]` means the same. A hidden field → 417 `Field '<f>' is not readable`. An unknown field → 417 `Unknown field '<f>' for this document type`. No relation traversal |
| `filters` | none | ANDed. Grammar below |
| `or_filters` | none | ORed together, then ANDed with `filters` |
| `order_by` | the model's default, `-modified` | `"modified desc"`, comma-separated clauses, optional `` `tabX`. `` or `X.` prefix. Hidden → 417 `Cannot order by '<f>'`; unknown → 417 `Cannot order by unknown field '<f>'` |
| `limit_start` | 0 | Negative becomes 0. Not an integer → 417 `Invalid offset ...` |
| `limit_page_length` | 20 | **Capped at 500. `0` means no limit.** Negative → 417 |
| `group_by` | none | Validated like `order_by`: `Cannot group by '<f>'`, `Cannot group by unknown field '<f>'` |

**Row permissions are applied before any client filter** — a list only ever contains
rows the caller may read.

### Filter grammar

Accepted shapes, all normalised to `(field, operator, value)`:

```
{"status": "Open"}                          equals
{"status": ["in", ["Open", "Lost"]]}        operator form
[["status", "=", "Open"]]                   3-tuple
[["CRM Lead", "status", "=", "Open"]]       4-tuple — the doctype is ignored
[["status", "Open"]]                        2-tuple — equals
```

| Operator | Meaning |
|---|---|
| `=` `!=` `>` `<` `>=` `<=` | As written |
| `like`, `not like` | **Case-insensitive.** `%x%` contains, `x%` starts with, `%x` ends with, `x` equals; other wildcards become an anchored regex. On a JSON list column (`_assign`, `_liked_by`) always a case-insensitive substring match |
| `in`, `not in` | A list, or a comma-joined string |
| `between` | Exactly two values |
| `is` | `set` / `not set`. **On a text column an empty string counts as not set** |
| `descendants of`, `descendants of (inclusive)`, `not descendants of (inclusive)`, `ancestors of`, `not ancestors of (inclusive)` | Tree fields (CRM Territory, CRM Sales Hierarchy) |

- **`@me` becomes the current user, and `%@me%` becomes `%<user>%`**, at any depth.
- Operators are matched case-insensitively and trimmed.
- Every filter refusal is **400, `ValidationError`, title `Invalid Filter`**:
  `Cannot filter on '<f>'` (hidden), `Unknown field '<f>' for this document type`,
  `Unsupported filter operator '<op>'. Supported: ...`, and the shape errors.

## 8. Writes through the generic routes

`backend/frappe_core/views.py`.

- **Create** checks the create rule against **an unsaved instance carrying the payload's
  own fields**, not an empty one. A comment's rule defers to the document it references,
  so an empty instance would wave every create through.
- **Update** checks the write rule on the document as stored, then — for Comment,
  Communication, File and WhatsApp Message — **re-checks the destination** if the update
  changes the document the row points at
  (`backend/crm_app/permissions/attachments.py:58-63`).
- A serializer refusal is a 417 `ValidationError` whose messages are flattened to
  `"<field>: <message>"`; the frontend splits on `": "` to find the field.
- **Delete** checks the delete rule, then deletes; a reference that forbids it answers
  `LinkExistsError`.
- Each write runs in one transaction, child rows included.

## 9. Guest endpoints and webhooks

Reachable without a token, listed as `guest` in `PORT_MAP.md`: `login`, `token/refresh`,
`crm.api.accept_invitation`, `crm.api.auth.oauth_providers`, `crm.api.get_translations`,
`frappe.core.doctype.user.user.reset_password`,
`frappe.core.doctype.user.user.update_password`, and the provider webhooks.

- **`reset_password` never reveals whether an address exists**, and is rate-limited per
  address as well as per IP (`backend/crm_app/api/auth_pages.py:50`).
- **Reset and invitation keys are single use**, each consumed by one conditional
  `UPDATE` rather than a read-then-clear (`auth_pages.py:159`, `auth_pages.py:386-388`).
- **Twilio webhooks verify the provider's signature** from the request URL and header.
  An unsigned webhook is an unauthenticated write from the public internet.
- **Exotel webhooks compare `webhook_verify_token` in constant time**, and refuse when no
  token is configured (`backend/crm_app/integrations/exotel/handler.py:74-98`).

## 10. WebSocket

`backend/crm_app/consumers.py`, `backend/crm_app/realtime.py`.

- Connect to `ws/realtime?token=<access token>` — the token rides in the query string
  because a browser cannot set headers on a handshake. **Missing or invalid token: close
  code 4001.** With `ENABLE_REALTIME=0` the route does not exist.
- Client → server: `{"event": "doc_subscribe", "args": ["CRM Lead", "<name>"]}` (answered
  `doc_subscribed`, permission-checked with the same rules as a document read),
  `doc_unsubscribe` (answered `doc_unsubscribed`), `ping` (answered `pong`).
- Server → client frames are `{"event": <name>, "message": <payload>}`. A payload-less
  event carries `{}`, never `null`. Event names published today: `crm_notification`,
  `docinfo_update`, `exotel_call`, `twilio_call_status`, `whatsapp_message`,
  `crm_customer_created`, `crm_product_sync_complete`.

## 11. Not part of the contract

- `/admin/` — Django admin. Useful, not promised.
- DRF's browsable API — off in both backends (JSON renderer only).
- Response header order, JSON key order, and whitespace.
- The exact text of a `DuplicateEntryError` from the database.
