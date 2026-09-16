# Rebuild plan — the same CRM API, as a conventional Django project

**Status: Draft for review, 2026-09-16.** Decisions below are marked **Settled** (made by
the owner), **Proposed** (recommended, awaiting the owner's confirmation) or **Open**
(still to discuss). An agent treats Settled as fixed, Proposed as the working assumption
until the review says otherwise, and never decides an Open one on its own.

**Paths are from the repository root.**

---

## 1. Why this exists

`backend/` works. The 1017-request `.http` suite in `docs/http/` passes against it, and
the Vue frontend runs on it. But it gets there by **re-implementing Frappe's request
layer on top of Django**: three generic URL patterns, a doctype registry filled by
decorators at import time, a whitelist of dotted method names, serializers generated per
model, and an ambient "current user" held in a context variable. `docs/BACKEND_LAYOUT.md`
explains why: the frontend speaks Frappe's wire protocol, and Frappe generates that
protocol from metadata.

That design was right for a faithful port. It is wrong for a **portfolio project**: a
Django developer opening `backend/` finds no `urls.py` listing the API, no ViewSet per
resource, and a framework of its own to learn before any of the CRM makes sense.

**The goal:** the same product and **the same JSON**, rebuilt as a Django project a Django
developer recognises on sight — one app per domain, explicit URLs, DRF ViewSets and
serializers, permission classes, services — in `backend_v2/`, beside the old backend.

## 2. What stays, what changes

| Stays exactly | Changes |
|---|---|
| Every response body and status code — `backend_v2/docs/API_CONTRACT.md` | Code layout: thirteen Django apps instead of `frappe_core` / `frappe_platform` / `crm_app` |
| Every URL the frontend calls | Routes are listed in each app's `urls.py`, not discovered from a registry |
| The frontend — not touched in this rebuild | One ViewSet per doctype with explicit field allowlists, instead of generated serializers |
| Every protection the old backend enforces — `backend_v2/docs/PORT_MAP.md` | Migrations start fresh |
| The stack: Django, DRF, SimpleJWT, PostgreSQL 17, Redis, Celery, Channels, treebeard, Python 3.13 | The test suite is written fresh (Proposed, P7) |

## 3. Decisions

### Settled — by the owner, 2026-09-16

| # | Decision |
|---|---|
| S1 | **A new Django project beside the old one.** `backend/` is not touched: not edited, not imported from, not migrated. It is the reference implementation until the rebuild is done. |
| S2 | **A fresh database and fresh migrations.** The old backend keeps its demo data. No data migration between them. |
| S3 | **JSON parity first.** Every endpoint returns what the old one returns, errors included. Moving errors to DRF's native shape, and updating the frontend to match, is a later and separate step (Open, O1). |
| S4 | **The frontend does not change in this rebuild.** It will change later; that is another project. |
| S5 | **Portfolio grade.** Conventional Django and DRF idioms win over cleverness wherever the contract allows a choice. |

### Proposed — confirm in review

| # | Proposal | Why |
|---|---|---|
| P1 | **The folder is `backend_v2/`**, renamed to `backend/` once the old backend is retired. | Unambiguous while both exist. Django package names do not include the folder, so the rename touches only paths in documents. |
| P2 | **Keep every method path exactly, and list each one in its app's `urls.py`.** Conventional REST URLs come later, one module at a time, together with the frontend change that uses them. | The frontend and the `.http` suite keep working unchanged, which is what makes parity checkable at all. |
| P3 | **Keep `/api/resource/<DocType>`, served by the same per-doctype ViewSets** through the one explicit doctype map. Child tables and withheld doctypes stay absent. | **Changed from the earlier chat recommendation to drop it.** The frontend never calls it, but the `.http` suite does, in about 155 request lines, much of it setting up data for other blocks. Keeping it costs one small view pair once the ViewSets exist; dropping it means rewriting a fifth of the suite. Revisit when the REST move starts. |
| P4 | **The generic layer is built from DRF's own extension points** (section 5). | Every model "inherits" the API through class inheritance, which is what Django developers expect, instead of through a registry. |
| P5 | **Thirteen apps** (section 4). | Split by domain, and on the lines agents can work in parallel without editing the same file. |
| P6 | **Precedence when sources disagree:** the old backend's behaviour is the contract; the Frappe source (CRM app on `main`, framework on `version-15`) settles anything the old backend leaves unclear; a deliberate difference is written in `PARITY_EXCEPTIONS.md` first. | The old backend already made 39 recorded decisions about upstream's bugs (`docs/UPSTREAM_BUGS_PHASE_*.md`). Re-deciding them from the Frappe source would undo that work. |
| P7 | **A fresh pytest suite.** The old tests are read to learn what behaviour matters and how it was pinned, then written again against the new code. | About 21,800 lines of old tests reach into `frappe_core` internals that will not exist. |
| P8 | **Parity is proven three ways** (section 6): pytest per app, the `.http` suite replayed against `backend_v2`, and a response-body diff between the two backends. | The `.http` runner checks status codes and a few chosen body values only. On its own it would pass a response with a missing key. |
| P9 | **No ambient current user.** The user is passed explicitly: `request.user` in views, an argument to services and to the filter parser. | The old backend binds the user into a context variable (`backend/frappe_core/session.py`) so deep code can find it. That is Frappe's `frappe.session.user`; Django code takes the user as an argument. |
| P10 | **Current supported versions, pinned exactly in FOUNDATION**: Django 5.2 LTS rather than the old backend's 5.1, and the DRF, SimpleJWT, Celery and Channels releases that support it. | 5.1 is out of support. The contract does not depend on the minor version, and the body diff will say if a default changed. |
| P11 | **Both backends run at once without sharing state** (section 7). | Parity checking needs both up, and two Celery workers on one Redis database steal each other's jobs. |

### Open — to discuss before the unit that needs it

| # | Question | Needed by |
|---|---|---|
| O1 | **The long-term error format.** DRF-native errors plus a frontend update, or keep Frappe's shape permanently. | After parity; not blocking |
| O2 | **Where `backend_v2`'s baseline data comes from.** The suite expects `Administrator`, the demo sales users, statuses, sources and settings rows to exist (credentials in `docs/http/.env`). Options: a `seed_dev_data` management command written from what the `.http` files assume; or reference rows exported from the old backend through its own API and loaded into the new one. | FOUNDATION |
| O3 | **The old backend's eight "awaiting review" doctypes**: Contact, CRM Organization, CRM Product, CRM Service Level Agreement, CRM Call Log, CRM Telephony Agent, Email Template, Tag. Each is open to every authenticated user today, with a question recorded against it in `PORT_MAP.md`. Parity says copy that access; this rebuild is a natural moment to decide them. Proposal: copy for parity, and list each in `PARITY_EXCEPTIONS.md` as a decision still owed. | CONTACTS, SALES, ACTIVITIES, SLA, TELEPHONY |
| O4 | **How the frontend gets pointed at `backend_v2`** for the final check. The Vite dev proxy targets port 8000; changing that is a frontend config change, so S4 applies. | The final gate |

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
├── CLAUDE.md  AGENTS.md
├── docs/                   this plan, the contract, the map, as-built, exceptions, runs/
└── specs/                  one spec per unit, and the index
```

Inside an app, the usual Django files and nothing unusual: `models.py` (or a `models/`
package), `serializers.py`, `viewsets.py` (one ViewSet per doctype), `views.py` (method
endpoints), `urls.py`, `permissions.py`, `services.py` (business logic that is not one
model's), `tasks.py`, `signals.py`, `admin.py`, `migrations/`, `tests/`.

| App | Owns | Unit |
|---|---|---|
| `core` | The shared API layer: base document model and naming, exceptions and the error body, renderers, parameter parsing, the method-endpoint base view, the filter and ordering backends, pagination, field access, the base document ViewSet. `Version` (the change history). No product logic | FOUNDATION |
| `accounts` | `User` and roles, login/logout/refresh, lockout and rate limits, password reset, invitations, user administration, the sales hierarchy | FOUNDATION (User, auth), then ACCOUNTS |
| `crm_settings` | FCRM Settings and its dropdown items, Email Account, the Desk plumbing calls (`get_apps`, `boot_config`, translations, site info), demo data, exchange rates | SETTINGS |
| `metadata` | Saved views, field layouts, form scripts, global settings, per-user list settings, field metadata, and the `get_data` list/kanban engine | METADATA |
| `contacts` | Contact and its email/phone rows, Dynamic Link, Organization, Industry | CONTACTS |
| `sales` | Lead, Deal, their statuses, sources, lost reasons, territories, products, deal contacts, status history, lead-to-deal conversion, and the org-hierarchy row rules | SALES |
| `activities` | Comments, emails (Communication, `email.make`, templates), notes, tasks, files, tags, likes, assignments (ToDo) and assignment rules, the activity timeline | ACTIVITIES |
| `documents` | The doctype map, `/api/resource/`, `frappe.client.*`, bulk delete and bulk update, rename, linked-document operations, link search | FOUNDATION (map, resource route, basic `frappe.client.*`), then DOCUMENTS |
| `notifications` | In-app notifications, and the Channels WebSocket that delivers live events | NOTIFICATIONS |
| `dashboard` | Dashboard layouts and the chart endpoints | DASHBOARD |
| `sla` | Service level agreements, service days, priorities, holiday lists, response-time tracking | SLA |
| `telephony` | Call logs, telephony agents and phones, Twilio and Exotel settings and webhooks | TELEPHONY |
| `integrations` | ERPNext, Facebook lead sync, WhatsApp — all behind `ENABLE_*` flags, off by default | INTEGRATIONS |

The row-by-row assignment of every doctype and method path is `PORT_MAP.md`. Unit order
and dependencies are `backend_v2/specs/README.md`.

## 5. The generic layer — how every model "inherits" the API

Frappe gives every doctype CRUD, a query grammar, search, bulk actions and permission
filtering for free. `backend_v2` gets the same by **inheriting from one base ViewSet**,
with each Frappe behaviour placed at the DRF extension point built for it:

| Frappe behaviour | Where it lives in `backend_v2` |
|---|---|
| CRUD for every doctype | `core.viewsets.DocumentViewSet` — a `GenericViewSet` with the list/retrieve/create/update/destroy mixins. Each doctype subclasses it |
| `filters` / `or_filters` grammar, `@me` | `core.filters.FrappeFilterBackend`, a `BaseFilterBackend` |
| `order_by="modified desc"` | `core.filters.FrappeOrderingBackend`, against the ViewSet's `ordering_fields` |
| `limit_start` / `limit_page_length` | `core.pagination.LimitStartPagination` — returns the bare list, as the contract requires |
| `fields=` | `core.fields` — narrows the queryset's columns against the ViewSet's readable fields |
| Link search | `search_fields` on each ViewSet, read by `frappe.desk.search.search_link` |
| Row-level permissions | `get_queryset()` narrows the list; a DRF permission class answers the object check. The rules live in the owning app's `permissions.py` |
| Sensitive / restricted / read-only fields | Declared on the ViewSet and enforced in one place for output, `fields`, filters, ordering and grouping; encryption at rest is a model field type |
| `{"message": …}` / `{"data": …}` | `core.renderers` |
| Frappe's error body | `core.exceptions.exception_handler`, set as DRF's `EXCEPTION_HANDLER` |
| Controller hooks (`validate`, `before_save`, `on_update`) | Serializer `validate()`, model `clean()`/`save()`, or a function in `services.py` — never a signal where a direct call would do |

A doctype then declares only what is its own:

```python
class LeadViewSet(DocumentViewSet):
    doctype = "CRM Lead"
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticated, LeadAccess]
    filterable_fields = [...]      # explicit — a new column is not filterable until listed
    ordering_fields = [...]
    search_fields = ["lead_name", "email", "organization"]
    sensitive_fields = []
