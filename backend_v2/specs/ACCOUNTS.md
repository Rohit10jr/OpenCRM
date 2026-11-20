# ACCOUNTS — users, roles, password reset, invitations, the sales hierarchy

**Status: gate passed 18 Nov 2026** (milestones 1-3, PRs #74, #75, #76); **rewritten 18 Nov 2026** against `backend_v2/docs/AS_BUILT.md` and
the spec check (`tasks\ACCOUNTS_00_spec_check_verdict.md`, `temp` A-21); spec review
approved with fixes (A-22), made here. Paths are from the repository root; `backend/` is read at `main` `8f5ff1b`.

## 1. Scope

App `accounts`, finishing what FOUNDATION started (the `User` model, login, the lockout
and the limiter). Every row below is written into `PORT_MAP.md` (ACCOUNTS, and the
FOUNDATION `User` row, which this unit marks built).

**Resources (3)** — plain CRUD; none opts in to a shared action except `User` to search:

| DocType | New routes (each written out in its `PORT_MAP.md` row) | Old protection |
|---|---|---|
| User | `/api/v1/users/` (GET, POST), `users/value/` (GET), `users/search/` (GET, POST), `users/<name>/` (GET, PATCH, DELETE), `users/<name>/permissions/` (GET) | §4.1 |
| CRM Invitation | `/api/v1/invitations/` as `users/` without `search/` | §4.6 |
| CRM Sales Hierarchy | `/api/v1/sales-hierarchies/` as `users/` without `search/` | §4.7 |

The frontend uses only list, read, insert, `set_value` and delete on CRM Invitation
(`frontend/src/components/Settings/InviteUserPage.vue:198-205`, `:86`) and CRM Sales
Hierarchy (`Settings/Hierarchy/Hierarchy.vue:303-312,468,494`, `useRemoveNode.js:11,25,32,44`),
and reads and saves the session user's own `User` document (`ProfileSettings.vue:154`,
`PreferencesSettings.vue:106`, `UserEmailSettings.vue:136`, `EmailEditor.vue:241`).

**Method paths (13)** — REBUILD_PLAN S25; inputs keep their names, and only the user
moves into the URL for the two per-user role actions (`<name>` in the route map). For a
route served by `GET` alone, an old `POST` body moves into the query string — a reshaped
input, recorded in the route map:

| Old path | New route | Frontend caller |
|---|---|---|
| `frappe.core.doctype.user.user.reset_password` | `POST /api/v1/auth/reset-password/` | `pages/auth/ForgotPassword.vue:69-73` (`user`) |
| `frappe.core.doctype.user.user.update_password` | `POST /api/v1/auth/update-password/` | `pages/auth/UpdatePassword.vue:106-113` (`new_password`, `key` or `old_password`) |
| `crm.api.accept_invitation` | `POST /api/v1/auth/accept-invitation/` | `pages/auth/AcceptInvitation.vue:58-62` (`key`) |
| `crm.api.auth.oauth_providers` | `GET /api/v1/auth/oauth-providers/` | none; only `docs/http/13_bulk_and_misc.http` 5.1 |
| `crm.api.user.change_password` | `POST /api/v1/auth/change-password/` | `Modals/ChangePasswordModal.vue:88-95` |
| `crm.api.session.get_users` | `GET /api/v1/users/directory/` (`include_all`) | `stores/users.js:17-22,48-53` |
| `crm.api.session.get_user_info` | `GET` and `POST /api/v1/users/info/` (`users`; POST because 200 names do not fit a URL, S25 (4)) | `stores/users.js:99-102` |
| `crm.api.user.add_existing_users` | `POST /api/v1/users/add-existing/` (`users`, `role`) | `Modals/AddExistingUserModal.vue:98-103` |
| `crm.api.user.update_user_role` | `POST /api/v1/users/<name>/update-role/` (`new_role`) | `Settings/Users.vue:255` |
| `crm.api.user.remove_crm_roles_from_user` | `POST /api/v1/users/<name>/remove-crm-roles/` | `Settings/Users.vue:274` |
| `crm.api.get_user_signature` | `GET /api/v1/users/signature/` | `CommunicationArea.vue:156-160` |
| `frappe.core.doctype.user.user.get_timezones` | `GET /api/v1/users/timezones/` | `Settings/PreferencesSettings.vue:130-138` |
| `crm.api.invite_by_email` | `POST /api/v1/invitations/invite-by-email/` (`emails`, `role`) | `Settings/InviteUserPage.vue:175-182` |

Action routes are matched before `<name>` (S25 (8)). Nothing enforces that a user's name
is an email address (`accounts/models.py:45,98-101`): a user named `info`, `directory`,
`add-existing`, `signature`, `timezones`, `search` or `value` cannot be reached by its
document route — the known S25 (8) limit.

**Rename** (`frappe.client.rename_doc`) for `User` and CRM Invitation: served, as §10
says (owner, 20 Nov 2026). It was not served before.

**Moved out (decided A-21 D-D, flagged for the owner):** the **User Email** child table,
its Email Account hook and `test_user_emails.py` go to CONFIGURATION with Email Account
(§8.1). `crm.api.session.get_organizations` is CONTACTS'.

## 2. Depends on

FOUNDATION and SHARED_ACTIONS (search mixin). Pieces that need a later unit are built in
their minimum form here and carried (§8):

| Piece | Here | Carried to |
|---|---|---|
| User Email (`user_emails`) | a User document returns `user_emails: []` and drops an incoming `user_emails` | CONFIGURATION |
| `get_user_signature` | the user's own `email_signature` | CONFIGURATION: the default-outgoing Email Account fallback |
| Mail carrier | the settings-configured account in `core` (§4.8) | CONFIGURATION/ACTIVITIES: the Email Account lookup, tried **before** the config account |
| `get_users`' `is_telephony_agent` | always `false` | INTEGRATIONS: the CRM Telephony Agent lookup |
| `User.default_list_data` (the User list view) | not built | CONFIGURATION, with the list views |
| Hierarchy cases needing CRM Deal or FCRM Settings (`test_hierarchy_access.py:64`, the `hierarchy_on` fixture `:37-43`) | not ported | SALES (already claims them, `specs/SALES.md:43-44`) |

