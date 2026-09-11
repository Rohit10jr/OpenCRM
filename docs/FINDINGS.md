# Findings from the API test suite

Defects the `docs/http/*.http` files turned up, one entry each. **Expected** is what
upstream Frappe does, read from its source; **Actual** is what this port answered. A
finding stays here until it is fixed or a decision records that the port diverges on
purpose, in which case the block's expectation is changed and the entry says so.

The block reference (`02 / 6.9`) is the file and block that reproduces it; run that file
through `backend/scripts/run_http.py` and the failing line is the reproduction.

| # | Block | Severity | Summary | Status |
|---|---|---|---|---|
| 1 | 02 / 6.9 | medium | A filter on a field the doctype does not have answers **500** | open |
| 2 | 02 / 10.9, 10.10 | high | A document without a name, or a name containing `<`, answers **500** | open |
| 3 | 02 / 10.11 | medium | Deleting a row another row links to answers **409 DuplicateEntryError** with Django's internal wording | open |
| 4 | 02 / 10.4, 10.5 | low | Serializer validation answers **400**, the port's own validation answers **417**, both as `ValidationError` | open |
| 5 | 01 / 1.11 | medium | An email typed in a different case cannot log in; upstream accepts `Ada@Example.com` | open |
| 6 | 01 / 1.4 | low | A malformed bearer token answers `exc_type: InvalidToken`, not `AuthenticationError` | open |
| 7 | 03 / 5.8 | medium | A child-table row missing a mandatory field reaches the database and answers **409 DuplicateEntryError**, not `MandatoryError` | open |
| 8 | 04 / 4.9, 5.1 | medium | Validation that depends on child rows runs **before the rows are written**, so expected-value auto-update and primary-contact derivation lag one save behind | open |
| 9 | 04 / 4.12, 5.1 | **high** | A child row whose Link is given by name, as every form sends it, answers **500** — deal contacts and product lines with a product code cannot be written | open |
| 10 | 05 / 2.7, 2.9, 2.10 | medium | Contact's primary-email and primary-phone rules are not applied on a document save: a lone email row is not made primary, a stray `email_id` is not cleared, two primaries are accepted | open |
| 11 | 05 / 2.13 | low | Email addresses are never validated — on a contact's email rows, and `crm_lead.py:146` explicitly validates a lead's email too | open |
| 12 | 05 / 3.12 | low | `crm.api.contact.*` on a contact that does not exist answers 417 `ValidationError`; upstream answers 403 `PermissionError` | open |
| 13 | 05 / 5.1–5.5 | **high** | `rename_doc` inserts a copy and deletes the original: a referenced document cannot be renamed, and renaming a contact **deletes** its email and phone rows and its deal links | open |
| 14 | 05 / 6.2, 6.3 | low | The territory tree is unmaintained: `lft`/`rgt` stay null and no tree resolver is registered, so `descendants of` answers 400. Latent — the frontend never sends it | open |
| 15 | 06 / 2.2, 2.4 | medium | A task's `assigned_to` never becomes an assignment: no ToDo, empty `_assign`, and changing it does not unassign the previous user | open |
| 16 | 06 / 2.8, 3.4, 4.7, 4.9 | **high** | Task, Note and Call Log declare no list columns or rows, so their three screens fall back to Name and Last Modified; call-log rows are not parsed and the document hides its `links` | open |

---

## 1. Unknown field in a filter → 500

**Block:** `02_resource_grammar.http` 6.9 — `filters=[["no_such_field","=","x"]]`

**Expected:** a 4xx with `exc_type: ValidationError`. The port's own contract
(`AS_BUILT.md` §4: "unknown row/field names raise, they are not dropped") and the comment
in `frappe_core/exceptions.py` on `FilterError` both say a malformed filter is a client
error, and `fields=` and `order_by=` already answer 417 for the same mistake.

**Actual:** 500. `filters.resolve_field_path` returns the name unchanged when the model
has no such field, `Q(no_such_field="x")` reaches the ORM, and Django raises `FieldError`,
which nothing catches. With `DEBUG=True` the body is the HTML debug page.

**Where:** `frappe_core/filters.py:build_q` — validate `fieldname` against
`concrete_field_names(model)` before building the `Q`, raising `FilterError`.

