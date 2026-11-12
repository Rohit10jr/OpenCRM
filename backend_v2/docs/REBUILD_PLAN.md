# Rebuild plan — the same CRM API, as a conventional Django REST project

**Status: In review.** Decisions below are **Settled** (made by the owner) or **Open**
(still to discuss). An agent treats Settled as fixed, and never decides an Open one on its
own.

**Paths are from the repository root.**

---

## 1. Why this exists

`backend/` works. The `.http` suite (1,072 requests) in `docs/http/` passes against it, and
the Vue frontend runs on it. But it gets there by **re-implementing Frappe's request
layer on top of Django**: three generic URL patterns, a doctype registry filled by
decorators at import time, a whitelist of dotted method names (RPC-style URLs such as
`/api/method/crm.api.doc.get_data`), serializers generated per model, and an ambient
"current user" held in a context variable. `docs/BACKEND_LAYOUT.md` explains why: the
frontend speaks Frappe's wire protocol, and Frappe generates that protocol from metadata.

That design was right for a faithful port. It is wrong for a project other people will
read and build on — a **portfolio project now, and possibly a broader product later**: a
Django developer opening `backend/` finds no `urls.py` listing the API, no ViewSet per
resource, and a framework of its own to learn before any of the CRM makes sense.

**The goal:** the same product, rebuilt in `backend_v2/` as a **conventional Django REST
API** — one app per domain, REST routes under `/api/v1/`, DRF ViewSets and routers,
serializers, permission classes, services — that **answers every request with the same
body the old backend gives**. The frontend is not changed in this rebuild. When it is,
moving it to `backend_v2` means changing which URL and HTTP method each call uses, and
nothing it does with the response.

## 2. What stays, what changes

| Stays exactly | Changes |
|---|---|
| Every response body and status code, errors included — `backend_v2/docs/API_CONTRACT.md` | **The URLs**: REST routes under `/api/v1/` replace the RPC-style dotted paths and the generic `/api/resource/` route |
| **Every input's name and format** — the same parameters, the same filter grammar (S7) | **The HTTP method** says what happens: `GET` reads, `POST` creates or runs an action, `PATCH` updates, `DELETE` deletes |
| Every protection the old backend enforces — `backend_v2/docs/PORT_MAP.md` | Code layout: ten Django apps instead of `frappe_core` / `frappe_platform` / `crm_app` |
| The stack: Django, DRF, SimpleJWT, PostgreSQL 17, Redis, Celery, Channels, treebeard, Python 3.13 | One ViewSet per resource with explicit field allowlists, registered on a DRF router |
| The frontend, during this rebuild | Migrations and the test suite start fresh |

## 3. Decisions

### Settled — by the owner