## 3. Read in `backend/` first

- `crm_app/api/auth_pages.py` (reset, update, accept), `frappe_core/password_reset.py`,
  `crm_app/mail.py`, `crm_app/templates/emails/*.txt`, `frappe_core/api/auth.py:issue_tokens`
- `crm_app/api/user.py`, `api/session.py`, `api/misc.py` (`invite_by_email`,
  `get_user_signature`), `api/auth.py`, `api/desk.py:get_timezones`,
  `api/client.py:45-60,683-708` (User search)
- `crm_app/permissions/platform_docs.py` — `User` `:47,90-136`, CRM Sales Hierarchy
  `:346-361`, CRM Invitation `:394-407`
- `frappe_platform/models.py` — `User` `:111-318` (fields, `SENSITIVE_FIELDS`,
  `READONLY_FIELDS`, `PRIVILEGED_WRITE_FIELDS`); `crm_app/models/metadata.py` (CRM
  Invitation, CRM Sales Hierarchy, `full_name` fetched from the user `:272`)
- `crm_app/tasks.py` (`expire_invitations`, `flush_expired_tokens`, the invitation email
  `:219-284`), `crm_app/async_signals.py:208-218`, `config/celery.py:40-56`,
  `crm_app/communication.py:375-440` (`find_outgoing_account`)
- `frappe_core/registry.py:198-205` and `crm_app/apps.py:20-34` (why `User` needs a
  doctype and its delete cascade), `frappe_core/views.py:233-238` (delete runs
  `check_dynamic_links`), `crm_app/api/doc.py:_link_sources`
