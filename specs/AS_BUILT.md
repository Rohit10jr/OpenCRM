# As-built reference — read this before writing any code

**Authoritative.** Phases 0–6 are complete and reviewed; this describes what actually
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

### Added by phase 4

**`frappe_core.field_meta` is the port's `frappe.get_meta(doctype).fields`.** Use it
whenever you need a field's **Frappe** fieldtype, label, options, `reqd` or `hidden` —
the Django model cannot tell you any of those faithfully.

| Need | Call |
|---|---|
| All fields, declaration order, **layout breaks included** | `field_meta.get_fields(doctype)` |
| Value fields only (no Section/Column/Tab Break, no Table) | `field_meta.get_value_fields(doctype)` |
| One field / its Frappe fieldtype | `field_meta.get_field(doctype, name)`, `get_fieldtype(...)` |
| A Select's options as a list | `field_meta.select_options(field)` |
| Form layout, expanded | `crm_app.api.fields_layout.get_fields_layout(doctype, type)` |
| Default layout from the breaks | `crm_app.api.fields_layout.get_default_layout(doctype)` |
| A doctype's client-side script | `crm_app.api.form_script.get_form_script(dt, view)` |
| Saved-view columns for a user | `crm_app.metadata_hooks.saved_view_columns(doctype, user, view_type)` |
| Kanban manual ordering | `frappe_core.api.doc.get_records_based_on_order(...)` |
| Kanban badge counts | `frappe_core.api.doc.get_counts(row, doctype)` |

The data behind it is **generated**: `backend/crm_app/data/doctype_meta.json`, produced by
`python scripts/generate_field_meta.py` from the DocType JSON and committed.
`test_generated_field_meta_is_current` regenerates and diffs, so it cannot go stale
silently. **Re-run the generator if you change anything in `crm/fcrm/doctype/`.**

**C7 is closed.** `metadata.FILTERABLE_FIELDTYPES` / `GROUP_BY_FIELDTYPES` are now
transcriptions of `crm/api/doc.py`'s lists, keyed on the Frappe fieldtype. The old
`FILTERABLE_INTERNAL_TYPES` / `GROUP_BY_INTERNAL_TYPES` are gone, and so is phase 3's
`_resolved_fieldtype` plaster.

**`get_data`'s stubs are filled in, not rewritten.** `_load_saved_view` resolves through
the registered provider, `_get_views` and `_get_form_script` delegate to `crm_app`. The
four-step order and every response key are unchanged.

**Saved views are per user.** The lookup key is
`{dt, type, is_standard: 1, user}` — one person's columns are invisible to everyone else.
A provider returning `None` means "fall through to the controller default"; returning an
empty dict would render a column-less list.

### Added by phase 5

| Need | Call |
|---|---|
| Enqueue anything | `@shared_task` — `config.celery.app` is imported by `config/__init__.py`, so bare `shared_task` binds |
| Scheduled work | `config.celery.app.conf.beat_schedule` — one entry per `crm/hooks.py:scheduler_events` row |
| Emit a realtime event | `crm_app.realtime.publish(event, message=None, user=...)` — **message is second**, see phase 6 below |
| Object rule for a whole batch | `frappe_core.permissions.filter_object_permitted(doctype, instances, ptype, user)` |
| Bulk delete, split for the worker | `crm_app.api.doc.authorize_bulk_delete(...)` / `perform_bulk_delete(...)` |

**`publish` is never load-bearing.** It returns a bool and swallows a missing transport —
phase 6 fills in the Channels layer, and everything written against it already works with
Channels switched off. Never branch on its return value to decide whether a write happened.

**`filter_object_permitted` is the batched form of `check_object_permission`, and it is a
cost optimisation only.** A doctype opts in by registering `has_permission_batch` (CRM
Lead and CRM Deal do); everything else falls back to the per-object hook and gets the same
answer more slowly. `test_the_batched_object_rule_agrees_with_the_single_object_one` pins
the two together — if they ever disagree, the single-object answer is the one the rest of
the app uses and therefore the one to trust.

**A write path needs both `apply_permission_filter` and the object rule.** They are
allowed to differ and for the metadata doctypes they deliberately do: a public
`CRM View Settings` row is readable by everyone and deletable only by its owner. Phase 5's
review found `delete_bulk_docs` authorizing from the list filter alone, which let it
delete what `DELETE /api/resource/<dt>/<name>` refuses.