**Upstream, for the record:** `frappe/utils/data.py:get_filter` (version-15) checks the
*operator* against a fixed list and throws 417 `Operator must be one of ...` for a bad
one, and sanitises the column name against injection. It then asks
`meta.has_field(fieldname)`, and when the answer is no it only tries the child tables and
carries on; nothing throws. `prepare_filter_condition` builds the column into the SQL,
MariaDB rejects the unknown column, and the request fails with a database error. So
upstream is also a 500 here. The 4xx expectation is the port's
own contract, not a fidelity requirement, and it is the better behaviour: a typo in a
saved view's filter should not read as a server crash.

## 2. Naming validation errors → 500

**Blocks:** `02_resource_grammar.http` 10.9 (no `organization_name`) and 10.10 (name
`ZZ <script>`)

**Expected:** two different answers, both from `frappe/model/naming.py:validate_name`
(version-15):

* no name → `frappe.throw(_("No Name Specified for {0}"))` with the default exception,
  `ValidationError`, so **417**;
* `<` or `>` in the name → `frappe.throw(..., frappe.NameError)`, and `NameError` is
  declared with `http_status_code = 409`, so **409** with `exc_type: NameError` and the
  message `Name cannot contain special characters like '<', '>'`.

The frontend branches on neither; it displays `messages[0]`, so the sentence is what a
person sees.

**Actual:** 500 for both. `frappe_core/naming.py` raises its own `NameError_`, a plain
`ValueError` subclass, for every naming failure - the two above and five more. It is not
a `FrappeError`, so `frappe_exception_handler` returns `None` and Django's 500 handler
takes over. The message text was transcribed correctly; it never reaches the client.

**Where:** `frappe_core/naming.py` - raise `frappe_core.exceptions.ValidationError` for
the empty name and a `NameError` subclass of `FrappeError` (status 409) for the rest, so
both the status and the `exc_type` match upstream. **User-visible:** the Organization
form's Save with an empty name shows a generic failure instead of the message written
for it.

## 3. Deleting a linked row → 409 with Django's wording

**Block:** `02_resource_grammar.http` 10.11 — `DELETE CRM Industry/ZZ Grammar Industry`
while an organization links to it

**Expected:** 417, `exc_type: LinkExistsError`, message
`Cannot delete or cancel because CRM Industry ZZ Grammar Industry is linked with CRM
Organization ZZ Grammar Alpha` (`frappe/model/delete_doc.py:check_if_doc_is_linked`).
The frontend shows that message.

**Actual:** 409, `exc_type: DuplicateEntryError`, message *"Cannot delete some instances
of model 'CRMIndustry' because they are referenced through protected foreign keys:
'CRMOrganization.industry'."* — Django's `ProtectedError` is a subclass of
`IntegrityError`, and the handler maps every `IntegrityError` to "Duplicate".

**Where:** `frappe_core/exceptions.py` — catch `ProtectedError` before `IntegrityError`
and render it as `LinkExistsError` (417) with the Frappe sentence. The referencing rows
are in `exc.protected_objects`.

## 4. Two status codes for one exc_type

**Blocks:** `02_resource_grammar.http` 10.4 (bad Select value) and 10.5 (Link to a
missing row)

**Expected:** 417. Every validation failure upstream is `frappe.exceptions.ValidationError`
with `http_status_code = 417`, and the port's own `ValidationError` uses 417.

**Actual:** 400. DRF's serializer raises its own `ValidationError`; the handler relabels
`exc_type` to `ValidationError` but keeps DRF's 400. So the same `exc_type` arrives as
400 from the serializer and 417 from model or filter code. The frontend branches on
`exc_type`, not the number, so nothing breaks; it is an inconsistency, and the reason the
suite keeps 417 as the expectation is that `PORT_PLAN.md` §3 fixes the wire protocol.

**Where:** `frappe_core/exceptions.py`, the `drf_exceptions.APIException` branch — use 417
when the mapped `exc_type` is `ValidationError`.

## 5. Login is case-sensitive on the email

**Block:** `01_auth.http` 1.11 — `{"usr": "ADA@EXAMPLE.COM", "pwd": <correct>}`

