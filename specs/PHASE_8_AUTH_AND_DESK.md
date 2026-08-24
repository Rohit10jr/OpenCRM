# Phase 8 — Auth UI and the rest of the Desk

> **IN PROGRESS** — unparked and running on `phase-8-auth`, **scope A only**.
> See `docs/internal/PROGRESS_PHASE_8.md`.

## Why this phase is different from every other one

Phases 0–7 **port the CRM app**. This one ports part of the framework's **website layer**
instead — the half the port dropped along with the Desk.

> *This section used to open "This one does not port anything."* That was the same wrong
> claim the correction below was written to fix, still sitting two paragraphs above it where
> a reader who skims gets the wrong answer first. Fixed in phase 8; the marked correction is
> left exactly as it was.

Frappe ships two halves: the framework's **Desk** (a generic admin UI, auth screens,
record editors) and the **CRM app** that runs alongside it. Our port replaces the CRM
app. It silently dropped the Desk — and the CRM app assumes the Desk is there.

**This file used to say there is no upstream source to be faithful to, and that the rule
governing every other phase does not apply. That was wrong**, and it was written before
anyone looked. Corrected here rather than quietly deleted, because an agent who believed it
would invent a password-reset token scheme with a reviewed one sitting in the source tree.

The Desk's *screens* are Jinja templates and do not port to a Vue app. **Its auth logic
does**, and it is all in the cloned source:

| Upstream | What it holds |
|---|---|
| `frappe/www/login.html` + `login.py` | The login page. `login.py` is page context; the form posts `cmd=login`, `usr`, `pwd` |
| `frappe/www/update-password.html` | The set/reset page. **`update_password.py` is 10 lines** — pure context; the logic is elsewhere |
| `user.py:383` `_reset_password` | Generates the key and the `/update-password?key=…` link |
| `user.py:828` `update_password` | Redeems it. `200` → redirect path, `401` old password wrong, `410` link invalid or expired |
| `user.py:945` `_get_user_for_update_password` | Expiry and validity, and the two distinct messages |
| `user.py:1044` `reset_password` | Forgot-password entry, rate-limited, deliberately unenumerable |

So the rule **does** apply to the backend half: read the source and match it. It applies to
the markup not at all. Review this phase as a port with a new front end, not as green-field
work.

---

## What actually depends on the Desk

Verified by reading the copied frontend and the CRM's invitation flow.

### Blocking — the app cannot be used without these

| # | Dependency | Where |
|---|---|---|
| 1 | **Login page.** Unauthenticated users are redirected out of the app entirely | `frontend/src/router.js:222` → `window.location.href = '/login?redirect-to=/crm'` |
| 2 | **Set-password page.** Accepting an invitation redirects to a Desk-hosted reset URL | `crm/api/__init__.py:97-103` → `user._reset_password()` |
| 3 | **Welcome email + password link** for a newly invited user | `crm_invitation.py:57-59` → `send_welcome_mail_to_user()` |
| 4 | **Forgot password / reset flow** | Desk, no CRM equivalent |

Items 2 and 3 matter more than they look: **there is currently no way to onboard a
second user.** The invitation is created and emailed, and the acceptance link lands
nowhere.

### Degraded — the app works, some links go nowhere

Seven places open a Desk record editor for something the CRM has no screen for:

| Where | Opens |
|---|---|
| `components/Modals/WhatsappTemplateSelectorModal.vue:111` | `/app/whatsapp-templates/new` |
| `components/Settings/AssignmentRules/AssignmentRuleView.vue:377` | `/app/assignment-rule/<name>` |
| `components/Settings/ERPNextSettings.vue:724` | `/app/<doctype>/<name>` |
| `components/Settings/Sla/SlaHolidays.vue:241,284` | `/app/crm-holiday-list[/<name>]` |
| `components/Settings/Sla/SlaPolicyView.vue:292` | `/app/crm-service-level-agreement/<name>` |
| `composables/document.js:33` | `/app/item/new` (ERPNext) |
| `components/UserDropdown.vue:169` | the apps switcher (`app.route`) |

