# Rebuild plan — the same CRM API, as a conventional Django REST project

**Status: Draft for review.** Written 2026-09-16; the REST decisions (S6–S8) added
2026-09-21. Decisions below are marked **Settled** (made by the owner), **Proposed**
(recommended, awaiting the owner's confirmation), **Withdrawn**, or **Open** (still to
discuss). An agent treats Settled as fixed, Proposed as the working assumption until the
review says otherwise, and never decides an Open one on its own.

**Paths are from the repository root.**

---

## 1. Why this exists

`backend/` works. The 1017-request `.http` suite in `docs/http/` passes against it, and
the Vue frontend runs on it. But it gets there by **re-implementing Frappe's request
layer on top of Django**: three generic URL patterns, a doctype registry filled by
decorators at import time, a whitelist of dotted method names (RPC-style URLs such as
`/api/method/crm.api.doc.get_data`), serializers generated per model, and an ambient
"current user" held in a context variable. `docs/BACKEND_LAYOUT.md` explains why: the
frontend speaks Frappe's wire protocol, and Frappe generates that protocol from metadata.

That design was right for a faithful port. It is wrong for a **portfolio project**: a
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
| Every protection the old backend enforces — `backend_v2/docs/PORT_MAP.md` | Code layout: thirteen Django apps instead of `frappe_core` / `frappe_platform` / `crm_app` |
| The stack: Django, DRF, SimpleJWT, PostgreSQL 17, Redis, Celery, Channels, treebeard, Python 3.13 | One ViewSet per resource with explicit field allowlists, registered on a DRF router |
| The frontend, during this rebuild | Migrations and the test suite start fresh |

## 3. Decisions

### Settled — by the owner

| # | Decision |
|---|---|
| S1 | **A new Django project beside the old one.** Rebuild work never edits `backend/`, imports from it or migrates it. It is the reference implementation. The owner still fixes it on its own branches as testing finds problems, and those fixes are part of the reference once they reach this branch. |
| S2 | **A fresh database and fresh migrations.** The old backend keeps its demo data. No data migration between them. |
| S3 | **Same responses.** Every route returns exactly the body and status the old path it replaces returned, **errors included**: the Frappe error body and the `{"message": …}` / `{"data": …}` envelopes stay. Moving errors and envelopes to DRF's native shape, with the frontend updated to match, is a later and separate step (O1). |
| S4 | **The frontend does not change in this rebuild.** Later it moves to `backend_v2`'s routes, and only its URLs and HTTP methods should need to change. |
| S5 | **Portfolio grade.** Conventional Django and DRF idioms win over cleverness wherever the contract allows a choice. |
| S6 | **REST routes under `/api/v1/`** (settled 2026-09-21). `backend_v2` serves no RPC-style dotted paths and no generic `/api/resource/<DocType>` route. The version prefix leaves room for a later `/api/v2/` with DRF-native responses. |
| S7 | **Inputs keep their names and formats** (settled 2026-09-21). Only three things change: the resource goes into the URL (`doctype="CRM Lead"` → `/api/v1/leads/`), the document name goes into the URL (`/api/v1/leads/<name>/`), and the HTTP method says what happens. Every other input — `filters`, `or_filters`, `fields`, `order_by`, `limit_start`, `limit_page_length`, every action's body — keeps its name and format. Where an old call names a field inside the request (`frappe.client.set_value` with `fieldname` and `value`), the value moves into the body instead (`PATCH` with `{"status": "Won"}`); the route map lists each such case. |
| S8 | **A route map** from every old path to its new route, method and any reshaped input, kept in `PORT_MAP.md` (settled 2026-09-21). It is the frontend's migration guide, and what the parity tooling uses to send one request to both backends. **Its contents are written after all the planning documents are reviewed** (O6). |

### Proposed — confirm in review

