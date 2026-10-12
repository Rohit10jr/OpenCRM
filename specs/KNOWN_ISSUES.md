# Known issues

Things that are wrong, or not yet trustworthy, and are **not** recorded elsewhere.

Not a substitute for the per-phase progress files — those record what a phase built and
what it left. This is for problems that outlive a phase: flaky tests, half-built features,
and anything a future agent would otherwise rediscover the hard way.

| # | Issue | Status |
|---|---|---|
| 1 | A WebSocket test fails intermittently under full-suite load | ✅ **Characterised and fixed** — root cause understood, and it is a production concern too |
| 2 | `crm.api.accept_invitation` is not implemented; invitation links 404 | ✅ **Closed in phase 8** — implemented, and the flow walked end to end |
| 3 | `Communication`, `File` and `Comment` leak content from records the caller cannot open | ✅ **Fixed** — see below for what it took |
| 4 | The async stack had never run against a real broker, worker or scheduler | ✅ **Smoke-tested** — passed; see below for what is still untested |
| 5 | The frontend test suite had never been executed; the realtime layer had never run on real Redis | ✅ **Both run** — 152 frontend tests pass, cross-process delivery confirmed |
| 6 | Logging out does not stop an access token already issued — it works for up to 5 more minutes | ⏸️ **Open, accepted** — inherent to stateless JWT; three ways out are costed below |
| 9 | The frontend is slow to load | ⏸️ **Open, deferred** — to be examined after the browser testing is finished and `phase-8-followup` is merged; what is known and what to measure first are below |
| 10 | Nothing is translated: the interface and the server's messages are English only | ⏸️ **Open, deferred** — to be built after the browser testing; the design, step by step, is below |

---

## 1. `test_subscribing_to_a_missing_document_is_refused_the_same_way` fails intermittently

**Where:** `tests/test_phase6_realtime.py:321`

Fails with `TimeoutError` from `asgiref/timeout.py` on
`await communicator.receive_from(timeout=5)`. Passes when run alone, and passed on an
immediate full re-run. Observed twice, weeks apart, both times only under a full-suite run.

**What is known:**

* it is unrelated to whatever change was in flight when it appeared — the test subscribes
  to `CRM Lead` and a nonexistent doctype, and both sightings followed changes that
  touched neither;
* the machine it runs on has been memory-constrained before (PostgreSQL was killed twice
  by `ERROR_NO_SYSTEM_RESOURCES` with 0.2 GB free), so load-dependent timing is plausible;
* the suite runs ~1250 tests in roughly five minutes, and the WebSocket tests are near the
  end, which is where contention would be worst.

**What is not known:** whether the five-second wait is genuinely too short under load, or
whether a previous WebSocket test leaves a connection un-torn-down and this one inherits
the mess. Those want different fixes.

### Settled, 2026-08-20

**Rate.** Six consecutive full-suite runs, **zero failures**. Roughly two sightings in
about twenty-five runs overall — the "slow machine" end of the range set out above, not
the "teardown is broken" end. No leaked connections either: 22 disconnects for 22
connecting tests, and no test that connects without one.

**Mechanism, which turned out to matter more than the rate.** `_may_read` is
`@database_sync_to_async`. Channels wraps that in `close_old_connections()` on entry *and*
exit (`channels/db.py`), and with `CONN_MAX_AGE` at Django's default of **0**, "old" means
immediately. So **every `doc_subscribe` permission check opens a fresh Postgres connection
and closes it.**

The flaky test's first message (`CRM Lead / no-such-lead`) takes that path; its second
(`No Such DocType / x`) short-circuits at `registry.has_doctype` and never touches the
database. Under a suite already churning connections, on a machine that has twice run out
of memory, occasionally exceeding a five-second wait is unsurprising.

**Fix applied.** `RECEIVE_TIMEOUT = 15` as a named constant in
`tests/test_phase6_realtime.py`, replacing twenty bare `timeout=5` literals, with the
evidence recorded beside it. The `receive_nothing(timeout=1)` calls are deliberately
unchanged — they assert *absence*, where a longer wait buys nothing and costs suite time.

**If this ever needs raising again, do not.** A second increase is the point at which this
stops being a slow machine. Fix `CONN_MAX_AGE` instead.

### The root cause is a production concern, not just a test one

This is the part worth carrying forward. In a running system:

* opening ten documents costs **ten Postgres connections**, opened and closed;
* a reconnect replays every subscription (phase 6 built that deliberately, and rightly),
  so one reconnect fans out into one connection per subscribed document;
* a backend restart has every client doing that at once. The backoff jitter spreads the
  *reconnects*; it does nothing about the fan-out inside each one.

**The fix is safe, which is not obvious.** The usual objection to persistent connections
under ASGI is one connection per concurrent request. It does not apply here:
`database_sync_to_async` uses `thread_sensitive=True` by default, so these calls share a
single executor thread — `CONN_MAX_AGE > 0` yields **one reused connection**, not many.

