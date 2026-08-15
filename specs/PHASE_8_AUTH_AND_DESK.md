# Phase 8 — Auth UI and the rest of the Desk

> **PARKED.** Do not start this until phases 0–7 are complete. Recorded now so the
> dependency is not rediscovered late; deliberately not scheduled.

## Why this phase is different from every other one

Phases 0–7 **port the CRM app**. This one does not port anything.

Frappe ships two halves: the framework's **Desk** (a generic admin UI, auth screens,
record editors) and the **CRM app** that runs alongside it. Our port replaces the CRM
app. It silently dropped the Desk — and the CRM app assumes the Desk is there.

So there is no upstream source to be faithful to here. The rule that governs every other
phase — *read the Frappe source and match it* — **does not apply**. This is new product
work, and it should be reviewed as such.

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

## Open questions for that day

- Is `/login` a route inside the Vue app, or a separate page? The redirect at
  `router.js:222` leaves the SPA entirely, so either the route changes or something
  must serve that path.
- Password reset needs token issue/verify endpoints — new, with no upstream to match.
  Django's own `PasswordResetTokenGenerator` is the obvious basis.
- Invite acceptance needs an endpoint that accepts the key, creates the user, assigns
  roles per `crm_invitation.accept()` (already ported logic), then lands them somewhere
  that lets them set a password.
- Does the apps switcher (`UserDropdown.vue:169`) still make sense with no other apps?
