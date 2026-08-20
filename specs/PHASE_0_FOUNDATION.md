# Phase 0 — Foundation

**Single agent. Blocks every other phase. Do not parallelise.**

Phase 0 builds no CRM features. It builds the contract that all CRM features plug
into. Everything here is read by 5+ concurrent agents later, so ambiguity is the
enemy — where a choice exists, make it, write it down, and make it hard to do
differently.

Source: `D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm`

---

## 1. Deliverables

1. Django project skeleton + settings (Postgres, Redis, DRF, SimpleJWT)
2. `BaseDocument` abstract model — PK strategies + Frappe standard fields
3. DocType registry
4. Frappe filter-grammar translator
5. Generic `/api/resource/` viewset (CRUD)
6. `/api/method/crm.api.doc.get_data` — the list/kanban engine
7. JWT auth endpoints + the `frappe-ui` request-layer patch
8. Response/error envelope middleware
9. Named extension points for phases 2 and 4
10. Revised phase 3–6 specs (see `README.md` — you own them)

---

## 2. Primary keys — six strategies, not one

Frappe's `autoname` decides the PK per doctype. **Verified mapping from source:**

| Strategy | Django implementation | DocTypes |
|---|---|---|
| `naming_series:` | Series generator, `CRM-LEAD-.YYYY.-` → `CRM-LEAD-2026-00001` | `crm_lead`, `crm_deal` |
| `field:<name>` | PK = that field's value **verbatim** — `.strip()` only, **never slugified**; uniqueness enforced by the PK constraint | 14 doctypes: `crm_organization` (`organization_name`), `crm_territory`, `crm_industry`, `crm_lead_status`, `crm_deal_status`, `crm_lead_source`, `crm_lost_reason`, `crm_product` (`product_code`), `crm_call_log` (`id`), `crm_dashboard` (`title`), `crm_holiday_list`, `crm_telephony_agent` (`user`), `crm_communication_status`, `crm_service_level_agreement` (`sla_name`) |
| `autoincrement` | `BigAutoField` — **genuinely integer PKs** | `crm_task`, `crm_view_settings`, `crm_product_sync_issue` |
| `hash` | Random 10-char hex string | `crm_global_settings`, `crm_sales_hierarchy` |
| `format:{dt}-{type}` | Template interpolation from field values | `crm_fields_layout` |
| `prompt` | Client supplies `name` on create; reject if absent | `crm_form_script` |

> Correction to `PORT_PLAN.md` §3: "always string PKs" is *near*-universal, not
> universal. Three doctypes really are autoincrement. Implement `NameStrategy` as a
> pluggable class on the model Meta so phase-1 agents declare a strategy rather than
> hand-rolling one.

### Names are verbatim, and that has consequences

Verified against Frappe `version-15` — the branch CRM `main` targets
(`.github/workflows/builds.yml:43`), cloned at
`D:\02_Personal\01_OpenSource\02_FrameWorks\frappe`:

- **`_field_autoname` is `(cstr(doc.get(fieldname)) or "").strip()`** and nothing else
  (`frappe/model/naming.py:553-559`). No slugification anywhere in Frappe or the CRM app.
- **`validate_name` forbids only `<` and `>`** (`naming.py:498-501`). Spaces, slashes,
  `#`, `&`, `?` are all legal document names.
- Corroborated in the app: `crm/demo/deals.py:75-96` keys `_org_logos` by the **raw**
  organization name (`"ScaleUp Labs"`) while its *values* are slugified asset paths
  (`scaleup-labs.png`). Upstream slugifies filenames, never record names.

Two things follow, both implemented:

1. **A name may contain `/`.** "R/GA" is a real company. Upstream routes these with a
   path converter — `Rule("/resource/<doctype>/<path:name>/")`
   (`frappe/api/v1.py:148-151`). Our URL pattern must do the same; `[^/]+` makes such
   records permanently unreachable, and percent-encoding does not help because WSGI
   decodes `%2F` before Django resolves.
2. **`validate_name` must run on insert for every name** — generated, prompt-supplied,
   or caller-forced — reproducing upstream's three rules and their message text.

The naming series counter must be atomic under concurrency — use a dedicated
`NamingSeries` table with `select_for_update()`, not `max(id)+1`.

### A seventh strategy: controller `autoname()`