**Applied** (`CONN_MAX_AGE = 60`, `CONN_HEALTH_CHECKS = True`), as a decision of its own
rather than a side effect of the flake work. Measured on the real
`database_sync_to_async` path, by backend PID:

```
before (CONN_MAX_AGE=0):  [15132, 15056, 9272, 15512, 10228, 14800]  -> 6 connections
after  (CONN_MAX_AGE=60): [ 5540,  5540, 5540,  5540,  5540,  5540]  -> 1 connection
```

**60 is not derived, and does not need to be.** Nearly all the benefit is in the first
reuse: `0 -> 60` removes ~99.9% of the churn, and `60 -> 3600` removes the remaining 0.1%
during idle periods, when there is no load to slow down. Each held connection is a
Postgres backend holding ~5-10 MB, on a machine that has twice run out of memory. `None`
was avoided deliberately: unbounded lifetime pins a connection for the process's life, and
is the version that surprises people during a failover.

Nothing in this environment would drop a long-lived connection anyway - `idle_session_timeout`
is 0, and there is no pooler or load balancer between Django and Postgres. So the choice is
about the benefit curve, not about safety.

**Tests override it back to 0** (`config/settings/test.py`). Persistent connections and
`transaction=True` do not mix: a connection still held from the previous test blocks the
test database being dropped -

```
database "test_opencrm" is being accessed by other users
```

Observed rather than anticipated, and the failed teardown then poisoned the *next* run
with two unrelated-looking timeouts - which is worth knowing, because that failure mode
reads like a fresh flake rather than fallout.

---

## 2. `crm.api.accept_invitation` was never implemented — CLOSED in phase 8

> **Closed.** Implemented in `crm_app/api/auth_pages.py`, along with the `accept()` it
> needed, which did not exist either. The protections below were left exactly as they were —
> and the note addressed to "whoever builds the endpoint" was read and followed: redemption
> takes the key from the email, and neither the manager-only rule nor `SENSITIVE_FIELDS`
> was relaxed to make it easier.
>
> Kept rather than deleted, because it is the record of a hole being disarmed *before* the
> endpoint that could open it existed. That is the only reason building it was a small
> change rather than a risky one, and it is worth someone seeing that worked.

### Original entry

**Where:** `crm_app/tasks.py:214` sends the link; nothing serves it.
Upstream implements it at `crm/api/__init__.py:83`.

Inviting a colleague sends an email containing
`/api/method/crm.api.accept_invitation?key=...`. **That URL 404s.** So the invitation flow
is broken end to end: you can invite someone, they receive the mail, and they cannot join.

It is not recorded in any phase's progress file — the endpoint appears to have been missed
rather than deferred. Phase 8 owns auth and desk, so it belongs there.

### The security half is already disarmed

