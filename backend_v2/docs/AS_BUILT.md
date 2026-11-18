# As built — what `backend_v2` actually contains

**Status: FOUNDATION built through its final records (2026-11-15); its gate has not yet
changed the unit status to Done.**

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

`core` now supplies the legacy-compatible exception classes and error body, the DRF
`api_exception_handler`, the `{"message": ...}` / `{"data": ...}`
`EnvelopeRenderer`, merged input parsing, surplus-input binding, and `BaseAPIView` for
endpoints that are not resources.
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
covering every naming strategy and the completed generic-layer tests.

Change history is withheld from the API and stored in `core.models.Version`, named with
`Hash(10)`. A document opts in with a `TRACKED_FIELDS` class attribute; `BaseDocument`
snapshots those values when loading, writes one `{"changed": [[field, old, new], ...]}`
row after a save that changes any of them, stamps its owner from the explicit
`save(user=...)` user, and refreshes the snapshot for a second save on the same instance.
Creates and saves that alter no tracked field write no row. The daily 00:10 task deletes
only versions whose `ref_doctype` is `CRM View Settings` and whose creation is more than
14 days old. That doctype deliberately does not opt into tracking today, so normal saves
give the task nothing to delete; keeping the narrow task implemented makes later view
tracking safe without ever applying retention to Lead, Deal, or other timeline history.
Deleting a document also deletes every `Version` row that names its doctype and name.
`references_handled()` suppresses only per-row reference cleanup, while
`children_and_references_handled()` suppresses both child and reference cleanup after a
batch caller has run both batch helpers. The cleanup table currently registers only
`Version`; ACTIVITIES adds ToDo, Comment, File, and Communication when their models
exist, with a Communication's reference cleared rather than deleting the email.

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
disabled, preventing old tokens from becoming valid again after re-enabling. The only
other trigger, `update_password` with `logout_all_sessions`, is ACCOUNTS'; a password
change or plain reset revokes nothing (`specs/ACCOUNTS.md` §4.4).

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

ACCOUNTS routes `User` (`specs/ACCOUNTS.md` §4.1) without making it a `BaseDocument`: it
has none of the standard fields. It declares `DOCTYPE = "User"`, so `model_for_doctype`,
the delete-time dynamic-link check, the DocType search and the delete cascade find it
(`core.children.connect_cascades` connects every non-child model with a `DOCTYPE`).
`User.save()` accepts and ignores the resource recipe's `user=` actor and, like
`BaseDocument`, forces an insert on create, so a name differing only by case is a
duplicate (409, the raw body: `User` has no naming strategy), never an update.
`UserViewSet` (`/api/v1/users/`) carries the old static rules, emits `user_emails: []`
until CONFIGURATION, ignores a `name` sent on update (PE-7, proposed), and opts in to
search only — never export, rename, bulk update or bulk delete. Its directory and role
actions (`directory/`, `info/`, `add-existing/`, `<name>/update-role/`,
`<name>/remove-crm-roles/`) read `User` directly, as the old endpoints did; the two
per-user role actions never load the target through `get_object()`.
`CRMSalesHierarchy` (`/api/v1/sales-hierarchies/`) is a `TreeDocument` parented by
`reports_to`; System Manager alone writes it.

The front door (ACCOUNTS milestone 2) is guest-reachable and lives in
`accounts/front_door.py` and `accounts/invitations.py`: `auth/reset-password/` answers
one sentence on every branch; `auth/update-password/` sets a password by reset key (410
`LinkNoLongerValid` for a dead link) or old password (through the login lockout, 401
`WrongPassword`) and answers login's token pair, with `logout_all_sessions` as the only
revocation trigger besides a save while disabled; `auth/accept-invitation/` redeems by
key. Reset keys (`accounts/password_reset.py`) are SHA-256 at rest and claimed by one
conditional update. `CRMInvitation` (`/api/v1/invitations/`) is listed, read and deleted
by the manager pair only, with `key` sensitive; its object rule refuses `create` and
`write` for every caller (PE-8, proposed), so `invitations/invite-by-email/` is the only
way one comes to exist, and the only place a key is minted. Its `save()` queues
`accounts.send_invitation_email` with `transaction.on_commit` on every insert — a test
that wants the mail at once patches `accounts.models.transaction` (see
`tests/test_invitations.py`), and one test proves the deferral. System mail goes through
`core/mail.py`: today only the settings-configured account (`EMAIL_HOST`), which
CONFIGURATION extends with saved Email Accounts tried first. `accounts.tasks.BEAT_SCHEDULE`
runs `expire_invitations` at 00:00 and `flush_expired_tokens` at 01:00. No beat entry or
task names a queue; `CELERY_TASK_DEFAULT_QUEUE = "default"` in the base settings puts
every `backend_v2` task on the queue the old backend uses
(`backend/config/settings/base.py:317`), so a worker started the old way receives them.

CONFIGURATION's first milestone (`configuration/views.py`, `specs/CONFIGURATION.md` §4.1)
serves the Desk plumbing with no model: `desk/apps/` (the CRM entry for a CRM role, `[]`
otherwise), `desk/site-info/` (`{}`, System Manager or Administrator), `desk/telemetry-config/`
(on only when both `POSTHOG_PROJECT_ID` and `POSTHOG_HOST` are set), `demo/clear/` (POST,
the manager pair or Administrator, answers `null`) and the guest `translations/` (`{}`).
Administrator passes each gate by name, not by its groups.

