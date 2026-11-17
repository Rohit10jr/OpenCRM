# ACCOUNTS — users, roles, password reset, invitations, the sales hierarchy

**Status: Provisional** — the scope is right, the details are guesses. **Rewrite against
`backend_v2/docs/AS_BUILT.md` before building.** Paths are from the repository root.

## 1. Scope

App `accounts`, finishing what FOUNDATION started (the `User` model and login). The
`PORT_MAP.md` rows under **ACCOUNTS**:

- **Doctypes:** CRM Invitation, CRM Sales Hierarchy; the child table User Email (a user's
  email accounts) — plus `User`'s access rules, which FOUNDATION models but does not rule
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
- `docs/history/PHASE_8_AUTH_AND_DESK.md` — link lifetimes and what was matched exactly
- Tests to read and write again: `test_auth_pages.py`, `test_password_reset_keys.py`,
  `test_invitation_access.py`, `test_hierarchy_concurrency.py`
- **Tests to port** (REBUILD_PLAN S14): `test_user_access.py`, `test_disable_user.py`,
  `test_hierarchy_access.py`, `test_user_emails.py`, and this unit's routes in
  `test_phase3_endpoints.py`. The spec check confirms the list.
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
  blacklists every outstanding refresh token for the account and bumps its
  `token_version`, so access tokens already issued stop working too (built in FOUNDATION;
  KNOWN_ISSUES §6, fixed).
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

- pytest: every test in the port list passing with its expected answers unchanged, and new
  tests for each item in section 4 no old test covers — each shown failing without its
  protection.
- `docs/http/01_auth.http`, `09_users_and_invitations.http` (its non-ACCOUNTS blocks
  excepted until those units exist) and `99_lockout.http`, run last.
- An equivalent of `walk_auth_flow.py` against `backend_v2`.
- The body diff over the same blocks.

## 6. Open questions

None. (KNOWN_ISSUES §6, the logout window, was closed in `backend/` with `token_version`;
parity copies it.)

## 7. Carried from FOUNDATION

- Port the change-password, reset, and logout-all-sessions cases from
  `backend/tests/test_security.py` and `backend/tests/test_token_version.py`.
- **Store `User.reset_password_key` as `sha256(key)`**, as `backend/` does
  (`frappe_platform/models.py`, the reset flow in `crm_app/api/auth_pages.py`).
  FOUNDATION's credential guard (`backend_v2/tests/guards/test_model_fields.py`,
  `REVIEWED_HASHED_AT_REST`) already excuses the field from encryption on that ground, so
  the excuse is false until the reset flow hashes it. **Back the excuse with a storage
  test**: after a reset request, the stored column holds `sha256(key)`, never the key
  sent in the email (milestone-3 review, finding 7).
- Before any role-dependent body comparison, restore the old `opencrm` database's
  drifted suite-user roles: ada currently also has Sales Manager, grace has Sales User
  instead of Sales Manager, and alan has no role. **How (owner, 17 Nov 2026; DECISIONS
  19):** run `backend_v2`'s users seed step against `opencrm` once, before this unit's
  gate, with `DEV_DATA_ALLOWED` on for that run only; passwords from `backend_v2\.env`,
  never printed; it deletes nothing. Re-check the roles read-only afterwards
  (`backend/crm_app/management/commands/seed_e2e_users.py` resets only Administrator and
  ada, so it is not enough on its own).
- **Two `parity_diff.py` fixes before this unit's gate** (owner, 17 Nov 2026; from #66):
  run `99_lockout` against each backend in turn, not interleaved (alternating the two
  servers spreads the 11 failed logins past the 60 s window, so neither locks); and
  compare `Retry-After` within ±1 s, or by presence, not exactly (it counts down).
- **Development-data safety, both measures** (owner, 17 Nov 2026; DECISIONS 9): move
  `DEV_DATA_ALLOWED` from the settings files into `backend_v2\.env`, next to `DB_NAME`,
  default off (the flag belongs to the database it names, as Frappe's per-site
  `allow_tests`); and make the seed record every row it creates (e.g. a small
  `DevDataRecord`: model, primary key, step) so `clear_dev_data` deletes only those
  rows. Reason: a future setup wizard will load demo data on real sites, as Frappe CRM's
  `crm/demo/` does. Note for that wizard: its demo users are created only if absent
  (as `crm/demo/users.py:38`), unlike the dev seed, which resets passwords every run.
- **`User` as a resource** (owner, 17 Nov 2026; DECISIONS 18, `temp` A-13): route it on a
  `DocumentViewSet` subclass. `User` is not a `BaseDocument`, so give it the
  `BaseDocument` helpers and class settings (`get_doctype()`, `DOCTYPE`, …) **in any
  case** — without `get_doctype()` the old per-record permission check answered
  "allowed" for every User (`backend/frappe_core/permissions.py:34-43`, patched at
  `registry.py:198-205`) — and handle its missing `owner`/`modified_by` in one small,
  tested place in the base. Test that `User`'s object rule is actually applied (a Sales
  User editing another user's row is refused). **First, investigate** (supervisor, with
  Codex/agy) whether `User` should also get the standard fields (`owner`, `modified_by`,
  `idx`, `docstatus`, `_assign`…): compare Frappe's own User doctype with `backend/`'s
  and find every use. If the evidence supports adding them, a `User`-only parity
  exception is pre-approved by the owner, under the conditions in A-13.

## 8. Carried from SHARED_ACTIONS

Opt the resources below in to the `core/mixins/` actions (AS_BUILT §2, "Opting a
resource in to a shared action"), write each generated route's row in `PORT_MAP.md`,
and port the real-doctype cases SHARED_ACTIONS left (its §3 table). Their generic
mechanism is tested on `tests_support`; the cases below prove it on real records.

- User overrides the search mixin's `search_filters` hook with `ignore_user_type`
  and the enabled / Website User rules (`backend/crm_app/api/client.py:45-60`,
  FINDINGS 46).
- PE-6 (proposed): if approved, the bulk-delete worker also refuses a disabled
  requester; if rejected, the bulk-update worker stops refusing one.