An invitation row carries the **role being granted** and a **`key` that redeems it**, and
upstream redeems by key alone — unauthenticated, with no binding to the caller. Upstream
also lets any Sales User read that table (bug #21), so reading a pending System Manager
invitation is enough to become one.

This port now gates `CRM Invitation` to managers and keeps `key` off the wire entirely
(`crm_app/permissions/platform_docs.py`, `CRMInvitation.SENSITIVE_FIELDS`). Both were put
in place **before** the endpoint exists, deliberately, so that implementing it cannot
quietly open the hole.

**Whoever builds the endpoint:** the protection is already there, so do not remove it to
make redemption easier. Redemption needs the key from the *email*, not from the API.

---

## 3. `Communication`, `File` and `Comment` leak content from invisible records

**Fixed.** Kept here rather than deleted, because the investigation turned up two extra
holes that the obvious fix would have left standing, and both are the kind of thing that
gets reintroduced.

Originally confirmed by driving the real route as a plain Sales User against a deal she is
refused:

```
GET /api/resource/CRM Deal/<bob's deal>   -> 403

GET /api/resource/Communication  -> 200  content='We can go down to 400k if they push back.'
GET /api/resource/File           -> 200  file_url='/private/files/signed-contract.pdf'
GET /api/resource/Comment        -> 200  content='Client is desperate, hold firm on price.'
POST /api/resource/Comment       -> 201  (forged onto that same deal)
```

These are the three widest remaining holes, and they are **worse than the record they
hang off**. A deal row leaks a number; its Communications leak the negotiating position in
prose, and its Comments leak what colleagues say to each other privately.

### Severity, stated accurately

* **`Communication` — the worst.** Full email bodies, subjects, senders and recipients.
  Every email ever exchanged about any lead or deal, readable by anyone with a login.
* **`Comment` — read and write.** Reading exposes internal remarks. Writing is the part
  worth noticing: a forged comment appears on a colleague's record under whatever
  authorship the row claims, on a record the author cannot see.
* **`File` — metadata today, documents tomorrow.** The row leaks the filename, the private
  URL and which record it hangs off. **Nothing currently serves the bytes** — there is no
  upload or download route in this port at all (`config/urls.py` has only `admin/` and
  `api/`). So today this is a metadata leak. **The day a file-serving route is added, that
  leaked URL becomes a live document link**, and whoever adds it must check permission at
  the serving layer as well as fixing the row rule.

### The fix, and it is one fix

All three carry `reference_doctype`/`reference_name` (`attached_to_doctype`/
`attached_to_name` on `File`), so the rule is the same in each case:

> **Defer to the referenced document.** Read it if you can read the parent; write it if
> you can write the parent.

Upstream already does exactly this for `File`, and the implementation is directly portable
— our model carries every field it reads:

```python
# frappe/core/doctype/file/file.py:908
if not doc.is_private and ptype in ("read", "select"):
    return True                                   # public files are public
if user != "Guest" and doc.owner == user:
    return True                                   # your own upload
if doc.attached_to_doctype and doc.attached_to_name:
    ref_doc = frappe.get_doc(doc.attached_to_doctype, doc.attached_to_name)
    if ptype in ["write", "create", "delete"]:
        return ref_doc.has_permission("write", user=user)
    return ref_doc.has_permission("read", user=user)
return False
```

Upstream protects `Communication` with a hook too
(`get_permission_query_conditions_for_communication`), but on a **different axis** — it
filters by which email accounts the user owns, not by the referenced document. That suits
a mail client; it does not suit a CRM where the question is "may I see this deal?".
Porting it verbatim would be faithful and wrong here. **Follow `File`'s shape for all
three.**

`Comment` has no hook upstream at all — it relies on the doctype's role permissions, which
grant only System Manager and Website Manager. That is the same "no hook means no
protection" trap as bug #14: upstream had a layer this port does not model.

### Two things to get right

1. **The list route needs `permission_query_conditions`, not just `has_permission`.**
   Deferring per row would be an N+1 across every timeline; the query hook has to express
   "referenced document is visible to me" as a subquery. `org_hierarchy` already builds
   that shape for Leads and Deals and is the thing to reuse.
2. **`get_activities` must keep working.** It already checks read on the parent
   (`_require_readable`) and then reads Comments and Communications over the ORM, so it is
   unaffected by a wire-level rule — but it is the regression to watch, because it is the
   one legitimate consumer of all three.

### What it actually took — three mechanisms, not one

The rule alone closes the *read* leak. It closes neither write path, and both were open.

**1. The rule.** `crm_app/permissions/attachments.py`. Defer to the referenced document:
read it if you can read the parent, write it if you can write the parent. The list route
gets a **subquery per restricted reference doctype**, not a per-row check — deferring row
by row would be an N+1 across every timeline in the product.

Only doctypes that *have* a rule are considered as targets, and only those with a
`CharField` primary key. `CRM View Settings` has a `BigAutoField`, and including it did not
merely waste a branch: Postgres refused `character varying = bigint` and the whole query
died.

**2. The create check was looking at an empty shell.** Both create doors —
`/api/resource/` POST and `frappe.client.insert` — called
`check_object_permission(entry.model(), "create", ...)`. That was correct when written and
documented as such: *"every registered rule decides `create` before it looks at any
field."* It stopped being true the moment a rule started deferring to a reference. An empty
instance has no reference, so **every create was waved through** and a comment could still
be forged onto an invisible record with the rule in place.

Both doors now build a candidate from the payload's own plain fields.

**3. Update could still move a row onto an invisible parent.** Write permission is checked
against the instance *as it stands* — which is the right question everywhere except a row
that names its own parent. A comment on your own deal passes that check; repointing it at
someone else's deal then plants a comment there. Same hole as (2), entered through
`update`.

Closed by `views.check_destination`, and made **opt-in** via
`DocTypeEntry.reference_fields`. Running it for every doctype would make every write in
the product pay a second `has_permission` call — a real cost against the org-hierarchy
rules, which query — to close a hole that exists in three places. An existing test caught
that: it asserts the hook receives exactly one `write`, and the universal version made it
two.

### The carve-outs, and why each is upstream's

* **public files stay public** (`file.py:916`) — brand logos and avatars are Files the
  product serves to everyone;
* **your own upload is yours** (`file.py:919`) — otherwise uploading to a record you later
  lose access to would strand your own file;
* **rows referencing nothing are not hidden** — an orphan hides nothing, and the product
  creates them;
* **rows referencing an unrestricted doctype are not hidden** — a comment on an
  Organization needs no check, since everyone can read Organizations.

### Still true, and worth carrying forward

**One hop, not transitive.** A Comment on a Communication on an invisible Deal is checked
against the *Communication*. Upstream does not chase the chain either, and doing so needs
cycle detection for a case the product does not produce.

**Files are served since 29 Sep 2026** (`docs/FINDINGS.md` 49), and the condition set
here was met: `/private/files/<name>` asks `file_has_permission` through
`find_file_by_url` before it opens the file (`frappe_core/file_views.py`), so a `file_url`
that leaked before the row rule is a link to a 403. `/files/` is public, as upstream's web
server serves it. `specs/SECURITY_MODEL.md`, "Frontend stage — files on disk", has the
per-route comparison.

---

## 4. The async stack, smoke-tested against a real broker

**Phase 5 A2/A3, resolved.** Every automated test runs Celery in
`CELERY_TASK_ALWAYS_EAGER` mode, which executes task bodies inline, in-process, with no
queue, no worker and no scheduler. That proves the *code* and nothing about the
*plumbing* — three things could be broken with the whole suite green:

* the worker cannot reach the broker, or cannot resolve tasks by name;
* beat starts but cannot parse the schedule;
* a task works inline but fails in a worker, which has **no request context**.

The third was the real risk. Several tasks call `session_user`, and in a worker the
ambient user is `Guest` unless the task rebinds it from its arguments.

### What was run, 2026-08-20

Memurai 8.2.7 on `127.0.0.1:6379`, a solo-pool worker on `default,long`, and beat with the
real schedule. All against `config.settings.local` — `eager` confirmed off first, since a
smoke test that silently ran eagerly would prove nothing while appearing to pass.

| Check | Result |
|---|---|
| Worker registers every task | ✅ 13 of 13 |
| Task queued and executed **in the worker** | ✅ `clear_old_versions`, `expire_invitations` — matching ids in both logs |
| Beat loads the schedule | ✅ 9 entries, crontabs correct |
| Beat → broker → worker, end to end | ✅ `lead-sync-5-minutes` fired at 18:15:07 and executed in the same second |
| `bulk_delete` above the enqueue threshold | ✅ 12 rows, deleted in the worker |
| **Worker rebinds the caller's identity** | ✅ see below |
| `flush_expired_tokens` against real rows | ✅ expired row and its blacklist entry gone, live row kept |
| Queues drained afterwards | ✅ `default` and `long` both 0 |

### The identity check, and why its first result looked like a failure

Twelve leads, six owned by the caller and six by a colleague, handed to the worker as the
caller. The task **raised `PermissionError` naming `CRM-LEAD-2026-00002`**.

That is the correct answer, and *which* row it named is the evidence: 00002 belongs to the
colleague. A worker running as `Guest` would have refused 00001 — the caller's own. So the
worker evaluated the real caller's permissions.

`authorize_bulk_delete` refuses the whole batch rather than deleting the permitted subset.
Both the request path and the worker call it, so the two agree. Re-run with twelve leads
all owned by the caller: all twelve deleted, returning `"success"` — which is upstream's
literal return value (`crm/api/doc.py:837`), not a count.

### Still not exercised

* **A retry.** `send_invitation_email` retries on `SMTPException`/`OSError`; no failing
  SMTP server was put in front of it.
* **Concurrency.** One solo-pool worker. Nothing has run with a prefork pool or two
  workers competing for a queue.
* **Queue routing.** The worker listened on `default` *and* `long`, so a task landing on
  the wrong queue would still have been picked up. Worth a worker per queue to prove
  routing.
* **A real schedule boundary.** The daily entries were never observed firing; only the
  `*/5` and `*/15` ones came round during the window.

---

## 5. Phase 6 verified: the frontend suite runs, and realtime works across processes

**Phase 6 A1/A2, resolved.** Both had been recorded as blocked, and one of the blockers
had quietly stopped being true.

### A1 — the frontend suite had never executed

`docs/internal/PROGRESS_PHASE_6.md` recorded: *"`frontend/node_modules` does not exist and there is no
network to install it, so `vitest` cannot run."* **Node 22.13 and network access are both
available now**, so the constraint was stale rather than real.

Result: **8 files, 152 tests, all passing.** Not just the socket tests — *nothing* in
`frontend/tests` had ever been run in this repo. The socket file has **23** tests, not the
22 the progress file claimed.

A mutation check confirms they are not vacuous: deleting the re-subscribe replay loop from
`src/socket.js` fails exactly one test —
`re-subscribes to open documents on reconnect` — and nothing else. That is the criterion
`PHASE_6_REALTIME.md` §4 names and the one whose absence is hardest to notice in
production, because a reconnected client looks live and receives nothing.

**Installing it needs a workaround, and this is the part worth knowing.** `package.json`
carries `"@framework/ui": "link:../../frappe/ui"` — upstream's own line, which assumes a
Frappe bench layout (`apps/crm/frontend` alongside `apps/frappe/ui`). This repo is not
laid out that way, so the link target does not exist:

* `yarn install` cannot resolve it;
* `npm install` rejects the `link:` protocol outright (`EUNSUPPORTEDPROTOCOL`).

The tests do not need it. `socket.test.js` mocks both of `socket.js`'s imports, so only
`vitest`, `happy-dom` and `frappe-ui` are actually required. They were installed into
`backend/scratch/vitest-install` (which has no `link:` line) and `frontend/node_modules`
was made a **directory junction** to it. Copying instead of junctioning was tried first and
abandoned: ~358 packages of small files took over ten minutes on this filesystem without
finishing.

That junction is a local convenience, not a committed artefact — `frontend/node_modules`
is gitignored. **Anyone wanting a real install should fix the layout or the link, not
repeat this.**

### A2 — realtime had only ever run in-process

Tests use `InMemoryChannelLayer`, which cannot demonstrate the architecture's central
claim (`config/settings/base.py`): *"A Celery worker publishing an event reaches the same
layer the web process serves from."* In-memory means in-*this*-memory; publisher and
subscriber were the same process.

Run against real `channels_redis` on Memurai, with a subscriber in one process and a
publisher in another:

```
subscriber: joined 'user_e299ab7f9873bd0cdac2a64182502fbc'
publisher:  pid 12456, publish() returned True
subscriber: RECEIVED {'type': 'realtime.event', 'event': 'smoke_event',
                      'message': {'hello': 'from another process'}}
```

The publisher calls the real `crm_app.realtime.publish`, not a hand-built frame, so what is
proven includes the flag gate, the layer lookup, the group hashing and the frame shape —
each of which could be wrong independently of whether Redis relays bytes.

### Still not exercised

* **No task actually publishes.** The only publishing Celery task is
  `run_product_reconciliation`, and it returns early unless `ENABLE_ERPNEXT` is on — and
  with it on, it raises at the phase-7 `_reconcile_products` seam *before* the publish
  line. So "a worker publishes to a browser" is architecturally proven (a worker is just
  another process, and cross-process delivery works) but has **no live caller to
  demonstrate it end to end** until phase 7.
* **No daphne, no browser.** `WebsocketCommunicator` in tests, raw channel-layer calls
  here. The actual ASGI server and a real browser socket remain untested.
* **The frontend tests use a fake WebSocket.** Backoff and reconnect are verified as
  logic, not against a server that really drops a connection.

---

## 6. Logging out does not revoke an access token that has already been issued

**Status: open, and accepted deliberately.** Recorded so the next person meets it here
rather than discovering it during an incident.

> **A note on where this was.** `docs/internal/PROGRESS_PHASE_8.md` and the docstring on
> `_blacklist_outstanding_tokens` both say this is *"recorded in `KNOWN_ISSUES` §4"*. It
> was not — §4 is the async smoke test, and this entry did not exist until now. The claim
> was written in good faith and nobody checked it. **This is that entry.**

### What happens

Login issues two tokens (`frappe_core/api/auth.py`):

| Token | Lifetime | How it is checked |
|---|---|---|
| **access** | 5 minutes (`SIMPLE_JWT.ACCESS_TOKEN_LIFETIME`) | **Signature only.** Nothing is looked up |
| **refresh** | 7 days | Looked up, and can be blacklisted |

`logout` blacklists the refresh token it is given; `logout_all_sessions` blacklists every
outstanding refresh token for the account (`crm_app/api/auth_pages.py:_blacklist_outstanding_tokens`).
Both stop the holder obtaining a **new** access token. Neither can stop one already issued,
because verifying it consults no state — that is what "stateless" means.

**So:** a user who believes they are compromised changes their password with *log out all
sessions* ticked, and the attacker keeps full read and write access **for up to five more
minutes**.

Upstream Frappe does not have this window: it uses server-side sessions, which die the
moment they are deleted. This port swapped to JWT as one of phase 0's two sanctioned
deviations (`PORT_PLAN.md` §3), and this is the part of that trade that was never paid.

### Three ways to close it

**1. Accept it.** Five minutes, documented, and the attacker must already hold a live
access token. This is the current state and the right one for a project that is not
holding anything an attacker would spend five minutes on.

*Cost: nothing. Risk: a five-minute window after every revocation.*

**2. Check a blacklist on every request.** The complete fix, and what the docstring means
by "a different decision". Every authenticated request asks whether this token's family
has been revoked.

*Cost: a cache or database round trip on **every** authenticated request, forever. It also
gives away the main thing JWT was chosen for. If the answer is going to be stateful, a
session is the simpler stateful thing.*

**3. Stamp the user, and reject tokens older than the stamp.** The targeted middle.
Add `password_changed_at` (or an integer `token_version`) to `User`; bump it in
`update_password` and wherever sessions are dropped; in the authentication class, reject an
access token whose `iat` predates it.

*Cost: one migration, one comparison per request — **and the user row is already loaded on
every authenticated request** for permission checks, so no extra query. Closes the window
for the case that actually matters (a deliberate revocation) and leaves ordinary requests
stateless.*

**Recommendation if this is ever picked up: option 3.** Option 2 is more complete and buys
little the project needs; option 1 is fine until the data is worth something. Whichever is
chosen, the test to write first is the one that fails today — call `logout_all_sessions`,
then use the access token issued before it, and require a 401.

### If option 1 stands, two things follow

* **`ACCESS_TOKEN_LIFETIME` is the size of the window.** It is 5 minutes and env-tunable
  (`JWT_ACCESS_TOKEN_LIFETIME_MINUTES`). Raising it in production for convenience widens
  this hole by exactly the same amount, and that trade should be made knowingly.
* **Do not describe logout as revocation** in any UI copy. "Signed out everywhere" is
  true; "your other sessions have been terminated" is not, for another five minutes.

## 7. Sending email from a lead or deal: the edges of what was ported

**Status: open, recorded 16 Sep 2026** with `frappe.core.doctype.communication.email.make`
(`crm_app/api/communication.py`, `crm_app/communication.py`). None of these breaks the
send button; each is a case the port answers differently from upstream, or not at all,
and the next person to touch mail should meet them here.

### A subject with a line break is a 500 on the inline path

Django refuses a header containing CR or LF (`BadHeaderError`, a `ValueError`) when the
message is built, which is the right security answer - it is header injection - but the
inline send (`now: 1`) catches only `SMTPException` / `OSError`, so the caller gets a
500 rather than a 417. Queued, the task fails without retry, since the exception is not
on its retry list, and the row stays claimed (see below). Upstream does not validate
the subject either. Left as is because choosing a sentence would be inventing copy
upstream does not have; if it is picked up, catch `BadHeaderError` in
`crm_app/api/communication.py:_send` and `throw` a 417, and clear the claim in the task.

### A worker killed between the claim and the send leaves the mail unsent

`send_communication` stamps `communication_date` under a row lock *before* the message
goes out, so two deliveries cannot both send, and clears it when the send raises. A
process killed in between leaves the row stamped and the mail unsent, and nothing
retries it. That is the same state as an upstream `Email Queue` row stuck in "Sending":
both designs err toward no duplicate. Upstream has a Desk screen to resend from; this
port has no screen and no `delivery_status`, so the only sign is a timeline entry whose
mail never arrived. If it matters, the fix is a `delivery_status` column set to
"Sending" at the claim and "Sent" after, plus a periodic task that re-queues rows stuck
in "Sending" older than a few minutes.

### Nothing sends without a Celery worker

Real clicks queue on `crm.send_communication_email`. A development machine with no
worker running logs the Communication and sends nothing; the http blocks and hand
testing pass `now: 1` to send inside the request. Not a defect, but the first thing to
check when "the email never arrived".

### Two smaller divergences, both stated in the code

* `frappe.desk.form.assign_to.remove_multiple` clears every open assignment; upstream's
  `get()` carries `limit=5`, so on a document with six assignees upstream leaves one.
* `submit_cancel_or_update_docs` cannot show upstream's "Bulk operation is enqueued in
  background." alert on the 20-to-500 path: a success response here carries no message
  channel. The frontend reloads the list either way.

## 8. Data Import is not built

The frontend ships three pages under `/crm/data-import` (`DataImport.vue`: the list,
the new-import form and the import detail) and frappe-ui's `DataImport` components
call three framework endpoints for them: `form_start_import`, `get_import_logs` and
`get_preview_from_template` under `frappe.core.doctype.data_import.data_import`. None
exists here: there is no Data Import doctype, no upload-and-map pipeline, no
background importer. Nothing links to the pages from the sidebar, so a user reaches
them only by typing the URL, and then sees a list that never loads.

Recorded 28 Sep 2026 when the guard test was extended to the calls frappe-ui makes
from inside the package (`tests/test_phase3_endpoints.py::test_every_library_dotted_path_resolves`);
the three paths sit in its `LIBRARY_OUT_OF_SCOPE` with a pointer here, so they cannot
be forgotten and cannot be mistaken for a regression. Building it is a feature, not a
fix: upstream's importer is about 1,500 lines with its own doctype, child table, file
handling and a background job.

---

## 9. The frontend is slow to load

Recorded 30 Sep 2026, from the hand testing in the browser (`docs/BROWSER_TESTING.md`):
the Vue app takes too long to load. **Deferred by decision**: nothing is to be changed
until the browser testing is finished and `phase-8-followup` is merged. This entry is
the note to come back to, and it is `docs/FINDINGS.md` 55.

### What is already known

* **A cold `yarn dev` start is the large, measured cost** (`docs/FINDINGS.md` 29).
  frappe-ui cannot be pre-bundled (finding 27: its source imports `~icons/lucide/*`
  virtual modules esbuild cannot resolve), so Vite serves its 930 source files raw and
  transpiles some 1,300 files before `main.js` runs: a minute or two on the development
  machine, down from many minutes before finding 29's fix. Nine tenths of that time was
  Vite's own TypeScript transpile and Vue compile, so it is bound by the CPU, not by the
  network or the backend. Every restart of the dev server pays it again.
* **The app makes about ten calls before the first screen settles**, and a list page
  about eight more (the App boot and N1 rows of the browser log). In the `runserver` log
  of the Notes pass the first ones after a start took 1.9 to 2.8 seconds each and later
  ones 0.15 to 0.7 seconds.
* **`main.js` waits for the boot-values call before it mounts** (`JWT_PATCH.md`, the
  third deviation), so nothing is drawn until the backend has answered once.

### What is not known

Which of these the slowness actually is. Nobody has timed a warm reload, a page change
inside the app, or a production build. A built bundle has none of the dev server's
per-file transpile, so the cold-start cost may not exist outside development at all.
Until that is measured, any fix is a guess.

### Where to start, in order

1. **Measure three things**: a cold dev load, a warm reload, and the same page from
   `yarn build` served statically. Browser Network tab, plus `vite --debug transform`
   for the dev numbers.
2. **If it is the dev server**: `server.warmup` for the entry files; making frappe-ui
   pre-bundlable by resolving the `~icons` imports in an esbuild plugin, which would
   undo the root of findings 27 and 29; a newer Vite.
3. **If it is the requests**: whether the boot calls can run in parallel or be merged,
   whether `getdoctype` and the view calls are cached between pages, and what the slow
   first calls on the backend are doing (each is a plain Django view; `runserver` under
   daphne is not a production server, so compare against a real ASGI setup first).
4. **If it is the bundle**: route-level code splitting and what the first chunk pulls
   in (TipTap, CodeMirror and echarts all arrive through frappe-ui).

Two rules already in force until then: start `yarn dev` once and leave it running, and
never run a second Vite server against the same tree.

---

## 10. Nothing is translated: the interface and the server's messages are English only

Recorded 30 Sep 2026, after the Language picker was made to work (`docs/FINDINGS.md` 58)
and picking a language turned out to change nothing on screen. **Deferred by decision**:
to be built once the browser testing is finished. This entry is the design to build from,
and it is `docs/FINDINGS.md` 59. The owner's two requirements are written into it: a
user's chosen language must also apply to the messages the server sends, and `enabled`
on a Language must mean what it means in Frappe.

### How upstream does it

Four pieces, all in the framework (`frappe/translate.py`, version-15) unless noted.

**1. The catalogue.** Each app ships one PO file per language: `crm/locale/<lang>.po`
(33 languages and the `main.pot` template) and `frappe/locale/<lang>.po` (39 and the
template). A line is a source string and its translation; a string may carry a context.
They are compiled to MO files when the site is built, and `get_translations_from_mo`
(`frappe/gettext/translate.py:347-378`) reads one locale into a dictionary: `msgid` ->
`msgstr`, or `msgid:context` -> `msgstr` for a contextual entry. `get_all_translations`
(148-183) merges them for a language: the parent language first (`pt` under `pt-BR`,
`get_parent_language`, 87-96), the language itself over it, every installed app in turn,
then the site's own `Translation` rows and the translated country names. The result is
cached per language. An entry with an empty translation is simply absent, so that one
string stays in English.

**2. Which language a request is in** (`get_language`, 36-84, and `get_user_lang`,
99-109). A `_lang` request parameter wins. A signed-in user gets `User.language`, else
the System Settings language, else `en`. A guest gets the `preferred_language` cookie,
then the browser's `Accept-Language`, each accepted **only if it, or its parent, is an
enabled Language** (`get_all_languages`, 951-966), and failing both the system language.

**3. The interface.** The page's boot values carry `translated_messages`, the whole
merged dictionary for that language (`crm/www/crm.py:81`, `get_messages_for_boot`). The
Vue app puts it on `window.translated_messages`, and `translation.js` looks each string
up as `message:context`, then `message`, then falls back to the source text and fills
the `{0}` placeholders. (`crm.api.get_translations` answers the same dictionary, but
nothing in this frontend calls it.)

**4. The server's own messages.** Every user-facing string in Python is written
`_("... {0}").format(value)`. `_` looks the template up in the same merged dictionary
for the request's language before the value is filled in, so "Incorrect current password.
Please try again." reaches a German user in German.

**What `enabled` does upstream.** Three things: the picker lists only enabled languages
(the Link search filters on it); a guest's cookie or browser language is honoured only
if enabled; and `get_boot_translations` ignores an explicitly requested language that is
not enabled. It does not un-set a language a user already holds. A System Manager flips
it on the Language record, in the Desk.

### What the port has today

* `Language` rows with `enabled`, seeded from the framework's list, and a picker that
  offers the enabled ones (finding 58). `User.language` is stored.
* The boot call answers `translated_messages: {}` (`crm_app/api/boot.py:65`) and
  `crm.api.get_translations` answers `{}`. So every lookup falls back to English.
* The server's messages are English literals, copied verbatim from upstream's `_()`
  strings (hard rule 4): 72 `throw(...)` calls and 128 direct `raise SomeError("...")`.
  Of those, 17 and 58 build the text with an f-string, which is the part that matters
  below.
* No System Settings doctype, so "the system language" has to be a Django setting.
* The boot call is made with the bearer token once a user is signed in (`main.js:87`
  goes through `jwtRequest`), so the server can know whose language to answer in.

### The plan, in the order to build it

**Step 1. Load the catalogues** (`frappe_core/translate.py`, new).
Copy `crm/locale/*.po` and `frappe/locale/*.po` into the repository as data, the way
`country_info.json` and `languages.csv` were copied. Read them with a PO parser in
Python (`polib`, or Babel, which is what upstream uses) rather than Django's
`compilemessages`: that command needs GNU gettext installed and a
`locale/<lang>/LC_MESSAGES/` layout, neither of which these files have, and the frontend
needs the result as a plain dictionary anyway. Build it in Frappe's exact shape, because
`translation.js` depends on it: `msgid` -> `msgstr`, `msgid:context` for contextual
entries, empty and fuzzy entries skipped, framework first and CRM over it, parent
language first and the language over it. Cache per language in the process; the files
never change at runtime.

**Step 2. Decide the language of a request.** A context variable set beside the session
user in `FrappeAPIView.initial`, holding upstream's answer: `_lang` parameter; signed-in
user -> `User.language` -> a `DEFAULT_LANGUAGE` setting -> `en`; guest -> the
`preferred_language` cookie -> `Accept-Language`, each only if enabled or its parent is
-> the setting -> `en`.

**Step 3. Translate the interface.** `boot.py` returns the merged dictionary for that
language in `translated_messages`, and `crm.api.get_translations` returns the same.
That alone translates the whole Vue app. A language with no file yields an empty
dictionary, which is English, and nothing breaks.

**Step 4. Translate the server's messages.** This is the requirement that needs care.
A `_()` function in `frappe_core/translate.py` that looks a template up for the request's
language and returns it unchanged when there is no entry. Then, in three moves:

1. *The literal messages, with no edits to call sites.* `throw()` and the base exception
   translate a message that is exactly a catalogue entry. That covers the roughly 125
   call sites that pass a plain string.
2. *The interpolated messages, one by one.* The roughly 75 f-string sites cannot match
   a catalogue entry, because the catalogue holds the template ("DocType {0} not found")
   and the f-string has already filled it in. Each becomes
   `_("... {0}").format(value)`, using upstream's template, which is the line each was
   ported from. Mechanical, but every site needs a look at its upstream source.
3. *A guard test.* Every literal passed to `_()` or `throw()` must exist in a `main.pot`.
   A message that does not is either a typo, which the test catches, or the port's own
   wording (the JWT and sign-in pages have some), which goes on a short reviewed list and
   stays English until someone translates it.

Texts that are not exceptions come after: the `_server_messages` titles, the notification
sentences built in `crm_app/api/comment.py` ("mentioned you in"), and the two email
templates in `crm_app/templates/emails/`. Upstream translates the first two with `_()`;
whether an email goes out in the sender's language or the recipient's needs reading
before it is decided.

**Step 5. `enabled`, as Frappe uses it.** The picker already honours it. Steps 2 and 3
add the other two uses: a guest's language is accepted only if enabled, and the boot
dictionary ignores a language that is not. Switching a language on or off stays a System
Manager action on the Language record (`/api/resource/Language/<code>`; upstream has no
CRM screen for it either). A user who already holds a language that is later disabled
keeps it, as upstream's `get_user_lang` does not check the flag.

**Step 6. Django's own strings.** Validation messages that Django and DRF produce ("This
field is required.") come from their own catalogues. Calling
`django.utils.translation.activate(lang)` for the request, with `USE_I18N` already on,
translates those for free and costs one line in step 2.

### Build it with System Settings and Currency

Decided 30 Sep 2026: three open findings are one piece of work and are to be built
together once the browser testing is finished.

* **`docs/FINDINGS.md` 64, System Settings.** The framework's single document holding
  the system-wide defaults. The port has none, so Settings → Defaults goes blank. It is
  also where upstream keeps the system language that step 2 above falls back to, so the
  `DEFAULT_LANGUAGE` setting named there becomes `System Settings.language` once the
  document exists.
* **`docs/FINDINGS.md` 63, Currency.** The Link target of `System Settings.currency` and
  of the dashboard's currency setting. Same kind of port as Language and Country.
* **`docs/FINDINGS.md` 59, translations.** This entry.

Order: Currency and System Settings first (a model each, the seed, the metadata, the boot
call reading the row), then the six steps above on top of them.

### Things to settle when it is built

* Only 33 of the 82 languages have a CRM file and only 17 are enabled by default; the
  two lists overlap but are not the same. Decide whether to enable exactly the languages
  that have a file.
* The http suite asserts English message text. It runs as users whose language is unset,
  so it should not move, but one block per translated message type is worth adding.
* Tests: the loader's shape against a real PO file, language resolution for a user and
  for a guest, the boot dictionary, one literal and one interpolated server message in a
  second language, and the guard test of move 3.

## 11. Upstream has moved on since the pin

The port's frontend, and every upstream line number cited in the specs and findings,
come from the clone at `6583bfcdc` (11 Sep 2026). `git fetch origin main` on 7 Oct 2026
put upstream `main` at `deedce73c` (30 Sep 2026), **514 commits ahead**. Anyone comparing
the port with a hosted demo will see differences that are not the port's: the first one
noticed was the Products grid's Edit Grid Fields dialog (`docs/FINDINGS.md` 84), reworked
upstream in `946c24d8f`, `53080db04` and `b29f99452`.

The clone's working tree is still at the pin; only `origin/main` moved. Moving the pin is
a piece of work of its own: re-run the frontend diff for the port's patches
(`frontend/JWT_PATCH.md`), re-check every cited line number, and re-port whatever the
514 commits changed on the backend side. Until then, compare against the clone, not the
cloud, and record cloud-only differences the way 84 is recorded.

