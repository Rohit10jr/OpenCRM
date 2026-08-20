# Known issues

Things that are wrong, or not yet trustworthy, and are **not** recorded elsewhere.

Not a substitute for the per-phase progress files — those record what a phase built and
what it left. This is for problems that outlive a phase: flaky tests, half-built features,
and anything a future agent would otherwise rediscover the hard way.

| # | Issue | Status |
|---|---|---|
| 1 | A WebSocket test fails intermittently under full-suite load | **Unexplained** — do not paper over |
| 2 | `crm.api.accept_invitation` is not implemented; invitation links 404 | **Open** — phase 8; the security half is disarmed |
| 3 | `Communication`, `File` and `Comment` leak content from records the caller cannot open | ✅ **Fixed** — see below for what it took |
| 4 | The async stack had never run against a real broker, worker or scheduler | ✅ **Smoke-tested** — passed; see below for what is still untested |
| 5 | The frontend test suite had never been executed; the realtime layer had never run on real Redis | ✅ **Both run** — 152 frontend tests pass, cross-process delivery confirmed |

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

### Do not just raise the timeout

That converts a question into a silence. If the cause is a leaked connection, a longer
wait makes the failure rarer and no less real, and the next person to see it has less
information than we do now.

**How to settle it:** run the full suite ten times and count. Roughly 1 in 20 says slow
machine, and raising the wait is then a legitimate fix with evidence behind it. Anything
like 1 in 3 says the teardown is wrong, and the fix is in `_connect`/`disconnect`, not the
timeout. Ten runs is about an hour of wall-clock and nobody has to watch it.

---

## 2. `crm.api.accept_invitation` was never implemented

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

**`File` remains metadata-only protection until something serves files.** There is still
no upload or download route. When one is added, it must check permission **at the serving
layer** — a `file_url` that leaked before this fix may already be written down somewhere.

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

`PROGRESS_PHASE_6.md` recorded: *"`frontend/node_modules` does not exist and there is no
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
