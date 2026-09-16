# CONTACTS — contacts, their emails and phones, organizations

**Status: Provisional, 2026-09-16.** Written before FOUNDATION exists: the scope is right,
the details are guesses. **Rewrite against `backend_v2/docs/AS_BUILT.md` before running.**
Paths are from the repository root.

## 1. Scope

App `contacts`. The `PORT_MAP.md` rows under **CONTACTS**:

- **Doctypes:** Contact, CRM Organization, CRM Industry; child tables Contact Email,
  Contact Phone, Dynamic Link
- **Method paths (5):** `crm.api.contact.create_new`, `get_linked_deals`,
  `search_emails`, `set_as_primary`; `crm.api.session.get_organizations`

## 2. Depends on

ACCOUNTS.

## 3. Read in `backend/` first

- `frappe_platform/models.py` — Contact, its child tables, Dynamic Link, and the
  delete-time handling of its rows
- `crm_app/models/core_sales.py` (CRM Organization), `models/taxonomy.py` (CRM Industry)
- `crm_app/api/contact.py`, `api/session.py`
- `frappe_core/naming.py` — `append_number_if_name_exists`, which Contact naming calls
- `docs/FINDINGS.md` entries 10, 11, 12 and 23
- Tests: `test_contact_naming.py`, `test_contact_rules.py`, `test_platform_models.py`

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
- **Contact and CRM Organization are open to every authenticated user today**, each with
  a question still owed (`PARITY_EXCEPTIONS.md`, "Decisions owed").

## 5. Acceptance

- pytest for each item in section 4.
- `docs/http/05_contacts_organizations.http` — green once DOCUMENTS exists, because its
  rename blocks belong there; this unit's gate names the blocks it owns.
- `docs/http/02_resource_grammar.http`'s Organization and Industry blocks.
- The body diff over the same blocks.

## 6. Open questions

- O3 for Contact and CRM Organization: copy the open access, or decide now?
