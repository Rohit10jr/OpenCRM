# CONTACTS — contacts, their emails and phones, organizations

**Status: Provisional** — the scope is right, the details are guesses. **Rewrite against
`backend_v2/docs/AS_BUILT.md` before building.** Paths are from the repository root.

## 1. Scope

App `contacts`. The `PORT_MAP.md` rows under **CONTACTS**:

- **Doctypes:** Contact, CRM Organization, CRM Industry, Address, and the reference data
  Salutation and Gender; child tables Contact Email, Contact Phone, Dynamic Link
- **Method paths (5):** `crm.api.contact.create_new`, `get_linked_deals`,
  `search_emails`, `set_as_primary`; `crm.api.session.get_organizations`

## 2. Depends on

ACCOUNTS, and SHARED_ACTIONS (Contact and CRM Organization opt in to its rename mixin).

## 3. Read in `backend/` first

- `frappe_platform/models.py` — Contact, its child tables, Dynamic Link, and the
  delete-time handling of its rows
- `crm_app/models/core_sales.py` (CRM Organization), `models/taxonomy.py` (CRM Industry)
- `crm_app/api/contact.py`, `api/session.py`
- `frappe_core/naming.py` — `append_number_if_name_exists`, which Contact naming calls
- `docs/FINDINGS.md` entries 10, 11, 12 and 23
- Tests to read and write again: `test_contact_naming.py`, `test_platform_models.py`
- **Tests to port** (REBUILD_PLAN S14): `test_contact_rules.py`, `test_contact_numbers.py`,
  `test_contact_delete_rule.py`, `test_address.py`, `test_salutation_gender.py`, and this
  unit's routes in `test_phase3_endpoints.py`. The spec check confirms the list.

## 4. Must not be lost

- **A contact's name gets `-1`, `-2` … on collision**, counting from the highest
  existing suffix, the way upstream does.
- **Primary email and phone rules run on every save** (finding 10): a lone email row
  becomes primary, a stray `email_id` is cleared, two primaries are refused.
- **Email addresses are validated** on contact rows (finding 11).
- **`crm.api.contact.*` on a contact that does not exist answers 403
  `PermissionError`**, as upstream does, not 417 (finding 12).
- **A contact can be deleted whatever state its rows are in** (finding 23).
- **Names are verbatim and may contain slashes.** `R/GA` is a legal organization.
- **Contact now has a list rule and an object rule** in `backend/`; **CRM Organization is
  open to every CRM role**, reviewed and kept as upstream's role table grants (REBUILD_PLAN
  S21). Carry each over as `PORT_MAP.md` records it.

## 5. Acceptance

- pytest: every test in the port list passing with its expected answers unchanged, and
  new tests for each item in section 4 no old test covers.
- `docs/http/05_contacts_organizations.http`, including its rename blocks: this unit opts
  Contact and CRM Organization in to the rename mixin from SHARED_ACTIONS. The file's
  deal blocks wait on SALES; the gate names them.
- `docs/http/02_resource_grammar.http`'s Organization and Industry blocks.
- The body diff over the same blocks.

## 6. Open questions

None yet.