- `config/settings/base.py:123-128,214-260,337`, `config/settings/test.py:20,22`
- `specs/SECURITY_MODEL.md` (`User` `:155`, CRM Sales Hierarchy `:219`, "Phase 8 — the
  front door" `:451`), `docs/history/PHASE_8_AUTH_AND_DESK.md`
- `backend/scripts/walk_auth_flow.py`

### Tests (REBUILD_PLAN S14: API tests are ported, not rewritten)

| File | Here | Notes |
|---|---|---|
| `test_user_access.py` | port | |
| `test_auth_pages.py` | port | rewrite only the direct-call race tests (`:446`, `:460`) and the email-link test (`:486`) |
| `test_invitation_access.py` | port | 8 of 9 cases call the resource |
| `test_password_reset_keys.py` | rewrite (internal) | except `:290`, `:311`, `:329`: port |
| `test_hierarchy_access.py` | port, except `:64` and the `hierarchy_on` cases | those are SALES' |
| `test_hierarchy_concurrency.py` | extend `backend_v2/core/tests/test_tree.py:232` | do not duplicate |
| `test_phase3_endpoints.py` | port `:494`, `:506`, `:515`, `:542`, `:1123`, `:1137`, `:1144`, `:1389` | |
| `test_token_version.py` | port `:64`, `:79`, `:114`, `:126`, `:278`, `:283`, `:289` | the other 9 are in v2; `:236` is ACTIVITIES' |
| `test_security.py` | port `:182`, `:190`, `:205` | |
| `test_desk_plumbing.py` | port `:108`, `:125` (`get_timezones`) | |
| `test_phase5_async.py` | port `:138-191`, `:368-428` (both jobs, the invitation email), except `:377` | `:377` creates an Email Account: CONFIGURATION |
| `test_platform_models.py` | port `:119` (needs the `User` route) | |
| `test_mail_config_account.py` | port the cases §4.8 lists | the rest carried (§4.8) |
| `test_disable_user.py` | — | all 9 cases already in `backend_v2/tests/test_disable_user.py` |
| `test_user_emails.py` | — | CONFIGURATION (§8.1) |

`test_language.py:65` and `test_onboarding_status.py` write `User` from CONFIGURATION:
they need this unit's route and are ported there.

## 4. Must not be lost

### 4.1 `User` as a resource

**Rules** (`platform_docs.py:90-136`, `ADMIN_ROLES = {"System Manager"}` at `:47`):
- List: everyone except the literal `Administrator` sees all rows but `Administrator` and
  `Guest` (`~Q(pk__in=STANDARD_USERS)`, `:97-100`).
- A **System Manager** may read, write, create and delete any non-built-in row. A Sales
  Manager may not (`docs/http/09_users_and_invitations.http` 2.12, 2.13).
- Anyone may read a non-built-in row and write **their own** row. Delete is never
  self-service.
- Nobody but the literal `Administrator` reads or writes `Administrator` or `Guest`,
  System Managers included (`:125-126`).

**Fields** (`frappe_platform/models.py:214-249`): never on the wire, not selectable, not
filterable — `password`, `last_login`, `groups`, `user_permissions`, `is_superuser`,
`is_staff`, `reset_password_key`, `last_reset_password_key_generated_on`,
`token_version`. Readable, never writable — `enabled`, `user_type`. `name` is read-only
on update (below). The User document always carries `user_emails` (§2).
`PRIVILEGED_WRITE_FIELDS = ("user_emails",)` (System Manager only) arrives with User
Email in CONFIGURATION. Field lists for search: `name` and `modified` readable,
filterable and sortable; `enabled` and `user_type` filterable
(`backend_v2/core/mixins/search.py:71-84`).

**How `User` fits the resource recipe (decided A-21 D-A; A-13 closed).** `User` stays an
`AbstractBaseUser` and gets **none** of the standard fields (`owner`, `modified_by`, `idx`,
`docstatus`, `_assign`, `_liked_by`, `_comments`, `_user_tags`): `backend/` returns none
of them (`frappe_platform/models.py:119-120,179-180`; `tests/test_platform_models.py:354`)
and no `frontend/src` file reads them on a User. No parity exception is used. Instead:
- `DOCTYPE = "User"`, so `core.doctypes.declared_doctypes()` and `model_for_doctype`
  know it (today `doctype_of` answers "User" only by its class-name fallback, and
  `DoctypeSearchView` omits it).
- **One save seam**, tested: the shared serializer calls `save(user=...)`
  (`core/serializers.py:150,154,170`); `User.save` must accept and ignore the actor (today
  a `TypeError`, a 500). A create **forces an insert**: a name that differs only by case
  must raise the duplicate refusal, never update the existing row
  (`core/serializers.py:149`, AS_BUILT §4).
- **Delete** keeps the old path: `check_dynamic_links` runs (`backend/frappe_core/
  views.py:236`; v2's `core/delete.py:44,98` returns early without `DOCTYPE`), and the
  reference/polymorphic-child cascade is connected for `User` as for every registered
  non-child doctype (`User` is registered, `frappe_platform/models.py:110`, and
  `backend/crm_app/apps.py:30-34` connects every registered non-child doctype;
  `registry.py:198-205` only lets the cleanup ask its doctype). v2's
  `core/children.py:393-409` skips non-`BaseDocument` models — include `User`. The
  wiring has nothing to clean up until ACTIVITIES (v2's cleanup table holds only
  `Version`, `core/children.py:326-328`, and `User` writes none); ACTIVITIES proves it
  (§8).
- **Link scan:** in `backend/`, every FK to `User` (`owner`, `modified_by`, …) is a link
  source for target "User" (`crm_app/api/doc.py:_link_sources`, via the registry patch).
  `User` does not opt in to linked documents or bulk delete, so the scan never runs with
  `User` as its target. `User` has no outgoing FK, so it is never a link source itself.
- **Guards cover `User`:** served-or-withheld (`tests/guards/test_resource_access.py:
  149-188`) skips non-`BaseDocument` models today; extend it to `User`. The write-stamp guard
  (`test_write_stamps.py`) does not apply (no stamps). Each new direct `User` or
  invitation read gets a reviewed entry in `test_direct_model_access.py`.
- **Opt-ins:** search (§4.3) and rename (§10). Never export (it always fetches `owner`,
  `core/mixins/export.py:118`), bulk update or bulk delete.
- A test proves the object rule runs: a Sales User's PATCH of another user's row is
  refused.

**`name` cannot be changed through the User resource (decided A-21 D-B; PE-7
proposed).** On PATCH a sent `name` is **ignored**, as other read-only fields are (the
profile screens may post the unchanged name back); the old backend accepts it. Frappe v15
refuses it too (`frappe/model/document.py:850-859`). Tested. A User is renamed by its
own route (§10).

### 4.2 Roles and the user directory

- **`get_users`** (`session.py:62-135`): a CRM role is required, else 403 "You are not
  permitted to access CRM resources."; answers the pair `[users, crm_users]`;
  `include_all` honoured only for a System Manager (a string `"1"`/`"true"`/`"yes"` is
  true); enabled users only, ordered by `full_name`; nine fields (`session.py:14-24`)
  plus `roles` (with "All" and "Guest" appended), `role` (first of System Manager, Sales
  Manager, Sales User, Guest), `is_telephony_agent`, and `session_user: true` on the
  caller's row; `Administrator` is hard-coded as `["System Manager", "All"]` /
  "System Manager". Without `include_all` both halves are the CRM users.
- **`get_user_info`** (`:138-155`): CRM role required; at most 200 names; five fields
  (`name`, `email`, `full_name`, `user_image`, `user_type`); **no** enabled or built-in
  filter (parity: it returns Administrator, Guest and disabled users); empty input → `[]`.
- **`add_existing_users`, `update_user_role`, `remove_crm_roles_from_user`**
  (`user.py:110-217`): System Manager or Sales Manager (`Administrator` always), else 403
  "Not permitted". Refusals, verbatim: "Only System Managers can assign the System
  Manager role", "Only System Managers can assign the Sales Manager role", "Only System
  Managers can modify other System Managers" (403); "Cannot assign this role", "User
  {user} not found", "Remove this user from the sales hierarchy before changing their
  role to Sales User" (417) — the last when the user has reports or is a tree root.
  Setting System Manager grants all three roles; Sales Manager grants two and removes
  System Manager; Sales User removes both. `remove_crm_roles_from_user` refuses "You
  cannot remove yourself." (403), removes the CRM roles (System Manager only by a System
  Manager), **deletes the user's hierarchy node with no reports guard**, and answers
  "User {user} has been removed from CRM roles.". `add_existing_users` accepts `users` as
  a JSON string or a single name; `role` defaults to "Sales User" (`user.py:111`).
- **No object rule on the two per-user actions** (A-22): the old code checks only the
  manager pair (`user.py:139,192`), so a Sales Manager changes another user's role
  (`09` 3.2), which `User`'s write rule would refuse. `update-role` and
  `remove-crm-roles` therefore load the user **directly** by the URL's name (a reviewed
  entry in `test_direct_model_access.py`), never through the ViewSet's object lookup, and
  keep the old check order: manager pair, then the role value ("Cannot assign this role"),
  then the user — a missing user is 417 "User {user} not found" (`:142-147`, `09` 3.16),
  not the base 404/403.

### 4.3 Search

`User` overrides the search mixin's `search_filters` hook with `ignore_user_type` and the
enabled / Website User rules (`backend/crm_app/api/client.py:45-60`, FINDINGS 46). Old
`User` has no `SEARCH_FIELD` (`client.py:701-708`), so search matches the name only.

### 4.4 Passwords, reset and revocation