Several are already phase-7 territory (WhatsApp, ERPNext, Item), so they resolve
themselves if those integrations stay deferred.

---

## The backend is already done

Worth stating so this is not over-scoped when it is unparked. Built and tested in
phase 0:

- `POST /api/method/login` — issues the token pair
- `POST /api/method/logout` — revokes the refresh token (blacklist installed, A9)
- `POST /api/method/token/refresh` — rotates, single-use
- `GET /api/method/frappe.auth.get_logged_user`
- The `frappe-ui` interceptor: attaches the header, refreshes once on 401, bounces to
  login on failure (`frontend/src/auth/`)

What is missing is **the pages**, not the plumbing. Password reset and invite acceptance
also need endpoints, which do not exist yet.

---

## Scope, when it is unparked

The decision is not "build a login page." It is **how much of the Desk you are
replacing** — because the same reasoning reaches password reset, invite acceptance,
email verification, and an admin UI for every doctype without a CRM screen.

| | Scope | Cost |
|---|---|---|
| **A** | Auth screens only — login, set password, forgot password, invite acceptance | Smallest coherent unit. Unblocks onboarding |
| **B** | A, plus CRM screens for the Desk-linked doctypes (assignment rules, holiday lists, SLA policies) | Removes the degraded links that are not phase-7's problem |
| **C** | A generic admin UI over the doctype registry | Rebuilding the Desk. Large, and arguably the wrong product |

**A is the recommendation.** It is the only part that blocks use, and the backend for
most of it already exists.

---

---

## Decisions already made — do not re-open

### Scope: A. Auth screens only

Login, set password, forgot password, invite acceptance. Not the Desk-linked record
editors (B), not a generic admin UI (C). A is the only part that blocks use, and three of
the seven degraded links are phase-7 territory that stayed deferred anyway.

### The pages live **inside the Vue app**

`router.js:222` currently does `window.location.href = '/login?redirect-to=/crm'`, which
leaves the SPA for a URL nothing serves — `config/urls.py` has only `admin/` and `api/`.
That redirect is the bug, not the contract. Replace it with a route; do not stand up a
second server to answer it.

### Link lifetimes — set deliberately, not inherited

Upstream's `reset_password_link_expiry_duration` defaults to **zero, meaning never
expires**. Do not copy that. A password-reset link that works forever is the same class of
problem as the invitation key phase 4 locked down: a mail archive becomes a credential
store.

| Link | Lifetime | Why |
|---|---|---|
| **Password reset** | **1 hour** | Long enough to walk to your desk, short enough that a forwarded or archived email is dead. The standard for this kind of link |
| **Invitation** | **3 days** — already set | `tasks.INVITATION_EXPIRY_DAYS = 3`, with `expire_invitations` sweeping nightly. Do not change it |
| **Set-password key issued when an invitation is accepted** | **1 hour**, like any reset | The *invitation* may sit for three days; once redeemed, the key it mints is a password-reset key and lives as long as one |

That last row is the one to get right. The two clocks are separate: three days to accept,
one hour to choose a password after accepting.

Make it a setting (`PASSWORD_RESET_LINK_EXPIRY_MINUTES`, default 60) rather than a
constant, and **treat zero as one hour rather than as infinity** — upstream's "0 disables
the check" is a footgun worth not reproducing.

### `test_password_strength` is not ported

Upstream ships a fifth endpoint that scores a password server-side as the user types. Skip
it: validate in the browser with the frontend's own schema validation. It is a UI nicety,
it costs a network round trip per keystroke, and a rule the server does not enforce does
not belong on the server.

**Enforce the actual minimum server-side** in `update_password`, where it cannot be
skipped by a client that does not run your JavaScript. Django's
`AUTH_PASSWORD_VALIDATORS` are already configured in `config/settings/base.py` and are the
right place.

### JWT, not a session cookie

