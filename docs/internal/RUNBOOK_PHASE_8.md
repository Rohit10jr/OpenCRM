# Unattended Run — Phase 8, Auth

**You are running without a human available. Read this whole file before starting.**

Supersedes `RUNBOOK_PHASE_7.md`. **Step 0 and "How to work here" in that file still
apply** — read them there; they are not repeated here. The commit rule is the same: one
per meaningful change, never one per phase.

---

## Scope — A, and only A

Four screens and the endpoints behind them:

| # | Screen | Backend |
|---|---|---|
| 1 | **Login** | Exists — `POST /api/method/login` |
| 2 | **Forgot password** | New — port `user.py:1044` |
| 3 | **Set / reset password** | New — port `user.py:828` and `:945` |
| 4 | **Invite acceptance** | New — `crm.api.accept_invitation` |

**Not in scope:** record editors for Desk-linked doctypes (assignment rules, holiday
lists, SLA policies), and any generic admin UI. Three of the seven degraded links are
phase-7 territory that stayed deferred; the rest is a product decision nobody has taken.

**This is the last phase.** After the gate passes, STOP.

## What makes this phase different

Every other phase ported a Frappe *app*. This one ports part of the *framework's website
layer*, which the port dropped along with the Desk.

**The spec used to say there is no upstream to be faithful to. That was wrong and is
corrected** (`specs/PHASE_8_AUTH_AND_DESK.md`). The screens are Jinja and do not port. The
logic is all there and does:

| Read | For |
|---|---|
| `frappe/www/login.html`, `templates/includes/login/login.js` | What the login form posts |
| `frappe/www/update-password.html` | Request shape and the `200` / `401` / `410` handling |
| `frappe/core/doctype/user/user.py:383` | Key generation and the link |
| `…:828` | Redeeming, and the 410 path |
| `…:945` | Expiry, validity, and the two messages |
| `…:1044` | Forgot-password, rate-limited and unenumerable |

`frappe/www/update_password.py` is **10 lines of page context** — do not go looking there
for logic.

---

## The decisions, all made

`specs/PHASE_8_AUTH_AND_DESK.md` carries them in full. In short, and none are yours to
revisit:

- **Pages live inside the Vue app.** `router.js:222`'s redirect out of the SPA is the bug.
- **Password-reset links last 1 hour**, as `PASSWORD_RESET_LINK_EXPIRY_MINUTES` (default
  60). **Zero means one hour, not infinity** — upstream's "0 disables the check" is a
  footgun and is not reproduced.
- **Invitations last 3 days** — already `tasks.INVITATION_EXPIRY_DAYS`, already swept
  nightly. Unchanged. The set-password key an accepted invitation mints is a *reset* key
  and lives one hour. **Two clocks, deliberately.**
- **`test_password_strength` is not ported.** Validate in the browser; enforce the real
  minimum server-side through Django's `AUTH_PASSWORD_VALIDATORS`, already configured.
- **JWT, not a session.** `update_password` returns a token pair, not a redirect;
  `logout_all_sessions` blacklists outstanding refresh tokens.
- **Email wording lives in a Django template** — `crm_app/templates/emails/`. `APP_DIRS`
  already finds it; no doctype, no settings screen. **Move the invitation email there
  too** (`tasks.py:217` builds it as an f-string), so there is one answer to "where does
  the wording live" rather than two.
- **The apps switcher stays dead** (`UserDropdown.vue:169`). Not this phase's work — see
  the spec. Do not tidy it while you are in the file.

### Four things to match exactly

1. **Store the key hashed** — raw only in the link.
2. **Single use** — clear it on success.
3. **The forgot-password response never varies**, whatever happened. Upstream names the
   weakness in a comment: CWE-204, username enumeration. Same reasoning as our 404-not-403.
4. **Two failure messages, and only two** — expired, versus used-or-invalid. The second
   merges "used" and "never existed" on purpose.

**Rate-limit the reset endpoint.** `frappe_core.security.rate_limit` exists — phase 3 built
it and it fronts `change_password`. Unlimited, forgot-password is a mail cannon aimed at any
address the caller names.

> **Correction.** An earlier version of this line said `rate_limit` "already fronts login".
> It does not, and deliberately: `frappe_core/api/auth.py:52-53` explains that login is
> protected by `check_login_allowed` — an IP-**and**-account attempt tracker — and that *"a
> hard request cap here is what locks out a whole office behind one NAT address."* The
> instruction above is unchanged; only the precedent cited for it was wrong. Do not copy a
> pattern from login, because there is none there.

---

## Security notes specific to this phase

You are building the front door. Three things this project has already learned apply
directly:

- **`CRM Invitation` is manager-only and its `key` never reaches the wire** (bug #21 —
  upstream lets any Sales User read a pending invitation's key and redeem it). **Do not
  relax either to make redemption easier.** Redemption reads the key from the *email*.
- **A disabled account is refused at authentication** — SimpleJWT checks `is_active`,
  which maps to `enabled`. Verify a reset cannot resurrect one.
- **Any new endpoint is a public surface.** These are `allow_guest`, which is rarer here
  than anywhere else in the port — each one deserves the scrutiny a webhook got in phase 7.

If you add a doctype — a reset-token model, say — `tests/test_route_surface.py` and
`tests/test_credential_fields.py` will both have opinions. A stored reset key is
credential-shaped and the second test will say so.

---

## The gate

Unchanged from phase 7, with one addition.

1. **Tests pass.** Full suite green, nothing weakened.
2. **Migrations clean**, applying from empty.
3. **Independent review** — Codex on PowerShell 7, then 5.1, then a fresh Claude subagent.
   State the tier. `codex exec` exits 0 even when it ran nothing.
4. **Commits** — one per meaningful change.
5. **NEW: the flow works end to end, and you say how you checked.** This phase's whole
   point is that a second person can get into the product. Drive it: invite an address,
   read the link out of the outbox, redeem it, set a password, log in with it. A green
   unit suite over a flow nobody walked is exactly what phase 7 shipped with the Twilio
   signature — correct, tested, and unreachable in production.

## Fail-stop

If the gate fails twice, write up what happened in
`docs/internal/PROGRESS_PHASE_8.md` and **stop**. Login working and password reset
half-built, honestly reported, beats four screens nobody has walked through.

---

## When it is done

`docs/internal/PROGRESS_PHASE_8.md`, same format as phases 3–7. Say what you are unsure
about; that section has been the most valuable one every time.

**Then update `specs/README.md`** — phase 8 is the last one, and the table should say the
port is complete rather than leaving the final row saying "Parked".
