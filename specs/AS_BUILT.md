# As-built reference — read this before writing any code

**Authoritative.** Phases 0–2 are complete and reviewed; this describes what actually
exists, as opposed to what the phase specs predicted. Where a phase spec and this file
disagree, **this file wins** — the specs were written before the code.

The single biggest time-waster in this project is reimplementing something that is
already here. Check this file first.

---

## 1. Both sources are now readable

| | Path | Branch |
|---|---|---|
| **Frappe CRM app** | `D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm` | `main` |
| **Frappe framework** | `D:\02_Personal\01_OpenSource\02_FrameWorks\frappe` | `version-15` |

The framework was **not** available during phases 0–2, and several defects were only
findable in it. That pairing (`main` + `version-15`) is what the CRM's own CI uses
(`.github/workflows/builds.yml:43`) — do not read `develop`, it is v16 pre-release.

**When behaviour seems impossible, suspect a missing framework mechanism.** `fetch_from`
was never ported, and the symptom was "converted deals have a contact but no email" — it
looked like a conversion bug for an hour.

---

## 2. The framework layer — call these, do not rewrite them

### Registering an endpoint

```python
from frappe_core.whitelist import whitelist

@whitelist("crm.api.contact.get_linked_deals")     # path is DECLARED, not derived
def get_linked_deals(contact: str):
    ...
```

Import the module from your app's `AppConfig.ready()` or it never resolves.
`frappe_core/apps.py` is the worked example.

### `frappe_core` API

| Need | Call |
|---|---|
| List rows, permission-filtered | `query.fetch_rows(doctype, fields=, filters=, or_filters=, order_by=, limit_start=, limit_page_length=, user=)` |
| Count, permission-filtered | `query.count_rows(doctype, filters=)` |
| A permission-filtered queryset | `query.base_queryset(doctype, user)` / `build_list_queryset(...)` |
| Validate a field list | `query.resolve_fields(model, fields)` — **raises** on unknown |
| Validate order_by / group_by | `query.resolve_order_by`, `query.resolve_group_by` |
| Parse a JSON-or-native param | `query.parse_json_param(value)` |
| Filters → `Q` | `filters.normalize_filters`, `filters.build_q`, `filters.apply_filters` |
| `@me` resolution | `filters.resolve_me_tokens(value, user)` |
| Object permission check | `permissions.check_object_permission(doc, ptype, user)` |
| Current user | `session.get_current_user()` |
| Model/serializer/defaults | `registry.get_entry(doctype)`, `get_model`, `all_doctypes`, `routable_doctypes` |
| Raise a user-facing error | `exceptions.throw(msg)` or `raise ValidationError(msg)` |
| Who is assigned (via ToDo) | `assignment.get_assigned_users(doctype, name, for_permission=False)` |
| **Assign someone** | `assignment.assign_to_user(doctype, name, user)` |
| Rebuild the `_assign` cache | `assignment.rebuild_assign_cache(doctype, name)` |
| Rebuild the `_comments` cache | `doc_caches.rebuild_comment_cache(doctype, name)` |
| **Tag / untag a document** | `doc_caches.add_tag(doc, tag)`, `remove_tag`, `remove_all_tags`, `get_tags` |
| Child tables | `children.discover_child_tables`, `read_children`, `replace_children` |
| Delete polymorphic children | `children.delete_polymorphic_children(instance)` (wired on `post_delete`) |
| Naming | `naming.validate_name`, `naming.append_number_if_name_exists` |
| Field metadata | `metadata.get_filterable_fields`, `get_group_by_fields`, `get_list_columns` |
| Credential columns | `field_security.sensitive_fields(model)` — never selectable |

### `crm_app` helpers

| Need | Call |
|---|---|
| **Convert a lead to a deal** | `crm_app.conversion.convert_to_deal(lead, deal=, existing_contact=, existing_organization=, ignore_permissions=)` |
| Its parts | `create_contact`, `create_organization`, `contact_exists`, `update_lead_contact`, `create_deal` |
| Rebuild the sales hierarchy | `crm_app.permissions.tree.rebuild_sales_hierarchy()` (advisory-locked) |

