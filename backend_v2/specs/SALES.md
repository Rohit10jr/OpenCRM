# SALES — leads, deals, and everything that describes them

**Status: Provisional, 2026-09-16.** Written before FOUNDATION exists: the scope is right,
the details are guesses. **Rewrite against `backend_v2/docs/AS_BUILT.md` before running.**
Paths are from the repository root.

## 1. Scope

App `sales`. **The largest unit**, and the one the frontend's two main screens depend on.
The `PORT_MAP.md` rows under **SALES**:

- **Doctypes:** CRM Lead, CRM Deal; the reference data CRM Lead Status, CRM Deal Status,
  CRM Lead Source, CRM Lost Reason, CRM Territory (a tree), CRM Communication Status,
  CRM Product; child tables CRM Products, CRM Contacts (a deal's contacts), CRM Status
  Change Log
- **Method paths (8):** `convert_to_deal`, `create_deal`, the deal-contact calls
  (`add_contact`, `remove_contact`, `set_primary_contact`, `get_deal_contacts`), and
  `crm.api.onboarding.get_first_lead` / `get_first_deal`
- **The org-hierarchy row rules** for leads and deals
- **The list definitions** for Lead and Deal that `get_data` reads

It may run as more than one agent, split on files inside the app — models, row rules,
conversion, endpoints — with the shared files decided first.

## 2. Depends on

ACCOUNTS (the sales hierarchy), SETTINGS (the FCRM Settings flags), METADATA (the list
engine), CONTACTS (organizations and contacts).

## 3. Read in `backend/` first

- `crm_app/models/core_sales.py` — Lead, Deal and their mixins (status lifecycle, owner
  assignment, the SLA fields); `models/taxonomy.py`
- `crm_app/permissions/org_hierarchy.py`, `permissions/tree.py`
- `crm_app/conversion.py`, `crm_app/api/lead.py`, `api/deal.py`, `api/onboarding.py`
- `specs/AS_BUILT.md` section 4 — the invariants, starting with the owner column
- `docs/PORT_PLAN.md` section 4, trap 3 — `org_hierarchy` is row-level security
- `docs/FINDINGS.md` entries 7, 8, 9 and 14
- Tests: `test_crm_models.py`, `test_crm_behaviour.py`, `test_conversion.py`,
  `test_lead_endpoints.py`, `test_deal_endpoints.py`, `test_status_lifecycle.py`,
  `test_owner_assignment.py`, `test_territory_tree.py`, `test_hierarchy_access.py`,
  `test_permissions.py`, `test_deal_forecasting.py`, `test_list_definitions.py`

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
- **The territory tree** answers the `descendants of` / `ancestors of` operators.
- **CRM Product is open to every authenticated user today**, with a question still owed
  (`PARITY_EXCEPTIONS.md`).

## 5. Acceptance

- pytest for each item in section 4. **The org-hierarchy rules get a matrix:** each role,
  on its own record, a subordinate's, a peer's, and an assigned one — through
  the lead and deal list, document and action routes, and the list view.
- `docs/http/03_leads.http`, `04_deals.http`, and `02_resource_grammar.http` in full; the
  blocks of each that wait on ACTIVITIES or DOCUMENTS are named in the progress report.
- The body diff over the same blocks — including a decimal in a document read and in a
  list row.

## 6. Open questions

- O3 for CRM Product.
- How to split the unit between agents without two of them editing one file.