| # | Proposal | Why |
|---|---|---|
| P1 | **The folder is `backend_v2/`**, renamed to `backend/` once the old backend is retired. | Unambiguous while both exist. Django package names do not include the folder, so the rename touches only paths in documents. |
| P2 | ~~Keep every method path exactly.~~ **Withdrawn — superseded by S6.** | |
| P3 | ~~Keep `/api/resource/<DocType>`.~~ **Withdrawn — superseded by S6.** The `.http` suite's use of it is handled through the route map instead (section 6). | |
| P4 | **The generic layer is built from DRF's own extension points** (section 5). | Every model "inherits" the API through class inheritance, which is what Django developers expect, instead of through a registry. |
| P5 | **Thirteen apps** (section 4). | Split by domain, and on the lines agents can work in parallel without editing the same file. |
| P6 | **Precedence when sources disagree:** the old backend's behaviour is the contract; the Frappe source (CRM app on `main`, framework on `version-15`) settles anything the old backend leaves unclear; a deliberate difference is written in `PARITY_EXCEPTIONS.md` first. | The old backend already made 39 recorded decisions about upstream's bugs (`docs/UPSTREAM_BUGS_PHASE_*.md`). Re-deciding them from the Frappe source would undo that work. |
| P7 | **A fresh pytest suite.** The old tests are read to learn what behaviour matters and how it was pinned, then written again against the new code. | About 21,800 lines of old tests reach into `frappe_core` internals that will not exist. |
| P8 | **Parity is proven three ways** (section 6): pytest per app, the `.http` suite sent to `backend_v2` through the route map, and a response-body diff between the two backends. | The `.http` runner checks status codes and a few chosen body values only. On its own it would pass a response with a missing key. |
| P9 | **No ambient current user.** The user is passed explicitly: `request.user` in views, an argument to services and to the filter parser. | The old backend binds the user into a context variable (`backend/frappe_core/session.py`) so deep code can find it. That is Frappe's `frappe.session.user`; Django code takes the user as an argument. |
| P10 | **Current supported versions, pinned exactly in FOUNDATION**: Django 5.2 LTS rather than the old backend's 5.1, and the DRF, SimpleJWT, Celery and Channels releases that support it. | 5.1 is out of support. The contract does not depend on the minor version, and the body diff will say if a default changed. |
| P11 | **Both backends run at once without sharing state** (section 7). | Parity checking needs both up, and two Celery workers on one Redis database steal each other's jobs. |

### Open — to discuss before the unit that needs it

| # | Question | Needed by |
|---|---|---|
| O1 | **The long-term response format.** DRF-native errors and envelopes plus a frontend update, or keep Frappe's shapes permanently. | After parity; not blocking |
| O2 | **Where `backend_v2`'s baseline data comes from.** The suite expects `Administrator`, the demo sales users, statuses, sources and settings rows to exist (credentials in `docs/http/.env`). Options: a `seed_dev_data` management command written from what the `.http` files assume; or reference rows exported from the old backend through its own API and loaded into the new one. | FOUNDATION |
| O3 | **The old backend's eight "awaiting review" doctypes**: Contact, CRM Organization, CRM Product, CRM Service Level Agreement, CRM Call Log, CRM Telephony Agent, Email Template, Tag. Each is open to every authenticated user today, with a question recorded against it in `PORT_MAP.md`. Parity says copy that access; this rebuild is a natural moment to decide them. Proposal: copy for parity, and list each in `PARITY_EXCEPTIONS.md` as a decision still owed. | CONTACTS, SALES, ACTIVITIES, SLA, TELEPHONY |
| O4 | **When the frontend moves to `backend_v2`** — after the whole rebuild, or module by module as units finish. Until it moves, the frontend cannot run on `backend_v2`. | Before the first unit's routes are final |
| O5 | **The filter, sort and pagination design for the REST routes.** The working assumption is S7: Frappe's grammar, unchanged, sent to the new routes. To be discussed in detail. | FOUNDATION |
| O6 | **The route map's contents**: each resource's URL name, each action's path, which old paths collapse into one route, and the few reshaped inputs. After the planning documents are reviewed. | FOUNDATION (conventions), then each unit |
| O7 | **Where the generic operations live** now that no route takes a doctype as data: bulk delete and update, rename, linked documents, link search, the `get_data` list view, field metadata. Per-resource actions inherited from mixins, or endpoints in one app that look the resource up. Part of the route-map discussion. | FOUNDATION |

## 4. The apps

