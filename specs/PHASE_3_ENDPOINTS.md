# Phase 3 — API Endpoints

> **PROVISIONAL** — written before phase 0 landed. The phase-0 agent must revise the
> registry/serializer assumptions here and flip this to Authoritative.

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
(`PHASE_2_PERMISSIONS.md` §2).

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
