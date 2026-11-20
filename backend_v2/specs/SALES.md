# SALES — leads, deals, and everything that describes them

**Status: Provisional** — the scope is right, the details are guesses. **Rewrite against
`backend_v2/docs/AS_BUILT.md` before building.** Paths are from the repository root.

## 1. Scope

App `sales`. **The largest unit**, and the one the frontend's two main screens depend on.
The `PORT_MAP.md` rows under **SALES**:

- **Doctypes:** CRM Lead, CRM Deal; the reference data CRM Lead Status, CRM Deal Status,
  CRM Lead Source, CRM Lost Reason, CRM Communication Status, CRM Product (CRM Territory
  moved to CONTACTS, owner 20 Nov 2026, `CONTACTS.md` §11.1; Lead and Deal `territory`
  point at `contacts.CRMTerritory`); child tables CRM Products, CRM Contacts (a deal's contacts), CRM Status
  Change Log
- **Method paths (8):** `convert_to_deal`, `create_deal`, the deal-contact calls
  (`add_contact`, `remove_contact`, `set_primary_contact`, `get_deal_contacts`), and
  `crm.api.onboarding.get_first_lead` / `get_first_deal`
- **The org-hierarchy row rules** for leads and deals
- **The list definitions** for Lead and Deal that `get_data` reads
- **The calls on save** into SLA and the assignment engine from ASSIGNMENTS, so a lead
  or deal gets its deadline and its auto-assignment when it is saved

## 2. Depends on

ACCOUNTS (the sales hierarchy), CONFIGURATION (the FCRM Settings flags and the list
engine), SHARED_ACTIONS (the mixins), CONTACTS (organizations and contacts), ASSIGNMENTS (the
engine a lead or deal calls after owner sync), SLA (the deadline a lead or deal gets on save).

## 3. Read in `backend/` first

- `crm_app/models/core_sales.py` — Lead, Deal and their mixins (status lifecycle, owner
  assignment, the SLA fields); `models/taxonomy.py`
- `crm_app/permissions/org_hierarchy.py`, `permissions/tree.py`
- `crm_app/conversion.py`, `crm_app/api/lead.py`, `api/deal.py`, `api/onboarding.py`
- `specs/AS_BUILT.md` section 4 — the invariants, starting with the owner column
- `PORT_PLAN.md` section 4, trap 3 — `org_hierarchy` is row-level security
- `docs/FINDINGS.md` entries 7, 8, 9 and 14
- Tests to read and write again: `test_crm_models.py`, `test_crm_behaviour.py`,
  `test_conversion.py`, `test_lead_endpoints.py`, `test_status_lifecycle.py`,
  `test_owner_assignment.py`, `test_deal_forecasting.py` (`test_territory_tree.py` is
  CONTACTS'),
  `test_list_definitions.py`
- **Tests to port** (REBUILD_PLAN S14): `test_deal_endpoints.py`, `test_permissions.py`
  (the org-hierarchy matrix), the lead and deal cases of `test_hierarchy_access.py`
  (ACCOUNTS ports the hierarchy doctype's own), and this unit's routes in
  `test_phase3_endpoints.py`. The spec check confirms the list.

## 4. Must not be lost

- **`lead_owner` and `deal_owner` are the access columns, not `owner`**, and **nothing
  fills them in on the server**. A lead created without one is invisible to its creator.
  That is deliberate and pinned by tests (`specs/AS_BUILT.md` section 4).
- **Row rules apply to the list and to the object, through every door**, and read
  assignment from `ToDo` — never from the `_assign` cache. "Assigned" means excluding
  Cancelled for permissions, and excluding Closed and Cancelled for display.
- **Names:** `CRM-LEAD-.YYYY.-` and `CRM-DEAL-.YYYY.-` series; reference data keyed on its
  own field value, verbatim.
- **Status lifecycle:** the default status on create; a Lost status requires a lost
  reason; every status change is logged in the status change log.
- **Child rows are written before the parent's validation**, so the expected deal value
  and the primary contact are right in the same response (finding 8). **A child row's
  Link given by name is accepted** (finding 9) — every form sends it that way.
- **A deal contact's details are fetched from the linked Contact on every save.**
- **Conversion** creates the deal, and reuses or creates the contact and organization
  exactly as the old backend does. `create_deal` keeps the modal's contact on the deal.
- **The territory tree** is CONTACTS' (§11.1); a Lead or Deal filter with `descendants
  of` / `ancestors of` on `territory` resolves through it.
- **CRM Product is open to every CRM role**, reviewed and kept as upstream's role table
  grants (REBUILD_PLAN S21).

## 5. Acceptance

- pytest: every test in the port list passing with its expected answers unchanged, and
  new tests for each item in section 4 no old test covers. **The org-hierarchy rules get
  a matrix:** each role,
  on its own record, a subordinate's, a peer's, and an assigned one — through
  the lead and deal list, document and action routes, and the list view.
- `docs/http/03_leads.http`, `04_deals.http`, and `02_resource_grammar.http` in full; the
  blocks of each that wait on ACTIVITIES are named in the progress report. Lead and Deal
  opt in to the SHARED_ACTIONS mixins (bulk delete, bulk update, rename, search) and the
  CONFIGURATION list view, and this unit's gate proves those routes on leads and deals.
- The body diff over the same blocks — including a decimal in a document read and in a
  list row.

## 6. Open questions

None. It is the largest unit, so it is built as more briefs, not more agents.

## 7. Carried from FOUNDATION

- Port the CRM Deal cases from `backend/tests/test_child_rows.py` for products and
  contacts. FOUNDATION proved the shared child-table behavior on generic test resources;
  these original Deal cases still belong here.
- Port the Deal and assignment cases from
  `backend/tests/test_unrouted_doctypes.py`.

## 8. Carried from SHARED_ACTIONS

Opt the resources below in to the `core/mixins/` actions (AS_BUILT §2, "Opting a
resource in to a shared action"), write each generated route's row in `PORT_MAP.md`,
and port the real-doctype cases SHARED_ACTIONS left (its §3 table). Their generic
mechanism is tested on `tests_support`; the cases below prove it on real records.

- Lead and Deal opt in to bulk delete, linked documents, bulk update and search;
  export once CONFIGURATION supplies field labels (see CONFIGURATION).
- From `test_delete_dialog_links.py` / `test_unlink_linked_docs.py`: Deal comments
  and tasks, the Call Log/Lead/Deal cases (with ACTIVITIES), Contact-on-Deal unlink
  and Deal-Organization unlink/delete (with CONTACTS), write-denied Deal cases, and
  converted Lead-Deal unlink.
- The Deal linked-document title (`organization_id`, `backend/crm_app/api/doc.py:465-466`)
  through the model's `linked_document_title` hook.
- From `test_rename.py`: Lead unique columns and Deal links. From
  `test_bulk_actions.py`: the Lead bulk-update cases. From `test_export_query.py`:
  the Lead row-rule cases. From `test_reference_doctype_search.py`: the saved
  reference case (:56-82, with ACTIVITIES). From `test_conditions.py`: the Lead
  model-conversion case (:279-295).
- From `test_delete_link_check.py`: a hidden CRM Notification blocking a Deal
  (with NOTIFICATIONS).
- Lead keeps `lead_name` and Deal `organization` (their `SEARCH_FIELD`s) in their
  readable and filterable fields, or link search stops matching on them (A-12).

## 9. Carried from CONTACTS

Moved here by CONTACTS' spec rewrite (`temp` A-41, A-42; DECISIONS 57, flagged for the
owner). `CONTACTS.md` §9 has the detail.

- **`crm.api.contact.get_linked_deals`** (`backend/crm_app/api/contact.py:44-72`;
  `docs/http/05_contacts_organizations.http` 4.2-4.5): the contact check first (a
  missing or refused contact is 403 "Not permitted", not the base 404); the deals read
  through the caller's Deal row rule, stricter than upstream on purpose
  (`contact.py:48-53`); the fields `name, organization, currency, deal_value, status,
  email, mobile_no, deal_owner, modified`; list-shaped values. SALES proposes its route.
- **`CRMContacts.contact` CASCADE and `CRMDeal.contact` SET_NULL**
  (`core_sales.py:1120-1122`, `:836-842`): deleting a contact removes its rows on deals
  and clears `contact`, leaving the deal's `email` and `mobile_no`; upstream refuses the
  delete, and SALES records the difference.
- **`CRMDeal.organization` PROTECT**, and the Lead and Deal PROTECT foreign keys to CRM
  Industry.
- **Tests** `CONTACTS.md` §3 hands on: `test_rename.py` (all of it),
  `test_contact_rules.py:121-133`, `:136-147`, `:183-191`,
  `test_salutation_gender.py:76-87`, `:128-140`, and the Contact and Organization cases of
  `test_delete_dialog_links.py` and `test_unlink_linked_docs.py`.