**Expected:** 200. Upstream's `User.find_by_credentials` (`user.py`) looks the name up
with `frappe.db.get_value`, and MariaDB's default collation compares case-insensitively,
so any casing of the address logs in. The User primary key is stored lowercased
(`frappe_platform/models.py:226`) for exactly that reason.

**Actual:** 401 `Invalid login credentials`. `frappe_core/api/auth.py:login` lowercases
the name only for the lockout tracker key and passes the raw value to
`authenticate()`, which does an exact match on `name`.

**Where:** `login` — resolve the account case-insensitively before authenticating.
Not a blanket `.lower()`: the built-in `Administrator` is stored with its capital, so the
lookup should be `name__iexact` (or try exact, then lowercased). **User-visible:** anyone
whose mail client capitalises their address gets "Invalid login credentials" for a
correct password.

## 6. A malformed bearer token is not an `AuthenticationError`

**Block:** `01_auth.http` 1.4 — `Authorization: Bearer this-is-not-a-token`

**Expected:** 401 with `exc_type: AuthenticationError`, which is what every other
authentication failure in the port answers and what `frontend/src/stores/users.js:34`
branches on.

**Actual:** 401 with `exc_type: InvalidToken` and SimpleJWT's wording *"Given token not
valid for any token type"*. The handler maps `drf_exceptions.AuthenticationFailed` by
exact type; SimpleJWT's `InvalidToken` is a subclass and falls through to its own class
name.

**Where:** `frappe_core/exceptions.py` — match with `isinstance` rather than the exact
type, or add `InvalidToken` to the map. The status is already right, so the frontend's
refresh-on-401 works; only the label and message differ.

## 7. A child row missing a mandatory field is a database error

**Block:** `03_leads.http` 5.8 — `PUT` a lead with
`products: [{"product_name": "ZZ No Rate", "qty": 1}]`

**Expected:** 417 with `exc_type: MandatoryError` and Frappe's message
`Error: Value missing for CRM Products: Rate` (`frappe/model/document.py:_validate_mandatory`
walks child rows too). The frontend branches on `MandatoryError` (`data/document.js:61`,
`Modals/DoctypeModal.vue:115`) to highlight the missing field.

**Actual:** 409, `exc_type: DuplicateEntryError`, message *"null value in column "rate" of
relation "crm_app_crmproducts" violates not-null constraint"*. The nested child payload
is written by `children.replace_children` without going through the child doctype's
serializer, so nothing checks required fields before the INSERT; the NOT NULL constraint
fires and the handler renders it as a duplicate.

**Where:** `frappe_core/serializers.py:_write_children` — validate each row through the
child's serializer (or check its required fields) before `replace_children`, raising
`MandatoryError`. Parent-level mandatory fields already answer correctly (03 / 2.5).

## 8. Child-dependent validation runs before the child rows are written

**Blocks:** `04_deals.http` 4.9 (with 4.9b/4.9c showing the catch-up), and 5.1 once
finding 9 is fixed.

**Expected:** upstream's `validate()` sees the child rows as part of the document, so a
single save that adds product lines moves `expected_deal_value` to the new total
(`crm_deal.py:240-248`, with `auto_update_expected_deal_value` on), and a single save that
adds a contact row makes it primary and copies its email, mobile and phone onto the deal
(`crm_deal.py:120-149`).

**Actual:** the port's serializer calls `instance.save()` first and writes the child rows
afterwards (`frappe_core/serializers.py:update`, then `_write_children`). `save()`
therefore runs `update_expected_deal_value` and `set_primary_contact` against the rows
that existed *before* this request. The totals are then refreshed by a bare `update()`,
so the very next save of any field catches up (4.9c passes), but the request that made
the change answers with stale derived values. For contacts the same order means a
contact added through the document is never made primary and the deal's email stays
empty until something else saves the deal.

**Where:** `frappe_core/serializers.py` — write the children before the final `save()`
(create the parent with `save()` first only to obtain a name, or run the derivations
again after `_write_children`), so the derived fields and the child rows land in the
same request as they do upstream.

## 9. A child row whose Link is given by name answers 500

**Blocks:** `04_deals.http` 4.12 (`products: [{"product_code": "ZZ-P1", ...}]`) and 5.1,
5.3, 5.5, 5.8 (`contacts: [{"contact": "ZZ Primary"}]`)