```

**Allowlists are explicit.** In the old backend every concrete field was readable,
filterable and sortable unless declared hidden; five security findings came from that
default. Here a new field is invisible until it is listed. For parity the first lists
contain exactly what the old backend exposes today.

**The doctype map is one explicit dictionary**, `documents.doctypes.DOCTYPES`, from a
doctype name to its ViewSet. It is assembled from each app's own `doctypes.py`, imported
by name in one literal list, so two units working in parallel never edit the same file
and nothing is added by an import side effect. The generic routes that receive a doctype
as data —
`/api/resource/<DocType>`, `frappe.client.get_list`, `search_link`, `get_data`, bulk
actions — look the ViewSet up there and reuse its queryset, permissions, filter backend
and serializer. A doctype absent from the map is not reachable by any of them.

**Method endpoints** subclass `core.views.MethodView`, which merges query and body
parameters, enforces the verbs, answers 401 for a missing token unless the view is marked
guest, and wraps the return value in `{"message": ...}`. Each app's `urls.py` lists its
paths through a small helper:

```python
urlpatterns = [
    method_path("crm.api.contact.set_as_primary", views.SetAsPrimary.as_view()),
]
```

## 6. How parity is proven

1. **pytest, per app** — behaviour and permissions, written fresh (P7).
2. **The `.http` suite against `backend_v2`** — the old runner replays any file against
   any host:
   `backend/.venv/Scripts/python.exe backend/scripts/run_http.py docs/http/03_leads.http --host http://127.0.0.1:8001`.
   **Never pass `--mark`**: it writes to `docs/ROUTES.md`, which describes the old
   backend. Which unit turns each file green is tabled in `PORT_MAP.md`.