- **Reset keys are SHA-256 hashed**, never encrypted, and consumed by one conditional
  update of both columns (`password_reset.py:81-109,153-176`). A storage test proves the
  column holds `sha256(key)`, never the emailed key (FOUNDATION milestone-3 finding 7;
  `tests/guards/test_model_fields.py` `REVIEWED_HASHED_AT_REST`).
- Reset key lifetime: `PASSWORD_RESET_LINK_EXPIRY_MINUTES`, 60; zero or junk means 60
  (`password_reset.py:66-78`). After accepting an invitation a new user gets an ordinary
  one-hour reset key.
- `reset_password` answers one sentence on every branch, never revealing whether the
  address exists (`auth_pages.py:36-39,96`).
- `update_password`: the old-password path goes through the login lockout
  (`:250-259`); it answers `login`'s exact shape, 401 and 410 for its two failures
  (`:441-455`; the frontend reads 410 as a dead link). The account comes from `usr`,
  `user` or the token's user (`:177-190`); the old-password path lowercases the name
  before `authenticate` (`:190,253`) — copied as is. Refusals, verbatim: "New password is
  required" (`:133`); "Password size exceeded the maximum allowed size." above 512
  characters (`:42,136`); "Provide either a reset key or your current password" (`:147`);
  401 "Invalid password" (`:248,257`); the two 410 sentences (`password_reset.py:56-57`).
- **Revocation (finding 11):** `token_version` changes in three places — a save while
  disabled (built in FOUNDATION), a rename (§10, a fresh random value), and
  `update_password` with a truthy
  `logout_all_sessions`, which also blacklists every outstanding refresh token
  (`:275-305`). The bump runs **before** the new pair is issued (`:169-174`), so the
  returned tokens are valid. `change_password` and a plain reset revoke nothing
  (`backend/tests/test_token_version.py:114`).
- **`change_password`** (`user.py:54-107`): its Guest branch (401 "You must be logged in
  to change your password") is unreachable — the route is not guest, so an anonymous
  caller is refused before the view; not tested. The account lockout (`LoginAttemptTracker(user)`), "Too many failed
  attempts. Please try again after some time."; "New password cannot be the same as
  current password. Please choose a different password."; "Incorrect current password.
  Please try again." (counts a failure); weak password → "Password is too weak. " plus
  Django's validator messages; success → "Password Updated Successfully".

### 4.5 Rate limits

All refuse with 429 "You hit the rate limit because of too many requests. Please try
after sometime." and send **no** `Retry-After` header (neither limiter is a DRF throttle).

| Endpoint | Limit | Bucket | Source |
|---|---|---|---|
| `reset_password` | 10 per hour | (IP, lowercased `user` input) | `auth_pages.py:50` |
| `update_password` | 20 per hour | IP alone with a `key`; (IP, account) on the old-password path | `:104`, `:193-217` |
| `accept_invitation` | 10 per hour | IP | `:319` |
| `change_password` | 5 per 300 s | IP, successes counted too | `user.py:55` |

v2's `core.security.rate_limit` hands a callable key only the merged inputs
(`core/security.py:121-129`); it must also see the request's authenticated user for
`update_password`'s token-user bucket (§7).

### 4.6 CRM Invitation

- System Manager and Sales Manager list, read and delete; everyone else gets a deny-all
  list (`platform_docs.py:394-407`). `key` is never on the wire.
- **PE-8 (proposed; A-24):** CRM Invitation cannot be created or changed through its
  resource, for any caller; invitations are created by `invite_by_email` alone. The
  routes stay served and always refuse (403).
- The key is minted **only** in `invite_by_email` (`misc.py:115-117`); `accept_invitation`
  refuses an empty key (`auth_pages.py:340-344`). **The model must not generate a key.**
- `invite_by_email` (`misc.py:75-123`): the manager pair first, 403 "Not permitted"
  (`:86`, `09` 4.1); then the role checks — "You are not allowed to invite
  System Managers", "You are not allowed to invite Sales Managers", "Cannot invite for this
  role" (403); then `null` for an empty or wholly invalid `emails`; existing members by
  email and existing invitations **of any status** (an expired or accepted one blocks a
  re-invite) are skipped; answers `{"existing_members", "existing_invites", "to_invite"}`.
  `to_invite` comes from a set, so its order is not stable: the body diff compares it as
  a set.
- **The invitation email is sent on any creation of an invitation row** (old: `post_save`
  and a Celery task, `async_signals.py:208-218`, `tasks.py:219-284`). In v2 **the CRM
  Invitation model's save, on insert, queues the email task after commit** (A-22;
  REBUILD_PLAN §5: no signal where a direct call reaches) — covering `invite_by_email` and
  the walk script's model create; a rolled-back create sends nothing. Subject "You have been invited to
  join Open CRM"; link `{FRONTEND_ORIGIN}/crm/accept-invitation?key=<key>`.
- `accept_invitation`: every refusal is 417 "Invalid or expired key"
  (`auth_pages.py:344,348,386,396`). It claims the row with one conditional update (`:392-396`),
  grants the role plus its implied roles (`:311-315`), never removes a role, and reuses an
  existing account (`:409-421`). New user → `{"status": "set_password", "redirect_to":
  <frontend update-password link with a reset key>}`; existing user →
  `{"status": "logged_in", "redirect_to": "/crm", …login shape}` (`:353-367`).
- Lifetime 3 days (`tasks.py:23`), enforced only by the daily sweep on `creation`.

### 4.7 CRM Sales Hierarchy

- Reads are open to any authenticated caller; **writes are System Manager only**
  (`platform_docs.py:346-361`) — not the manager pair. Writing the org tree is writing
  your own permissions: a Sales User once read a colleague's deals by adding themselves
  above that colleague.
- A `TreeDocument` (`core.models`), nested set kept by the old rebuild. `full_name` is
  fetched from the user (`metadata.py:272`).