The six above are the JSON `autoname` values. Frappe also lets a **controller define an
`autoname()` method**, which takes precedence and can implement anything. No CRM doctype
uses this, but three *platform* doctypes do — `User`, `Contact` and `File`
(`PHASE_1_MODELS.md` §1). `Contact`'s also calls `append_number_if_name_exists`
(`frappe/model/naming.py:506-530`), which is ported in `frappe_core/naming.py` and
returns the value untouched when free, else `-1`, `-2`, … taking **last + 1**.

---

## 3. `BaseDocument` — the standard fields

Every Frappe document carries these. The frontend reads them; they are not optional.

| Field | Type | Notes |
|---|---|---|
| `name` | PK, see §2 | |
| `owner` | FK User | creator, set once |
| `modified_by` | FK User | |
| `creation` | datetime | |
| `modified` | datetime | frontend sorts on this by default |
| `idx` | int | ordering within child tables |
| `docstatus` | small int | 0 draft / 1 submitted / 2 cancelled. CRM is 0 everywhere — implement the column, ignore the workflow |

### The four underscore fields — read this carefully

These are **denormalised caches** in Frappe, and the frontend reads them directly:

| Field | Real source of truth | Implementation |
|---|---|---|
| `_assign` | **`ToDo` records** — not a real column | JSON list of user emails, kept in sync by signal on ToDo write |
| `_liked_by` | itself | JSON list of user emails |
| `_comments` | `Comment` records | JSON cache |
| `_user_tags` | `Tag` links | comma-joined string |

`_assign` is the one that catches people out. **Assignment in Frappe is a `ToDo`
record**, and `_assign` is a cached projection of it. The permission engine (phase 2)
queries `ToDo` directly, not `_assign`. Implement both, keep them consistent via
signals, and never let a phase-1 agent treat `_assign` as the source of truth.

---

## 4. DocType registry

One place that maps a Frappe DocType name to a Django model, so a phase-1 agent adding
a model makes it routable in three lines and nothing else.

```python
@register_doctype("CRM Lead")
class CRMLead(BaseDocument):
    class Meta:
        name_strategy = NamingSeries("CRM-LEAD-.YYYY.-")
```

The registry must expose, for a given doctype string: the model, its serializer, its
default list columns/rows, its permission hooks, and its filterable fields. Phases 2,
3 and 4 all read from it. Design it as the single lookup surface — if a later phase
needs doctype metadata and can't get it here, phase 0 was under-built.

Naming rule, applied uniformly: `CRM Lead` → `crm_lead` (module/dir) → `CRMLead`
(class). Acronyms stay uppercase: `CRM`, `SLA`, `FCRM`.

---

## 5. Filter grammar translator

The single most reused piece of code in the project.

```
"="        → exact        "like"      → icontains   ← NOT contains, see below
"!="       → ~exact       "not like"  → ~icontains
">"        → gt           "in"        → in
"<"        → lt           "not in"    → ~in
">="       → gte          "between"   → range
"<="       → lte          "is"        → set/not set → ~isnull / isnull
"descendants of"  → tree query (phase 2 territory/hierarchy)
```

**Postgres caveat (settled decision, `PORT_PLAN.md` §10):** upstream runs MariaDB where
`like` is case-insensitive. On Postgres it is not. Map `like` → `icontains` or every
text search silently diverges from upstream. This is the single easiest way to ship a
subtly wrong port.

### The `@me` token — verified in `api/doc.py:get_data`

Filter values are rewritten before querying:

- value `"@me"` → current user's email
- value `"%@me%"` → `"%" + user email + "%"` (substring match)
- applies inside lists too, element by element

Implement this in the translator, not in individual views.

### Input shapes

Filters arrive as **both** a dict and a list-of-tuples depending on the call site:

```
{"status": "Open"}                       → equals
{"status": ["in", ["Open", "Lost"]]}     → operator form
[["CRM Lead", "status", "=", "Open"]]    → full tuple form
```

Accept all three. Upstream normalises via `frappe.utils.make_filter_tuple`.

---

## 6. Endpoints

### 6a. Generic resource CRUD

```
GET    /api/resource/<DocType>            list   → {"data": [...]}
GET    /api/resource/<DocType>/<name>     read   → {"data": {...}}
POST   /api/resource/<DocType>            create → {"data": {...}}
PUT    /api/resource/<DocType>/<name>     update → {"data": {...}}
DELETE /api/resource/<DocType>/<name>     delete → {"data": null}
```