**Commenting bumps `modified`; the cache write does not.** `update_modified_background`
(`crm/utils/__init__.py:238-253`) is what makes a lead rise to the top of a
`modified desc` list when someone comments. It is a bare `update()`, so `modified_by`
keeps naming the last person who actually edited the document, not the worker.

**SLA has no scheduled job and must not acquire one** — it is computed on write. See
`PHASE_5_ASYNC.md` §4 and `test_no_sla_job_exists_in_the_beat_schedule`.

### Added by phase 6

| Need | Call |
|---|---|
| Publish to one user, or broadcast | `crm_app.realtime.publish(event, message=None, user=...)` |
| Publish to everyone watching a document | `crm_app.realtime.publish_to_doc(doctype, name, event, message=...)` |
| The same, from inside a coroutine | `realtime.apublish(...)` / `realtime.apublish_to_doc(...)` |
| Group names | `realtime.user_group(user)`, `realtime.doc_group(doctype, name)` |
| The WebSocket endpoint | `GET /ws/realtime?token=<access token>` → `crm_app.consumers.RealtimeConsumer` |

**The argument order is `frappe.publish_realtime`'s: `(event, message, user=...)`.** Not a
style choice — the publish sites still to be ported pass the payload positionally
(`crm/api/whatsapp.py:50`, `crm/integrations/exotel/handler.py:41`), and under any other
order `publish("exotel_call", payload)` would hash the payload into a group name nobody is
in and return True.

**A missing message body goes out as `{}`, never `null`**, matching
`frappe.publish_realtime`. Frontend handlers destructure their argument
(`Activities.vue:590`), and destructuring `null` throws.

**`whatsapp_message` is a broadcast, not a doc-room event** — `crm/api/whatsapp.py:49-56`
sends `{reference_doctype, reference_name}` with no room and the client filters. Phase 7
should call `publish`, not `publish_to_doc`.

**Group names are hashes.** Channels restricts them to `[-\w.]` under 100 characters, and
both halves of a real key break that: `o'brien+crm@example.co.uk` is a legal user PK and
every doctype name has a space. Always go through `user_group` / `doc_group`; the
publisher and the consumer compute them independently, and a mismatch is not an error, it
is silence.

**Realtime is switched off in one place — `ENABLE_REALTIME`.** It drops the WebSocket
route in `config/asgi.py` *and* makes `get_channel_layer()` return `None`. Both halves are
needed: routing alone would leave every publisher opening a Redis connection and waiting
for it to time out, which turns "realtime is off" into "every comment write pauses".

**Nothing may branch on a publish result.** Every path returns a bool and swallows its
failures; a caller that treats `False` as "the write did not happen" has reintroduced the
dependency `PHASE_6_REALTIME.md` §4 forbids.

**A `doc_subscribe` is permission-checked, not trusted.** `consumers._may_read` applies
the list filter *and* the object rule, the same pair the HTTP detail route uses. Any new
client event that names a document must do the same, or realtime becomes a permission
bypass with a pleasant API.

---

### Added by the phase-4 security review — read this before adding any doctype

Registering a doctype **publishes it**. `@register_doctype("X")` gives every authenticated
caller create, read, update and delete at `/api/resource/X`, and through the
`frappe.client.*` endpoints, unless something says otherwise.

Five findings across four phases were the same mistake: a phase gated the endpoints it
wrote, and the generic route stood open beside them doing the same job unguarded. Every
agent's tests passed, because they tested the endpoint just written. The mechanisms below
exist so that does not happen a sixth time.

**Full reasoning, per doctype, with the upstream comparison: `specs/SECURITY_MODEL.md`.**

#### Four field declarations, and how to choose

| Declaration | Read | Write | Use for |
|---|---|---|---|
| `SENSITIVE_FIELDS` | **nobody** | nobody | Credentials. Never on the wire, not selectable, not filterable |
| `ENCRYPTED_FIELDS` | via `get_password()` | — | Credentials **at rest**. The attribute holds ciphertext once saved |
| `RESTRICTED_FIELDS` | **managers only** | — | Visible to admins, not to ordinary users |
| `READONLY_FIELDS` | everybody | **nobody** | Must be visible, must not be set by its subject |