- PE-4 (approved): a parent loop is refused with "Item cannot be added to its own
  descendants"; a hierarchy-specific test proves it on this model.

### 4.8 Mail

- Reset subject "Reset your Open CRM password", link `{FRONTEND_ORIGIN}/crm/update-password?key=<key>`;
  bodies from `crm_app/templates/emails/*.txt` (`mail.py:82-96`).
- **The minimum carrier, in `core`:** the settings-configured outgoing account — step 4
  of `find_outgoing_account` (`communication.py:400-440`), `None` unless `EMAIL_HOST` is
  set (`:375-377`); with none, sending raises "Please setup default outgoing Email
  Account…" (`mail.py:66-70`). The old config account is an **unsaved `EmailAccount`**
  built from the `EMAIL_*` settings (`communication.py:372-398`) and marked
  `from_site_config`, which `open_backend` reads to use Django's own connection
  (`:617`). v2 has no Email Account yet, so the carrier in `core` returns a small object
  with the account name, the sender address, the SMTP settings and that flag; CONFIGURATION
  replaces it with the unsaved Email Account (§8).
- Ported here from `test_mail_config_account.py`: `:140`, `:147` (without the class
  check), `:179`, `:188`, `:221`, `:314`, `:331`, `:341`, `:367`, `:378`. Carried:
  `:262` and `test_phase5_async.py:377` to CONFIGURATION (a saved Email Account);
  `:233`, `:250`, `:282` to ACTIVITIES (a lead or a Communication).

### 4.9 Scheduled jobs

`expire_invitations` daily at 00:00 and `flush_expired_tokens` daily at 01:00
(`config/celery.py:40-56`). `flush_expired_tokens` is not upstream's: SimpleJWT's blacklist
grows with every refresh and nothing else removes the rows. v2's `accounts/tasks.py` has
an empty schedule today.

### 4.10 Small routes

- `get_timezones` → `{"timezones": [...]}`, a flat list, cached for the process
  (`desk.py:get_timezones`).
- `oauth_providers` → `[]`, guest (no Social Login Key model); no frontend caller.
- `get_user_signature` → `'<br><p class="signature">{signature}</p>'` or `null`
  (`misc.py:42-72`), from the user's own `email_signature` here (§2).

## 5. Acceptance

- pytest: every case in §3's table passing with its expected answers unchanged, and new
  tests for each §4 item no old test covers, each shown failing without its protection.
- `.http` blocks (finding 16 of the spec check):
  - **This unit's:** `01_auth` 2.12, 3.1-3.3, 4.1-4.11, 5.1-5.2; `09_users_and_invitations`
    0.4-0.7, 1.1-1.6, 2.1-2.13, 3.1-3.16, 4.1-4.11, 5.1-5.3, 5.5, 6.1-6.4, 8.2-8.4;
    `99_lockout` 3.1; `00_walkthrough` 4.8; `11_permissions_matrix` 0.6-0.9, 5.1-5.8,
    6.12, 7.1-7.2; `13_bulk_and_misc` 5.1, 9.3. The 17 `User` blocks in
    `backend_v2/http/09_users_and_invitations.http` tagged `# @waiting FOUNDATION`
    (0.4, 2.1-2.6, 2.8-2.13, 6.2, 6.4, 8.3, 8.4) become runnable when the FOUNDATION `User`
    row is marked built with its New route (`scripts/build_http_suite.py:338-340`).
    `01_auth` 5.3 (a GET on `accept_invitation`) becomes a negative case: the new route is
    POST only.
  - **Already pass from FOUNDATION:** `01_auth` 1.1-2.11a; `09` 0.1-0.3, 5.4; `99` 1.1-2.2.
  - **Wait for later units:** `09` 0.8-0.9, 7.1, 8.1 (SALES); 6.5 (CONFIGURATION); 6.6,
    7.2-7.6 (ACTIVITIES).
- `99_lockout.http` runs last, each backend in turn (§7).
- The body diff over the same blocks, after the `opencrm` roles are reset (§7).
- An equivalent of `walk_auth_flow.py` (invite → accept → set password → log in → reset),
  run as the old one is: Django's test client and `mail.outbox` on a test database
  (`:26-33,194-199`). The invitation is made the only way one can be since PE-8, a System
  Manager's `invitations/invite-by-email/`, and the key is read from the outbox
  (`backend_v2/scripts/walk_auth_flow.py`, run by `tests/test_walk_auth_flow.py`).

## 6. Decided in the rewrite (checked at the spec review)

1. **Routes:** §1's table, under S25.
2. **Shared actions:** `User` opts in to search only; CRM Invitation and CRM Sales
   Hierarchy to none (the frontend uses plain CRUD, §1).
3. **`User.default_list_data`** (the User list view) goes to CONFIGURATION with the list
   views; **`test_mail_config_account.py`** stays here with the carrier.
4. **PE-4 on the hierarchy:** a hierarchy-specific loop test, yes.
5. **`get_user_info`** keeps returning built-in and disabled users (parity).
6. **PE-6's ACCOUNTS test** disables the user through the model: no route writes
   `enabled` (`READONLY_FIELDS`, `frappe_platform/models.py:241`); disabling is Django
   admin's.
7. **Milestones:** three (§9).

8. **CRM Invitation's shared actions:** none; and create and write are refused through
   the resource for every caller (PE-8, A-24).

Open for the owner: PE-7 (§4.1) and PE-8 (§4.6), recorded `proposed`. Neither parity
version is built: D-B and A-24 are decisions to build the change and flag it.

## 7. Carried from FOUNDATION, and tooling

