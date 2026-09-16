# Frappe CRM → Django Port Plan

Source analysis and architecture brief for agents working on this port.

> **Start at [`specs/AS_BUILT.md`](../specs/AS_BUILT.md)** — what phases 0-2 actually built.
> Then this document for context and settled decisions, then your phase spec.

## Where this stands

| | |
|---|---|
| **Shipped** | Phases 0, 1, 2 — foundation, 46 models, row-level permissions |
| **Tests** | 813 passing, 31 skipped, 0 failing |
| **Branch** | `phase-0-foundation` |
| **Next** | Phase 3 (~50 endpoints), then 4, 5, 6 |
| **Deferred** | Phase 7 (integrations, flagged off) |
| **Parked** | Phase 8 (auth UI and the Desk — ports nothing, needs a scope decision) |

Phases 0-2 were reviewed afterwards and every concern resolved, reproduced with reasoning,
or assigned to a later phase — see the **Review Resolution** section at the end of
`docs/internal/PROGRESS.md`. Nine upstream bugs found along the way are catalogued in `UPSTREAM_BUGS.md`
(local, gitignored).

Both source repositories are now readable, which they were not during phases 0-2:

```
CRM app    D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm    (main)
framework  D:\02_Personal\01_OpenSource\02_FrameWorks\frappe           (version-15)
```

| | |
|---|---|
| **Source** | `D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm` (frappe/crm, app package) |
| **Target** | `D:\02_Personal\01_OpenSource\03_Applications\CRM\frappe_django_crm\backend` |
| **Stack decision** | Django + Django REST Framework + Celery + PostgreSQL |
| **Analysis date** | 2026-08-13 |

---

## 1. Why Django and not FastAPI

Decided, not open. Reasons specific to this codebase:

1. **Frappe is metadata-driven and so is DRF.** Frappe generates CRUD, filtering and
   permissions from DocType JSON. In DRF, one generic `ModelViewSet` plus a doctype
   registry serves all 29 resources. In FastAPI you hand-write routes and schemas per
   model — 29× the boilerplate, or you rebuild Frappe's metadata layer yourself.
2. **A CRM needs exactly what Django ships.** Migrations, auth/sessions, role
   permissions. Frappe's role + owner/assigned-to model maps near 1:1 onto Django
   groups/permissions + `django-guardian`.
3. **Async buys nothing here.** This is CRUD- and permission-heavy, not
   streaming-heavy. Background work (email, SLA timers, notifications) goes to Celery
   either way.
4. **Convergence across parallel agents.** Django's conventions are prescriptive, so
   agents working in parallel produce the same shape. FastAPI's freedom produces N
   different auth layers that then need reconciling.

---

## 2. Source inventory — 21,411 LOC across 226 Python files

| Area | LOC | Disposition |
|---|---|---|
| `fcrm/` | 9,111 | **Port** — 39 doctypes + controllers, the domain |
| `api/` | 4,351 | **Port** — 51 whitelisted endpoints, 18 modules |
| `integrations/` | 1,788 | **Defer** — ERPNext, Exotel, Twilio |
| `tests/` | 1,724 | **Rewrite** — do not port, write pytest-django fresh |
| `demo/` | 1,393 | **Regenerate** — seed data, use factories |
| `install.py` + `hooks.py` | 925 | **Replace** — becomes migrations + AppConfig + signals |
| `patches/` | 594 | **Skip entirely** — upstream migration history, irrelevant |
| `lead_syncing/` | 551 | **Defer** — Facebook lead forms |
| `permissions/org_hierarchy.py` | 368 | **Port** — row-level access, critical |
| `utils/`, `overrides/`, `www/` | 476 | **Port selectively** |

**Real port surface ≈ 14k LOC. Deferring integrations and lead sync → ≈ 11k LOC.**

Framework coupling to unwind: 557 `frappe.db`, 258 `frappe.get_doc`, 128 `frappe.utils`,
123 `frappe.throw`, 111 `@frappe.whitelist`, 76 `frappe.session`, 73 `frappe.qb`,
26 `frappe.get_meta`, 23 `frappe.get_roles`, 18 `frappe.has_permission`.

### Where the business logic actually lives