`SENSITIVE_FIELDS` and `ENCRYPTED_FIELDS` are usually declared **together** on a
credential: one keeps it off the wire, the other keeps it out of the database in plain
text. Neither implies the other.

#### Withholding a route entirely

`@register_doctype("X", routable=False)` publishes no route at all. Everything else —
model, permissions, internal callers — is unchanged. Correct when **nothing addresses the
doctype over HTTP**, because a route that does not exist is a smaller surface than one
guarded by a rule. `ToDo` and `Version` are the two; `specs/UNROUTED_DOCTYPES.md` says why,
and spells out the permission rule to write instead if one is ever needed.

#### Rules that defer to another document

A row that is *about* another record — `Comment`, `Communication`, `File` — reads if you
can read its parent and writes if you can write its parent
(`crm_app/permissions/attachments.py`). If you add another such doctype, follow that shape
and register `reference_fields=(...)`, which opts it into the destination re-check on
update. Without that, a row can be **moved** onto a document the caller cannot write.

#### Two tests will fail on you, deliberately

* **`tests/test_route_surface.py`** — every routable doctype must be ruled, reviewed-open
  with a reason, or not-yet-reviewed with the question. Registering one without a recorded
  decision fails the build. It does not decide for you; it refuses to let you skip
  deciding.
* **`tests/test_credential_fields.py`** — a field whose *name* looks like a credential must
  be declared. See the checklist below.

#### Checklist: adding a doctype that holds a credential

Phase 7 does this repeatedly — ERPNext API keys, Meta page tokens, webhook signing
secrets. In order:

1. `SENSITIVE_FIELDS` — keeps it out of responses, out of `fields=`, and out of filters.
   Hiding it from output alone is not enough: a filter turns the row count into an oracle,
   and `like` narrows a value one character per request. That is how a real SMTP password
   was recovered from this codebase.
2. `ENCRYPTED_FIELDS` — plus `frappe_core.secrets`, and a data migration if rows already
   exist. Read it back with `instance.get_password("field")`, never the attribute.
3. **A permission rule** — `SENSITIVE_FIELDS` hides the value; it does nothing to stop the
   *record* being rewritten. Hiding a mail password did not stop anyone repointing the
   server it belonged to.
4. **Decide the route** — `routable=False` if the frontend never addresses it.
5. **Consider `TRACKED_FIELDS`** — for a credential, record *that* it changed, never the
   old value. `specs/VERSION_HISTORY.md`.

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

> ### There is no server-side default, and that is deliberate
>
> **Verified against source.** `crm_lead.json` declares no `default` and no `reqd` for
> `lead_owner`; nothing in `crm_lead.py` fills it. The **browser** does, before the
> request is sent — `frontend/src/components/Modals/LeadModal.vue:187-189`:
>
> ```javascript
> if (!lead.doc?.lead_owner) {
>   lead.doc.lead_owner = getUser().name
> }
> ```
>
> Upstream gets away with this because the browser is realistically its only client. Ours
> has an API as a first-class interface, so the gap is reachable:
>
> **A bulk import that omits `lead_owner` creates records nobody can see.** No error, no
> warning — the rows exist, and only a manager or System Manager will ever find them.
>
> **A server-side default was considered and rejected.** Stamping the caller as owner
> would silently claim every imported record for whoever ran the script, which is wrong
> for any workflow that assigns afterwards — and unrecoverable once the data exists.
> Inventing that semantic is a bigger risk than the documented gap.
>
> **So: any caller creating a lead or deal is responsible for setting the owner.** That
> includes integrations, imports and scripts, not just endpoints in this repo.
> `frappe.client.insert` is a generic passthrough and deliberately does not fill it in.
> Pinned by tests that fail if someone adds a default without justifying it.

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

Upstream has bugs. **21** are catalogued across `UPSTREAM_BUGS_PHASE_0-2.md` and
`UPSTREAM_BUGS_PHASE_3-6.md` — both gitignored as local working notes (`.gitignore:59`),
so a divergence recorded only there is invisible to a reviewer. Summarise the ones that
matter in the phase's progress file too.

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