- **Settings** (spec check finding 6), from the environment as `backend/config/settings/`
  does: `AUTH_PASSWORD_VALIDATORS` (old `base.py:123-128`; without them `validate_password`
  accepts anything), `PASSWORD_RESET_LINK_EXPIRY_MINUTES` (`:337`), the `EMAIL_*` settings
  (`:214-260`) (`FRONTEND_ORIGIN` exists already, `backend_v2/config/settings/base.py:132`); in the test settings
  `CELERY_TASK_ALWAYS_EAGER` and the locmem mail backend (old `test.py:20,22`). Never
  print `.env`.
- **The `.http` generator** (`backend_v2/scripts/build_http_suite.py`, milestone 1): it
  pastes a new route literally (`:425`) and marks a block `# @negative` when the old verb
  is not among the new route's (`:418-425`). Teach it, with
  `tests/test_http_suite_builder.py` cases, to (a) move an old `POST` body into the query
  string for a route served by `GET` alone (`09` 1.1-1.4, 2.7, 3.3, 3.8, 3.15, 6.1, 6.3
  POST to `get_users` and `get_user_signature`), and (b) move a named body key into the
  URL's `<name>` (the per-user role actions); and remove the hard-coded `01_auth` runnable
  set and `99_lockout` 3.1 waiting tag (`:461-486`) so the route map decides.
- **`rate_limit` sees the user:** extend `core.security.rate_limit` so a callable key
  receives the request's authenticated user (one small commit, tested).
- Port the change-password, reset and logout-all-sessions cases of `test_security.py` and
  `test_token_version.py` (§3).
- **Reset-key hashing** with its storage test (§4.4).
- **Development-data safety, both measures** (owner, 17 Nov 2026; DECISIONS 9):
  `DEV_DATA_ALLOWED` moves from `config/settings/base.py:17`, `local.py:6` and `test.py:10`
  into `backend_v2\.env` next to `DB_NAME`, default off, read by the settings; the test
  settings keep it on for the test database (the flag belongs to the database it names,
  and the test database is always a scratch one); `tests/test_dev_data_commands.py:50`
  keeps overriding it. And the seed records every row it creates in a `DevDataRecord`
  (model, primary key, step) owned by `core` (where `core/dev_data.py` runs the steps), so
  `clear_dev_data` deletes only recorded rows — today `clear_users` deletes ada, grace and
  alan by name whether or not the seed created them (`accounts/dev_data.py:86-93`). Note
  for the future setup wizard: its demo users are created only if absent
  (`crm/demo/users.py:38`).
- **`parity_diff.py`: each backend in turn** for `99_lockout` (`backend_v2/scripts/
  parity_diff.py:150-205`, `run_pair`): alternating the two servers spreads the 11 failed
  logins past the 60 s window, so neither locks. The `Retry-After` half of A-18 is
  dropped (A-21 D-E): nothing sends the header.
- **The `opencrm` role reset (A-21 D-C, replaces A-14's mechanism; flagged):** `backend_v2`'s
  seed cannot run against `opencrm` (its tables are `"tabUser"`/`"tabUser_groups"`, v2's
  `accounts_user`). Before the gate: (1) extend the read-only
  `backend_v2/scripts/check_opencrm_dev_data.sql` to compare, for the four suite users,
  `first_name`, `last_name`, `full_name`, `user_image`, `language`, `user_type`,
  `enabled`, `time_zone`, `mobile_no`, `phone`, `email_signature` with
  `accounts/dev_data.py` `SEEDED_USERS`, run it read-only and post the result; (2) a
  one-off script under `backend/`'s own settings and models sets **only** the role
  memberships of ada, grace and alan to `SEEDED_USERS`' (`groups.set(...)`, no `save()`,
  no password, no other row). The owner approved resetting those roles once before the
  gate (DECISIONS 19); this script is narrower than what they approved, so it runs after
  (1)'s result and the script are posted and the supervisor answers (A-22). If (1) shows
  profile columns differ, that part waits for the owner.
- **Correct FOUNDATION's wording:** `specs/FOUNDATION.md` and `AS_BUILT.md` give ACCOUNTS
  "the password-change and password-reset revocation triggers"; there is one trigger
  (§4.4), fixed in this rewrite's commit.

## 8. Carried from SHARED_ACTIONS, and handed on