Its second milestone (`configuration/models.py`, §4.2) adds the reference data and the
boot call. `SystemSettings` is the first production `SingletonDocument` (`system-settings/`,
System Manager or Administrator only, reads included); `POST boot/` is the guest
`get_context_for_dev` and writes a missing System Settings row again from
`FRAPPE_SYSDEFAULTS` with Administrator as the actor. Country, Language and Currency are
document resources with link search (`<resource>/search/`); Currency is read only by the
CRM and accounting roles. Data migrations write the System Settings row (`0002`) and the
250 countries, the currencies (nine enabled) and the languages (`0004`) from
`configuration/data/`, copies of `backend/crm_app/data/`; they are not dev data. Onboarding
status lives at `onboarding/status/` (GET reads, POST updates the caller's own column).

Its third milestone (§4.3) adds FCRM Settings at `crm-settings/` (everyone reads; the
manager pair or Administrator writes; `access_key` restricted; no list route, PE-11) with
its inline CRM Dropdown Item rows; data migration `0006` writes the row and the six
standard items, and `FCRMSettings.load_or_create(user=...)` adds them only when it
creates the row. `core/http.py` is the one outbound HTTP helper (timeout and retry
policy), ported whole for every later caller. `configuration/exchange_rate.py` serves
`GET exchange-rate/` (PE-10, PE-12); `ENABLE_EXCHANGE_RATE_API` is off in the test
settings. A settings record's `value/` refuses a field it does not list (PE-13). The
`.http` generator serves a singleton's document URLs at its root and marks a list-shaped
read of one `# @retired PE-11`.

Its fourth milestone (§4.4) adds Email Account at `email-accounts/` (everyone reads; the
manager pair or Administrator writes, renames and deletes; `password` and `api_secret`
encrypted and never served; eleven mail-server fields restricted) and
`email-accounts/setup/` (`create_email_account`, credentials checked before the row
exists). `core/mail.py` holds the server checks (`smtp_settings`, `check_smtp`,
`check_imap`, `validate_email_account`) and reaches saved accounts through
`MAIL_ACCOUNT_PROVIDER = "configuration.mail"` (system check `core.E003`):
`find_outgoing_account` tries a saved account before the config account, `open_backend`
sends a saved account through its own SMTP settings, and `default_signature()` is the
signature fallback `accounts` uses. An Email Account's `save()` links it to the user
whose address it is, as a User Email row on that user's `user_emails`, which only System
Manager writes through User. Parked for the owner, built as `backend/`: a password sent
on update is ignored, and a rename keeps `email_account_name`.

Its fifth milestone (§4.5) adds field metadata. `configuration/data/doctype_meta.json` is
the old 39-doctype file, read by `configuration/field_meta.py` (with a model fallback on
`TEXT_LINK_FIELDS`, `DYNAMIC_LINK_FIELDS`, `ATTACH_FIELDS` and choices) and regenerated by
`scripts/generate_field_meta.py`; `tests/test_field_meta.py` compares the two, and CI
checks out upstream frappe/crm so it runs there. `configuration/metadata.py` says what
exists: a declared doctype that is served, or a child of a served resource; a withheld
doctype is 404 (PE-14), a child answers only `meta/doctype/` (PE-15), and every answer
leaves out the fields the caller may not read (PE-16). Routes: `meta/doctype/`
(`getdoctype`), `meta/fields/`, `meta/sort-options/`, `meta/filterable-fields/`,
`meta/group-by-fields/`, and `user-settings/` (the caller's own `UserSettings` row, a plain
model). `configuration/export_fields.py` gives a resource's export its field labels and
types through `export_field_info_for(model)`. The `.http` generator makes a `meta/` block
about an unbuilt doctype wait for its unit.

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
prefix, pass-through migration behavior, key failures and changed-key wording.

`core.filters` and `core.query` now supply the one registry-free list-query layer used
by later resources. It accepts Frappe's filter shapes and operators, recursively resolves
`@me` from the explicitly supplied user, validates all field-naming parameters against
model field access and optional ViewSet allowlists, and projects `.values()` rows with
the three underscore caches converted back to JSON strings. Callers provide an already
row-rule-narrowed queryset; these functions never start from a model manager.

`core.conditions` evaluates the condition editor's JSON as data through `is_empty`,
`validate`, `document_values`, `evaluate`, and `evaluate_safely`, without executing saved
code.

`core.filter_backends.FilterBackend` adapts that layer to DRF and records a validated
projection on its ViewSet. The completed `DocumentViewSet` calls the same query layer
directly with its `readable_fields`, `filterable_fields`, and `sortable_fields` tuples.
`core.pagination.LimitStartPagination` uses `limit_start` and `limit_page_length`, caps
positive lengths at 500, treats zero as unlimited, and returns a bare list for the
envelope renderer.

`core.models.TreeDocument` is the abstract Frappe nested-set base. Concrete trees declare
their parent foreign-key name, inherit indexed `lft`/`rgt`, rebuild all bounds after each
save or delete with siblings ordered by name, and serialize rebuilds with a
per-model PostgreSQL transaction advisory lock taken before reading nodes. Its
`tree_q()` classmethod is the only contract the five tree-filter operators use.
On save, the same transaction takes that lock before checking the requested parent,
writing the row, and rebuilding. A node whose new parent is itself or one of its
descendants raises `NestedSetRecursionError` with upstream's `Item cannot be added to
its own descendants`; serializing the check and write means two concurrent reparents
cannot together form a loop. The parity rebuild walks roots only, retains the
`depth > len(nodes)` guard, and updates only visited nodes. A rootless cycle created by
writing around `save()` therefore keeps its old bounds, as the old backend does.
Instance and queryset deletes both take the same transaction advisory lock before the
tree row is deleted; the post-delete rebuild runs while that lock is still held.
`tests_support.TestTree` and `TreeItem` exercise that generic contract only under test
settings.

S26 renamed every application-owned identifier that formerly carried the framework
name: `FrappeAPIView` → `BaseAPIView`, `FrappeEnvelopeRenderer` →
`EnvelopeRenderer`, `FrappeError` → `APIError`, `frappe_exception_handler` →
`api_exception_handler`, and `frappe_not_found` → `not_found`. Test-only aliases were
also made descriptive: `FrappeNameError` → `DocumentNameError` and
`FrappePermissionError` → `APIPermissionError`; the paginator test's
`frappe_parameters` phrase became `legacy_parameters`. The settings import strings use
the new renderer and handler names. Wire values for the concrete exception subclasses
and every `frappe.exceptions.*` string are unchanged; the base class is not raised.

`core.serializers.DocumentSerializer` is the base for document resources. It keeps each
subclass's explicit `Meta.fields`, applies model field-access declarations, requires the
caller in `context["user"]`, and accepts `save(user=...)` only for that same caller. It
adds `doctype`, renders the three JSON caches as strings, preserves DRF's padded decimal
strings, maps text `null` to `""`, and translates duplicate field-value and prompt names
to the old `DuplicateEntryError` sentence. A sensitive field accidentally included in
`Meta.fields` is silently excluded rather than made readable.

`core.children` implements declared inline child tables. A real-FK table is declared on
its parent serializer; a polymorphic table is declared on the parent model so the same
metadata drives serialization and the post-delete cascade. Every child model declares
its row fields once in `CHILD_FIELDS`; serialization and writes use only those explicit
names, with field-access rules applied on top. Writes validate links and mandatory
values, replace the named table wholesale, assign `idx` from list order, and save every
row with the explicit caller. Update writes rows before the parent; create saves the
parent, writes rows, refreshes it, and saves it again, all atomically.

`core.models.SingletonDocument`, `core.views.SingletonViewSet`, and
`core.routers.SingletonRouter` are the shared settings-record stack. The model pins its
one row to the document type's name and supplies a concurrency-safe `load(user=...)`.
The route exposes the document at the resource root with GET and PATCH only. It has no
name segment and refuses POST, PUT, and DELETE with the standard 405 body.

Every `DocumentViewSet` also exposes `GET <resource>/value/` and
`GET <resource>/<name>/permissions/`. The value lookup uses the same row-rule-narrowed
queryset and field allowlists as list; the permission lookup returns all seven old
permission booleans without raising for a denied row. Every `SingletonViewSet` exposes
`GET <settings>/value/`, applying its object rule and the model's sensitive and
restricted field access before returning one value.

`core.access.Access` makes each routed resource declare whether it is row-ruled or
deliberately open. The guards in `tests/guards/` enforce those declarations, require
every production document model to be routed or named in `core.withheld`, reject
unreviewed direct manager reads, keep concrete built route-map entries in lockstep with
the production URLconf, require explicit credential and child-field declarations, and
prove that resource writes stamp the authenticated caller. `Version` is the sole
withheld document type. The served-or-withheld guard covers every model that declares a
`DOCTYPE`, not only `BaseDocument`s, so `User` (routed by ACCOUNTS) is held to it too.
`core.resources.rules_for(model)` now exposes independently callable row rules for a
routed model, or for an unrouted model with an explicit `ROW_RULES` provider.

`seed_dev_data` and `clear_dev_data` run the one explicit step list in
`core.dev_data.STEPS`. FOUNDATION's account step creates or restores Administrator,
ada, grace, and alan from four environment passwords; every seed restores enabled
state, the exact groups, and the password. The seed records each row it creates in
`core.models.DevDataRecord` (`core/dev_records.py`), and clear deletes only recorded rows,
then forgets them: an account that existed before the seed is never deleted. Both commands are atomic and report counts without printing a
password. `--demo` is accepted but deliberately adds nothing until later units append
their own explicit steps.
Both commands refuse to run unless `DEV_DATA_ALLOWED` is true. The base settings read it
from the environment, default off: it belongs in the `.env` of the database it names
(DECISIONS 9). Only the test settings turn it on, for the scratch test database.

`scripts/build_http_suite.py` parses all 15 old `docs/http/*.http` files and deterministically
regenerates their REST copies in `backend_v2/http/` from `PORT_MAP.md`. It keeps waiting
blocks in place, tags wrong-verb and unknown-route negative cases, and records the three
PE-3 blocks as not served. `scripts/run_http.py` replays a generated file with isolated
captured variables, dotenv substitution, status and `# @expect` checks, redacted output,
and explicit pass/fail/skip lines. `scripts/parity_diff.py` gives the old and new runs
separate state, compares status and the complete JSON body, and permits only the
type-preserving value paths documented in `scripts/parity_ignore.json` to differ.

## 2. Recipes

These recipes describe the completed FOUNDATION conventions every later unit follows.
The code remains authoritative when a recipe goes stale.

### Adding development data

Put an app's seed and clear functions in that app (the account example is
`accounts/dev_data.py`). Each accepts `(user, force)` and returns the number of rows it
created or removed. Existing rows are normally kept; use `force` only for a row whose
old restore-defaults behaviour rewrites it. Document-model saves receive the supplied
user, which the commands resolve to Administrator.

Import both functions in `core/dev_data.py` and append one explicit `DevDataStep` line
to `STEPS`. This is the only step list: there is no app registry or discovery hook.
Clearing runs the same list in reverse, and a clear function must identify only its own
rows and must not remove migrations' built-ins or roles. Add the app's command tests in
the same change, including a hand-made row that proves clearing is narrow.

### Adding a resource

Start the model by subclassing `BaseDocument`, or `AutoIncrementDocument` for a genuine
integer name. Declare `DOCTYPE` and `NAME_STRATEGY` as class attributes. The other
model declarations are `IS_CHILD_TABLE`, `IS_SINGLE`, `FETCH_FROM`, `EMAIL_FIELDS`, and
`TEXT_LINK_FIELDS`; the last maps a text column to `(app_label.Model, label)`. A field
that deliberately keeps a deleted target's name as audit data is also named in
`ALLOW_DANGLING_LINK_FIELDS`.

Creating through Django's ordinary `objects.create()` is intentionally unsupported,
because it cannot supply the required actor. Use `Model(...).save(user=user)`, or
`Model.objects.create_for_user(user=user, ...)`. Updates likewise call
`save(user=user)`. A request passes `request.user`; seeds and scheduled jobs pass
`accounts.roles.ADMINISTRATOR`; an enqueued job passes the user who enqueued it.
Passing `None` or an empty string raises `TypeError` with
`` `user` is required to save a document ``.

Write one `DocumentSerializer` subclass with an explicit `Meta.fields` tuple. Include
every standard or resource field that may appear; the base never adds parent fields.
Sensitive fields are still silently excluded if listed, standard/model read-only fields
are input-ignored, and restricted fields are removed per `context["user"]`. The ViewSet
passes `request.user` in that context and calls `serializer.save(user=request.user)`.
Using the serializer without the context user is a `TypeError`.

For a single-parent child, put its virtual field in `Meta.fields` and declare the child
model label on the serializer:

```python
class WidgetSerializer(DocumentSerializer):
    CHILD_TABLES = {"items": ("widgets.WidgetItem", "parent_widget")}

    class Meta:
        model = Widget
        fields = (*STANDARD_FIELDS, "title", "items")
```

Name the child model and its parent-link field in the declaration. A bare model label
remains supported when the child has exactly one foreign key to the parent; if it has
several, resolving the serializer raises an error listing the fields that can be named.
On the child model, declare `CHILD_FIELDS` as a literal tuple containing every concrete
field the row may show or accept, including the standard document and parent fields:

```python
class WidgetItem(BaseDocument):
    IS_CHILD_TABLE = True
    CHILD_FIELDS = (
        "name", "owner", "modified_by", "creation", "modified", "idx",
        "docstatus", "_assign", "_liked_by", "_comments", "_user_tags",
        "parent_widget", "parentfield", "parenttype", "value",
    )
```

Do not derive this tuple from model metadata. A new concrete column stays off the wire
and is ignored on write until explicitly added. Sensitive and restricted fields are
still hidden per caller, and standard/model read-only fields are ignored on write. A
child model without `CHILD_FIELDS` raises `TypeError` when its table is used. Keep this
policy on the child model so a child embedded by several parents has only one list.
For a child doctype shared by multiple parent types, declare the string parent columns on
the child and put
`POLYMORPHIC_CHILD_TABLES = {"items": "widgets.WidgetItem"}` on each parent model;
again name `items` in the serializer's fields. If the same child model is declared under
two field names, `parentfield` distinguishes them. Neither kind receives its own route.

### Adding a singleton resource

Subclass `core.models.SingletonDocument`, declare `DOCTYPE`, and add ordinary model
fields; do not declare a naming strategy. Create or fetch the one row with
`Model.load(user=user)`. Both `load()` and a direct first save pin its name to `DOCTYPE`,
and two concurrent first loads converge on the same row.

Use an explicit `DocumentSerializer` as for any other document, then subclass
`core.views.SingletonViewSet`. Declare the same serializer, field allowlists, and object
rule a document resource would use. Register it on `SingletonRouter` in the app's
`urls.py`. The router writes only the root GET/PATCH route and collection actions; it
cannot create a list, create, delete, PUT, or name route. The inherited
`GET <settings>/value/?field=<field>` action returns the scalar or `null` and applies the
read object rule before sensitive and restricted field access.

### Adding an action or an endpoint

For an endpoint that is not a resource, subclass `core.views.BaseAPIView`, implement
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
body winning and `cmd` removed. With `pass_user=True` a callable key is called as
`key(inputs, user)`, `user` being the request's authenticated user or `None`, for a
bucket on the signed-in account (ACCOUNTS' `update_password`). A key that raises falls
back to the IP-wide bucket, never to no limit.

Every view is authenticated by default. A guest endpoint declares
`permission_classes = [AllowAny]`; JWT authentication still runs first when the request
carries a token. No view binds a user into ambient state: pass `request.user` to any
service that needs it. Write both slash forms with one explicit `re_path`, using a final
`/?$`; do not rely on `APPEND_SLASH`, because POST bodies must not be redirected.

For a document resource, subclass `core.views.DocumentViewSet`, set its explicit
`serializer_class`, and declare `readable_fields`, `filterable_fields`,
`sortable_fields`, and `searchable_fields` as tuples. The first three govern list
projection, filters, and both ordering and grouping; an empty tuple permits no fields
for that operation. Register the class explicitly on the app's
`core.routers.DocumentRouter` and include the app's URLconf under `/api/v1/`.

Every resource ViewSet also declares its access decision directly on the class. Use
`access = Access.ruled()` when rows are protected, and define both `list_rule(user)` and
`has_object_rule(user, document, ptype)` on that ViewSet. Both rules are
`@staticmethod`s: a shared mixin can apply another resource's rules through
`core.resources.rules_for(model)` without constructing a ViewSet or inheriting hidden
request or action state. Existing calls through `self` remain valid. Use
`access = Access.open(reason="…")` only after review, with a substantive reason. The
base `DocumentViewSet` deliberately has no declaration, so a subclass that forgets one
fails the access guard. A model with a concrete sensitive or encrypted field cannot be
open. Document types that intentionally have no resource route are recorded once in
`core.withheld.WITHHELD_DOCUMENT_TYPES`, with a reason; `Version` is currently the only
entry because the timeline reads it server-side.

`rules_for(model)` walks the production `config.urls`, including nested resolvers, and
maps each routed `DocumentViewSet` or `SingletonViewSet` by its serializer model. A
caller handling a request under another URLconf passes it explicitly. The map is cached
per URLconf; tests that replace a URLconf's patterns in place call
`clear_rules_cache()`. An unrouted model that needs row rules declares
`ROW_RULES = "<app>.permissions.<name>"`; that dotted object must provide callable
`list_rule` and `has_object_rule` functions. If the provider is a class, both must be
`staticmethod`s; modules and other non-class providers may expose plain functions. The
guard resolves every project model's declaration. There is no implicit fallback.
Django's `core.E001` system check refuses one model served by two different ViewSet
classes; registering the same class at several prefixes is valid.

### Opting a resource in to a shared action

Add the action's mixin before `DocumentViewSet` in the resource ViewSet's bases. The
mixin then uses that ViewSet's `get_queryset()`, access rules, serializer model, and
field allowlists; registering the ViewSet writes the action route explicitly through
the same resource router. Record that concrete route in `PORT_MAP.md` when a production
resource opts in.

For Link autocomplete, add `LinkSearchMixin`. The model may declare `SEARCH_FIELD` and
`SHOW_TITLE_FIELD_IN_LINK` as class attributes. `name`, the search field, and
`modified` must be present in the corresponding readable, filterable, and sortable
allowlists; an `enabled` or `disabled` field must also be filterable. The action accepts
GET and POST at `<resource>/search/`, reads through `get_queryset()`, and deliberately
ignores `ignore_user_permissions`.

Override `search_filters(self, filters, flags, user)` only for a resource's standard
query branch. ACCOUNTS' User override (built) copies `filters`, defaults `enabled` to 1,
and excludes `Website User` unless `flags["ignore_user_type"]` is true and the passed
user is a System User; it does not use ambient request state and does not call the base
disabled filter (`backend/crm_app/api/client.py:45-60,683-691`). A list-shaped `filters`
gets the same two conditions appended (the old code answered 500 there). CONTACTS' Address override must
pop `link_doctype` and `link_name`, find matching Address parents through Dynamic Link
rows, add those names as a `name in [...]` filter, then call the base hook so the normal
disabled rule still applies (`backend/crm_app/api/client.py:63-81,692-696`).

The base serves list, create, retrieve, PATCH, and delete with the client-reference
`{"message": ...}` envelope and status 200, including create. It never serves PUT.
Every serializer receives `request.user` in its context and every save receives the
same user explicitly. Create, PATCH, and delete are transactional; delete checks
declared dynamic links before Django's protected-link check, while the existing
post-delete hook removes polymorphic child rows.

The same registration also writes two read actions. `GET <resource>/value/` keeps the
old `fieldname`, `filters`, `as_dict`, and ignored `parent` inputs; it calls
`get_queryset()` before the shared query layer, so list row rules and field allowlists
cannot be bypassed. `GET <resource>/<name>/permissions/` returns the seven permission
booleans from `has_object_rule()` and deliberately does not raise when `read` is false;
a missing row returns an empty permissions map.

The guards in `tests/guards/` walk both production and test URLconfs to validate every
routed resource declaration, while excluding unrouted `tests_support` scaffolding from
production-model completeness. They also reject stale or overlapping withheld entries,
direct `Model.objects` or `_default_manager` reads in project `views.py`, `viewsets.py`,
and `services.py` unless the exact read has a written reason, malformed or unmatched
`built` route-map rows, production `/api/v1/` patterns absent from the route map, and
resource creates or PATCHes that fail to stamp the authenticated caller. Test-only
routes under `config.test_urls` are not part of production route-map coverage.

### Opting a resource in to a shared action

Add the action mixin before `DocumentViewSet` in the resource's bases. For bulk update,
use `class LeadViewSet(BulkUpdateMixin, DocumentViewSet)`. This writes only that
resource's `POST <resource>/bulk-update/` collection action; the app still registers the
resource explicitly and records the concrete route in `PORT_MAP.md` when it opts in.
No production resource opts in yet; `tests_support.WidgetViewSet` proves the mechanism.

`RenameMixin` writes `POST <resource>/<name>/rename/`. It reads only `new_name` and
`merge`; the URL supplies the old name and surplus body keys are ignored. The lookup
starts from the model's default manager so list-invisible rows still reach the static
object-write rule. Merge, missing, unchanged, taken, and write-denied refusals keep the
old order, 417 status, and wording before `core.naming.validate_name` runs.

`core.rename.rename_document` locks the original and completes the rename in one
transaction. It inserts a hook-free copy under the new primary key, temporarily parks
non-key unique values, repoints every reverse FK/O2O (including hidden through-table
relations), declared polymorphic child parent, declared `DYNAMIC_LINK_FIELDS` pair, and
(PE-5, approved) every model's declared `TEXT_LINK_FIELDS` column that targets the renamed
model and holds the old name, then deletes the old row and restores the unique values. The dynamic-link declaration
guard scans every concrete, managed model in project apps, including `tests_support`;
like the direct-manager guard, it identifies project apps by their path directly under
`backend_v2/`, excluding Django and third-party apps. It covers the old seven pair shapes
and same-stem `*_doctype` plus `*_name`/`*_docname`/`*_doc` columns;
`Version` declares `ref_doctype`/`docname` while remaining in `IGNORE_LINKS_ON_DELETE`.
No production resource opts in yet; the test
Widget resource proves the action, permission path, slash-bearing names, and every
reference shape.

`LinkedDocumentsMixin` writes `GET` and `POST <resource>/<name>/linked-documents/`.
The GET first uses the resource's `_object_by_name("read")`, then calls the batched
`core.mixins.linked.linked_documents(model, names, user)` scan. A routed or
`ROW_RULES` source is narrowed by its `list_rule`; a child row is admitted without its
own list rule, resolved to its actual FK or polymorphic parent, and kept only when that
parent's object-read rule is not false. The scan combines every FK and declared dynamic
pair for one source model into one query, independent of the number of target names.
Ignored delete-link doctypes and a child table's own parent FK are never links.
The link-scan row-rule guard calls the scanner's own `is_link_source()` discovery, so
FKs, declared dynamic pairs, and conventional reference pairs cannot drift between the
runtime scan and its classification check.

The dialog result deliberately deduplicates by document name alone: the first position
is retained and the last model with that name supplies the value. A model can declare
`linked_document_title(instance)` for its special dialog title; otherwise a truthy
`title`, then the name, is used. POST performs no source-document check. It silently
skips malformed, unknown, missing, unruled, or object-write-denied items, clears generic
reference pairs and direct FKs with plain `update()` calls, and optionally deletes an
item after the ordinary dynamic-link check. A refused delete leaves the item present but
already unlinked, matching the old endpoint. `clear_linked_document_reference(instance)`
is the per-model override for special reference-pair clearing. No production resource
opts in yet; the test Widget resource covers both actions and slash-bearing names.

The batched scan tags its results into the old collection order before that deduplication:
FK sources, parent reference pairs, then child Dynamic Link parents; within each phase it
sorts source models by `doctype_of(model)` and fields by model-field order. Only child
Dynamic Link rows are ordered by primary key. FK and parent-pair rows deliberately retain
their query order because the old PostgreSQL queries have no explicit `order_by()`.

`BulkUpdateMixin` merges query and body inputs through `core.inputs.build_payload`, with
the body winning, and ignores surplus keys. Fewer than 20 names run inline and return
the failed-name list. From 20 through 500, `core.bulk_update_docs` receives the ViewSet's
dotted class path and the requester's name and the response is `{"message": null}`;
above 500 is the old 417 refusal. Both paths use the ViewSet's model lookup, write rule,
serializer and destination re-check. The worker accepts only a `DocumentViewSet` that
also subclasses `BulkUpdateMixin`, reloads an enabled requesting user, and applies the
same plain per-document loop. Every document has its own transaction and save actor.

`BulkDeleteMixin` writes `POST <resource>/bulk-delete/`. It validates the old `items`
input and authorizes the complete batch before changing anything: two batched manager
queries distinguish missing, list-invisible, and visible rows, then the resource's
object-delete rule runs on the loaded visible instances. Missing names are dropped;
the first invisible name in sorted order, then the first object-denied name, refuses
the batch. Ten authorized existing targets run inline and eleven queue
`core.delete_bulk_docs`; both answer `{"message": "success"}`. The worker reloads the
requesting user, treats a disabled one as missing (PE-6), repeats authorization, accepts only a `DocumentViewSet` opted in with
the mixin, and calls the perform half directly so it never re-enqueues. Its queued
URLconf is limited to the production URLconf or the running settings' URLconf; an omitted
value selects production, and any other value is refused before authorization.

The perform half is one transaction. It reuses the linked-document batched scan and
clear helpers, skips links whose resource or actual child-row parent denies object
write, optionally deletes a cleared link only when its own dynamic-link check permits,
then checks every target for remaining dynamic links. It batch-removes reference rows,
stands down per-row reference cleanup, and deletes all targets with one queryset.
`bulk_delete_remove_contact = True` selects the old Contact-specific clearing hook;
it defaults off. No production resource opts in yet; the test Widget resource does.

`ListExportMixin` writes `GET` and `POST <resource>/export/`, merges query and body
inputs, reads through the resource queryset and field allowlists, and returns the raw
CSV/XLSX `HttpResponse`. Selection replaces both filter sets; client paging is ignored
and the query fetches every matching row. An opting-in ViewSet must define a callable
`export_field_info(fields)` provider that returns `fieldname`, `label`, and `fieldtype`
for each column. CONFIGURATION's field metadata is intended to supply the production
provider. Django's `core.E002` check rejects a routed production ViewSet with no provider
or with the field-name/`Data` placeholder, which lives only in `tests_support`.

**Export always fetches `owner`**, as the old code does (`backend/crm_app/api/reportview.py`).
Keep `owner` in an opting-in resource's readable fields, or every export of it is refused.

### Carrying a document name with slashes in a route

Use `DocumentRouter`, whose document lookup is `.+?` and whose trailing slash is
optional. It orders collection actions, document actions, and finally the catch-all
document route. Thus `/organizations/R/GA/` reaches the `R/GA` record while
`/organizations/R/GA/convert/` can reach a declared `convert` action. A collection
action wins over a record with exactly the same one-segment name; that record is the
settled S25 (8) known limit.

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
maintain.

Each resource ViewSet declares `readable_fields`, `filterable_fields`,
`sortable_fields`, and `searchable_fields` as explicit tuples. The first three are
passed to the plain query functions; `sortable_fields` also governs `group_by`.
`DocumentViewSet` defaults each tuple to empty, so an operation has no fields until the
resource opts them in. Supplying an allowlist only narrows access and never widens model
field access. A real column outside an allowlist receives the same refusal as a hidden
field, so the response does not disclose that it exists. The standalone
`FilterBackend` uses its adapter name `selectable_fields`; resource ViewSets use
`readable_fields` directly.

`User.get_roles()` memoises on that instance. Call `user.clear_roles_cache()` after a
test changes group membership in place; `user.refresh_from_db()` clears it automatically.

### Writing a row rule

**Before adding any model, decide which of these it is** (owner, 17 Nov 2026; DECISIONS
15, A-10). In the old backend a model with no permission hook was silently *allowed*
(`backend/frappe_core/permissions.py:34-43`) and a missing helper made checks pass
silently (`backend/frappe_core/registry.py:198-205`); here each case has a guard that
fails instead, and this list is how to stay clear of them:

1. **Routed** (it has a ViewSet): write `list_rule(user)` and
   `has_object_rule(user, document, ptype)` as **`@staticmethod`s** on the ViewSet —
   they may not read the request; the user comes in as an argument — and declare
   `access = Access.ruled()` or `Access.open(reason=...)` (D-1).
2. **A child table** (`IS_CHILD_TABLE`): no rules of its own. Its rows are checked
   through the parent's `has_object_rule` (`read` to show, `write` to unlink), never the
   parent's `list_rule`. Declare its parent link so each row's parent can be found.
3. **Neither** (e.g. ToDo, Data Import Log): add it to `IGNORE_LINKS_ON_DELETE` with the
   reason, or declare `ROW_RULES = "<app>.permissions.<name>"` whose `list_rule` and
   `has_object_rule` are static. Also list it in `core/withheld.py` and update the exact
   withheld set in `tests/guards/test_resource_access.py`.
4. **Never two ViewSets for one model** in the production routes (`core.E001`).
5. **Every `*_doctype` + `*_name` column pair** goes in `DYNAMIC_LINK_FIELDS`.
6. **Run `tests/guards/`** before committing.

Write `list_rule(user)` as a static method on the resource ViewSet and return a Django
`Q`, or `None` for no narrowing. `get_queryset()` applies this rule before client filters. Record
lookup instead starts from the model's default manager and then applies the object rule:
list and object rules may intentionally differ, so exclusion from a list is not a 404.

Write `has_object_rule(user, document, ptype)`, also static, for the record decision, returning
`True`, `False`, or `None`; `None` means no additional restriction. The base calls it
with `read`, `write`, `delete`, or `create`. Create receives an unsaved candidate built
from the payload's plain concrete fields, falling back to an empty instance only when
construction fails.

For a resource whose plain fields identify a referenced destination, declare those
names in `reference_fields`. A PATCH changing one copies the current document, applies
the validated values, and runs the `write` object rule again. Refusal answers
`Not permitted to move <DocType> there`. Dynamic-link models declare
`DYNAMIC_LINK_FIELDS` as `(doctype_field, name_field)` pairs so deletion can find them
without a registry.

### Raising an error

Raise a class from `core.exceptions`, or call `throw(message, exc=ValidationError)`.
Messages are copied verbatim into the scalar `message`, the plain-string `messages`
list, and the double-encoded `_server_messages` list. The available classes and statuses
are:

| Class | Status | Title |
|---|---:|---|
| `ValidationError` | 417 | Message |
| `NestedSetRecursionError` | 417 | Message |
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

User-facing messages use the identity marker `core.translate._`; translation is
deliberately deferred. Write numbered templates as
`_("DocType {0} not found").format(doctype)`. Use the upstream template verbatim when
one exists, and preserve the old port's wording when it does not. Do not use Django's
`gettext`: activating a Django language must not translate API messages yet. This covers
exception-envelope fragments, naming, links, email validation, lockout, filters,
queries, trees, children, serializers, resource views, and history. Construction that
is not a client message stays ordinary Python: identifiers and query keys, generated
document names, `repr`s, logs, test data, and developer-only programming errors.

A wrong method has this body (shown for `GET`) and an `Allow` header:

```json
{"exception":"frappe.exceptions.MethodNotAllowed: Method \"GET\" not allowed.","exc_type":"MethodNotAllowed","_server_messages":"[\"{\\\"message\\\": \\\"Method \\\\\\\"GET\\\\\\\" not allowed.\\\", \\\"title\\\": \\\"Message\\\"}\"]","message":"Method \"GET\" not allowed.","messages":["Method \"GET\" not allowed."]}
```

`core.views.not_found` decides the response for an unknown non-admin URL. A
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

The local command path uses Django's ASGI-capable `runserver`; `daphne` is installed and
the project points `ASGI_APPLICATION` at `config.asgi.application`, so the HTTP and
placeholder WebSocket routes are both served. From the repository root on Windows,
create the isolated Python 3.13 environment and install the pinned dependencies:

```powershell
py -3.13 -m venv backend_v2\.venv
backend_v2\.venv\Scripts\python.exe -m pip install -r backend_v2\requirements.txt
```

Copy the dedicated example and edit the copy. Settings read only `backend_v2/.env`; do
not reuse the repository-root `.env`, which belongs to `backend/`:

```powershell
Copy-Item backend_v2\.env.example backend_v2\.env
```

Set a real `DJANGO_SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, and the PostgreSQL connection
values needed locally. Append all four suite passwords—`ADMIN_PWD`, `SALES_PWD`,
`MANAGER_PWD`, and `SALES2_PWD`—using the values shared with the main checkout so the
two servers can replay the same login blocks. Never commit or print this file.

Start PostgreSQL 17 and Redis before Django. PostgreSQL must contain the configured
database (normally `opencrm_v2`) and accept the `.env` credentials. Redis supplies the
cache, Celery broker/result backend, and channel layer at the four URLs in `.env`.
Then enter `backend_v2`, apply migrations, seed the four suite users, and check the
project:

```powershell
Set-Location backend_v2
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py seed_dev_data
.venv\Scripts\python.exe manage.py check
```

The command reports created and reset counts per explicit seed step plus a created-row
total. It is idempotent: FOUNDATION creates no account on a second run, while every run
restores the four suite users' passwords, enabled flags, and exact groups. `--force` is
accepted for later restore-default steps. `--demo` currently adds no rows and says so;
later units use it for upstream records from `crm/demo/`.

Remove only rows owned by those steps with:

```powershell
.venv\Scripts\python.exe manage.py clear_dev_data
```

Today this deletes ada, grace, and alan. It keeps Administrator and its initialized
password, Guest, every role, and all users not named by the account seed step.

Migrations also create SimpleJWT's `token_blacklist` tables. JWT and auth-security settings
may be overridden with `JWT_ACCESS_TOKEN_LIFETIME_MINUTES`,
`JWT_REFRESH_TOKEN_LIFETIME_DAYS`, `TRUSTED_PROXY_COUNT`,
`LOGIN_MAX_CONSECUTIVE_ATTEMPTS`, and `LOGIN_LOCK_INTERVAL_SECONDS`; their defaults are
5 minutes, 7 days, 0 proxies, 10 failures, and 60 seconds respectively.

Start the new backend on port 8001 from `backend_v2/`:

```powershell
.venv\Scripts\python.exe manage.py runserver 8001
```

For pytest, keep only one pytest process alive. Run one file while developing, and the
full suite only when the unit gate calls for it:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_skeleton.py
.venv\Scripts\python.exe -m pytest
```

Regenerate the REST copy of all 15 walkthrough files whenever a unit marks routes built:

```powershell
.venv\Scripts\python.exe scripts\build_http_suite.py
```

The command reads `../docs/http/*.http` and `docs/PORT_MAP.md`, then replaces the
committed files in `http/` deterministically. A block marked `# @waiting UNIT` is kept
in its original position but is not runnable until that unit supplies a concrete New
route, marks the row `built`, and regenerates. A block marked `# @negative` deliberately
exercises a method or URL the REST API does not serve; the runner executes it, while the
old/new body comparison excludes it. `# @not-served PE-3` records the three
`frappe.client.get`-by-filter blocks that have no REST copy. Do not edit generated files
by hand.

The generated files use `http://localhost:8001`; `{{$dotenv NAME}}` remains intact and
the runner reads values from `backend_v2/.env`. With the new server already running,
replay one generated file from `backend_v2/`:

```powershell
.venv\Scripts\python.exe scripts\run_http.py http\01_auth.http
```

The runner prints one `PASS`, `FAIL`, or `SKIP` line per request block, checks the title's
status and every `# @expect`, executes tagged negative cases, and skips blocks waiting
for another unit. It exits non-zero if any block fails. `--new` overrides the default
`http://localhost:8001`, and `--timeout` sets the per-request timeout. Values read from
`.env` are redacted from all output.

For a body comparison, the old backend must be the `backend/` application in the
**main checkout**, not the `backend/` directory in this rebuild worktree: the worktree's
root environment names the v2 database. Seed that main checkout's old database, run it
on port 8000, keep the new server on 8001, and then run from `backend_v2/`:

```powershell
.venv\Scripts\python.exe scripts\parity_diff.py http\01_auth.http `
  --old http://localhost:8000 --new http://localhost:8001
```

The comparison reports `same`, `differs` with **every** differing path, or `skipped` for
waiting, negative, and PE-3 blocks. Each server has its own response-label and variable
state, so one server's login token is never sent to the other. How it compares (ACCOUNTS,
A-25 and A-26):

- **Status**, then the headers, then the body; a header difference never hides the body.
  `WWW-Authenticate` and `Retry-After` are compared exactly. `Allow` is compared only on a
  405, and only for presence: the method sets differ by design (S7, PE-1).
- **Resource envelope:** a block marked `# @resource-envelope` compares the old
  `{"data": ...}` (201 on create) with the REST `{"message": ...}` (200).
- **Rows by name:** a list whose rows all carry `name` is compared row by row, matched by
  name, with names only one side holds and a change of order reported separately.
- **Timestamps:** only under `creation`, `modified` and keys ending `_at` or `_on`, and
  there only the digits are blanked, so the format (separator, precision, zone) still
  counts. A timestamp anywhere else is compared exactly.
- **Generated names:** a ten-character lowercase hex token with at least one letter a-f is
  normalised, and old and new tokens must pair one-to-one across the response. A wrong
  link to another generated record is therefore still seen when the pairing breaks, but
  not when it is consistent — the limit of the rule.
- Rules in `scripts/parity_ignore.json` ignore only values: the path must exist on both
  sides and its type must match. Two rules today, `$.message.access` and
  `$.message.refresh`. Error `exception` and `_server_messages` values are never ignored.

`99_lockout.http` locks this machine out for 60 seconds. Run it by itself and last; it
runs against each backend in turn, not interleaved, so the failed logins land inside one
server's window. The diff refuses to combine it with other files unless
`--include-lockout` is explicit; with that flag it reorders the lockout file to the end.

`scripts/walk_auth_flow.py` walks onboarding end to end (invite-by-email, the emailed
accept link, set password, log in, forgot password) on its own test database;
`tests/test_walk_auth_flow.py` runs it under pytest. `kombu` is pinned to 5.6.2, the old
backend's version, because 5.7 refuses the pinned redis-py 5.3.1 on a real broker. The
Celery settings (queue `default`, late acknowledgement, prefetch one, JSON, results kept a
day) are the old backend's. The one-off script that reset the old `opencrm` database's
suite roles (A-25) ran once from the main checkout and is not in the tree. Neither script starts or stops a
server, and both report an unreachable configured server without a traceback.

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

Credential and child-field declarations are closed lists. A credential-shaped concrete
field must be sensitive or have a written exception; every encrypted field is sensitive,
and a sensitive true secret is encrypted unless its reviewed exception says it is hashed
or deliberately restricted-only. Exceptions must still name real fields and give a
substantive reason. Every child model declares `CHILD_FIELDS` directly. Installed models
belong in their app's `models` module or package; temporary test models belong under
`isolate_apps`, never at test-module import time. The four rules and the exception
hygiene are guarded by `tests/guards/test_model_fields.py`.

Every production `BaseDocument` model is either served or explicitly withheld, and a
routed ViewSet declares `Access.ruled()` or a reasoned `Access.open(...)`. Ruled resources
define both list and object rules; a model with a concrete sensitive or encrypted field
cannot be open. `Version` is the only current withheld type. These are guarded by
`tests/guards/test_resource_access.py`; direct manager reads that could bypass the one
resource queryset are rejected by `tests/guards/test_direct_model_access.py`.

Routes and writes remain explicit. Every concrete `built` New route resolves with its
recorded method, every production `/api/v1/` pattern has a built route-map row, malformed
route tables fail loudly, and test-only URLs do not count. Resource creates and PATCHes
must stamp the authenticated caller. The guards are
`tests/guards/test_route_map.py` and `tests/guards/test_write_stamps.py`.

An unsaved document always issues an INSERT (`force_insert=True`). A caller-supplied name
that is already taken therefore raises instead of silently updating the existing row.
Names follow the declared strategy, are never slugified, may contain slashes, and reject
only `<` and `>`. Every document save requires the acting `user`; there is no ambient
current-user state or Guest fallback (`core/tests/test_base_document.py`,
`core/tests/test_naming.py`, `tests/test_name_validation.py`, and
`tests/test_name_lookup.py`).

User tokens carry `token_version`; refresh and authentication reject stale versions, and
every save while disabled bumps the version. User admin bulk actions must stay disabled
because `QuerySet.update()` would skip that save hook. Login failures count against both
the shared IP and account trackers, and only the configured trusted proxy suffix may
supply the client IP (`tests/test_token_version.py`, `tests/test_disable_user.py`,
`tests/test_auth.py`, `tests/test_security.py`, and `tests/test_accounts_user.py`).

An encrypted field's attribute is ciphertext after save and load. Code needing plaintext
calls `get_password()`; a missing or changed key fails with the recorded wording. The
field is also sensitive, so it cannot be selected or inferred through queries
(`core/tests/test_encrypted_fields.py`, `core/tests/test_field_access.py`, and the secret
guard in `tests/guards/test_model_fields.py`).

List-query callers apply the row rule first and pass that queryset to
`build_list_queryset()`, `fetch_rows()`, or `count_rows()`; client filters only narrow
it. Hidden or non-opted-in fields are refused in `fields`, `filters`, `or_filters`,
`order_by`, and `group_by`. Text matching is case-insensitive, nested `@me` resolves from
the explicit user, and the five tree operators accept only `TreeDocument` relations.
Tree saves, reparents, and deletes take the same PostgreSQL advisory lock; a rootless
cycle written around `save()` keeps its old bounds (`core/tests/test_filters.py`,
`core/tests/test_query.py`, `core/tests/test_filter_backend.py`,
`core/tests/test_tree.py`, and `tests/test_field_security.py`).

A serialized document and every inline child row carry `doctype`. Documents render
decimals as padded strings; list projections leave them numeric. `_assign`, `_liked_by`,
and `_comments` are JSON strings in both shapes. Child input replaces only the named
table: update writes children before the parent, while create saves parent, children,
then parent atomically. Child columns remain off the wire until added to `CHILD_FIELDS`
(`core/tests/test_document_serializer.py`, `core/tests/test_child_tables.py`,
`tests/test_child_rows.py`, `tests/test_document_doctype_key.py`, and
`tests/test_wire_shapes.py`).

Lists use the row-rule queryset; record routes intentionally look up by name first and
then apply the object rule. Thus a missing record is 404 and a found denied record is
403. Create checks an unsaved instance carrying payload fields, PATCH re-checks a changed
destination, delete checks dynamic links before protected links, and an invalid integer
lookup is an ordinary 404. The value route keeps the list rule and field policy; the
permissions route returns seven booleans without turning denied read into an exception
(`tests/test_document_viewset.py`, `tests/test_resource_api.py`,
`tests/test_client_get_value.py`, `tests/test_document_value_routes.py`,
`tests/test_delete_link_check.py`, and `tests/test_delete_dependants.py`).

A singleton always has its doctype as its name and is exposed only at the resource root
with GET, PATCH, and `value/`; no list, name route, POST, PUT, or DELETE exists. Its value
route applies the object rule before field access (`tests/test_singleton_names.py` and
`tests/test_document_value_routes.py`).

Change history is opt-in through `TRACKED_FIELDS`; no-op saves and creates write no
Version, a changed save writes one row, and document deletion cleans matching references.
The 00:10 retention task deletes only old `CRM View Settings` versions, never general
history (`core/tests/test_versions.py` and `core/tests/test_version_retention.py`).

Development data has one explicit ordered step list. Seeding is idempotent but restores
the four login accounts each run; clearing reverses the steps and removes only owned
rows. Password values never appear in output (`tests/test_dev_data_commands.py`).

`backend_v2/http/` is generated, not hand-edited. Generation is deterministic and fails
on unknown or malformed mappings; replay keeps variables per runner and redacts dotenv
values; parity comparison keeps old and new state separate and ignores a value only when
the path exists on both sides with the same type (`tests/test_http_parser.py`,
`tests/test_http_suite_builder.py`, `tests/test_run_http.py`, and
`tests/test_parity_diff.py`).
