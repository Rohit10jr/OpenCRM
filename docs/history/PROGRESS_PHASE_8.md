# Phase 8 — PASS   [branch: `phase-8-auth`]
Started: 2026-08-24   Finished: 2026-08-24

**Built:** Scope A — the four auth screens and the endpoints behind them. **The port can
now onboard a second user**, which it could not before: the invitation flow was broken end
to end.

**Tests:** **1644 backend passing** (from 1574), 31 skipped (all pre-existing), 0 failing.
**166 frontend passing** (from 152). Nothing skipped or weakened. **Migrations clean.**
**Review: tier 1 (Codex, PowerShell 7)**, two passes — the second found two more, both real.

**The flow was walked**, which is gate step 5 and the reason this phase has one:
`backend/scripts/walk_auth_flow.py`, **26 of 26 steps**. See "How I checked" below.

**7 commits**, each green.

| # | Commit | What |
|---|---|---|
| 1 | `2802513` | Step 0 orientation + five stale claims |
| 2 | `d303db7` | Reset keys, and a third answer for the credential guard |
| 3 | `b6de2a6` | The three endpoints, and both emails behind one template |
| 4 | `4909f2d` | The four screens, and the redirect that was the bug |
| 5 | `adbcb52` | Review fixes |
| 6 | `c319ebf` | Docs |
| 7 | *(this)* | Second-pass review fixes |

## Acceptance criteria

| Criterion | Covered by |
|---|---|
| Login page exists, inside the SPA | `frontend/src/pages/auth/Login.vue`, `authRouting.test.js` |
| Forgot password, unenumerable, rate-limited | `test_every_path_produces_a_byte_identical_response` + 8 more |
| Set/reset password, 200 / 401 / 410 | `test_auth_pages.py` — one test per status |
| Invite acceptance | `test_accepting_creates_the_user_and_returns_a_set_password_link` |
| Key stored hashed, single use, 1 hour | `test_password_reset_keys.py` (27) |
| Zero means one hour, not never | `test_a_zero_setting_still_expires_a_key` |
| Password rules enforced server-side | `test_a_weak_password_is_refused_server_side` |
| JWT rather than a session | `test_the_new_password_actually_logs_in` |
| **A second person can get in** | the walk, step by step |

---

## How I checked — gate step 5

`backend/.venv/Scripts/python.exe backend/scripts/walk_auth_flow.py`. It builds and drops
its own test database, so it runs anywhere with no setup.

It deliberately **does not import the endpoint functions**. It drives real HTTP through
Django's test client, reads the link out of `django.core.mail.outbox` by parsing the email
body, and never touches a key it did not receive by mail. Ten stages:

1. a manager invites an address → 2. the email goes out **on create** (phase 5 wired it to a
signal) and carries a link → 3. the invitee redeems it → 4. the set-password link points
into the app → 5. they choose a password → 6. they log in with it → 7. the token works
against `get_logged_user` → 8. both links are now dead (417 / 410) → 9. forgot-password
sends a second link that also works → 10. an unknown address answers byte-identically.

**It found two things a unit test would not**, and I am recording both because the second
one is the more interesting failure:

* My first version cleared the outbox *after* creating the invitation and then called the
  send task by hand — and found an empty outbox, because the real send had already happened
  and been wiped. My mental model was "create, then send"; the system sends on create.
* **It still missed the invitation link being wrong** (see the review, below). It followed
  the *endpoint* rather than the *URL a person clicks*. That is the same gap as phase 7's
  Twilio signature, one frame smaller, and it is worth knowing that running the walk is not
  automatically enough — you have to walk what the *user* touches.

---

## Decisions made without you

1. **`last_reset_password_key_generated_on` is hidden too.** Not a credential — a timestamp.
   But `User` reads are open to every authenticated caller (divergence #5, so kanban can
   build a column per user), so a visible issue time tells any colleague which accounts have
   a live reset link and when. That is the window an attacker with mailbox access wants.
2. **A third exception list in `test_credential_fields.py`.** The guard demanded
   `SENSITIVE` + `ENCRYPTED`, and a hash is neither and should not be — encryption is
   reversible, hashing is stronger here, and it is only available because the server never
   needs the value back. `REVIEWED_HASHED_AT_REST`, kept separate from the two existing
   lists because `NOT_CREDENTIALS` would be a lie and `RESTRICTED_ONLY` would assert a
   manager may read it.
3. **`issue_tokens` extracted from `login`** so `update_password` returns an identical
   shape. A set-password page that landed the user with a subtly different payload would log
   them in and then show an empty header.
4. **`?redirect=` after login**, sanitised to same-origin paths. I introduced the open
   redirect by adding the feature and closed it in the same change; the regex rejects
   `//host` as well as `https://host`, since the protocol-relative form is what a naive
   "starts with `/`" check lets through.
5. **`rate_limit` gained a `normalise` hook** (see the review).
6. **`auth_pages.py` added to the permission-layer allowlist**, with the reasoning per
   endpoint. These run before anybody has an identity.
7. **Five stale claims fixed in Step 0** — most importantly the runbook's statement that
   `rate_limit` "already fronts login". It does not, deliberately, and `auth.py:52` explains
   why. The instruction it supported was right; the precedent was not.

## Deviations from spec

- None. All four settled decisions were followed: pages inside the SPA, 1-hour resets
  against 3-day invitations, no `test_password_strength`, JWT rather than a session, email
  wording in Django templates, apps switcher untouched.

