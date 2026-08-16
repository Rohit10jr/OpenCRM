# Phase 3 — API Endpoints

> **BUILT** — phase 3 landed on `phase-3-endpoints`, 944 tests passing, reviewed.
> See `PROGRESS_PHASE_3.md` for what was built, what diverged and what is still open,
> and `specs/AS_BUILT.md` for the helpers it added.
>
> Two things this spec did not anticipate, both delivered:
> the `frappe.client.*` / `frappe.desk.*` built-ins the frontend needs
> (`PORT_PLAN.md` §3 lists them; §2 below does not), and the fact that **C4's totals are
> a client-side form script upstream**, not server logic.
>
> Known gaps, named rather than hidden: six dashboard charts, and the `Version`-derived
> field-change entries in `get_activities`. Both in `PROGRESS_PHASE_3.md`.

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

## 1a. What already exists — use it, do not rebuild it

`specs/AS_BUILT.md` is the full inventory. The parts you will reach for constantly:

| Need | Call |
|---|---|
| Register an endpoint | `@whitelist("crm.api.x.y")` from `frappe_core.whitelist` |
| List rows, permission-filtered | `query.fetch_rows(doctype, fields=, filters=, order_by=, ...)` |
| Count, permission-filtered | `query.count_rows(doctype, filters=)` |
| Object permission check | `permissions.check_object_permission(doc, ptype, user)` |
| Current user | `session.get_current_user()` |
| Model / serializer / defaults | `registry.get_entry(doctype)` |
| Who is assigned | `assignment.get_assigned_users(doctype, name)` |
| **Assign someone** | `assignment.assign_to_user(doctype, name, user)` |
| **Tag / untag** | `doc_caches.add_tag(doc, tag)` / `remove_tag` / `get_tags` |
| **Convert a lead** | `crm_app.conversion.convert_to_deal(lead, ...)` |
| Child tables | `children.read_children` / `replace_children` |
| Field metadata | `metadata.get_filterable_fields` / `get_group_by_fields` |

**Already registered — do not rebuild:** `login`, `logout`, `token/refresh`,
`frappe.auth.get_logged_user`, `crm.api.doc.get_data`.

Behaviours you can rely on, all covered by `backend/tests/`:

- **Parameters** merge query string + JSON body and are JSON-decoded, so a param may
  arrive as `'["a","b"]'` or `["a","b"]`. No `parse_json` needed in your handler.
- **Surplus parameters are dropped**, matching Frappe, so `cmd` and cache-busters do not
  500 an endpoint.
- **Auth**: non-`allow_guest` endpoints return 401 when unauthenticated. Do not re-check.
- **Permissions**: `fetch_rows` / `count_rows` / `base_queryset` apply the phase-2 hook.
  Reading through them cannot bypass row-level security. **`Model.objects` directly
  can — don't.**
- **`fields`, `order_by`, `group_by` are validated**; relation traversal is rejected 417.
- **Envelope** is automatic: `{"message": ...}`.

### Three invariants that will cost you a debugging session

**`lead_owner` / `deal_owner` is the access column, not `owner`.** Any endpoint that
creates a lead or deal **must set it**, or the record is invisible to the user who just
created it. This is upstream's rule, and it has already caught two tests.

**Unknown field and row names raise**, they are not silently dropped. If an endpoint
passes a field the model lacks, you get a 417 rather than a quietly missing column.

**Query `ToDo` for anything access-related, never `_assign`.** The two have deliberately
different status filters — display excludes `Closed` *and* `Cancelled`, permissions
exclude only `Cancelled` — so a Closed ToDo still grants access while not appearing in
the cache.

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

## 2a. Carried-over work this phase owns

Three items from the phase 0-2 review were assigned here (`PROGRESS.md`, Review
Resolution):

- **C4** — `crm_products` totals (`amount`, `net_amount`, `total`, `net_total`) are
  columns with nothing computing them. Upstream derives them from qty x rate less
  discount; find the source before implementing.
- **C5** — `CRM Call Log.links` is a `Table` of Frappe's `Dynamic Link`, which is not
  ported. Upstream uses it to attach notes/tasks/leads/deals to a call. Porting
  `Dynamic Link` also unblocks `Contact.links`, which `Contact.autoname` reads
  (`frappe_platform.Contact.name_links_suffix` is the waiting seam).
- **C9** — `has_permission` issues one query per object. `delete_bulk_docs` is specced to
  check per item, so that path needs batching rather than N round-trips.

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