| # | Decision |
|---|---|
| S1 | **A new Django project beside the old one.** Rebuild work never edits `backend/`, imports from it or migrates it. It is the reference implementation. The owner still fixes it on its own branches as testing finds problems, and those fixes are part of the reference once they reach this branch. |
| S2 | **A fresh database and fresh migrations.** The old backend keeps its demo data. No data migration between them. |
| S3 | **Same responses.** Every route returns exactly the body and status the old path it replaces returned, **errors included**: the Frappe error body and the `{"message": …}` / `{"data": …}` envelopes stay. Moving errors and envelopes to DRF's native shape, with the frontend updated to match, is a later and separate step (S19). |
| S4 | **The frontend does not change in this rebuild.** Later it moves to `backend_v2`'s routes, and only its URLs and HTTP methods should need to change. |
| S5 | **Portfolio grade, built to grow into a product.** It is a portfolio project first, and may be developed into a broader product later, so the code is written for other developers to read and extend. Conventional Django and DRF idioms win over cleverness wherever the contract allows a choice. |
| S6 | **REST routes under `/api/v1/`**. `backend_v2` serves no RPC-style dotted paths and no generic `/api/resource/<DocType>` route. The version prefix leaves room for a later `/api/v2/` with DRF-native responses. |
| S7 | **Inputs keep their names and formats**. Only three things change: the resource goes into the URL (`doctype="CRM Lead"` → `/api/v1/leads/`), the document name goes into the URL (`/api/v1/leads/<name>/`), and the HTTP method says what happens. Every other input — `filters`, `or_filters`, `fields`, `order_by`, `limit_start`, `limit_page_length`, every action's body — keeps its name and format. Where an old call names a field inside the request (`frappe.client.set_value` with `fieldname` and `value`), the value moves into the body instead (`PATCH` with `{"status": "Won"}`); the route map lists each such case. |
| S8 | **A route map** from every old path to its new route, method and any reshaped input, kept in `PORT_MAP.md`. It is the frontend's migration guide, and what the REST copy of the `.http` suite is generated from (S9). **Its rows are written next, following the naming rules in S25.** |
| S9 | **`backend_v2` gets its own copy of the `.http` suite**. The old files in `docs/http/` use the old URLs, so they cannot be sent to `backend_v2` as they are. A script generates a REST copy from the route map into `backend_v2/http/`: same file names, same requests and expected answers — only the URLs, methods and reshaped inputs change. It is `backend_v2`'s acceptance suite, can be clicked through in VS Code like the old one, and stays after `backend/` is retired. The old files stay unchanged, for the old backend. |
| S10 | **The folder is `backend_v2/`**, renamed to `backend/` once the old backend is retired. Django package names do not include the folder, so the rename touches only paths in documents. |
| S11 | **The shared behaviour is built from DRF's own classes** (section 5). CRUD comes from DRF's `GenericViewSet` and its list/create/retrieve/update/destroy mixins, with routers, serializers, filter backends and pagination. One base class, `DocumentViewSet`, adds what is specific to this CRM — the Frappe filter format, the envelopes, the field and permission rules — and every resource subclasses it. No registry. |
| S12 | **Ten apps** (reduced from thirteen; section 4), split by area and on the lines agents can work in parallel without editing the same file. The split is a starting point, not a rule: a building agent may improve it with a proper reason (section 4). |
| S13 | **When sources disagree, the old backend wins**. The Frappe source (CRM at tag `port-base`, upstream v1.82.0; framework `version-15`) only settles what the old backend leaves unclear, and a deliberate difference is written in `PARITY_EXCEPTIONS.md` first. The old backend has made 83 recorded decisions about upstream's bugs (`UPSTREAM_BUGS.md`); deciding them again would undo that work. |
| S14 | **Old API tests are ported; the rest are written new**. This is about the Python tests in `backend/tests/` (119 files, about 30,800 lines), not the `.http` files (S9). **About 50 files call the API through the test client: these are ported** — new URLs, methods and imports, the same expected answers — because their expectations come from the old backend, not from the author of the new code, who would otherwise test only what they believe it does. The others test old internals — the registry, `frappe_core`, the field-security layer — that `backend_v2` does not have: they are read to learn what behaviour matters and written again against the new code. **A new test is written only where no old test covers the behaviour.** A ported test changes its expected answer only with an approved `PARITY_EXCEPTIONS.md` entry. |
| S15 | **Parity is checked three ways** (section 6): `backend_v2`'s own pytest tests; the REST copy of the `.http` suite, which checks status codes and chosen values; and the full-response comparison, which catches what the `.http` runner cannot — a missing key, a reworded message. |
| S16 | **The user is passed along** — `request.user` in views, an argument to services and to the filter code — never read from a hidden global, as the old backend does (`backend/frappe_core/session.py`). |
| S17 | **Django 5.2 LTS**, the old backend's version too (5.2.18 in `backend/requirements.txt`), with the DRF, SimpleJWT, Celery and Channels releases that support it — pinned exactly in FOUNDATION. Moving to the next LTS (6.2) is a step after parity, not during it; the body comparison would show if a default changed. |
| S18 | **Both backends run at once without sharing anything** (section 7): `backend_v2` has its own port, `.env`, database, test database and Redis databases. Sharing the `.env` would run the new migrations inside the old demo database, and sharing Redis would let one backend's Celery worker take the other's jobs. |
| S19 | **Same responses now; DRF-style responses later, step by step**. Every response keeps Frappe's shape (S3) until `backend_v2` is finished and runs with the frontend. After that, errors and envelopes move to DRF's normal shape a step at a time, with the frontend updated at each step. This will happen — it is a later phase, not an option. |
| S20 | **Two management commands for development data**. `seed_dev_data` loads what a fresh install and the `.http` suite need; `clear_dev_data` removes exactly what it loaded, and nothing else. **The old backend's own seed commands are ported**, so both backends start from the same rows by construction: **(1)** `seed_defaults` (`backend/crm_app/management/commands/seed_defaults.py`, data and rules in `backend/crm_app/setup.py`) — the reference rows upstream's install step writes: lead, deal and communication statuses, field layouts, industries, lead sources, lost reasons, quick filters, the user menu, the standard form scripts and the manager dashboard; **(2)** the users the `.http` suite and the browser tests log in as, with their roles, as the old `seed_e2e_users` does — passwords read from `backend_v2/.env`, never written in code; **(3)** optionally, behind a flag, upstream's demo records from `crm/demo/` — three demo users, leads, deals, notes, tasks, call logs and activities — which upstream also removes with `clear_demo_data`. FOUNDATION checks that the old backend's demo database holds the same reference rows, so the two backends can be compared, and records any gap. |
| S21 | **The eight doctypes the old backend left "awaiting review" keep the access the old backend gives them** (**resolved on `main` since**). The old backend has now decided all eight: Contact, CRM Service Level Agreement, Email Template and Tag got list and object rules; CRM Organization, CRM Product, CRM Call Log and CRM Telephony Agent were reviewed and stay open to every CRM role, as upstream's role table grants. `PORT_MAP.md` carries those decisions, and the rebuild copies them like any other (S13). No question is left for after the rebuild. |
| S22 | **The frontend moves after the whole of `backend_v2` is finished**, not module by module. |
| S23 | **Lists keep Frappe's filter, sort and paging format for now**. A list request sends `filters`, `or_filters`, `order_by`, `limit_start` and `limit_page_length` exactly as today — e.g. `GET /api/v1/leads/?filters=[["status","=","Open"]]&order_by=modified desc&limit_page_length=20` — so the frontend's list code does not change and every Frappe operator keeps working (`like`, `between`, `@me`, `descendants of`). Normal DRF-style parameters (`?status=Open&ordering=-modified&limit=20`) come later, together with the DRF-style responses (S19). |
| S24 | **Shared operations are mixins**. Bulk delete, bulk update, rename, linked documents and link search come from mixins in `core` (`core/mixins/`); the list view (`get_data`) and field metadata from mixins in the `configuration` app. A resource's ViewSet opts in to the ones it needs, and gets them as its own routes — `/api/v1/leads/bulk-delete/`, `/api/v1/leads/search/`, `/api/v1/leads/list-view/` — with its own permission and field rules applied. No endpoint takes a resource name as data. |
| S25 | **Route naming rules**. **(1)** A resource is plural, lower-case and hyphenated, without the CRM/FCRM prefix: CRM Lead → `/api/v1/leads/`, CRM Call Log → `/api/v1/call-logs/`, FCRM Note → `/api/v1/notes/`, CRM Lead Status → `/api/v1/lead-statuses/`. **(2)** One record is `/api/v1/<resource>/<name>/`: `GET` reads, `PATCH` updates, `DELETE` deletes. **Updates are PATCH only; PUT is not served**, and DRF's default PUT is switched off in the base ViewSet — every old update was partial, and a full replacement would blank any field a client forgot. **(3)** A settings record that exists once has no name in the URL: `/api/v1/crm-settings/`, `/api/v1/twilio-settings/`, with `GET` and `PATCH` only. **(4)** Actions are hyphenated verbs — on one record `POST /api/v1/leads/<name>/convert-to-deal/`, on the collection `POST /api/v1/leads/bulk-delete/`. Read-only actions use `GET`; the list view also accepts `POST`, because its inputs (columns, kanban settings) are too big for a URL. **(5)** Things that belong to one record nest one level, never deeper: `/api/v1/deals/<name>/contacts/`. **(6)** Endpoints that are not a resource are grouped by area: `/api/v1/auth/login/`, `/api/v1/auth/logout/`, `/api/v1/auth/token/refresh/`, `/api/v1/auth/me/`, `/api/v1/dashboard/charts/<name>/`, `/api/v1/webhooks/twilio/voice/` (moving a webhook also means updating the provider's console). **(7)** The trailing slash is optional, as in the old backend. **(8)** A name may contain slashes (the organization `R/GA`): the URL accepts them, and action routes are matched first, so `/organizations/R/GA/` is the record. A record named exactly like an action (an organization called `search`) cannot be reached — a known limit. |

