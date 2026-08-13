# Phase 3 — API Endpoints

> **PROVISIONAL — revised by phase-0 agent, pending human review.**
> The registry/serializer assumptions below now describe what phase 0 actually built
> (see §1a). The revision is itself unreviewed, so the status stays PROVISIONAL per
> `RUNBOOK.md`. Note this overrides `specs/README.md`, which told the phase-0 agent to
> flip these to Authoritative — the runbook wins.

**Fan out by module.** Needs phase 1. One agent per module group; never two agents in
one file.

Source: `crm/api/*.py` (51 whitelisted) plus ~60 more on doctype controllers.

---

## 1. The rule

Every endpoint keeps its **exact dotted path**, because the frontend hardcodes it:

```
POST /api/method/crm.api.contact.get_linked_deals
```

Response envelope is `{"message": <return value>}` for `/api/method/*`. Signatures below
are verified from source — **parameter names are part of the contract**, the frontend
sends them by name.

---

## 1a. What phase 0 actually built — use this, do not re-invent it

Registering an endpoint is one decorator. The dotted path is **declared, not derived**,
because our modules do not live at `crm.api.*`:

```python
from frappe_core.whitelist import whitelist

@whitelist("crm.api.contact.get_linked_deals")
def get_linked_deals(contact: str):
    ...
```

| Need | Use | Where |
|---|---|---|
| Register an endpoint | `@whitelist(path, allow_guest=False, methods=("GET","POST"))` | `frappe_core/whitelist.py` |
| Make it resolvable | import the module from your app's `AppConfig.ready()` | `frappe_core/apps.py` is the worked example |
| Envelope | automatic — `MethodView` wraps the return value in `{"message": ...}` | `frappe_core/method_views.py` |
| Throw a user-facing error | `throw("text")` / `raise ValidationError("text")` | `frappe_core/exceptions.py` |
| List rows, permission-filtered | `query.fetch_rows(doctype, fields=, filters=, order_by=, ...)` | `frappe_core/query.py` |
| Count, permission-filtered | `query.count_rows(doctype, filters=)` | `frappe_core/query.py` |
| Single-object permission check | `permissions.check_object_permission(doc, ptype, user)` | `frappe_core/permissions.py` |
| Current user (`frappe.session.user`) | `session.get_current_user()` | `frappe_core/session.py` |
| Model / serializer / defaults for a doctype | `registry.get_entry(doctype)` | `frappe_core/registry.py` |
| Who is assigned (via ToDo) | `assignment.get_assigned_users(doctype, name)` | `frappe_core/assignment.py` |

Behaviours you can rely on, all covered by `backend/tests/`:

- **Parameters** are merged from the query string *and* the JSON body, then JSON-decoded
  (`query.parse_json_param`). A param may therefore arrive as `'["a","b"]'` or `["a","b"]`
  — you do not need your own `parse_json` call.
- **Surplus parameters are dropped** (`whitelist.bind_arguments`), matching Frappe, so
  `cmd` and cache-busters do not 500 your endpoint.
- **Auth**: non-`allow_guest` endpoints return 401 `AuthenticationError` when
  unauthenticated. Do not re-check.
- **Permissions**: `fetch_rows` / `count_rows` / `base_queryset` all apply the phase-2
  hook. An endpoint that reads through them cannot bypass row-level security. An
  endpoint that calls `Model.objects` directly **can** — don't.
- **`fields`, `order_by` and `group_by` are validated** against the model's concrete
  fields, so relation traversal (`owner__password`) is rejected with 417.

`get_data` is **already built** at `frappe_core/api/doc.py` and registered as
`crm.api.doc.get_data`. Do not reimplement it; extend it.

---

## 2. Module assignment

### Group A — `doc.py` (12 endpoints) — **assign alone, highest coupling**

```python
sort_options(doctype)
get_filterable_fields(doctype)
get_group_by_fields(doctype)
get_quick_filters(doctype, cached=True)
update_quick_filters(quick_filters, old_filters, doctype)
get_data(doctype, filters, order_by, page_length=20, page_length_count=20,
         column_field, title_field, columns, rows, kanban_columns,
         kanban_fields, view, default_filters)
remove_assignments(doctype, name, assignees, ignore_permissions=False)
get_assigned_users(doctype, name, default_assigned_to=None)
get_fields(doctype, allow_all_fieldtypes=False)
get_linked_docs_of_document(doctype, docname)
remove_linked_doc_reference(items, remove_contact=False, delete=False)
delete_bulk_docs(doctype, items, delete_linked=False)
```