**Expected:** 200. A Link field in a child row is written by name over the wire, exactly
as a top-level Link is; `ConvertToDealModal.vue`, the deal contacts panel and the product
grid all send `{"contact": "<name>"}` / `{"product_code": "<code>"}`.

**Actual:** 500 with `ValueError: Cannot assign "'ZZ Primary'": "CRMContacts.contact" must
be a "Contact" instance.` `children.replace_children` copies the row dict into
`create(**payload)` untouched; Django accepts a raw key only under the `_id` attname
(`contact_id`), which the docstring there acknowledges and which no Frappe client ever
sends. Top-level Links are fine because the parent goes through a DRF serializer, which
resolves the key; child rows bypass the serializer.

**Where:** `frappe_core/children.py:replace_children` — for every `ForeignKey` on the
child model, move a value supplied under the field name to its `attname`, and let a
missing target surface as the 417 `LinkValidationError` upstream raises
(`Could not find Row #1: Contact: ZZ Nobody`) rather than a 500. Finding 7's validation
pass would be the natural place. **User-visible:** adding a contact to a deal, or a
product with a code, fails outright through the document route.

## 10. Contact's primary rules are not applied on a document save

**Blocks:** `05_contacts_organizations.http` 2.6/2.7 (a lone email row is not made
primary), 2.8/2.9 (a top-level `email_id` with no rows is not cleared), 2.10 (two
primary rows accepted)

**Expected:** `Contact.validate` (`contact.py:65`) calls `set_primary_email` and
`set_primary("phone")` / `set_primary("mobile_no")` on every save: one row means it is
primary; no rows means the mirror column is emptied; two primaries throw
`Only one Email ID can be set as primary.` (417).

**Actual:** the port's `Contact.save()` only derives `full_name`. The mirror columns are
refreshed by `sync_primary_values`, which runs from a signal when a *child row* is
written through `crm.api.contact.create_new` / `set_as_primary`, so those two endpoints
behave; a document saved through `/api/resource/Contact` with rows inline gets none of
the three rules. **User-visible:** a contact created with one email through the form
shows no primary, and a deal that later picks it up derives an empty email.

**Where:** `frappe_platform/models.py:Contact.save` — port the three methods, run them
after the child rows are written (finding 8's ordering applies here too).

## 11. Email addresses are never validated

**Block:** `05_contacts_organizations.http` 2.13 — an email row `not-an-email`

**Expected:** 417 `InvalidEmailAddressError`, *"not-an-email is not a valid Email
Address"*. Upstream validates every `Data` field whose `options` is `Email`
(`base_document.py:_validate_data_fields`), which covers `Contact Email.email_id`,
`Contact.email_id`, `CRM Lead.email` and `CRM Deal.email`; and `crm_lead.py:146` calls
`validate_email_address(self.email, throw=True)` explicitly on top.

**Actual:** 200; any string is stored. The port's `CRMLead.validate_email` ports only the
owner-equality check and drops the format check that precedes it.

**Where:** `frappe_core/serializers.py` (a validator for fields declared Email in
`doctype_meta.json`) and `CRMLead.validate_email`.

## 12. A missing contact is a validation error, not a permission error

**Block:** `05_contacts_organizations.http` 3.12

**Expected:** 403 `PermissionError`, `Not permitted`. Upstream asks
`frappe.has_permission("Contact", "write", name)`, which is False for a name that does
not exist, and throws `PermissionError`.

**Actual:** 417 `ValidationError` with the same words. `_require_contact` in
`crm_app/api/contact.py` uses `throw()` for the missing case and `PermissionError` only
for the denied case. Low, but the frontend branches on `PermissionError`.

## 13. rename_doc is insert-then-delete

**Blocks:** `05_contacts_organizations.http` 5.1/5.2 (organization referenced by a deal),
5.3–5.5 (contact with email rows and a deal link)

**Expected:** `frappe/model/rename_doc.py` renames in place: it updates the primary key
and every Link, Dynamic Link and child `parent` column that pointed at the old name
(`update_link_field_values`, `update_child_docs`), so the deal now points at
`ZZ Renamed Org`, and the renamed contact keeps its two email rows, two phone rows and
its place on the deal.

**Actual:** `frappe.client.rename_doc` in `crm_app/api/client.py` inserts a copy under
the new name and **deletes the original**. Two consequences:

* a document any row links to with `PROTECT` cannot be renamed at all — 409 with
  Django's "protected foreign keys" text (finding 3's rendering);