### Endpoints that already exist — do not rebuild

**Phase 3 landed the endpoint layer.** 58 dotted paths are registered; list them with
`frappe_core.whitelist.all_methods()`. They live in `crm_app/api/`, one module per
source module — `crm.api.contact.*` in `crm_app/api/contact.py` — except the endpoints
Frappe defines in `crm/api/__init__.py`, whose paths have no module segment
(`crm.api.invite_by_email`) and which live in `crm_app/api/misc.py`.

Covered: all of `PHASE_3_ENDPOINTS.md` groups A–D, plus the `frappe.client.*` /
`frappe.desk.*` built-ins the frontend needs (`PORT_PLAN.md` §3) in
`crm_app/api/client.py`.

`test_every_frontend_dotted_path_resolves` reads the frontend source and fails if it
calls a path nothing serves — so that list stays honest without being maintained by hand.

Still unported, deliberately: `crm.api.whatsapp.*` and `crm.integrations.*` (phase 7),
the doctype-controller methods (`PHASE_3_ENDPOINTS.md` §3), and `crm.demo.*`.

### Added by phase 3

| Need | Call |
|---|---|
| **Cancel an assignment** | `assignment.cancel_assignment(doctype, name, users, status="Cancelled")` — flips the ToDo, never deletes it |
| **Recompute product totals** | `crm_app.models.taxonomy.recalculate_parent_totals(parenttype, parent)` — fires automatically on `CRMProducts` save/delete |
| Quick-filter defaults | `crm_app.api.doc.STANDARD_FILTER_FIELDS` — `in_standard_filter` per doctype, verified against the JSON by test |
| Mention parsing | `crm_app.api.comment.extract_mentions(html)`, `notify_mentions(comment)` |
| Activity timeline parts | `crm_app.api.activities.get_linked_calls / get_linked_notes / get_linked_tasks / get_attachments` |
| Chart dispatch | `crm_app.api.dashboard.CHART_BUILDERS` — add a name here and both dashboard endpoints pick it up |
| Role guard | `crm_app.api.user.only_for([roles])` — the port of `frappe.only_for` |

**New model: `Dynamic Link`** (C5), in `frappe_platform`. Frappe's generic
"this document points at that one" child table — polymorphic on both ends, so it carries
`parent`/`parenttype` rather than a FK. Unblocks `CRM Call Log.links` and `Contact.links`.

**New platform fields:** `User.language`, `User.email_signature`; `Email Account` gained
the signature, Frappe Mail and IMAP/SMTP columns `create_email_account` writes.
`Email Account.api_secret` joins `password` in `SENSITIVE_FIELDS`.

---

## 3. Behaviours you can rely on

- **Parameters** merge query string + JSON body, then JSON-decode. A param may arrive as
  `'["a","b"]'` or `["a","b"]` — no `parse_json` needed in your handler.
- **Surplus parameters are dropped**, matching Frappe, so `cmd` and cache-busters do not
  500 an endpoint.
- **Auth**: non-`allow_guest` endpoints return 401 when unauthenticated. Do not re-check.
- **Permissions**: `fetch_rows` / `count_rows` / `base_queryset` apply the phase-2 hook.
  An endpoint reading through them **cannot** bypass row-level security. One calling
  `Model.objects` directly **can** — don't.
- **`fields`, `order_by`, `group_by` are validated** against concrete fields, so relation
  traversal (`owner__password`) is rejected with 417.
- **`validate_name` runs on every insert** — `<` and `>` are rejected, names are stripped.
- **`fetch_from`** mirrors linked-document fields on save; declare it as
  `FETCH_FROM = {"target": ("link_field", "source_field")}` on the model.
- **Envelopes are automatic**: `{"message": ...}` for `/api/method/`, `{"data": ...}` for
  `/api/resource/`.