```
backend_v2/
├── manage.py
├── requirements.txt
├── .env.example
├── config/                 settings/{base,local,test}.py, urls.py, asgi.py, routing.py, celery.py
├── apps/
│   ├── core/
│   ├── accounts/
│   ├── ...                 one package per app below
│   └── integrations/
├── scripts/                parity tooling
├── CLAUDE.md               rules for Claude here; Codex's brief is the root AGENTS.md
├── docs/                   this plan, the contract, the map, as-built, exceptions, runs/
└── specs/                  one spec per unit, and the index
```

Inside an app, the usual Django files and nothing unusual: `models.py` (or a `models/`
package), `serializers.py`, `viewsets.py` (one ViewSet per resource), `views.py`
(endpoints that are not a resource), `urls.py` (the app's router and routes),
`permissions.py`, `services.py` (business logic that is not one model's), `tasks.py`,
`signals.py`, `admin.py`, `migrations/`, `tests/`.

| App | Owns | Unit |
|---|---|---|
| `core` | The shared API layer: base document model and naming, exceptions and the error body, renderers, input parsing, the base view for non-resource endpoints, the filter and ordering backends, pagination, field access, the base document ViewSet. `Version` (the change history). No product logic | FOUNDATION |
| `accounts` | `User` and roles, login/logout/refresh, lockout and rate limits, password reset, invitations, user administration, the sales hierarchy | FOUNDATION (User, auth), then ACCOUNTS |
| `crm_settings` | FCRM Settings and its dropdown items, Email Account, the Desk plumbing calls (`get_apps`, `boot_config`, translations, site info), demo data, exchange rates | SETTINGS |
| `metadata` | Saved views, field layouts, form scripts, global settings, per-user list settings, field metadata, and the `get_data` list/kanban engine | METADATA |
| `contacts` | Contact and its email/phone rows, Dynamic Link, Organization, Industry | CONTACTS |
| `sales` | Lead, Deal, their statuses, sources, lost reasons, territories, products, deal contacts, status history, lead-to-deal conversion, and the org-hierarchy row rules | SALES |
| `activities` | Comments, emails (Communication, `email.make`, templates), notes, tasks, files, tags, likes, assignments (ToDo) and assignment rules, the activity timeline | ACTIVITIES |
| `documents` | The generic operations every resource offers — bulk delete and update, rename, linked documents, link search. Its exact shape is O7 | FOUNDATION (the base CRUD), then DOCUMENTS |
| `notifications` | In-app notifications, and the Channels WebSocket that delivers live events | NOTIFICATIONS |
| `dashboard` | Dashboard layouts and the chart endpoints | DASHBOARD |
| `sla` | Service level agreements, service days, priorities, holiday lists, response-time tracking | SLA |
| `telephony` | Call logs, telephony agents and phones, Twilio and Exotel settings and webhooks | TELEPHONY |
| `integrations` | ERPNext, Facebook lead sync, WhatsApp — all behind `ENABLE_*` flags, off by default | INTEGRATIONS |

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
| `filters` / `or_filters` grammar, `@me` | `core.filters.FrappeFilterBackend`, a `BaseFilterBackend` (design details: O5) |
| `order_by="modified desc"` | `core.filters.FrappeOrderingBackend`, against the ViewSet's `ordering_fields` (O5) |
| `limit_start` / `limit_page_length` | `core.pagination.LimitStartPagination` — returns the bare list, as the contract requires (O5) |
| `fields=` | `core.fields` — narrows the queryset's columns against the ViewSet's readable fields |
| Actions on one document or a collection | DRF `@action` on the resource's ViewSet — `POST /api/v1/leads/<name>/convert-to-deal/` |
| Link search, bulk actions, rename, linked documents, the list view | Per-resource routes; how they are shared is O7 |
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
is literal code rather than a registry (O7).

**Endpoints that are not a resource** — login, dashboard charts, the settings plumbing —
are ordinary DRF views on `core`'s base view, which parses inputs the old way (S7),
answers 401 for a missing token unless the view is a guest one, and applies the envelope.
Each is routed explicitly in its app's `urls.py`.

**Document names can contain slashes** (`R/GA` is a legal organization name), which a
REST path must allow without swallowing the action segment after it. FOUNDATION settles
how and records it in `AS_BUILT.md`.

## 6. How parity is proven

1. **pytest, per app** — behaviour and permissions, written fresh (P7).
2. **The `.http` suite, sent to `backend_v2` through the route map.** Its requests use the
   old paths, so each one is translated — path, HTTP method, and the few reshaped inputs
   (S7) — before it reaches `backend_v2`. The translation is mechanical by design. Whether
   it produces a translated copy of the files or happens inside the tooling is decided
   with the route map (O6). When replaying against `backend/`, **never pass `--mark` to
   `run_http.py`** from rebuild work: it writes to `docs/ROUTES.md`.
3. **A response-body diff between the two backends** — `backend_v2/scripts/parity_diff.py`,
   built in FOUNDATION. It sends the original request to `backend/` and the translated one
   to `backend_v2`, and compares status and body after normalising what legitimately
   differs (tokens, timestamps, generated names). This is what catches a missing key, a
   number that became a string, or a message reworded. How both servers get the same
   baseline data is O2.
4. **The frontend on `backend_v2`** — when it moves (O4), which is its own project.

## 7. Running both backends at once

| | `backend/` | `backend_v2/` |
|---|---|---|
| Port | 8000 | **8001** |
| Virtualenv | `backend/.venv` | `backend_v2/.venv` |
| Settings read from | repository-root `.env` | **`backend_v2/.env`** |
| PostgreSQL database | `opencrm` | **`opencrm_v2`** |
| Test database | `test_opencrm` | **`test_opencrm_v2`** |
| Redis: cache, broker, results, channels | DB 0, 0, 1, 2 | **DB 3, 4, 5, 6** |

## 8. Out of scope

- Any change under `frontend/`; and, from rebuild work, under `backend/`.
- DRF-native errors and envelopes (O1).
- Input formats beyond what S7 allows; the filter and sort design is O5.
- Moving data out of the old database (S2).
- New product features, and behaviour changes not recorded in `PARITY_EXCEPTIONS.md`.
- Deployment, Docker, CI.
- Integrations beyond parity: they stay behind their flags, off by default.

## 9. Done means

1. The route map in `PORT_MAP.md` gives every old path its new route, and every row is
   `parity` or `exception`.
2. Every `.http` block, translated through the route map, gets the same status and body
   from `backend_v2` as the original gets from `backend/`, apart from entries in
   `PARITY_EXCEPTIONS.md`.
3. The body diff is clean apart from recorded exceptions.
4. pytest is green in `backend_v2/`.
5. `backend_v2/docs/AS_BUILT.md` describes what exists, and a portfolio `README.md` explains
   the project to a stranger.
6. Moving the frontend (O4), retiring `backend/` and renaming the folder are then the
   owner's calls, each as its own step.

## 10. Risks, and what answers each

| Risk | Answer |
|---|---|
| **A protection is silently lost.** The old backend's hardest-won work is its security, and five findings came from one generic route standing open beside a guarded endpoint | `PORT_MAP.md` carries each doctype's protection and declared fields, and a row is not `built` until they are enforced. Allowlists default to nothing. The two guard tests are rebuilt in FOUNDATION: every resource has a recorded access decision, and every credential-shaped field is declared |
| **A route looks right and answers differently** from the old path it replaces | The body diff through the route map (section 6, step 3) |
| **Parity measured by status codes alone** | The same body diff |
| **The frontend migration turns out bigger than swapping URLs** | S7 keeps inputs as they are; the route map names every reshaped input, so the size of the migration is known before it starts |
| **Traps in the rendering** — decimals are strings in a document and numbers in a list | Written into `API_CONTRACT.md` section 6, and caught by the body diff |
| **Improving while porting** | Any behaviour change needs a `PARITY_EXCEPTIONS.md` entry first |
| **`get_data` is the keystone** — six screens render from it, and it is where filters, `@me`, saved views and columns meet | METADATA is its own unit, built early, against models written for its tests |
| **Two servers stepping on each other** — shared Redis, shared test database, a stale `runserver` still holding a port on Windows | Section 7, and the operational notes in `backend_v2/CLAUDE.md` |
