# ACCOUNTS — users, roles, password reset, invitations, the sales hierarchy

**Status: Provisional, 2026-09-16.** Written before FOUNDATION exists: the scope is right,
the details are guesses. **Rewrite against `backend_v2/docs/AS_BUILT.md` before running.**
Paths are from the repository root.

## 1. Scope

App `accounts`, finishing what FOUNDATION started (the `User` model and login). The
`PORT_MAP.md` rows under **ACCOUNTS**:

- **Doctypes:** CRM Invitation, CRM Sales Hierarchy — plus `User`'s access rules, which
  FOUNDATION models but does not rule
- **Method paths (13):** the guest trio `frappe.core.doctype.user.user.reset_password`,
  `update_password` and `crm.api.accept_invitation`; `crm.api.invite_by_email`;
  `crm.api.user.*` (add existing users, change password, remove CRM roles, update role);
  `crm.api.session.get_users` and `get_user_info`; `crm.api.get_user_signature`;
  `crm.api.auth.oauth_providers`; `get_timezones`

## 2. Depends on

FOUNDATION.

## 3. Read in `backend/` first

- `crm_app/api/auth_pages.py` — reset, update and accept, with their rate limits and
  single-use keys
- `frappe_core/password_reset.py`, `crm_app/mail.py`, `crm_app/templates/emails/`
- `crm_app/api/user.py`, `api/session.py`, `api/misc.py` (invite, signature), `api/auth.py`,
  `api/desk.py` (timezones)
- `crm_app/permissions/platform_docs.py` (User), `permissions/tree.py` and the hierarchy
  rules, `models/metadata.py` (CRM Invitation, CRM Sales Hierarchy)
- `specs/SECURITY_MODEL.md` — sections `User`, `CRM Sales Hierarchy`, and "Phase 8 — the
  front door"
- `specs/PHASE_8_AUTH_AND_DESK.md` — link lifetimes and what was matched exactly
- Tests: `test_auth_pages.py`, `test_password_reset_keys.py`, `test_invitation_access.py`,
  `test_user_access.py`, `test_hierarchy_access.py`, `test_hierarchy_concurrency.py`
- `backend/scripts/walk_auth_flow.py` — the invite → accept → set password → log in →
  reset walk over real HTTP

## 4. Must not be lost

- **`User`:** anyone may read, except the built-in `Administrator` and `Guest`, which are
  hidden; a user may write **their own row only**; managers create and delete; `groups`,
  `is_superuser`, `is_staff` and both reset-key columns are never on the wire; `enabled`
  and `user_type` are readable and never writable.
- **Reset keys are hashed** (SHA-256), never encrypted, and consumed by one conditional
  update. `reset_password` never reveals whether an address exists and is rate-limited
  per address and per IP.
- **`update_password`'s old-password path goes through the login lockout.** Before the
  phase-8 review it was a password oracle beside a protected login.
- **`update_password` returns `login`'s exact shape**, and `logout_all_sessions`
  blacklists every outstanding refresh token for the account.
- **CRM Invitation is manager-only, and its `key` never reaches the wire** (upstream bug
  #21: upstream lets any Sales User read and redeem a pending key). Acceptance reads the
  key from the email link, and the link opens the frontend page, not a JSON response.
- **CRM Sales Hierarchy is writable by System Manager only** — not the manager pair.
  Writing the org tree is writing your own permissions: a Sales User once read a
  colleague's deals by adding themselves above that colleague.
- **`change_password` allows five attempts per five minutes.**
- **Two scheduled jobs:** `expire_invitations` daily, and `flush_expired_tokens`, which is
  not upstream's — it exists because JWT's blacklist grows with every refresh and nothing
  else removes the rows (`backend/config/celery.py`).

## 5. Acceptance

- pytest for every item in section 4, each shown failing without its protection.
- `docs/http/01_auth.http`, `09_users_and_invitations.http` (its non-ACCOUNTS blocks
  excepted until those units exist) and `99_lockout.http`, run last.
- An equivalent of `walk_auth_flow.py` against `backend_v2`.
- The body diff over the same blocks.

## 6. Open questions

- KNOWN_ISSUES §6: logout cannot revoke an access token already issued. Keep the
  five-minute window (parity), or close it with a token version on the user?