`get_data` is **already built in phase 0** — do not reimplement it. The rest read
doctype metadata from the phase-0 registry; several overlap with phase 4, so
coordinate rather than duplicating.

`get_assigned_users` / `remove_assignments` operate on `ToDo`, not `_assign`
(`PHASE_2_PERMISSIONS.md` §2). Phase 0 already provides
`frappe_core.assignment.get_assigned_users(doctype, name, for_permission=False)` —
use it. Note its two status filters differ deliberately: the display list excludes
`Closed` **and** `Cancelled` (matching `crm/api/doc.py:615`), while the permission view
(`for_permission=True`) excludes only `Cancelled`. The endpoint here wants the default.

`get_filterable_fields` / `get_group_by_fields` already have phase-0 implementations in
`frappe_core/metadata.py`, but they key their allowlists on Django internal types rather
than Frappe fieldtypes — see `PHASE_4_METADATA.md` §3. Coordinate with phase 4 rather
than writing a third version.

### Group B — session, users, auth

```python
# session.py
get_users(include_all=False)
get_user_info(users)
get_organizations()
# user.py
change_password(old_password, new_password)
add_existing_users(users, role="Sales User")
update_user_role(user, new_role)
remove_crm_roles_from_user(user)
# auth.py
oauth_providers()
# __init__.py
get_translations()
get_user_signature()
invite_by_email(emails, role)
delete_attachment(doctype, docname, file_url)
get_file_uploader_defaults(doctype)
```

`change_password` must go through Django's password validators. `update_user_role` /
`remove_crm_roles_from_user` mutate Groups — permission-sensitive, guard them.

### Group C — contacts, comments, activities

```python
# contact.py
get_linked_deals(contact)
create_new(contact, field, value)
set_as_primary(contact, field, value)
search_emails(txt)
# comment.py
add_comment(reference_doctype, reference_name, content, attachments=None)
# activities.py
get_activities(name)
```

`get_activities` merges `Communication`, `Comment`, `ToDo` and status-change history
into one ordered timeline — the most involved item in this group. Read the source
carefully.

### Group D — views, dashboard, notifications, onboarding

```python
# views.py
get_views(doctype)
# dashboard.py
reset_to_default()
get_dashboard(from_date=None, to_date=None, user=None)
get_chart(...)
# notifications.py
get_notifications()
mark_as_read(doc=None)
# onboarding.py
get_first_lead()
get_first_deal()
# settings.py
create_email_account(data)
# exchange_rate.py
get_exchange_rate(from_currency, to_currency, date=None)
# assignment_rule.py
get_assignment_rules_list()
duplicate_assignment_rule(docname, new_name)
```

`get_views` is read by phase-0 `get_data` — align with phase 4.
`get_exchange_rate` calls an external FX service; stub behind a feature flag.

### Group E — deferred

`whatsapp.py` (6) → phase 7. `live_demo.py` (1) → skip unless you want the demo mode.
`todo.py` has no whitelisted endpoints, only `doc_events` hooks — those belong in
phase 1 lifecycle work.

---

## 3. Controller endpoints

~60 more `@frappe.whitelist` methods live on doctype controllers. Port them **with
their doctype in phase 1**, not here, so business logic stays with its model.
Concentrations: `crm_view_settings` (8), `crm_deal` (4), `crm_fields_layout` (3),
`crm_call_log` (2), `fcrm_settings` (2).

---

## 4. Acceptance criteria

- [ ] Every dotted path resolves at its original URL
- [ ] Parameter names match source exactly, including defaults
- [ ] Responses wrapped in `{"message": ...}`
- [ ] JSON-string params (`items`, `columns`, `filters`) accept both string and native forms — upstream calls `frappe.parse_json` liberally
- [ ] Permission checks applied; no endpoint bypasses phase 2
- [ ] `frappe.throw` messages preserved verbatim
- [ ] Bulk operations (`delete_bulk_docs`) are transactional and permission-checked per item
- [ ] No endpoint reaches `Model.objects` directly for a list read — everything goes
      through `frappe_core.query`, which is what applies the phase-2 hook
- [ ] Endpoints that take a document name check `permissions.check_object_permission`
      before returning or mutating it
