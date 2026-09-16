# Backend layout — what each folder is for

The `backend/` tree does not look like a typical Django project, and that is deliberate.
The Vue frontend was kept unchanged, and it hardcodes Frappe's URL scheme
(`/api/resource/<DocType>`, `/api/method/<dotted.path>`) in 225 places. Frappe generates
those URLs from metadata rather than from per-model code, so this port had to do the
same. The result is a **small re-implementation of Frappe's request layer on top of
Django**, and the folders mirror upstream's own split into *framework* and *app*.

```
backend/
├── config/            Django project: settings, URL root, ASGI, Celery
├── frappe_core/       the framework layer — generic routing, registries, filters, naming
├── frappe_platform/   Frappe's built-in doctypes — User, ToDo, Comment, File, ...
├── crm_app/           the CRM itself — models, endpoints, permissions, integrations
├── tests/             the pytest suite (~1,680 tests)
├── tests_support/     throwaway doctypes used only to test the framework layer
├── scripts/           committed utilities: generators and the auth-flow walk
└── scratch/           gitignored working files left by agents; safe to ignore
```

Everything underneath is still plain Django: models, migrations, the ORM, `manage.py`,
pytest-django, SimpleJWT, DRF's `APIView`. Only the routing and dispatch layer is custom.

---

## `config/` — the Django project

The standard project package. Nothing CRM-specific lives here.

| File | What |
|---|---|
| `settings/base.py` | Everything shared: Postgres, Redis cache, JWT lifetimes, Celery, Channels, integration feature flags. Reads the repo-root `.env` |
| `settings/local.py` | `DEBUG=True`. What `manage.py` defaults to |
| `settings/test.py` | What pytest uses: in-memory channel layer and cache, eager Celery, fixed encryption key, `tests_support` added |
| `urls.py` | Two lines: `admin/` and `api/` → `frappe_core.urls` |
| `asgi.py` / `routing.py` | The ASGI entry point and the one WebSocket route, `ws/realtime` |
| `celery.py` | The Celery app and the beat schedule, one entry per upstream `scheduler_events` row |

---

## `frappe_core/` — the framework layer

**Stands in for the Frappe framework.** Generic, and knows nothing about leads or deals.
This is where the two custom decorators live, and it is the layer every request passes
through.

Only three URL patterns exist for the whole application (`frappe_core/urls.py`):

```
/api/resource/<doctype>/<name>   ->  ResourceDetailView   read / update / delete
/api/resource/<doctype>          ->  ResourceListView     list / create
/api/method/<dotted.path>        ->  MethodView           call a named function
```

Each view reads the path segment and looks it up in a registry that decorators fill at
import time:

| Module | What |
|---|---|
| `registry.py` | `@register_doctype("CRM Lead")` — maps a doctype string to its model, serializer, permission hooks and list defaults. Registering a model is what publishes its five CRUD URLs |
| `whitelist.py` | `@whitelist("crm.api.doc.get_data")` — maps a dotted path to a Python function. The port of `@frappe.whitelist()` |
| `views.py` / `method_views.py` | The three generic DRF views above |
| `filters.py` / `query.py` | Frappe's filter grammar (`[["status","=","Open"]]`, `@me`, `like` → case-insensitive) translated to ORM queries, always permission-filtered |
| `models.py` | `BaseDocument` — the standard Frappe columns every document carries (`name`, `owner`, `modified`, `_assign`, ...) — plus `Version`, the field-change audit trail |
| `naming.py` | The six primary-key strategies (`naming_series`, `field:`, `hash`, ...) and `validate_name` |
| `serializers.py` / `children.py` | ModelSerializers built on the fly per model; child tables read and replaced inline |
| `permissions.py` | The hook points the row-level rules plug into; the rules themselves are in `crm_app/permissions/` |
| `field_security.py` / `secrets.py` | `SENSITIVE_FIELDS`, `RESTRICTED_FIELDS`, `READONLY_FIELDS` enforcement, and encryption at rest |
| `field_meta.py` / `metadata.py` | The port of `frappe.get_meta()` — Frappe fieldtypes, labels, options, read from the generated `crm_app/data/doctype_meta.json` |
| `assignment.py` / `doc_caches.py` / `versions.py` | Keep the `_assign`, `_comments` and `_user_tags` caches in step with the tables behind them; write `Version` rows |
| `session.py` / `security.py` / `password_reset.py` / `mail.py` | Current-user binding, login lockout and rate limiting, hashed reset keys, SMTP validation |
| `exceptions.py` / `renderers.py` | The `{"message": ...}` and `{"data": ...}` envelopes, and Frappe-shaped error bodies |
| `api/auth.py` / `api/doc.py` | The endpoints the framework itself owns: `login`, `logout`, `token/refresh`, and `crm.api.doc.get_data` — the list/kanban engine |

---

## `frappe_platform/` — Frappe's built-in doctypes

**Stands in for the parts of Frappe the CRM depends on but that ship no JSON in the CRM
repo.** One `models.py`, twelve doctypes, only the fields the CRM actually uses:

| Doctype | Role |
|---|---|
| `User` | `AUTH_USER_MODEL`. **Primary key is the lowercased email.** Roles are Django groups |
| `Contact`, `Contact Email`, `Contact Phone` | People, with their multi-value email and phone child tables |
| `ToDo` | **Assignment.** A row here is what `_assign` and the permission engine read. Deliberately not routable |
| `Comment`, `Communication` | The timeline: comments, and emails or calls |
| `File` | Attachment metadata. Nothing serves the bytes yet |
| `Tag`, `Email Template`, `Email Account` | Tagging, mail wording, outbound mail configuration |
| `Dynamic Link` | Frappe's generic "this row points at that document" child table |

Migration `0002` seeds the four roles and the two built-in users, `Administrator` and
`Guest`, both with unusable passwords.

---

## `crm_app/` — the CRM

**The port of the upstream `crm` app.** Everything a user would recognise as the product.

| Folder / file | What |
|---|---|
| `models/` | The 39 CRM doctypes, split by cluster: `core_sales.py` (Lead, Deal, Organization, Task, Note — the heavy controllers), `taxonomy.py` (statuses, sources, territories, products), `sla.py`, `telephony.py`, `metadata.py` (view settings, field layouts, dashboards, notifications, invitations, sales hierarchy, settings), plus the phase-7 `whatsapp.py`, `erpnext_integration.py`, `lead_syncing.py` |
| `api/` | The `/api/method/` endpoints, **one module per upstream module** — `crm.api.contact.*` is in `api/contact.py`. `client.py` holds the `frappe.client.*` and `frappe.desk.*` built-ins the frontend calls; `auth_pages.py` holds the phase-8 reset and invitation endpoints |
| `permissions/` | The row-level rules: `org_hierarchy.py` (who may see which leads and deals), `attachments.py` (comments, files and messages defer to their parent document), `platform_docs.py`, `metadata_docs.py`, `notification.py`, and `tree.py` (the nested-set rebuild for the sales hierarchy) |
| `integrations/` | ERPNext, Twilio, Exotel, Facebook lead sync, WhatsApp. All behind `ENABLE_*` flags, all off by default |
| `conversion.py` | Lead → deal conversion |
| `tasks.py` / `async_signals.py` | Celery tasks and the signals that enqueue them |
| `realtime.py` / `consumers.py` | Publishing over Channels, and the WebSocket consumer |
| `mail.py` / `templates/emails/` | The invitation and password-reset emails |
| `data/doctype_meta.json` | **Generated** Frappe field metadata for every doctype; `scripts/generate_field_meta.py` rebuilds it and a test fails if it goes stale |
| `metadata_hooks.py` | Wires saved-view columns into `get_data` |

---

## `tests/` and `tests_support/`

`tests/` is the whole suite, one file per concern rather than per app. Two are worth
knowing by name because they will fail on you by design: `test_route_surface.py` refuses
a new doctype until its permission decision is recorded, and `test_credential_fields.py`
refuses a field that looks like a credential until it is declared.

`tests_support/` is a Django app installed **only under test settings**. It holds
throwaway doctypes (`Widget`, `SeriesDoc`, `HashDoc`, ...) so the framework layer can be
tested without touching a CRM model.

---

## `scripts/` — committed utilities

| Script | What |
|---|---|
| `generate_field_meta.py` | Regenerates `crm_app/data/doctype_meta.json` from the upstream DocType JSON |
| `generate_route_inventory.py` | Regenerates `docs/ROUTES.md`, the route inventory used as the testing checklist |
| `walk_auth_flow.py` | Drives the invite → accept → set password → log in → reset flow over real HTTP against a fresh database. Run it after any auth change |

---

## `scratch/` — gitignored

Working files the agents left behind during the eight phases: review transcripts,
smoke-test scripts, probe files, a vitest install used as a `node_modules` junction.
It is excluded by `.gitignore` and nothing in the application imports from it. Safe to
ignore, and safe to delete, though the smoke scripts (`smoke_*.py`) are a usable record
of how the Celery and Redis stack was exercised by hand.

---

## How a request travels

```
browser ──► vite dev server (8080) ──proxy──► daphne (8000)
                                                │
                                   config/urls.py  →  frappe_core/urls.py (3 patterns)
                                                │
              ┌─────────────────────────────────┼──────────────────────────────┐
              ▼                                 ▼                              ▼
     ResourceListView                  ResourceDetailView                MethodView
     registry.get_entry(doctype)       registry.get_entry(doctype)       whitelist.get_method(path)
              │                                 │                              │
     filters → query (permission-filtered) → serializer                bind params → call function
              │                                 │                              │
              └────────────── {"data": ...} ────┘                    {"message": ...}
```

The permission rules in `crm_app/permissions/` are consulted inside `query` and the
detail view, so an endpoint that reads through `frappe_core.query` cannot bypass them.
One that reaches for `Model.objects` directly can, which is why the tests forbid it.
