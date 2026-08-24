# Orientation — phase 8

Written before any code, per `RUNBOOK_PHASE_7.md` Step 0 (which `RUNBOOK_PHASE_8.md` says
still applies). Branch cut from `phase-8-prep-2` as instructed.

---

## 1. What exists that I must not rebuild

**The auth plumbing is done.** What is missing is two endpoints and four pages.

| Thing | Where |
|---|---|
| `POST /api/method/login` → token pair | `frappe_core/api/auth.py:39` |
| `POST /api/method/logout` → blacklists the refresh token | `:99` |
| `POST /api/method/token/refresh` → rotates, single-use | `:118` |
| `GET /api/method/frappe.auth.get_logged_user` | `:155` |
| `crm.api.user.change_password` | `crm_app/api/user.py:54` |
| Brute-force protection on login | `frappe_core.security.check_login_allowed` — IP **and** account tracker |
| Rate limiting, for endpoints that want it | `frappe_core.security.rate_limit(limit=, seconds=, key=)` |
| Token storage + the `user_id` claim decode | `frontend/src/auth/tokens.js` |
| The 401-refresh-retry interceptor | `frontend/src/auth/jwtRequest.js` |
| Session store, `login`/`logout` resources | `frontend/src/stores/session.js` |
| `CRM Invitation`, its 3-day expiry, the nightly sweep | `crm_app/models/metadata.py:226`, `tasks.INVITATION_EXPIRY_DAYS`, `crm.expire_invitations` |
| The invitation email task | `crm_app/tasks.py:220` — retries on SMTP failure, idempotent on `email_sent_at` |
| Django password validators | `AUTH_PASSWORD_VALIDATORS` in `config/settings/base.py:90` |
| `APP_DIRS: True` | `:74` — so `crm_app/templates/` will be found without a settings change |

**Two protections are already in place for the endpoint I am about to write**, put there
deliberately before it existed (`KNOWN_ISSUES.md` §2): `CRM Invitation` is manager-only, and
`key` is in `SENSITIVE_FIELDS` so it never reaches the wire. Redemption reads the key from
the *email*. I must not relax either.

## 2. The mechanisms that protect a doctype, and which one a reset key needs

Registering a doctype **publishes it** — `/api/resource/X` gives every authenticated caller
CRUD, and `frappe.client.*` reaches it too, unless something says otherwise. Protection is
opt-in, in four field declarations plus a row rule:

- **`SENSITIVE_FIELDS`** — off the wire entirely: not serialised, not selectable in
  `fields=`, and not usable in `filters` / `order_by` / `group_by`. That last part is the
  point: hiding a value from output alone leaves the row count as an oracle, and
  `["password","like","sw%"]` recovers it one character at a time.
- **`ENCRYPTED_FIELDS`** — plaintext out of the database. Protects a dump, a backup, a log.
  Neither implies the other, and a real credential usually needs both.
- **`RESTRICTED_FIELDS`** — manager-only read, applied per request because serializers are
  cached per model and cannot know who is asking.
- **`READONLY_FIELDS`** — visible to all, writable by nobody.
- **The row rule** decides who may touch the document at all. A write path needs it *and*
  the object rule; they are allowed to differ.
- **`routable=False`** withholds the route entirely, for a doctype nothing addresses over
  HTTP.

**A password-reset key needs none of those and something stronger: a one-way hash.**
Encryption is reversible by design, so an `ENCRYPTED_FIELDS` reset key is still a working
key to anyone who can reach the encryption key. Upstream stores `sha256_hash(key)` and puts
the raw value only in the emailed link (`user.py:385-387`), so a database dump yields
nothing redeemable. That is the property to port, and it is why this is *not* just another
credential field.

`SENSITIVE_FIELDS` on top of the hash, because the hash is still a comparison target and has
no business on the wire.

## 3. What I believe is stale or wrong in these documents

Six, all verified against the code rather than suspected.

1. **`RUNBOOK_PHASE_8.md` says `rate_limit` "already fronts login". It does not.**
   `frappe_core/api/auth.py:52-53` says the opposite, deliberately: *"No `@rate_limit` on
   top, matching upstream: the tracker already stops brute force, and a hard request cap
   here is what locks out a whole office behind one NAT address."* Login is protected by
   `check_login_allowed`, an IP-**and**-account attempt tracker. The instruction to
   rate-limit the reset endpoint stands and I will follow it; the precedent cited for it is
   wrong, and an agent copying the "pattern" from login would find no pattern there.
2. **`TASK.md`'s last section says the human reads `PROGRESS_PHASE_7.md` first.** It should
   say `PROGRESS_PHASE_8.md`. Copy-paste from the phase-7 task file.