3. **A response-body diff between the two backends** — `backend_v2/scripts/parity_diff.py`,
   built in FOUNDATION. It sends the same requests to both servers and compares bodies
   after normalising what legitimately differs (tokens, timestamps, generated names).
   This is what catches a missing key, a number that became a string, or a message
   reworded. How both servers get the same baseline data is O2.
4. **The frontend on `backend_v2`** — the final gate, once O4 is settled.

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

- Any change under `frontend/`, and under `backend/`.
- Conventional REST URLs (P2), and DRF-native errors (O1).
- Moving data out of the old database (S2).
- New product features, and behaviour changes not recorded in `PARITY_EXCEPTIONS.md`.
- Deployment, Docker, CI.
- Integrations beyond parity: they stay behind their flags, off by default.

## 9. Done means

1. Every row in `PORT_MAP.md` is `parity` or `exception`.
2. Every `.http` file in `docs/http/` passes against `backend_v2`, apart from blocks named
   in `PARITY_EXCEPTIONS.md`.
3. The body diff is clean apart from recorded exceptions.
4. pytest is green in `backend_v2/`.
5. The frontend's main screens work against `backend_v2` (O4).
6. `backend_v2/docs/AS_BUILT.md` describes what exists, and a portfolio `README.md` explains
   the project to a stranger.
7. Retiring `backend/` and renaming the folder is then the owner's call, as its own step.

## 10. Risks, and what answers each

| Risk | Answer |
|---|---|
| **A protection is silently lost.** The old backend's hardest-won work is its security, and five findings came from one generic route standing open beside a guarded endpoint | `PORT_MAP.md` carries each doctype's protection and declared fields, and a row is not `built` until they are enforced. Allowlists default to nothing. The two guard tests are rebuilt in FOUNDATION: every mapped doctype has a recorded access decision, and every credential-shaped field is declared |
| **Parity measured by status codes alone** | The body diff (section 6, step 3) |
| **Traps in the rendering** — decimals are strings in a document and numbers in a list | Written into `API_CONTRACT.md` section 6, and caught by the body diff |
| **Improving while porting** | Any behaviour change needs a `PARITY_EXCEPTIONS.md` entry first |
| **`get_data` is the keystone** — six screens render from it, and it is where filters, `@me`, saved views and columns meet | METADATA is its own unit, built early, against models written for its tests |
| **Two servers stepping on each other** — shared Redis, shared test database, a stale `runserver` still holding a port on Windows | Section 7, and the operational notes in `backend_v2/CLAUDE.md` |