Most doctype controllers are thin. Real logic is concentrated in seven files:

```
690 LOC  erpnext_crm_settings   (deferred)
545 LOC  crm_lead
472 LOC  crm_deal
328 LOC  crm_view_settings
295 LOC  crm_call_log
259 LOC  crm_fields_layout
247 LOC  fcrm_settings
```

Port these with care and read the source line by line. The rest are near-mechanical
JSON→model conversions.

---

## 3. The frontend contract — READ BEFORE WRITING ANY ENDPOINT

The existing Vue frontend (52,449 LOC) makes **225** `createResource` /
`createListResource` / `createDocumentResource` calls via `frappe-ui`. If we keep that
frontend, **the Django backend must emulate Frappe's wire protocol.** This is a hard
external contract, not a design choice.

```
GET  /api/resource/<DocType>?filters=[["status","=","Open"]]
                            &fields=["name","lead_name"]
                            &order_by=modified desc
                            &limit_page_length=20
                            &limit_start=0
                            &or_filters=[...]
GET  /api/resource/<DocType>/<name>
POST /api/resource/<DocType>
PUT  /api/resource/<DocType>/<name>
DEL  /api/resource/<DocType>/<name>
POST /api/method/<dotted.python.path>
```

Response envelopes:

- `/api/resource/*` → `{"data": ...}`
- `/api/method/*` → `{"message": ...}`

Frontend also calls these Frappe built-ins directly — they must exist:
`frappe.client.delete` (15×), `set_value` (13×), `insert` (9×), `rename_doc` (5×),
`get` (3×), `get_single_value` (2×), `get_list` (1×), `get_doc_permissions` (1×).

### `get_data` is the real list engine

`/api/resource/` handles CRUD, but the list and kanban screens actually call:

```
POST /api/method/crm.api.doc.get_data
```

It resolves `@me` filter tokens, merges the user's saved View Settings, and returns
**data + columns + rows together**. Six of the CRM's screens depend on it. Spec:
`specs/PHASE_0_FOUNDATION.md` §6b.

### Primary keys — six strategies