* a document whose links are `CASCADE` renames "successfully" and **loses them**: the
  contact came back with zero email rows and zero phone rows, and the deal's contacts
  table was emptied. Silent data loss on an action the UI offers.

**Where:** `client_rename_doc` — rename in place. Django cannot change a primary key with
`save()`, so the faithful port is: insert the copy, repoint every inbound FK and
polymorphic `parent`/`reference_name` column to the new name (the registry knows every
model, and `children.discover_child_tables` knows the child rows), then delete the
original. Until then the endpoint should refuse rather than cascade.

## 14. The territory tree is unmaintained

**Blocks:** `05_contacts_organizations.http` 6.2 (`lft`/`rgt` null), 6.3
(`descendants of` → 400 "No tree resolver registered for 'CRM Territory'")

**Expected:** `CRM Territory` is `is_tree` upstream, so `frappe/utils/nestedset.py`
maintains `lft`/`rgt` on every write and `descendants of` finds the organization two
levels down.

**Actual:** neither. `crm_app/models/taxonomy.py:CRMTerritory` says phase 2 owns the tree
behaviour; phase 2 built `crm_app/permissions/tree.py` for the sales hierarchy only and
never registered a resolver, so `_TREE_RESOLVERS` is empty at runtime. Latent: the
frontend never sends a tree operator and nothing reads `lft`/`rgt`. Recorded so the
phase-2 spec's "give territory the same treatment" is known to be unfulfilled.

## 15. A task's assigned_to is not an assignment

**Blocks:** `06_tasks_notes_calls.http` 2.2 (create with `assigned_to`), 2.4 (change it)

**Expected:** `crm_task.py:30-56`: `after_insert` calls `assign_to.add` for
`assigned_to`, so the task gets a ToDo and `_assign == ["ada@example.com"]`; `validate`
on a later save unassigns the previous user and assigns the new one, so `_assign`
becomes exactly `["grace@example.com"]`. The task board's assignee chip reads
`_assign`, and the assignee's own task list is built from ToDo.

**Actual:** `_assign` stays `[]` throughout. `crm_app/models/core_sales.py:CRMTask`
has fields only; no lifecycle was ported. The `OwnerAssignmentMixin` used by Lead and
Deal does exactly this job and would fit with `owner_field = "assigned_to"` plus the
unassign-previous step.

## 16. Task, Note and Call Log have no list definitions

**Blocks:** `06_tasks_notes_calls.http` 2.8 (task columns), 3.4 (note rows), 4.9
(call-log columns and parsed rows), 4.7 (call-log `links`)

**Expected:** each controller declares what its screen needs:

* `crm_task.py:57` — columns title, status, priority, due date, assigned to, modified;
* `fcrm_note.py:24` — no columns but rows `title, content, reference_doctype,
  reference_docname, owner, modified`, which the Notes page renders as cards;
* `crm_call_log.py:57` — columns starting with caller, and `parse_list_data` adds
  `_duration`, `_caller`, `_receiver` and `activity_type` to every row, which
  `CallLogs.vue` and `CallArea.vue` read directly;
* the call log's `links` child table (Table of Dynamic Link) comes back on the document.

**Actual:** `get_data` for all three falls back to the registry default, two columns
(`name`, `modified`) and generic rows. The Tasks and Call Logs screens would render
with only those two columns, and the Notes page cards would have no title or content to
show. The port writes Dynamic Link rows for a call log but the model declares no
`POLYMORPHIC_CHILD_TABLES` entry for `links`, so the document never shows them.

**Where:** `crm_app/models/core_sales.py` (`CRMTask.default_list_data`,
`FCRMNote.default_list_data`), `crm_app/models/telephony.py` (`CRMCallLog.default_list_data`,
`parse_list_data`, and `POLYMORPHIC_CHILD_TABLES = {"links": "Dynamic Link"}`). Lead,
Deal, Organization and Contact all have theirs; these three were missed.