Query params: `filters`, `or_filters`, `fields`, `order_by`, `limit_start`,
`limit_page_length`, `group_by`, `parent`. All JSON-encoded strings, not native arrays.

`fields=["*"]` means all. `fields` selection must translate to `.only()` / `.values()`
— the frontend relies on partial payloads for list performance.

### 6b. `get_data` — the real list engine

**This is the keystone, more than `/api/resource/`.** Verified signature from
`api/doc.py`:

```
POST /api/method/crm.api.doc.get_data
  doctype, filters, order_by, page_length=20, page_length_count=20,
  column_field, title_field, columns, rows,
  kanban_columns, kanban_fields, view, default_filters
```

It does six things, in this order:

1. Resolves `@me` tokens in filters
2. Merges `default_filters`
3. Loads the user's saved `CRM View Settings` for this doctype+view_type, else falls
   back to the controller's `default_list_data()`
4. Ensures every column key is present in `rows`, drops hidden fields
5. Queries with permission filtering applied
6. Returns **data + columns + rows + view metadata together** in one payload

Branches on `view_type`: `list`, `kanban`, `group_by`. Kanban resolves its columns from
a Link field's target table or a Select field's options.

Phase 0 must implement the list branch fully and the kanban branch at least
structurally. The View Settings merge (step 3) may stub to controller defaults until
phase 4 lands — **but the response shape must be final now.**

### 6c. Error envelope

`frappe.throw` (123 uses) surfaces as a user-visible message. DRF `ValidationError`
must serialise to the shape the frontend already parses — check
`frontend/src/` error handling and match it exactly. Preserve message text verbatim;
it is user-facing copy.

---

## 7. Auth — JWT

Settled (`PORT_PLAN.md` §10). `djangorestframework-simplejwt`.

```
POST /api/method/login          → {"message": {"access": ..., "refresh": ...}}
POST /api/method/logout
POST /api/method/token/refresh
GET  /api/method/frappe.auth.get_logged_user → {"message": "user@example.com"}
```

**User PK is the email address**, matching Frappe. Do not use integer user IDs — 53
source references and every `_assign`/`owner` field assume email.

Roles to seed: `Administrator`, `System Manager`, `Sales Manager`, `Sales User`.
These map to Django Groups and drive phase 2.

### Frontend patch — contained, one file

Patch `frappe-ui`'s request layer to attach `Authorization: Bearer <token>` and handle
401→refresh. **Do not touch the 225 `createResource` call sites.** Drop CSRF token
handling once cookies are gone. Document the patch in the repo so a `frappe-ui` upgrade
doesn't silently revert it.

---

## 8. Extension points — stub these, named, now

Phases 2 and 4 must plug in without editing phase-0 code.

```python
# Phase 2 — row-level permissions
def get_permission_query_conditions(doctype, user) -> Q | None
def has_permission(doc, ptype, user) -> bool | None
```

Registered per doctype in the registry, mirroring Frappe's `hooks.py`. Upstream
registers these for **CRM Lead, CRM Deal, CRM Notification** only. Phase 0 wires the
call sites; phase 2 fills in the logic. A `None` return means "no restriction".

```python
# Phase 4 — metadata
def get_list_columns(doctype, user, view_type) -> list
def get_filterable_fields(doctype) -> list
```

---

## 9. Out of scope for phase 0

Do not build: any CRM model, any business logic, view-settings persistence, the
permission logic itself, Celery tasks, WebSockets. If you find yourself writing
`CRMLead`, stop — that is phase 1.

---

## 10. Acceptance criteria

- [ ] `GET /api/resource/CRM Lead?filters=[["status","=","Open"]]&fields=["name"]` returns a correct `{"data": [...]}`
- [ ] All six naming strategies produce correct PKs, verified by unit test
- [ ] Naming series is atomic under 50 concurrent creates
- [ ] `@me` resolves in dict, operator, and tuple filter forms
- [ ] `like` is case-insensitive (Postgres `ilike`) — explicit test
- [ ] `get_data` returns data + columns + rows for the list branch
- [ ] JWT login/refresh works; patched `frappe-ui` reaches an authenticated endpoint
- [ ] Permission and metadata hooks are called (returning `None`) and provably wired
- [ ] A throwaway model registers and becomes fully routable in ≤3 lines
- [ ] Phase 3–6 specs revised to match what was built, status flipped to Authoritative

**The last one is not optional.** Phases 3–6 were written before you built this.
Correcting them is part of phase 0.