3. **`TASK.md` says to continue `UPSTREAM_BUGS` "from #33".** #33 already exists (Meta
   tokens in the query string, phase 7). Continuing from 33 would overwrite it — I continue
   from **#34**.
4. **`TASK.md` says "this phase adds credential-bearing doctypes".** Also carried over from
   phase 7. Phase 8 adds a credential **field** to an existing model (`User`), not a
   doctype. The `AS_BUILT.md` checklist still applies to the field; the framing would send
   someone looking for a new doctype to register.
5. **`specs/PHASE_8_AUTH_AND_DESK.md` still opens `> **PARKED.** Do not start this until
   phases 0–7 are complete.`** They are complete, and this is the run. I will flip it.
6. **The same spec's opening line still reads "Phases 0–7 port the CRM app. This one does
   not port anything."** The correction two paragraphs later says exactly the opposite and
   says so loudly — but a reader skimming the first sentence gets the wrong answer, which is
   the failure the correction exists to prevent. I will fix the opening line and leave the
   marked correction alone.

*(And a cosmetic one I am not fixing: `UPSTREAM_BUGS_PHASE_3-6.md` now holds bugs 10–33,
which span phases 3–**7**. Renaming a tracked file mid-phase costs more than the confusion
saves.)*

## 4. What I do not understand yet

- **Whether `CRMInvitation.accept()` exists in this port at all.** Upstream's does role
  escalation (`System Manager` also gets `Sales Manager` + `Sales User`) and creates the
  user if absent. I have read upstream's; I have not yet found ours. If it is missing, that
  is part of this phase and not a surprise — the endpoint was never built.
- **What the frontend expects a set-password page to receive.** There is no upstream Vue to
  copy: `update-password.html` is Jinja. I will match the *request/response shape* upstream
  defines (200 / 401 / 410) and write the markup to this app's existing conventions.
- **Whether `logout_all_sessions` can reach every outstanding token.** SimpleJWT's blacklist
  covers refresh tokens; a five-minute access token stays valid until it expires. That is
  the same window `KNOWN_ISSUES.md` records for logout, and I expect to record it again
  rather than close it.

## 5. Risks I see in phase 8 specifically

1. **This is the front door, and every new endpoint is `allow_guest`.** Rarer here than
   anywhere else in the port — three of the four screens post to endpoints an unauthenticated
   stranger can reach. Each deserves the scrutiny a phase-7 webhook got.
2. **The failure mode phase 7 shipped.** A signature check that was correct, tested and
   unreachable in production. Gate step 5 exists because of it, and this phase is the worst
   place to repeat it: its entire point is that a second person can get in. A green unit
   suite proves nothing here until I have walked the flow.
3. **Enumeration.** The forgot-password response must not vary — not by message, not by
   status code, not by *timing* in an obvious way. Upstream names CWE-204 in a comment.
   Every path: unknown user, disabled account, Administrator, mail failure, unexpected
   exception.
4. **Two clocks that look like one.** Invitation 3 days, reset key 1 hour. A single constant
   used for both would pass every test I am likely to write and be wrong.
5. **Resurrecting a disabled account.** A reset must not re-enable one. SimpleJWT refuses at
   authentication, but the reset endpoint runs before that.
6. **The guard tests will fire.** `reset_password_key` matches `test_credential_fields.py`'s
   name heuristic. That is the system working; the answer is a declaration, not an exception.

## 6. Plan

1. **Fix the stale claims** found above — one commit, before anything reads them wrong.
2. **The reset-key model layer** — `User.reset_password_key` (hashed) +
   `last_reset_password_key_generated_on`, `PASSWORD_RESET_LINK_EXPIRY_MINUTES` (default 60,
   zero means 60), and the issue/verify/consume helpers. Tested against upstream's semantics
   before any endpoint exists.
3. **Email templates** — `crm_app/templates/emails/`, and move the invitation email off its
   f-string in the same change so there is one answer to "where does the wording live".
4. **`reset_password`** (forgot password) — unenumerable, rate-limited.
5. **`update_password`** — key or old password, 200 / 401 / 410, returns a JWT pair,
   `logout_all_sessions`.
6. **`crm.api.accept_invitation`** — redeem, mint a one-hour reset key, land on the
   set-password page. Plus `CRMInvitation.accept()` if it is missing.
7. **The four Vue pages and the router change** — replacing `router.js:222`'s redirect out
   of the SPA.
8. **Walk the flow end to end** and write down exactly how, per gate step 5.

If I run long, the order above degrades honestly: login already works, and stopping after
step 6 leaves a working backend with no pages, which is a smaller lie than four pages nobody
has walked through.