Record names are **mostly string PKs** (Frappe's `name` field), generated by six
different `autoname` strategies — naming series, field value, hash, format template,
prompt, and autoincrement. Three doctypes (`crm_task`, `crm_view_settings`,
`crm_product_sync_issue`) genuinely are integer autoincrement. Full verified mapping in
`specs/PHASE_0_FOUNDATION.md` §2. The frontend routes on these values, so do not
substitute your own scheme.

### The one sanctioned deviation: auth

Everything above is fixed **except authentication**. We use JWT, not Frappe session
cookies (§10). That means one contained patch to `frappe-ui`'s request layer to send
`Authorization: Bearer <token>`. Nothing else in the protocol changes, and the 225
`createResource` call sites are untouched. If you find yourself wanting to deviate
anywhere else, you are wrong — read the Frappe source and match it.

---

## 4. Three traps that will cost weeks if missed

### Trap 1 — The generic resource endpoint is the keystone
Build **one** DRF generic viewset + Frappe filter-grammar translator + doctype
registry, and build it FIRST, with a single agent. Every model plugs into it. Getting
it wrong means reworking all 29 models. Do not parallelize this.

Note that the keystone is **`get_data`**, not `/api/resource/` — that is where the
filter grammar, `@me` tokens, view-settings merge and column resolution all converge.
Build `/api/resource/` first because it is simpler, but design for `get_data`.

### Trap 2 — `crm_view_settings` + `crm_fields_layout` are runtime metadata, not code
587 LOC that let users define their own list views, columns, filters and form layouts
**at runtime**. This means the Django app needs `DocTypeMeta` / `FieldMeta` tables
alongside the concrete models. Teams that hard-code all models hit a wall two-thirds
through and restructure. Design the metadata layer in phase 0 even if it's built later.

### Trap 3 — `org_hierarchy.py` is row-level permissions
368 LOC. Access flows down a sales hierarchy and territory tree. Django's built-in
permissions are model-level only. Needs `django-guardian` or a custom queryset-filtering
layer wired into the phase-0 viewset. Retrofitting row-level security is painful.

---

## 5. DocType map

### First: the models that aren't DocTypes

The 39 CRM doctypes are **not the whole data model.** The app leans on Frappe
*platform* doctypes that ship no JSON in this repo and are easy to miss entirely:

`User` (53 refs, **PK is email**), `Contact` (24), `ToDo` (**backs `_assign`** — Frappe
assignment is a ToDo record), `Communication`, `Comment`, `Email Template`, `File`,
`Tag`, `Email Account`.

These must be built **before any CRM doctype** — everything foreign-keys into them.
Port only the fields the CRM uses; do not reimplement Frappe's platform.

### The 39 CRM doctypes — 29 main (4 singletons) + 10 child

Clusters are the suggested agent work-split boundaries. `(C)` = child table (Django
FK/inline, no standalone endpoint), `(S)` = singleton settings (one row, or a settings
model).

| Cluster | DocTypes |
|---|---|
| **Core sales** | `crm_lead`, `crm_deal`, `crm_organization`, `crm_task`, `fcrm_note`, `crm_contacts` (C) |
| **Taxonomy / lookups** | `crm_lead_status`, `crm_deal_status`, `crm_lead_source`, `crm_industry`, `crm_lost_reason`, `crm_territory`, `crm_communication_status`, `crm_product`, `crm_products` (C) |
| **SLA engine** | `crm_service_level_agreement`, `crm_service_day` (C), `crm_service_level_priority` (C), `crm_holiday_list`, `crm_holiday` (C), `crm_rolling_response_time` (C), `crm_status_change_log` (C) |
| **Telephony** | `crm_call_log`, `crm_telephony_agent`, `crm_telephony_phone` (C), `crm_twilio_settings` (S), `crm_exotel_settings` (S) |
| **UI metadata** | `crm_view_settings`, `crm_fields_layout`, `crm_form_script`, `crm_dashboard`, `crm_dropdown_item` (C) |
| **Notifications** | `crm_notification`, `crm_invitation` |
| **Org / permissions** | `crm_sales_hierarchy` |
| **Settings** | `fcrm_settings` (S), `crm_global_settings`, `erpnext_crm_settings` (S) |
| **Lead sync — DEFER** | `facebook_lead_form`, `facebook_lead_form_question`, `facebook_page`, `failed_lead_sync_log`, `lead_sync_source`, `crm_product_sync_issue` (C) |

---

## 6. API surface — 51 whitelisted endpoints in `crm/api/`

The remaining `@frappe.whitelist` methods (111 total) live on doctype controllers.

```
doc.py            12     onboarding.py      2
whatsapp.py        6     notifications.py   2
__init__.py        6     assignment_rule.py 2
user.py            4     views.py           1
contact.py         4     settings.py        1
session.py         3     live_demo.py       1
dashboard.py       3     exchange_rate.py   1
                         comment.py         1
                         auth.py            1
                         activities.py      1
                         todo.py            0
```

`doc.py` (12 endpoints) is the generic document API — it overlaps heavily with the
phase-0 generic viewset. Read it before designing phase 0; it defines much of the
contract.

---

## 7. Phase plan

| Phase | Work | Parallel | Blocking |
|---|---|---|---|
| **0** | Django skeleton, generic `/api/resource/` viewset, filter-grammar translator, doctype registry, JWT auth, metadata-layer design | **Single agent** | Blocks everything |
| **1** | 29 main models + 10 child tables from DocType JSON | Fan out by cluster (§5) | Needs 0 |
| **2** | Permission engine: org hierarchy, territory, row-level filtering | **Single agent** | Needs 0, touches 0 |
| **3** | 51 `api/` endpoints + controller methods | Fan out by module (§6) | Needs 1 |
| **4** | Metadata layer: view settings, field layouts, dashboards | Fan out | Needs 0, 1 |
| **5** | Celery: email queue, SLA timers, notifications, assignment rules | Fan out | Needs 1 |
| **6** | Channels realtime: notifications, live refresh | Fan out | Needs 5 |
| **7** | ERPNext / Exotel / Twilio / Facebook integrations | Fan out | **Deferred** — feature-flag off |
| **8** | Auth UI and the rest of the Desk | — | **Parked** — see below |

### Phase 8 is not a port

Frappe ships a **Desk** — auth screens and a generic admin UI — alongside the CRM app.
This port replaces the app and drops the Desk, but the CRM assumes the Desk is present:
`router.js:222` sends logged-out users to `/login`, and accepting an invitation redirects
to a Desk-hosted set-password page. **So there is no way to onboard a second user today.**

That work is real and wanted, but it is new product rather than a port — there is no
upstream to be faithful to — so it is recorded in `specs/PHASE_8_AUTH_AND_DESK.md` and
deliberately parked until phases 0–7 are complete.

**Phases 0 and 2 must be single-agent.** Both define contracts that everything else
depends on; splitting them produces divergent designs that then need reconciling.

For every other phase, **the orchestrating agent decides how many agents to spawn** —
size it to the actual work in the cluster or module list, not to a fixed number. The
§5 and §6 tables give the natural split boundaries. One rule: **no two concurrent
agents may edit the same file.** Split on cluster/module lines, not arbitrarily.

---

## 8. Rules for agents on this port

- **Do not invent API shapes.** The frontend contract in §3 is fixed. If unsure how an
  endpoint should respond, read the Frappe source at the path in §1 and match it.
- **Read the source controller before porting a doctype.** The JSON gives you fields;
  the `.py` gives you validation, hooks (`validate`, `before_save`, `on_update`), and
  business rules. Both matter.
- **Frappe lifecycle hooks → Django signals or model methods.** `validate` →
  `Model.clean()`, `before_save`/`on_update` → `pre_save`/`post_save` signals.
  Keep the mapping consistent across all agents.
- **`frappe.throw` → DRF `ValidationError`.** Preserve the message text; the frontend
  displays it.
- **Do not port `patches/`.** It is upstream migration history.
- **Do not port tests as written.** Write fresh pytest-django tests against the ported
  behaviour.
- **String primary keys.** See §3.
- **Flag, don't guess.** If a Frappe behaviour is unclear, note it in the PR/report
  rather than inventing semantics.

---

## 9. Reference oracle

The source repo ships `docker/` and `.devcontainer/`. Standing up real Frappe CRM in
Docker Desktop gives a **live oracle** to diff behaviour against — request/response
shapes, filter edge cases, permission outcomes. Strongly recommended before phase 0,
since phase 0 is where protocol mistakes are most expensive.

---

## 10. Decisions

### Settled

- [x] **Keep the existing Vue frontend.** Confirmed. This makes §3 a **hard external
      contract** — the Django backend must speak Frappe's wire protocol exactly. Not
      negotiable by any agent. The upside: the frontend is now the acceptance test.
      If a screen renders and behaves, that endpoint is correct.
- [x] **Database: PostgreSQL.** Confirmed. Note that upstream Frappe runs MariaDB, so
      when diffing against the Docker oracle (§9), expect differences in collation,
      case-sensitivity of string comparisons, and `JSON` column behaviour. Frappe
      filter semantics like `like` are case-insensitive on MariaDB but **case-sensitive
      on PostgreSQL** — the filter translator in phase 0 must use `ilike` to match
      upstream behaviour.

- [x] **Auth: JWT.** Confirmed — not Frappe session cookies. This is the one place we
      deliberately break protocol compatibility, and it requires a **frontend change**.
      The change is contained: `frappe-ui` centralises HTTP in a single request layer,
      so patch that one interceptor to attach `Authorization: Bearer <token>` and
      handle refresh. Do **not** touch the 225 `createResource` call sites — they stay
      as they are. Endpoints: `/api/method/login` returns the token pair rather than
      setting `sid`. CSRF token handling can be dropped once cookies are gone.
      Suggested: `djangorestframework-simplejwt`.
- [x] **Realtime: Django Channels.** Confirmed — faithful to upstream rather than
      polling. Frappe pushes over socket.io; Channels uses raw WebSockets, so the
      frontend's socket client needs replacing too. Scope is narrow: notifications and
      live list/document refresh. Needs Redis as channel layer — already required for
      Celery, so no new infrastructure. Not blocking; land it after phase 5.

### Still open

- [ ] Nothing outstanding. Re-open here if a phase-0 finding forces a change.
