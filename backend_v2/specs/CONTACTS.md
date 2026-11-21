# CONTACTS — contacts, their emails and phones, addresses, organizations

**Status: rewritten from the spec check and the spec review** (`temp` A-41, A-42,
DECISIONS 56-60; 18-19 Nov 2026). Milestone 0 and 1 may be briefed; milestone 2 onward
after the supervisor checks this rewrite. Paths are from the repository root; old paths
are `backend/` unless named.

## 1. Scope

App `contacts`. The `PORT_MAP.md` rows under **CONTACTS**:

- **Doctypes:** Contact, Address, CRM Organization, CRM Industry, and the reference data
  Salutation and Gender; child tables Contact Email, Contact Phone, Dynamic Link
- **Method paths (4):** `crm.api.contact.create_new`, `search_emails`, `set_as_primary`;
  `crm.api.session.get_organizations`. **`crm.api.contact.get_linked_deals` moves to
  SALES** (DECISIONS 57, flagged): it reads only the deal-contacts table and CRM Deal
  (`crm_app/api/contact.py:44-72`), and `contacts` cannot import `sales`. §9 says what
  SALES keeps.

**Routes** (S25; `PORT_MAP.md`'s route column, written in this unit's first commit):

| Old | New |
|---|---|
| Contact, Address, CRM Organization, CRM Industry, Salutation, Gender (`/api/resource/...`) | `/api/v1/contacts/`, `addresses/`, `organizations/`, `industries/`, `salutations/`, `genders/`: list, create, `value/`, record `GET`/`PATCH`/`DELETE`, `permissions/`, and the shared actions of §8 |
| `crm.api.contact.create_new` | `POST /api/v1/contacts/<name>/create-new/` (`field`, `value` in the body) |
| `crm.api.contact.set_as_primary` | `POST /api/v1/contacts/<name>/set-as-primary/` (`field`, `value` in the body) |
| `crm.api.contact.search_emails` | `GET /api/v1/contacts/search-emails/` (`txt` kept as input). The frontend sends POST (frappe-ui's default); as for the `meta/` calls, the `.http` generator rewrites the method and the frontend changes at S22 |
| `crm.api.session.get_organizations` | `GET /api/v1/organizations/directory/`, as ACCOUNTS' `get_users` is `users/directory/` |
| `frappe.client.set_value` on a Contact Email or Contact Phone row | `PATCH /api/v1/contacts/<name>/email-ids/<row>/`, `.../phone-nos/<row>/`, the value in the body as `{"<fieldname>": <value>}` (S7; the route map lists the reshaping) |
| `frappe.client.delete` on such a row | `DELETE /api/v1/contacts/<name>/email-ids/<row>/`, `.../phone-nos/<row>/` |

A contact or organization name may contain slashes (`R/GA`): the nested child-row routes
sit under `DocumentRouter`'s ordering (AS_BUILT §2, "Carrying a document name with
slashes in a route"). A record named exactly like a collection action cannot be reached
(S25 (8)): `search`, `value`, `export`, `bulk-delete`, `bulk-update`, `search-emails`,
`directory`, and a contact whose name ends `/email-ids/<x>` or `/phone-nos/<x>`.
`API_CONTRACT.md:262` ("a child row is never reachable on its own") gets the owner's
approved exception for these two nested routes (owner, 12 Nov 2026; FOUNDATION §6): the
supervisor writes it with milestone 4, since builders do not edit the contract.

## 2. Depends on

- **ACCOUNTS:** roles, `User` (Contact's `user` foreign key), the role check of
  `get_organizations` (`accounts/directory.py:36` has its message).
- **SHARED_ACTIONS:** rename, bulk delete, linked documents, bulk update, search, export.
- **CONFIGURATION:** Country (Address's `country`, PROTECT, `frappe_platform/models.py:1923-1925`);
  Currency and the exchange-rate provider for Organization's save
  (`crm_app/models/core_sales.py:58-96,133-139`; `configuration/exchange_rate.py`); the
  field metadata and `getdoctype` (§7a); the seeded layouts and quick filters
  (`configuration/data/default_rows.json`); the list engine and `list_view_class`
  (CONFIGURATION §4.8): **the Contacts and Organizations list pages wait for
  CONFIGURATION milestone 8** (`frontend/src/components/ViewControls.vue:518`).
- **SALES' CRM Territory** for Organization's `territory` foreign key
  (`core_sales.py:120-122`; `PORT_MAP.md:336`): **parked for the owner** (§6 A).
  Milestones run with CRM Organization last and stop before it until the owner answers.

## 3. Read in `backend/` first

- `frappe_platform/models.py`: Contact `:330-527`, Contact Email and Contact Phone
  `:529-572`, Dynamic Link `:1560-1598`, Salutation and Gender `:1842-1870`, Address
  `:1873-2030`, the row signals `:2104-2150`
- `crm_app/models/core_sales.py:58-160` (the exchange-rate mixin, CRM Organization),
  `models/taxonomy.py:83-91` (CRM Industry)
- `crm_app/api/contact.py`, `api/session.py:150-170`, `api/client.py:64-81` (Address
  search filter), `:393-459` (child-row edit and delete), `:462-495` (rename),
  `:701-733` (search fields)
- `crm_app/permissions/platform_docs.py:424-484`, `permissions/__init__.py`
- `frappe_core/naming.py:51-118`, `frappe_core/links.py:51-77`,
  `frappe_core/delete_doc.py:164-180`, `frappe_core/serializers.py:105-130,244-281`
- `frappe_platform/migrations/0014_seed_salutations_and_genders.py`,
  `frappe_platform/reference_data.py:34-60`, `crm_app/setup.py:159` (industries)
- `docs/FINDINGS.md` 8, 10, 11, 12, 13, 23, 44, 45, 66, 67, 68, 86
- `specs/SECURITY_MODEL.md:350`

### Fields

`backend/` has no allowlists: every concrete column is readable, filterable and sortable
(`frappe_core/serializers.py:244-281`, `fields="__all__"`), and none of these doctypes
declares a sensitive one. So each resource's lists name **every** concrete column below,
plus the standard fields: `name`, `owner`, `modified_by`, `creation`, `modified`, `idx`,
`docstatus` and the four caches `_assign`, `_liked_by`, `_comments`, `_user_tags` (`02`
8.1 expects `_assign` from `fields=["*"]`; leaving them out would also drop them from
`getdoctype`, PE-16).

| Doctype | Columns, in the old order, with the old labels | Access |
|---|---|---|
| Contact (model metadata, `frappe_platform/models.py:349-407`) | `first_name` First Name, `middle_name` Middle Name, `last_name` Last Name (each Char 140, blank ""); `full_name` Full Name (Char 420); `salutation` Salutation, `company_name` Company Name, `designation` Designation, `gender` Gender (Char 140); `image` Image (Char 500); `status` Status (Char 20; Passive, Open, Replied; default Passive); `address` Address (FK, SET_NULL, null, `related_name="+"`); `user` User Id (FK, SET_NULL, null, `related_name="+"`); `email_id` Email Address, `mobile_no` Mobile No, `phone` Phone (Char 140). `TEXT_LINK_FIELDS = {"salutation": ("contacts.Salutation", "Salutation"), "gender": ("contacts.Gender", "Gender")}`; `ATTACH_FIELDS` `image`; `EMAIL_FIELDS` `email_id`; `TABLE_FIELD_LABELS` (§7a) | `Access.ruled()` |
| Contact Email (child) | `email_id` Email ID (Char 140, required), `is_primary` Is Primary; `NAME_STRATEGY = Hash(10)`; `EMAIL_FIELDS` `email_id` | through Contact |
| Contact Phone (child) | `phone` Number (Char 140, required), `is_primary_phone` Is Primary Phone, `is_primary_mobile_no` Is Primary Mobile; `NAME_STRATEGY = Hash(10)` | through Contact |
| Address (model metadata, `models.py:1914-1932`) | `address_title` Address Title (Char 140, blank ""); `address_type` Address Type (Char 20, required; the twelve `ADDRESS_TYPES`); `address_line1` Address Line 1 (Char 240, required); `address_line2` Address Line 2 (Char 240); `city` City/Town (Char 140, required); `county` County, `state` State/Province (Char 140); `country` Country (FK to `configuration.Country`, PROTECT, required); `pincode` Postal Code, `email_id` Email Address, `phone` Phone, `fax` Fax (Char 140); `is_primary_address` Preferred Billing Address, `is_shipping_address` Preferred Shipping Address, `disabled` Disabled (booleans); `links` (Dynamic Link rows). `EMAIL_FIELDS` `email_id`; `PREFERRED_FLAGS` | `Access.ruled()` |
| Dynamic Link (child, polymorphic) | `parenttype`, `parentfield`, `parent` (Char 140, indexed); `link_doctype`, `link_name` (Char 140, required, indexed); `link_title` (Char 280); indexes on both pairs; `NAME_STRATEGY = Hash(10)`; `DYNAMIC_LINK_FIELDS = (("link_doctype", "link_name"),)` in v2's pair form (`AS_BUILT.md:693,710-712`), without which neither the delete check nor the linked-documents scan sees the rows | through its parent |
| CRM Organization (`doctype_meta.json`) | `organization_name`, `website`, `organization_logo`, `no_of_employees` (choices), `annual_revenue` (Decimal(18,6): a string in a document, a number in a list), `industry` (FK, PROTECT), `territory` (FK, PROTECT; §6 A), `currency` (text Link), `address` (text Link), `exchange_rate` (float) (`core_sales.py:108-127`) | `Access.open(reason=…)`, PORT_MAP's reason |
| CRM Industry (`doctype_meta.json`) | `industry` | `Access.ruled()`, a CRM role (PE-29) |
| Salutation, Gender | `salutation` / `gender` (Char 140, unique) | `Access.ruled()` |

- **Computed but not read-only, as `backend/`:** `full_name`, `email_id`, `mobile_no` and
  `phone` on Contact accept a write that the save then overwrites (upstream marks them
  read-only). No address-display field: `get_address_display` is not ported (FINDINGS 45).
- **`CHILD_FIELDS`, exactly** (v2 adds `doctype` itself, `AS_BUILT.md:1003`; it is not a
  column, and `core/children.py:45-51` raises on an unknown entry):
  - Contact Email: `name, owner, modified_by, creation, modified, idx, docstatus, _assign,
    _liked_by, _comments, _user_tags, parent_contact, parenttype, parentfield, email_id,
    is_primary`
  - Contact Phone: the same standard fields, then `parent_contact, parenttype,
    parentfield, phone, is_primary_phone, is_primary_mobile_no`
  - Dynamic Link: the same standard fields, then `parenttype, parentfield, parent,
    link_doctype, link_name, link_title`
- **Contact's and Address's metadata come from the model**, so the columns are declared
  in the old order with the old verbose names, or `getdoctype` differs.
- **Dynamic Link's `link_title`** is the linked document's name, as `backend/` stores
  it (its title-field lookup finds none; DECISIONS 65).

### Tests (REBUILD_PLAN S14)

Ported creates answer 200 with `message` (`API_CONTRACT.md:137-140`), not the old 201
with `data`.

| File | Here (milestone) | Waits for |
|---|---|---|
| `test_salutation_gender.py` | 1 (`:35-47` call the seed functions and expect their counts); the Contact parts at 3 | `:12` imports CRMLead: `:76-87`, `:128-140` SALES |
| `test_seed_defaults.py:122-123`, `:253` (51 industries) | 1 | — |
| `test_address.py` | `:68-97`, `:253-261` at 2; `:187-198` at 5 (needs Contact too) | the rest use the `acme` Organization fixture: 5; `:230-237`, `:264-270` are Country cases (CONFIGURATION) |
| `test_contact_naming.py` | 3 (`:135-146`'s docstring about Dynamic Link is stale) | `:161-197` is the User half: ACCOUNTS |
| `test_contact_rules.py` | 3 and 4 | `:14` imports Lead and Deal: `:121-133`, `:136-147`, `:183-191` SALES, ACTIVITIES |
| `test_platform_models.py` (Contact half) | 3; `:226-244` (`default_list_data`) at 7 | — |
| `test_crm_behaviour.py:424-430` (Contact) | 3 | — |
| `test_contact_delete_rule.py` | `:38-75` at 3; `:78-92` (bulk) at 6a | — |
| `test_form_load.py:300-313` | 3 | — |
| `test_contact_numbers.py` | `:25-150` at 4, without `:88-94` (7) | — |
| `test_phase3_endpoints.py:154-203`, `:211-312` | the existence checks of `search_emails` (4) and `get_organizations` (5); `:480-491` is named "Not permitted" and asserts `["Invalid field"]` with no status: ported as it asserts | `get_linked_deals`: SALES |
| `test_envelope.py:165-185` (Organization and Industry PROTECT), `test_null_as_blank.py:22-67`, `test_name_lookup.py:61-93`, `test_crm_behaviour.py:252-259`, `test_route_surface_review.py:173-200`, `test_versions.py:173-182` (Organization untracked); the organization cases of `test_currency.py` and `test_exchange_rate.py` | 5 | §6 A |
| `test_list_definitions.py` (Contact, Organization), `test_phase4_metadata.py:283-287` | 7 | CONFIGURATION milestone 8 |
| `test_rename.py` | — | all of it: SALES (the `linked` fixture makes a CRM Deal and its contacts row, `:12,34-41`); `:70-92` also ACTIVITIES, `:95-108` NOTIFICATIONS |
| the Contact and Organization cases of `test_delete_dialog_links.py`, `test_unlink_linked_docs.py` | — | SALES |
| `test_attach_on_save.py:44-47`, `test_phase5_async.py:292-304` | — | ACTIVITIES |

New tests: milestone 0's two `core` changes (on `tests_support`), `search_emails` and
`get_organizations` behaviour (no old one exists), the 403-before-404 rule, the
child-row routes, PE-24, PE-12f, each §4 item no old test covers.

## 4. Must not be lost

### Who may do what (DECISIONS 58, flagged)

`backend/` puts no CRM-role gate on these resources (DECISIONS 58); only
`get_organizations` needs a CRM role there. **PE-29** (owner, 20 Nov 2026) adds one, as
upstream's role tables (and `crm_industry.json`) grant the three CRM roles only: CRM
Industry and Address answer only to Sales User, Sales Manager, System Manager or
Administrator, and a caller with none gets an empty list and 403. Contact and CRM
Organization take the same rule when they are built. Salutation and Gender keep their
rule (owner, 21 Nov 2026).

| Doctype | List | Read | Write | Create | Delete |
|---|---|---|---|---|---|
| Contact | everyone (`platform_docs.py:437-440`; PE-29 when built) | everyone | everyone | everyone | the creator (`owner`), System Manager or Administrator (`:443-455`) |
| Contact Email, Contact Phone | through the contact | the contact's read | the contact's write | through `create_new` or the contact's rows | the contact's write; a refused delete is 404 |
| Address | a CRM role (PE-29; old: everyone, `:424-426`) | a CRM role | a CRM role | a CRM role | System Manager or Administrator (`:429-434`) |
| CRM Industry | a CRM role (PE-29; old: everyone signed in, no rule registered) | a CRM role | a CRM role | a CRM role | a CRM role, subject to PROTECT and Dynamic Link rows |
| CRM Organization | everyone signed in (no rule registered; PE-29 when built) | everyone | everyone | everyone | everyone, subject to PROTECT and Dynamic Link rows |
| Salutation, Gender | everyone (`:472-475`) | everyone | System Manager or Administrator (`:478-484`) | the same | the same |
| Dynamic Link | no route; through its parent | | | | removed with its parent |

| Call | Gate | On the named record |
|---|---|---|
| `create_new`, `set_as_primary` | signed in | Contact write; a missing or refused contact is 403 |
| `search_emails` | signed in | the Contact list rule |
| `get_organizations` | a CRM role, else 403 "You are not permitted to access CRM resources." (`session.py:41-42,167`), through `accounts.directory.session_role_flags` | — |

Every way to delete a contact or an address applies its delete rule: the record route,
the delete dialog, bulk delete (which refuses the whole batch with 403,
`test_contact_delete_rule.py:78-92`), and, after milestone 0 (PE-26), the unlink
action's `delete` and bulk delete's `delete_linked`, which skip an item the caller may
not delete.

### Milestone 0: two changes to the shared actions in `core` (DECISIONS 59, flagged)

No real resource opts in to these yet (only `tests_support`), so nothing is reachable
today; both come before Contact opts in.

- **PE-25 (proposed):** "remove contact" (`core/mixins/linked.py`, `_clear_contact`)
  clears the document's own `contact` field and the child table its serializer declares
  as `contacts` (`CHILD_TABLES`), never a reverse relation. Tests on `tests_support`:
  "remove contact" on an item whose model has no such table deletes no row.
- **PE-26 (proposed):** the unlink action with `delete` and bulk delete with
  `delete_linked` (`core/mixins/bulk_delete.py`) check the item's object `delete` rule
  before deleting it; an item the caller may not delete is skipped, like every other
  refusal in those loops (`SHARED_ACTIONS.md:141`), and its link is still cleared.
  Tests on `tests_support`; at milestone 6a the matrix gains these two doors for Contact
  and Address.

### Naming

- **Contact** (controller, `frappe_platform/models.py:434-478`): the base is first,
  middle and last name stripped and space-joined, `company_name` only when all three are
  empty; plus `name_links_suffix()`, which is always `""` in `backend/` (upstream would
  append the first Dynamic Link's name; Contact has no `links` table); then
  `core.naming.append_number_if_name_exists` (`core/naming.py:29`; old
  `naming.py:56-83`): `-1`, `-2` …, counting from the highest existing suffix, ordered by
  length then name so `-10` sorts above `-9`; the name is stripped after numbering.
  Naming runs on insert only; a sent `name` is ignored (`name` is `editable=False`, old
  `frappe_core/models.py:121`). `core.naming.validate_name` (`core/naming.py:44`; old
  `naming.py:101-118`): an empty name is 417 "No Name Specified for Contact"; a name
  starting "New Contact" is 409 "There were some errors setting the name, please contact
  the administrator"; a name equal to "Contact" is 409 "Name of Contact cannot be
  Contact"; `<` or `>` is 409 "Name cannot contain special characters like '<', '>'";
  slashes are legal. `full_name` is recomputed on every save.
- **Address** (controller, `models.py:1944-1955`): `<title>-<type>`, then the collision
  suffix; an empty title is 417 "Address Title is mandatory."
- **CRM Organization, CRM Industry, Salutation, Gender:** the field value, verbatim
  (`FieldValue`). A duplicate organization is 409 `DuplicateEntryError` "CRM
  Organization <strong>X</strong> already exists" (`test_name_lookup.py:61-93`).
- `PORT_MAP.md:258,261`'s Naming cells for Contact and Address are corrected to
  "controller (full name + `append_number_if_name_exists`)" and "controller
  (`<title>-<type>` + number)".

### Primary email and phone (`models.py:480-526`, `:2104-2150`)

- **(a)** On create the three mirror columns (`email_id`, `mobile_no`, `phone`) are
  cleared; the document route saves again once its rows are written (FINDINGS 8).
- **(b)** No rows empties the column. Rows but none flagged: the column is empty; no
  first-row fallback (FINDINGS 10).
- **(c)** Email only: a lone unflagged row is promoted, and that is persisted. A lone
  phone row is not promoted.
- **(d)** Two primaries are 417, verbatim: "Only one <strong>Email ID</strong> can be
  set as primary.", "Only one <strong>Phone</strong> can be set as primary.", "Only one
  <strong>Mobile No</strong> can be set as primary." Email is checked before phone,
  phone before mobile (`models.py:510-514`).
- **(e)** The mirrored email is stripped.
- **(f)** Saving or deleting one row outside a document write re-derives the contact
  through a row signal, so deleting the primary email promotes the other
  (`test_contact_numbers.py:138-143`). The signal writes with `update()`, so `modified`
  is not bumped.
- **(g)** The signal stands down while a document's rows are being replaced and while
  the contact itself is being deleted (FINDINGS 23): a contact can be deleted whatever
  state its rows are in.
- **(h)** `set_as_primary` clears and sets the flags with two set-based updates in one
  transaction, then derives once (FINDINGS 67). A `value` matching no row clears every
  flag and empties the column, still answering `true`; two rows with the same value
  raise "Only one …" and the transaction rolls back (`contact.py:131-137`).
- **(i)** `create_new` makes the row primary only when the table was empty; `mobile_no`
  and `phone` both set `is_primary_mobile_no`. Its rows keep `idx` 0 (parity,
  `contact.py:87-97`); child rows are read ordered by `idx`, then `name`, so the answer
  is stable (`05` 3.4 and 3.6 assert by index).

`test_platform_models.py:210-214` ("first email wins") and `test_contact_rules.py:50-56`
("two unflagged rows give an empty column") pass together only because of (c) and (f):
dropping the row signal breaks one of them.

### Validation

- Email addresses are validated on Contact, Contact Email and Address `email_id`
  (FINDINGS 11): 417 `InvalidEmailAddressError` "<value> is not a valid Email Address",
  the value HTML-escaped; split on commas and newlines only; the display-name form is
  accepted (`test_contact_rules.py:112-166`).
- Contact's `salutation` and `gender`, and Organization's `currency` and `address`, are
  text columns checked as Links on every save (`frappe_core/links.py:59-77`): 417
  `LinkValidationError` "Could not find <Label>: <value>", several misses joined into one
  message, and a case-only match rewritten to the stored spelling
  (`test_salutation_gender.py:118-153`).
- `null` on a text field saves as `""` (FINDINGS 68; `test_null_as_blank.py:22-67`).
- **PE-12f (approved, PE-12's kind):** a missing `field` or `value` on `create_new` or
  `set_as_primary`, or a missing `txt` on `search_emails`, is 417 with a fixed sentence
  ("Field is required", "Value is required", "Search text is required"); the old backend
  raises on the missing argument. An empty `txt` still lists every contact with an email.

### The contact calls

- **`create_new`, `set_as_primary`:** a missing or refused contact is 403
  `PermissionError` "Not permitted" (title "Not Permitted"), **before** the field is
  checked, so a missing contact with `field="banana"` is still 403
  (`contact.py:26-41`; FINDINGS 12). These actions **must not use the base ViewSet's 404
  record lookup** (`AS_BUILT.md:1012-1015`). An unknown `field` is 417 "Invalid field".
  Both answer `true`.
- **`search_emails`** (`contact.py:141-164`): contacts with `email_id` set, matched by
  `like` on `full_name`, `email_id` or `name`, ordered `email_id, full_name, name`, 20
  rows, each a **list** `[full_name, email_id, name]`.
- **`get_organizations`** (`session.py:158-170`): every column of every organization,
  ordered by `name`, no limit, in the list-projection shape (decimals as numbers, the
  caches as JSON strings).

### The child-row routes (DECISIONS 60; `client.py:393-459`)

- `PATCH` answers the **contact's** serialized document; `DELETE` answers `null`.
- The row is looked up first, as the old route does (`client.py:409-411,424`): a row
  that does not exist, belongs to another contact or to the other table, or a contact
  that does not exist, is 404 "<DocType> <row> not found", not the base lookup. A refused
  edit is 403 "Not permitted to write Contact" (title "Not Permitted"); a refused delete
  is 404 "DocType <DocType> not found", never 403.
- Only the row's non-relation columns are written; `parent_contact`, `parenttype` and
  `parentfield` never are (`client.py:376-389,435`), and **neither are the four caches**
  (v2's invariant, `API_CONTRACT.md:239`; the old route writes them: a proposed sentence
  of PE-24's entry, "A child-row write never writes the underscore caches; the old route
  writes them"). A body of standard fields only is 417 "Cannot edit standard fields";
  `{}` answers 200 (`values and not editable`, `:432`); unknown keys are ignored. The
  contact is saved again, so the email check and the primary rules apply.

### Delete

- **Contact:** its Contact Email and Contact Phone rows cascade, the row signal stood
  down (`models.py:533-535,559-561`). An Address deleted under a contact leaves
  `Contact.address` empty (SET_NULL). The deal side (`CRMContacts` CASCADE,
  `CRMDeal.contact` SET_NULL) is SALES' (§9).
- **The Dynamic Link refusal** (`frappe_core/delete_doc.py:143-161`): a record that a
  Dynamic Link row names, such as a Contact or a CRM Organization in an Address's
  `links`, cannot be deleted: 417 `LinkExistsError`, the message ending "… is linked
  with Address <name> at Row: <idx>", followed by "You can disable this {doctype}
  instead of deleting it." for a doctype with `disabled` (`:178-179`).
- **CRM Organization:** also refused by `CRMDeal.organization` PROTECT once SALES
  exists (417 `LinkExistsError`); `CRMLead.organization` and `Contact.company_name` are
  text and not checked.
- **CRM Industry:** refused by its PROTECT foreign keys (Organization now; Lead and Deal
  with SALES; `test_envelope.py:165-185`).
- **Address:** a System Manager may delete an address an organization's text `address`
  still names; that organization's next save is then 417 "Could not find Address:
  <name>" until the field is cleared. Reproduced, as `backend/` (DECISIONS 58, flagged;
  `delete_doc.py:164-180` checks dynamic links only). Upstream refuses the delete.

### CRM Organization (milestone 5, §6 A)

The name is `organization_name`, verbatim. Every save checks the `currency` and
`address` Links. A full save (not one with `update_fields`) recomputes `exchange_rate`
only when the currency changed (a new record counts as changed) or no rate is held: 1
with no currency or the FCRM Settings currency (USD by default), else the provider's
rate, and a provider failure refuses the save (`core_sales.py:58-96,133-139`;
`test_crm_behaviour.py:252-259`). The list definition keeps `backend/`'s widths
(Organization `11rem`, Industry with no `options`; `core_sales.py:141-160`).

### Address

The four save steps (`models.py:1962-2030`): on create, an address with no links takes
the links of the Contact whose email is the owner's; links are deduplicated, the first
kept; each link's `link_title` is the linked document's name; a preferred flag
set here is cleared on every other enabled address linked to the same document. Search
hides disabled addresses (FINDINGS 45); list-shaped search filters follow ACCOUNTS'
User precedent (`AS_BUILT.md:503-504`).

### What `backend/` does not do (DECISIONS 58, flagged; followed here)

Upstream does each of these; `backend/` does not, and neither does `backend_v2`:

- saving a contact does not copy its `email_id` and `mobile_no` onto the deals where it
  is the primary contact (upstream's `crm.api.contact.validate` hook, `crm/hooks.py:161-163`);
- phone numbers are not validated (upstream validates `options: Phone` fields);
- `user` is not filled from a matching User's email (upstream's `set_user`).

### Reference rows

- **Salutation and Gender by data migration**, as `backend/` does
  (`frappe_platform/migrations/0014_seed_salutations_and_genders.py`, through
  `reference_data.py:34-60`): a save is refused without them (FINDINGS 66). Two writers
  share the lists in `contacts/reference_rows.py`: the migration, on the historical
  model, and `contacts/restore.py` for the `restore_defaults` command
  (`specs/CONFIGURATION.md` §10.3), so a deleted row comes back as the old
  `seed_defaults` brings it back (`crm_app/setup.py:563-564`;
  `test_salutation_gender.py:35-47`). `clear_dev_data` never removes them. The
  `seed_dev_data` step milestone 1 built is retired (`specs/CONFIGURATION.md` §10.8). The migration stamps the
  rows' `owner` and `modified_by` as
  Administrator, as v2's Currency rows; the old migration saves with no session
  (`frappe_platform/migrations/0014_seed_salutations_and_genders.py:19-23`), flagged to
  the owner. Parity otherwise, not the parked S20 question.
- **The 51 industries** are written by data migration `contacts/0004_industries` and put
  back by `restore_defaults` (`specs/CONFIGURATION.md` §10; the owner's S20 change of
  20 Nov 2026). The `seed_dev_data` step milestone 1 built is retired (`specs/CONFIGURATION.md` §10.8).

## 5. Acceptance

- pytest: §3's table with expected answers unchanged; new tests for each §4 item no old
  test covers, each shown failing without its protection.
- `docs/http/05_contacts_organizations.http`:
  - milestone 1: 0.15, 1.1, 8.12; milestone 3: 2.x, 0.5-0.9b, 7.4 (`get_doc_permissions`
    on a Contact), 8.2-8.6b, 8.13; milestone 4: 3.1-3.14; milestone 5: 0.10-0.11, 7.1,
    7.3, 7.5, 8.7-8.8; milestone 6a and 6b: 5.1, 5.3-5.4, 5.6-5.7, 8.14;
  - waiting for SALES: 0.2-0.4, 4.1-4.5 (`get_linked_deals`), 5.2, 5.5, 8.1, and the
    territory blocks 0.12-0.14, 1.2-1.4, 6.1-6.4, 8.9-8.11 (or §6 A);
  - waiting for §6 A: 1.5 and 6.3 (they name `territory`), and 7.2 and 7.6 (they use
    1.5's organization).
- `docs/http/02_resource_grammar.http`: 11.4 (the industry) at milestone 1; the
  Organization blocks (11.1-11.3, 11.5 and the rest but 10.14) at milestone 5.
- The body comparison over the same blocks.

## 6. Decisions

| # | Decision | Status |
|---|---|---|
| A | Organization's `territory` foreign key to SALES' CRM Territory | **parked for the owner** (DECISIONS 56): (a) move CRM Territory into CONTACTS (recommended by the reviewer and the supervisor; changes REBUILD_PLAN §4 and PORT_MAP); (b) build Organization without the column, SALES adds it; (c) a text column checked as a Link. Milestones run with Organization last and stop before it |
| B | `get_linked_deals` | decided by the supervisor, flagged for the owner: moves to SALES (§9); the PORT_MAP unit move is the owner's to approve |
| C | The child-row routes | proposed (§1), checked at the spec review |
| D | The four paths' route names | proposed (§1), checked at the spec review |
| E | Upstream's deal sync, phone validation, `set_user` | decided by the supervisor, flagged for the owner: follow `backend/` (§4) |
| F | Deleting an address an organization names | decided by the supervisor, flagged for the owner: reproduced (§4) |
| G | Rename for Address, CRM Industry, Salutation, Gender | decided by the supervisor, flagged for the owner: not opted in (**PE-24**, proposed) |
| H | Seeding | Salutation, Gender and the industries by data migration, put back by `restore_defaults` (owner's S20 change, 20 Nov 2026; `specs/CONFIGURATION.md` §10) |
| I | Deal contacts on contact delete | decided by the supervisor, flagged for the owner: SALES' (§9) |
| J | Users with no CRM role | decided by the supervisor, flagged for the owner: the old openness, stated (§4; DECISIONS 58) |
| K | "Remove contact" and deleting linked documents in `core` | decided by the supervisor, flagged for the owner: **PE-25**, **PE-26** (proposed), milestone 0 (DECISIONS 59) |
| L | Dynamic Link's `link_title` | decided (DECISIONS 65, correcting 60): the linked document's name, as `backend/` stores it |

PE entries for this unit (PE-22 and PE-23 are CONFIGURATION milestone 8's), neutral:

- **PE-24** (proposed): "rename is served for the resources that opt in; the old
  backend's rename call accepts any doctype" (`crm_app/api/client.py:462-495`). With a
  second sentence: "A child-row write never writes the underscore caches; the old route
  writes them." `SHARED_ACTIONS.md:54` is corrected in the same commit: CONTACTS opts
  Contact and CRM Organization in to rename.
- **PE-25** (proposed): "'Remove contact' clears the document's own contact field and
  its contacts table. The old backend clears whatever the document exposes under that
  name."
- **PE-26** (proposed): "the unlink action's delete and bulk delete's `delete_linked`
  delete only the linked documents the caller may delete. The old backend checks the
  write rule."
- **PE-12f** (approved, it only replaces a crash): a missing `field`, `value` or `txt` is
  417 with a fixed sentence (§4 Validation).

## 7. Carried from FOUNDATION

- Child-row writes for Contact Email and Contact Phone (owner, 12 Nov 2026): §1 and §4.
- `API_CONTRACT.md:262`'s exception for those two nested routes: the supervisor writes
  it with milestone 4 (FOUNDATION §6).

## 7a. Carried from CONFIGURATION

Contact's field metadata has Table rows for `email_ids` and `phone_nos`. The old Contact
declares `TABLE_FIELD_LABELS = {"email_ids": "Email IDs", "phone_nos": "Contact
Numbers"}` (`frappe_platform/models.py:365-368`), and the old model fallback turns each
into a `Table` row naming the child doctype (`frappe_core/field_meta.py:181-195`), so
Contact's `getdoctype` bundle is Contact, Contact Email, Contact Phone
(`tests/test_form_load.py:300-313`). Declare the attribute under the old name on
Contact; `configuration/field_meta.py`'s `_derive_from_model` reads the children from the
**routed ViewSet's `serializer_class.CHILD_TABLES`**, found through `routed_rule_map()`
as `configuration/metadata.py:42-46` does, and appends the Table rows after the concrete
fields in `TABLE_FIELD_LABELS` order. Address declares no labels, so it gets no `links`
Table row; `test_data_import_doctypes.py:233-262` pins Contact's lack of `links`.

## 8. Carried from SHARED_ACTIONS

Opt the resources below in to the `core/mixins/` actions (AS_BUILT §2), write each
generated route's row in `PORT_MAP.md`, and port the real-doctype cases SHARED_ACTIONS
left.

- **Contact (6a) and CRM Organization (6b):** rename, bulk delete, linked documents,
  bulk update, export (`export_field_info_for` exists, `AS_BUILT.md:181-182`). Contact
  sets `bulk_delete_remove_contact = True` (the old `remove_contact=(doctype ==
  "Contact")`, `crm_app/api/doc.py:703`).
- **Search, all six** (the Link control searches every Link the contact and
  organization layouts show, `frontend/src/components/Controls/Link.vue:132`): Contact,
  CRM Organization, Address, CRM Industry, Salutation, Gender. None of the six declares
  a `SEARCH_FIELD`, so search matches `name` only and the description is `""`
  (`client.py:701-733`); upstream's Contact `title_field` is not ported. Address
  overrides `search_filters` with the `link_doctype`/`link_name` rewrite
  (`client.py:64-81`) and hides disabled rows.
- **Not opted in to rename:** Address, CRM Industry, Salutation, Gender (PE-24).
- `test_rename.py`'s Contact and Organization cases (a renamed Contact keeps its email
  and phone rows and its deal links, FINDINGS 13) wait for SALES (§3); from
  `test_contact_delete_rule.py`, the Contact permission matrix including its bulk-delete
  door, at 6a.

## 9. Carried to SALES and ACTIVITIES

Written also as "Carried from CONTACTS" in `SALES.md` and `ACTIVITIES.md`.

- **To SALES: `get_linked_deals`** (`crm_app/api/contact.py:44-72`; `.http` `05`
  4.2-4.5). SALES keeps: the contact check first (a missing or refused contact is 403
  "Not permitted", not the base 404); the deals read through the caller's Deal row rule,
  stricter than upstream on purpose (`contact.py:48-53`); the fields `name, organization,
  currency, deal_value, status, email, mobile_no, deal_owner, modified`; list-shaped
  values (`deal_value` a number). SALES proposes its route.
- **To SALES: `CRMContacts.contact` CASCADE and `CRMDeal.contact` SET_NULL**
  (`core_sales.py:1120-1122`, `:836-842`): deleting a contact removes its rows on deals
  and clears `contact`, leaving the deal's `email` and `mobile_no`. Upstream refuses the
  delete (`check_if_doc_is_linked`); SALES records the difference. The screen clears
  first through `remove_linked_doc_reference(remove_contact=True)`, which nulls
  `contact` and deletes the deal's contact rows (`crm_app/api/doc.py:579-586`; with
  PE-25, only the deal's own `contacts` table).
- **To SALES:** `CRMDeal.organization` PROTECT and the Lead and Deal PROTECT foreign
  keys to CRM Industry.
- **To ACTIVITIES:** Dynamic Link for CRM Call Log's `links` (`models.py:1574-1575`);
  attach-on-save for `Contact.image` and `CRMOrganization.organization_logo`
  (`files.py:202-272`; `test_attach_on_save.py:44-47`).

## 10. Milestones, smallest first

| # | Holds | Can test |
|---|---|---|
| **0. Shared actions in `core`** | PE-25, PE-26, on `tests_support` | the new `tests_support` cases |
| **1. Reference data** | Salutation, Gender (models, data migration, seed step, rules, search); CRM Industry (open; search; the `seed_dev_data` step) | `test_salutation_gender.py` without the Contact and Lead parts; `test_seed_defaults.py:122-123,253`; `02` 11.4; `05` 0.15, 1.1, 8.12 |
| **2. Dynamic Link and Address** | the polymorphic child, Address naming, the four save steps, the delete rules, Country, the search override | `test_address.py:68-97`, `:253-261` |
| **3. Contact core** | the model in the old order and labels; Contact Email and Phone inline with `CHILD_FIELDS`; naming; the primary rules and the row signals; validation; the rules; §7a; search | §3's milestone 3 rows; `05` 2.x, 0.5-0.9b, 7.4, 8.2-8.6b, 8.13 |
| **4. Contact actions** | `create_new`, `set_as_primary` (403 before 404), `search_emails`, PE-12f, the child-row routes (the supervisor writes the `API_CONTRACT.md` exception) | `test_contact_numbers.py:25-150` without `:88-94`; `05` 3.1-3.14; new `search_emails` tests |
| **6a. Contact's shared actions** | rename (PE-24), bulk delete, linked documents, bulk update, export for Contact; after 0 and 4 | `05` 5.1, 5.3-5.4, 5.6-5.7, 8.14 (the Contact half); `test_contact_delete_rule.py:78-92` |
| 5. CRM Organization | **waits for §6 A**: the model, exchange rate, text Links, duplicate 409, `get_organizations` | §3's milestone 5 rows; `02` but 10.14; `05` 0.10-0.11, 7.1, 7.3, 7.5, 8.7-8.8 |
| 6b. Organization's shared actions | as 6a, for CRM Organization; after 5 | the Organization half of the same blocks |
| 7. List views | `ContactListView`, `OrganizationListView` with the old `default_list_data`; after CONFIGURATION milestone 8 (Contact's half after 3, Organization's after 5) | the CONTACTS definitions in `test_list_definitions.py`; `07` 5.7; `test_contact_numbers.py:88-94` |

Until §6 A is answered, milestones 0-4 and 6a are built, then the unit stops; Contact's
list view (7) waits for CONFIGURATION milestone 8.