Upstream's `update_password` ends with `login_manager.login_as(user)` and returns a
redirect path. Ours cannot: this port issues a JWT pair (phase 0's sanctioned deviation).
So the endpoint returns **tokens**, and the page stores them the way
`frontend/src/auth/tokens.js` already expects.

`logout_all_sessions` has a real meaning here and should keep it: blacklist the user's
outstanding refresh tokens. The blacklist app is installed and `logout` already uses it.

---

## What to match exactly, and why

Four decisions upstream got right. Port them as they are.

1. **Store the key hashed.** `_reset_password` puts `sha256_hash(key)` in the row and the
   raw key only in the link. A database dump yields no working links.
2. **Single use.** On success the key is cleared. Redeemed once, dead.
3. **The forgot-password response never varies.** Upstream's comment says why, and names
   the weakness: *"Always return the same generic response regardless of whether the user
   exists, is disabled, or is restricted. This prevents username enumeration via different
   messages or HTTP status codes (CWE-204)."* Every path — unknown user, disabled account,
   mail failure, unexpected exception — returns the same sentence. Rate-limited per hour.
   This is the same reasoning as answering 404 rather than 403 for an unrouted doctype.
4. **Two distinct failure messages, and only two.**
   * *"The reset password link has been expired"*
   * *"The reset password link has either been used before or is invalid"*

   The second deliberately merges "already used" with "never existed", so a key cannot be
   probed. The first is separate because an expired link is a real user's real problem and
   telling them to request another is the whole job.

**Rate-limit the reset endpoint.** `frappe_core.security.rate_limit` exists from phase 3's
A1 work and already fronts login. An unlimited forgot-password endpoint is a mail cannon
pointed at whatever address the caller names.

## Open questions — answered

The first three are settled above and kept here so the change is visible.

- ~~Is `/login` a route inside the Vue app, or a separate page?~~ **A route inside the
  app.** The redirect out of the SPA is the bug.
- ~~Password reset needs token issue/verify endpoints — new, with no upstream to match.~~
  **There is upstream to match**: `user.py:383` issues, `user.py:945` verifies,
  `user.py:828` redeems. Django's `PasswordResetTokenGenerator` is *not* the basis —
  matching upstream's stored-hash-plus-timestamp keeps the semantics the frontend and the
  invitation flow already assume.
- ~~Invite acceptance needs an endpoint…~~ Still needed, and now specified: accept the
  key, run the already-ported `crm_invitation.accept()`, then mint a **one-hour**
  set-password key and land the user on `/update-password`. The permission rule on
  `CRM Invitation` is already in place (bug #21) — **do not weaken it to make redemption
  easier.** The key comes from the email, not from the API.

### Both now decided

**The apps switcher stays, dead.** `UserDropdown.vue:169` points at Frappe's app chooser —
the thing that hops between CRM, Helpdesk and Books on one install. There is one app here,
so it links to a page that does not exist, for a concept that does not apply.

**Not phase 8 work**: leaving it is zero effort, and removing it is a frontend change to a
component this phase has no other reason to touch. Recorded so it is a decision rather than
an oversight. Revisit if a second app ever exists, which is the only thing that would make
it mean something.

**The reset email is a Django template, editable by whoever deploys.**

`crm_app/templates/emails/password_reset.txt`. `APP_DIRS` is already `True` in
`config/settings/base.py`, so no settings change and no new doctype — Django finds it.

Upstream's answer is a `password_reset` template doctype with a System Settings override,
so a non-technical admin can reword it in the product. That needs a settings *screen* to
edit it, and building one to change an email body is not what "let a second person log in"
means. **If in-product editing is wanted later**, the field belongs on `FCRM Settings`
(manager-writable already) plus a screen — a feature, sized as one.

**Move the invitation email to a template in the same change.** It is currently an f-string
inside `tasks.py:217`. Two emails, one mechanism, and the next person looking for "where
does the wording live" finds one answer instead of two.