## Upstream bugs recorded — #34, #35

| # | Bug | Us |
|---|---|---|
| 34 | **A password-reset link never expires by default** (`user.py:955-962` — `0` disables the check) | diverge — zero means one hour |
| 35 | Forgot-password is rate-limited per caller, not per target | stricter |

## The review — tier 1 (Codex, PowerShell 7)

**Five findings, all real, all fixed.** The first pass hit a connection error mid-run and
reconnected; the output was a genuine review with `file:line` citations, so it was accepted.

**Medium, and the one that matters most: the invitation email linked to the JSON API.**
`/api/method/crm.api.accept_invitation?key=…` answers with JSON, so an invited colleague
clicking the link in their mail landed on a raw JSON blob. Upstream can link to its endpoint
because that one answers a GET with an HTTP *redirect* into the Desk; ours cannot.

Every unit test passed, because they tested the endpoint. **And the walk passed**, because it
called the endpoint too. This is the failure gate step 5 was written for and it still got
through, which is worth more than a clean review would have been.

**High — `update_password` was an unthrottled password oracle.** No rate limit, and its
old-password path takes an arbitrary `usr` and calls `authenticate()` — checking passwords
without `check_login_allowed`, the tracker that protects `login`. A second door past the
lockout makes the lockout decorative. Fixed both ways: a request cap *and* the tracker,
because they stop different things.

**High — the forgot-password limiter was bypassable.** The per-target bucket used the raw
parameter, so `Alice@x.com`, `alice@x.com` and `" alice@x.com "` were three buckets aimed at
one account. `rate_limit` gained a `normalise` hook.

**Medium — single use was sequential, not atomic.** Both flows resolved a key and cleared it
in two statements, so two concurrent requests could both proceed — and for a password reset
the second silently wins. Whoever holds a forwarded copy of the link *is* that second
request. Now a compare-and-swap in both places.

**Low — logout had the same redirect bug the router had**, in a file the review was not
asked to look at.

### The second pass — and the two that mattered most came last

Re-reviewed after the fixes. All five backend findings confirmed closed, and **two more
found, both frontend, and the first of them meant the product did not work.**

**Setting a password returned you to the login page.** `UpdatePassword.vue` and
`AcceptInvitation.vue` called `setTokens()` and then routed. `isLoggedIn` is *computed from
a ref the store holds*, and `setTokens` only writes localStorage — so the navigation guard
still saw a logged-out visitor and bounced them straight back to Login. Reset your password
successfully, land back at the login form.

**Every backend test passed. The end-to-end walk passed. Neither runs a browser.** This is
the third time in two phases that the same shape has appeared — correct code that nothing
real reaches — and it is the exact risk this file's own Concerns section named before the
review found it: *"the pages have no component tests… the Vue is covered by inspection."*
Fixed with one `acceptTokens` on the store that does both halves, used by all three
entry points, and asserted by test.

**`type="email"` on the login field blocked `Administrator`.** The backend authenticates
against `User.name`, and the seeded superuser's name is literally `Administrator`, not an
address — so the browser refused to submit the one account that always exists, before the
request was ever sent. Now `type="text"` with `inputmode="email"`.

I had marked this phase PASS before these two were found. That was premature, and it was
premature for a reason worth keeping: I had run every gate step, including the walk, and
they were all green.

## Not done — named, not hidden

- **Scope B and C**: no record editors for Desk-linked doctypes, no generic admin UI. Both
  are out of scope by decision, and three of the seven degraded links are phase-7 territory
  that stayed deferred.
- **The apps switcher stays dead** (`UserDropdown.vue:169`) — a decision, recorded in the
  spec, not an oversight.
- **`test_password_strength`** is not ported, deliberately.
- **In-product editing of email wording.** The templates are files; upstream has a doctype
  plus a settings screen. If that is wanted, the field belongs on `FCRM Settings` plus a
  screen — a feature, sized as one.

## Concerns — what I would look at first with another hour

1. **The pages still have no component tests, and this is now a demonstrated gap rather
   than a theoretical one.** The second review pass found two frontend bugs here, one of
   which broke the reset flow outright. What exists now asserts the *rules* by reading the
   source — that `acceptTokens` is used, that the login field is not `type="email"` — which
   catches a regression of exactly these two and nothing else. Mounting `Login.vue` and
   `UpdatePassword.vue` with a stubbed router is the real fix and is maybe two hours.
2. **Nobody has clicked these screens in a browser.** Still true, and the point is now
   sharper: the two bugs above were *only* findable that way or by reading, because the
   whole server side was green. A real browser pass — invite yourself, read the mail, click
   through — is an hour and would close the gap the walk provably cannot.
3. **An access token issued before `logout_all_sessions` stays valid for its five minutes.**
   Same window `logout` has, recorded in `KNOWN_ISSUES` §4 rather than closed. Closing it
   needs a per-request blacklist check, which is a different decision.
4. **`update_password`'s rate limit is per IP.** An office behind one NAT shares it. 20/hour
   is generous enough that this should not bite, but it is the same tension `auth.py:52`
   describes for login, and I resolved it the other way here because this endpoint has no
   tracker of its own for the key path.
5. **The reset email's `FRONTEND_ORIGIN` must be right in production.** Both links are built
   from it, and if it is wrong the mail is useless — silently, since nothing on the server
   fails. Worth an item on a deploy checklist.