- User's `search_filters` override (§4.3).
- PE-6 (approved; built in #73): both queued bulk workers refuse a missing or disabled
  requester. ACCOUNTS adds no route that disables a user (§6.6), so nothing more is
  needed here.

**Handed on** (each written into the receiving spec in this rewrite's commit):
1. CONFIGURATION: User Email (model, Email Account hook, `PRIVILEGED_WRITE_FIELDS`,
   `test_user_emails.py`); the signature's Email Account fallback; `User.default_list_data`;
   the Email Account step of the outgoing-account lookup, before the config account, and
   the carrier's object replaced by the unsaved Email Account;
   `test_mail_config_account.py:262`, `test_phase5_async.py:377`.
2. ACTIVITIES: the same lookup order wherever mail is sent from a document;
   `test_mail_config_account.py:233`, `:250`, `:282`; proving the delete cascade on a
   deleted `User` once File, Comment and ToDo join the cleanup table.
3. INTEGRATIONS: `get_users`' `is_telephony_agent` from CRM Telephony Agent.

## 9. Milestones

1. **`rebuild/accounts-1` — users, roles and the hierarchy:** settings; `rate_limit`
   with the user; the `User` resource (DOCTYPE, seam, forced insert, read-only `name`,
   `user_emails: []`, delete path, guards, search); CRM Sales Hierarchy; `get_users`,
   `get_user_info`; the three role actions; `change_password`; `get_timezones`,
   `oauth_providers`, `get_user_signature`; the `.http` generator changes (§7); this
   milestone's PORT_MAP rows marked built. Tests placed here besides §3's: the PE-4
   hierarchy test, the PE-7 test, `test_token_version.py:278`, `:283`, `:289`.
2. **`rebuild/accounts-2` — the front door and invitations:** the mail carrier; reset-key
   hashing and its storage test; `reset_password`, `update_password`,
   `accept_invitation`; CRM Invitation, `invite_by_email` and its email task; both
   scheduled jobs. Tests placed here: `test_token_version.py:64`, `:79`, `:114`, `:126`.
3. **`rebuild/accounts-3` — tooling and the gate:** dev-data safety; `parity_diff.py`;
   the `opencrm` check and role script; the `walk_auth_flow.py` equivalent; the `.http`
   and body-diff acceptance.

## 10. Rename for User and CRM Invitation (addendum, 20 Nov 2026)

Owner's decision (`temp` A-48 3c, A-51); written from the spec check and review
(`temp` A-53, A-54). A built-later addition to milestone-built ACCOUNTS: it has its own
brief. It changes these passages, which are corrected in the same commits as the code:
this file's §1 (rename not served), §4.1 (opt-ins; PE-7's last sentence), §4.4
(revocation); `docs/AS_BUILT.md:64-70` (a missing claim counts as 0; the two triggers),
`:97-99` (User never renames), `:590-594` (the mixin's order, which gains two hooks);
`specs/FOUNDATION.md:108-112` (`token_version`); `docs/PORT_MAP.md:235`
(`rename_doc`'s row); PE-24 (§10.6).

### 10.1 Route and who may call it

`POST /api/v1/users/<name>/rename/` (old `frappe.client.rename_doc` with `doctype=User`),
through `RenameMixin` and `core.rename.rename_document`. No merge.

**System Manager or Administrator only**, not the User write rule, which also lets a user
write their own row. `RenameMixin` asks `has_object_rule(user, doc, "write")` today; it
gains a `rename_rule` hook defaulting to that, which `UserViewSet` overrides (a change in
`core`). **A System Manager may rename their own account**, as upstream allows: the answer
is 200 with the new name; the caller's next call with their old token is 401, and their
refresh token is blacklisted (§10.4). *[Marked for the owner: the supervisor has asked.]*

### 10.2 Normalising, and the refusals in upstream's order

`RenameMixin` gains a `before_rename(instance, old, new)` hook, called right after the
record is found, which **returns the name every later check and `rename_document` use**
(upstream `rename_doc.py:151-152` lets `before_rename` replace `new` the same way). User's
hook strips and lowercases the new name, as `User.save` does
(`accounts/models.py:119-122`); `rename_document` writes with `bulk_create`
(`core/rename.py:110`), which skips `save()`. Messages print the name **as normalised**,
except row 3, which names the old record.

Upstream order: the document is fetched (`rename_doc.py:150`), `before_rename` runs
(`:151`; User's checks, `frappe/core/doctype/user/user.py:563-581`, v15), then
`validate_rename` (`:153`): exists, same name, taken (`:348-365`), then permission
(`:371-372`).

| # | Check | Answer, all **417** |
|---|---|---|
| 1 | `merge` sent | `Merging documents is not supported` (mixin, unchanged) |
| 2 | no such record | `Can't rename X to Y because X doesn't exist.` (mixin) |
| 3 | hook: the old name is Administrator or Guest | `User X cannot be renamed` |
| 4 | hook: the new name is not exactly one plain address — `validate_email_address(new)` (`core/models.py:23-44`) raises, or returns anything but the normalised name (so a list `a@x.com, b@x.com` and a display name `Bob <b@x.com>` are refused) | `Y is not a valid Email Address`, the validator's sentence |
| 5 | same name, after normalising | `No changes made because old and new name are the same.` |
| 6 | name taken: for User, through a `name_taken(new, old)` hook, **case-insensitive and excluding `pk=old`**, so a legacy mixed-case row can fix its own case | `Another User with name Y exists, select another name` |
| 7 | the rename rule (§10.1) | `You need write permission on User X to rename` |
| 8 | `validate_name` | as today; for User it cannot fire after row 4, since an address has none of the forbidden characters |

**Who sees what for the built-ins:** anyone — Administrator and a System Manager
included — gets row 3's sentence, because row 3 comes before the rule. That is
upstream's order. Rows 3-6 answer before the rule, in upstream's order.

### 10.3 One transaction

`rename_document` gains an `on_renamed(old, new)` hook, called inside its atomic block
after the copy and the repointing, before the old row is deleted. Every User step below
runs there. The cache delete is the only step outside, on `transaction.on_commit`. **No
step calls `save()` on either instance:**
- the copy is stale, and would write an old `token_version` back;
- saving the old instance would re-insert the deleted row;
- a disabled user's `save()` bumps the version again (`accounts/models.py:110-131`).

### 10.4 What User's hook does

1. **One update:**
   `User.objects.filter(pk=new).update(email=new, reset_password_key="",
   last_reset_password_key_generated_on=None, token_version=<fresh random>)`.
   - `email` follows the name (upstream `user.py:599-600`; `temp` A-48 3b).
   - The reset key is cleared, so a link mailed to the old address cannot reset the
     renamed account.
   - A **fresh random** `token_version` (§10.5), not `+ 1`.
2. **Every outstanding refresh token is blacklisted**, as `logout_all_sessions` does
   (`accounts/front_door.py:112-120`). The blacklisting moves to
   `accounts/authentication.py` as `revoke_all_tokens(user)`, shared by both. It runs
   after the FK repoint, so `OutstandingToken.user` already names the new row. Upstream
   clears the sessions of both names (`user.py:602-603`).
3. **On commit:** `cache.delete("login_attempts:<old>")`. Rate-limit buckets expire by
   themselves.

**Dev data: no repoint.** `clear_dev_data`'s user step intersects its records with the
fixed seed names (`accounts/dev_data.py:97-98`), so a renamed seed user is simply no
longer a dev row: `clear_dev_data` leaves it, and the next `seed_dev_data` creates a
fresh user under the seed name. Accepted.

### 10.5 Token binding: a random version per account

A token is valid for one account. An account created under a name that was used before
does not accept a token issued to the earlier account.

- `token_version` becomes a `PositiveBigIntegerField` whose **default is a callable**
  returning `secrets.randbelow(2**62) + 1`. Every creation path gets it:
  - `POST /users/`;
  - invitation accept (`accounts/invitations.py:123-127`);
  - the seed (`accounts/dev_data.py:74-85`);
  - the admin, `createsuperuser` and fixtures.

  An explicit value is kept, so the rename's copy keeps the account's value until
  §10.4's update replaces it.
- A rename draws a fresh random value (§10.4), so renaming into a name used before is
  safe whatever the earlier values were.
- **Bound:** an earlier account's tokens match the new account only by chance, about
  (k + j + 1) / 2⁶², where k and j are the two accounts' version changes. Improbable,
  not impossible. Overflow cannot happen: a value starts at or below 2⁶², a bump adds 1, and the column
  holds up to 2⁶³ − 1.
- **Existing rows (proposed, marked for the owner):** a data migration gives every
  existing row a fresh random version, the built-ins included, so the rule above holds
  for accounts created before this change as well. It signs everyone out once.
- The migration to bigint **cannot be reversed** once any value exceeds 2³¹ − 1.
  Recorded.

### 10.6 `_assign` and `_liked_by` follow, as their own exception

Upstream renames Link fields and `owner` / `modified_by` (`user.py:583-594`) and leaves
`_assign` and `_liked_by` naming the old user. v2 rewrites them through a new
`core/rename.py` helper, `_repoint_json_name_lists(old, new)`, called by User's hook:
- every model with the column, every row whose JSON list holds the old name;
- each element that is an **exact match on the normalised old name** becomes the new
  name, with order and duplicates kept; a near-match (`xa@x.com`) is not touched;
- a plain `update()`: `modified` is not bumped and no save hook runs. It is the one
  writer of the caches besides their own calls, which ACTIVITIES and ASSIGNMENTS
  otherwise require.

`_comments` text is left as it is. **PE-24** is amended for User: rename needs System
Manager or Administrator, not the write rule; and "the caches are written by their own
calls" gains this one writer. **New PE-32:** a User rename
- is System Manager's or Administrator's;
- revokes the user's tokens;
- clears the reset key;
- rewrites `_assign` and `_liked_by`;
- leaves the user names inside `UserSettings.data` and a saved view's `filters` as they
  are.

Also part of PE-32: every account starts at a random token version.

### 10.7 Followed by the generic rename, proved by tests

- `owner` and `modified_by`: FKs to User (`core/models.py`).
- The auth M2M rows (`groups`, `user_permissions`) and SimpleJWT's `OutstandingToken`:
  expected to be reached as hidden reverse relations. Not checked yet; a test each.
- The sales-hierarchy node: its key is a CASCADE FK, so a missed repoint would delete it
  silently. A test.

### 10.8 Not mirrored from upstream

| Upstream | Here |
|---|---|
| the "renamed from" comment | dropped; ACTIVITIES decides |
| Notification Settings renamed with the user (`user.py:596-597`) | NOTIFICATIONS carries it |
| a Channels group keyed by the user's name | NOTIFICATIONS carries it |
| user names inside `UserSettings.data` and a saved view's `filters` | left as they are (PE-32) |
| attachments | no File model yet; ACTIVITIES carries it |
| assignment rule rows naming a user as text | ASSIGNMENTS carries it |

**Recorded:** a pending invitation to the old address, accepted after the rename,
creates a new account under the old name. It is a new account with its own random
version, so the renamed user's tokens do not work for it.

### 10.9 CRM Invitation rename

`POST /api/v1/invitations/<name>/rename/`, with the resource's write rule. It depends on
A-48 2b landing first: today write is refused for everyone. Nothing points at an
invitation, and `email` and `role` are set once (A-50), so nothing else changes.
**Recorded race:** the mail task finds the invitation by name (`accounts/tasks.py:31`).
A rename before the worker runs sends no mail. The invitation is still accepted by its
`key`, which the rename keeps.

### 10.10 Tests (their own commit)

`backend/tests` has no User rename case to port (to confirm in the brief).

- **Who:**
  - a Sales User on their own row: 417, row 7;
  - a Sales Manager: 417;
  - a System Manager: 200;
  - a System Manager's self-rename: 200, then the next call with the old access token is
    401 and the old refresh token is refused (marked line).
- **Refusals:**
  - Administrator and Guest, for Administrator and a System Manager alike: row 3;
  - a bad address, a list, and a display name: row 4;
  - the same name after normalising (`" A@x.com "` for `a@x.com`): row 5;
  - another account's name differing only by case: row 6;
  - a legacy mixed-case row renamed to its own lowercase form: 200;
  - a leading space never ends as an IntegrityError.
- **What follows:**
  - `email`, `owner` and `modified_by`;
  - `groups`, `user_permissions` and `OutstandingToken`;
  - the sales-hierarchy node;
  - `_assign` and `_liked_by`: an exact match is rewritten, a near-match is not, and
    `modified` is unchanged;
  - the reset key and its timestamp are cleared.
- **Tokens:**
  - a `BlacklistedToken` row for each outstanding jti;
  - the old access and refresh tokens are refused, and a fresh login works;
  - after the rename, an account is created under the old name **through invitation
    accept and through `POST /users/`** (not the conftest helper), and it refuses the
    renamed user's old access and refresh tokens;
  - deleting and re-creating an account refuses the first account's tokens;
  - each creation path never starts at 0;
  - the rename's new version differs from the old one.
- **Atomic:** a forced failure in the hook leaves the old row, its tokens and its version
  as they were.
- **Lockout:** the old key is gone, asserted after `on_commit` runs (captured).
- **Invitation:** renamed by a System Manager (once 2b is in), it is still accepted by
  its key.