### Open — to discuss before the unit that needs it

| # | Question | Needed by |
|---|---|---|
| — | **None open.** The route map's rows are the next task, not a question (S8, S25). | — |

## 4. The apps

```
backend_v2/
├── manage.py
├── requirements.txt
├── .env.example
├── config/                 settings/{base,local,test}.py, urls.py, asgi.py, routing.py, celery.py
├── core/                   apps at the top level, imported as `core`, `accounts`, …
├── accounts/               (owner, 12 Nov 2026; FOUNDATION section 6)
├── ...                     one package per app below
├── integrations/
├── scripts/                parity tooling
├── docs/                   this plan, the contract, the map, as-built, exceptions
└── specs/                  one spec per unit, and the index
```

Inside an app, the usual Django files and nothing unusual: `models.py` (or a `models/`
package), `serializers.py`, `viewsets.py` (one ViewSet per resource), `views.py`
(endpoints that are not a resource), `urls.py` (the app's router and routes),
`permissions.py`, `services.py` (business logic that is not one model's), `tasks.py`,
`signals.py`, `admin.py`, `migrations/`, `tests/`.

| App | Owns | Unit |
|---|---|---|
| `core` | The shared API layer: base document model and naming, exceptions and the error body, renderers, input parsing, the base view for non-resource endpoints, the filter and ordering backends, pagination, field access, the base document ViewSet, and **the shared-action mixins** in `core/mixins/` (bulk delete and update, rename, linked documents, link search, list export — S24). `Version` (the change history). **The conditions evaluator and the assignment engine** (SHARED_ACTIONS): shared services SLA and SALES call on save, built before either. **Data Import** in `core/data_import/`: the CSV import that writes every importable doctype through its normal create path. No product logic | FOUNDATION, then SHARED_ACTIONS (the mixins), then DATA_IMPORT |
| `accounts` | `User` (and its User Email rows) and roles, login/logout/refresh, lockout and rate limits, password reset, invitations, user administration, the sales hierarchy | FOUNDATION (User, auth), then ACCOUNTS |
| `configuration` | Everything an admin configures, and the list engine that reads it: FCRM Settings and its dropdown items, Email Account, the Desk plumbing calls, exchange rates, saved views, field layouts, form scripts, global and per-user list settings, field metadata, the `get_data` list/kanban engine and its mixin, System Settings, the reference data (Country, Currency, Language), onboarding status | CONFIGURATION |
| `contacts` | Contact and its email/phone rows, Address, Dynamic Link, Organization, Industry, Salutation, Gender | CONTACTS |
| `sla` | Service level agreements, service days, priorities, holiday lists, and the deadline calculation that leads and deals call on save | SLA |
| `sales` | Lead, Deal, their statuses, sources, lost reasons, territories, products, deal contacts, status history, lead-to-deal conversion, and the org-hierarchy row rules | SALES |
| `activities` | Comments, emails (Communication, `email.make`, templates), notes, tasks, **call logs** (with phone-number lookup), files and uploads, tags, likes, assignments (ToDo) and the Assignment Rule doctypes and routes (with their bulk apply; the engine is in `core`), the activity timeline | ACTIVITIES |
| `notifications` | In-app notifications, and the Channels WebSocket that delivers live events | NOTIFICATIONS |
| `dashboard` | Dashboard layouts and the chart endpoints | DASHBOARD |
| `integrations` | Every outside service, each behind its `ENABLE_*` flag and off by default: **Twilio and Exotel** (settings, webhooks, telephony agents), ERPNext, Facebook lead sync, WhatsApp | INTEGRATIONS |

**This split is not final.** If the agent building a unit finds a better way to divide the code — merging, splitting or moving something — it may do so, provided it gives a proper reason: proposed in the unit's spec check or a brief's report before the code changes, and recorded in the unit's progress report (its pull request description) after. It then updates `PORT_MAP.md`, this section and `specs/README.md` in the same work, and never breaks a hard rule doing it — in particular, no two agents working at once may end up editing the same file.

The row-by-row assignment of every doctype and old path is `PORT_MAP.md`. Unit order
and dependencies are `backend_v2/specs/README.md`.

## 5. The generic layer — how every model "inherits" the API

Frappe gives every doctype CRUD, a query grammar, search, bulk actions and permission
filtering for free. `backend_v2` gets the same by **inheriting from one base ViewSet**
registered on a DRF router, with each Frappe behaviour placed at the DRF extension point
built for it:

| Frappe behaviour | Where it lives in `backend_v2` |
|---|---|
| CRUD for every doctype | `core.viewsets.DocumentViewSet` — a `GenericViewSet` with the list/retrieve/create/update/destroy mixins, registered on its app's router at `/api/v1/<resource>/`. Each resource subclasses it |
| `filters` / `or_filters` grammar, `@me` | `core.filters.FrappeFilterBackend`, a `BaseFilterBackend` (S23) |
| `order_by="modified desc"` | `core.filters.FrappeOrderingBackend`, against the ViewSet's `ordering_fields` (S23) |
| `limit_start` / `limit_page_length` | `core.pagination.LimitStartPagination` — returns the bare list, as the contract requires (S23) |
| `fields=` | `core.fields` — narrows the queryset's columns against the ViewSet's readable fields |
| Actions on one document or a collection | DRF `@action` on the resource's ViewSet — `POST /api/v1/leads/<name>/convert-to-deal/` |
| Link search, bulk actions, rename, linked documents, the list view | Mixins a resource's ViewSet opts in to, giving it its own routes (S24) |
| Row-level permissions | `get_queryset()` narrows the list; a DRF permission class answers the object check. The rules live in the owning app's `permissions.py` |
| Sensitive / restricted / read-only fields | Declared on the ViewSet and enforced in one place for output, `fields`, filters, ordering and grouping; encryption at rest is a model field type |
| `{"message": …}` / `{"data": …}` | `core.renderers`, applying the envelope the old path used (S3) |
| Frappe's error body | `core.exceptions.exception_handler`, set as DRF's `EXCEPTION_HANDLER` |
| Controller hooks (`validate`, `before_save`, `on_update`) | Serializer `validate()`, model `clean()`/`save()`, or a function in `services.py` — never a signal where a direct call would do |

A resource then declares only what is its own:

```python
class LeadViewSet(DocumentViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticated, LeadAccess]
    filterable_fields = [...]      # explicit — a new column is not filterable until listed
    ordering_fields = [...]
    search_fields = ["lead_name", "email", "organization"]
    sensitive_fields = []

    @action(detail=True, methods=["post"], url_path="convert-to-deal")
    def convert_to_deal(self, request, pk=None):
        ...

# sales/urls.py
router = DefaultRouter()
router.register("leads", LeadViewSet, basename="lead")
urlpatterns = router.urls
```

**Allowlists are explicit.** In the old backend every concrete field was readable,
filterable and sortable unless declared hidden; five security findings came from that
default. Here a new field is invisible until it is listed. For parity the first lists
contain exactly what the old backend exposes today.

**Nothing is routed by doctype name.** Every route belongs to a resource and is written
in its app's `urls.py`. Some inputs still name a doctype as data — field metadata, saved
views, `getdoctype` — and the lookup from a doctype name to its resource, if one is kept,
is literal code rather than a registry (S24).

**Endpoints that are not a resource** — login, dashboard charts, the settings plumbing —
are ordinary DRF views on `core`'s base view, which parses inputs the old way (S7),
answers 401 for a missing token unless the view is a guest one, and applies the envelope.
Each is routed explicitly in its app's `urls.py`.

**Document names can contain slashes** (`R/GA` is a legal organization name), which a
REST path must allow without swallowing the action segment after it. FOUNDATION settles
how and records it in `AS_BUILT.md`.

## 6. How parity is proven

1. **pytest, per app** — behaviour and permissions: the old API tests ported, the rest
   written new (S14).
2. **The REST copy of the `.http` suite** (S9), run against `backend_v2`. Example — one old
   block and its copy:

   ```
   ### Mark the deal as won -> 200                     (docs/http/04_deals.http)
   POST http://localhost:8000/api/method/frappe.client.set_value
   {"doctype": "CRM Deal", "name": "{{deal}}", "fieldname": "status", "value": "Won"}

   ### Mark the deal as won -> 200                     (backend_v2/http/04_deals.http)
   PATCH http://localhost:8001/api/v1/deals/{{deal}}/
   {"status": "Won"}
   ```

   Same test, same expected answer; only the URL, method and input shape changed, as the
   route map says. The copy grows as each unit adds its routes to the map.
3. **A response-body comparison** — `backend_v2/scripts/parity_diff.py`, built in
   FOUNDATION. The `.http` runner only checks the status code and a few chosen values, so
   it would miss a missing key or a reworded message. This tool sends each old block to
   `backend/` (port 8000) and its copy to `backend_v2` (port 8001), and compares the two
   full responses, ignoring what naturally differs (tokens, timestamps, generated names).
   Both servers start from the same reference data; `backend_v2` gets it from
   `seed_dev_data` (S20).
4. **The frontend on `backend_v2`** — after `backend_v2` is finished (S22), as its own project.

## 7. Running both backends at once

| | `backend/` | `backend_v2/` |
|---|---|---|
| Port | 8000 | **8001** |
| Virtualenv | `backend/.venv` | `backend_v2/.venv` |
| Settings read from | repository-root `.env` | **`backend_v2/.env`** |
| PostgreSQL database | `opencrm` | **`opencrm_v2`** |
| Test database | `test_opencrm` | **`test_opencrm_v2`** |
| Redis: cache, broker, results, channels | DB 3, 0, 0, 0 | **DB 4, 5, 6, 7** |

The old backend's column is its settings' defaults (`backend/config/settings/base.py`:
`CACHE_URL` on DB 3, `REDIS_URL` on DB 0 for the broker, results and channel layer).
`backend_v2` uses none of them. The root `.env.example` sets `CHANNELS_REDIS_URL`, which
the old settings do not read (they read `CHANNEL_LAYER_URL`), so that line has no effect.

## 8. Out of scope

- Any change under `frontend/`; and, from rebuild work, under `backend/`.
- DRF-native errors and envelopes (S19).
- Input formats beyond what S7 allows, and DRF-style filter parameters (S23).
- Moving data out of the old database (S2).
- New product features, and behaviour changes not recorded in `PARITY_EXCEPTIONS.md`.
- Deployment and Docker. **CI is in scope:** a `backend_v2` GitHub workflow runs its
  pytest suite on every push, beside the five workflows `main` already has
  (`.github/workflows/`), so parity is guarded as units land and not only on this machine.
- Integrations beyond parity: they stay behind their flags, off by default.

**After parity, in this order, each its own stage:** retire `backend/` and rename
`backend_v2/` to `backend/` (S10); move the frontend to it (S22) and then to DRF-style
responses (S19, S23); the upstream sync — the port's base was 1,083 commits behind
upstream `main` on 3 Nov 2026 (`specs/KNOWN_ISSUES.md` §11) — and translations; the next
Django LTS (S17). None of them is part of this rebuild.

## 9. Done means

1. The route map in `PORT_MAP.md` gives every old path its new route, and every row is
   `parity` or `exception`.
2. Every block in `backend_v2/http/` gets the same status and body from `backend_v2` as
   its original in `docs/http/` gets from `backend/`, apart from entries in
   `PARITY_EXCEPTIONS.md`.
3. The body diff is clean apart from recorded exceptions.
4. pytest is green in `backend_v2/`.
5. `backend_v2/docs/AS_BUILT.md` describes what exists, and a `README.md` explains
   the project to a stranger.
6. Moving the frontend (S22), retiring `backend/` and renaming the folder are then the
   owner's calls, each as its own step.

## 10. Risks, and what answers each

| Risk | Answer |
|---|---|
| **A protection is silently lost.** The old backend's hardest-won work is its security, and five findings came from one generic route standing open beside a guarded endpoint | `PORT_MAP.md` carries each doctype's protection and declared fields, and a row is not `built` until they are enforced. Allowlists default to nothing. The two guard tests are rebuilt in FOUNDATION: every resource has a recorded access decision, and every credential-shaped field is declared |
| **A route looks right and answers differently** from the old path it replaces | The response-body comparison (section 6, step 3) |
| **Parity measured by status codes alone** | The same body diff |
| **The frontend migration turns out bigger than swapping URLs** | S7 keeps inputs as they are; the route map names every reshaped input, so the size of the migration is known before it starts |
| **Traps in the rendering** — decimals are strings in a document and numbers in a list | Written into `API_CONTRACT.md` section 6, and caught by the body diff |
| **Improving while porting** | Any behaviour change needs a `PARITY_EXCEPTIONS.md` entry first |
| **`get_data` is the keystone** — six screens render from it, and it is where filters, `@me`, saved views and columns meet | It is built early, in CONFIGURATION, against models written for its tests |
| **Two servers stepping on each other** — shared Redis, shared test database, a stale `runserver` still holding a port on Windows | Section 7, and the traps in `AS_BUILT.md` section 3 |
| **The reference keeps moving** — `backend/` gained 230 commits between this plan and the first unit, and the owner still fixes it | `main` is merged into `django-rebuild` when the owner asks; a brief names the `main` commit its reference was read at; `PORT_MAP.md` is refreshed against `docs/ROUTES.md` before each unit, so new routes and changed protections are placed before they are built |