---

## 4. Invariants that will bite you

Each of these cost real time this session.

**`lead_owner` / `deal_owner` is the access column, not `owner`.** A Sales User who
creates a lead and leaves `lead_owner` blank **cannot see it afterwards**. Any endpoint
creating a lead or deal must set the owner field, or the record vanishes for its author.

**Names are verbatim and may contain slashes.** `field:` PKs are stored unchanged — no
slugification. `validate_name` forbids only `<` and `>`. The URL pattern accepts path-style
names, so `R/GA` is a legal, addressable record.

**`User`'s PK is the lowercased email.** `owner`, `modified_by`, `ToDo.allocated_to`,
`_assign` and every `@me` filter compare it as a plain string.

**"Assigned" has two definitions** — display excludes `Closed` **and** `Cancelled`;
permissions exclude only `Cancelled`. So a Closed ToDo still grants access while not
appearing in `_assign`. **Query `ToDo`, never `_assign`, for anything access-related.**

**Unknown row/field names raise, they are not dropped.** `_selectable` used to silently
skip them; that concession was retired once phase 1 landed.

**Underscore fields are read-only on the serializer** and maintained by signals. Write
them with a bare `update()`, never `save()` — a cache refresh must not bump `modified`.

**JWT access tokens live 5 minutes**, refresh tokens rotate and are single-use. A test
holding a token across a long block will see it expire.

---

## 5. Test fixture recipes

Every one of these cost a failed run this session.

```python
# A lead needs an owner to be visible to its creator, and a status row to exist.
status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
lead = CRMLead.objects.create(first_name="Ada", lead_owner=alice, status=status)

# status is now auto-defaulted on create (validate_status is ported), so omitting it
# is fine IF a "New" / "Qualification" status row exists.

# A Lost status requires a lost_reason, or validate_lost_reason raises.
CRMLead.objects.create(..., status=lost_status, lost_reason=reason)

# CRMProducts.rate and product_name are NOT NULL.
CRMProducts.objects.create(parenttype="CRM Lead", parent=str(lead.pk), idx=1,
                           product_name="Widget", rate=10)

# Contact details go on the CONTACT, not the child row - fetch_from overwrites the
# child's email/phone/full_name/gender from the linked Contact on every save.
contact = Contact.objects.create(first_name="Jane", email_id="jane@acme.com")
CRMContacts.objects.create(parent_deal=deal, contact=contact)
```

Available fixtures in `tests/conftest.py`: `alice`, `bob`, `administrator`, `make_user`,
`api` (unauthenticated), `auth_api` (bearer token for alice), `as_user`.

`logout` is **not** `allow_guest` — calling it from `api` returns 401 and tests nothing.

---

## 6. The rule that governed every divergence

Upstream has bugs. Nine are catalogued in `UPSTREAM_BUGS.md` (gitignored, local).

> **Diverge on bugs nothing can observe. Reproduce bugs that are user-visible.**

Before diverging, **check whether anything reads the field or behaviour**. `from_type` on
the status log was corrected because nothing reads it; `update_expected_deal_value`'s odd
guard was reproduced because users see the result. Record either choice in the code with
the source line, and add the entry to `UPSTREAM_BUGS.md`.

---

## 7. Test discipline that repeatedly caught real bugs

**Verify a test fails without the fix.** Twice this session a test passed either way and
proved nothing — phase 1's FK-target test passed vacuously because `get_doctype()` was
missing, and a concurrency test passed with the lock removed because it exercised the
wrong hazard. If a test cannot fail, it is not a test.

**Read the source rather than transcribing it.** Phase 1's schema tests compare the model
to the DocType JSON field-by-field, which is why they caught three truncated `Select`
option lists. Asserting your own transcription proves nothing.

**Suspect your tools.** A JSON inspection script truncated `options` at 50 characters and
the agent transcribed the visible prefix without noticing. The tool was the thing that
was wrong.
