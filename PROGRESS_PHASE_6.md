# Phase 6 — PASS   [branch: phase-6-realtime]
Started: 2026-08-16   Finished: 2026-08-16   Commit: `7693bfb`

**Built:** The realtime layer. A Channels consumer with JWT auth and permission-checked
document subscriptions, a publish helper that Celery tasks and model signals share, and
the frontend socket client that replaces socket.io.

**Tests:** **1106 passing**, 31 skipped (all pre-existing), 0 failing. 30 new on the
backend, plus 22 on the frontend. Nothing skipped or weakened in this phase.

| Criterion (`PHASE_6_REALTIME.md` §4) | Covered by |
|---|---|
| A notification created for user A reaches only user A | `test_a_notification_reaches_its_recipient`, `test_a_notification_does_not_reach_anybody_else` |
| Unauthenticated WebSocket connects are rejected | `test_a_connect_without_a_token_is_rejected`, `…garbage_token…`, `…refresh_token…`, `…disabled_users_token…` |
| Joining a doc group runs the phase-2 permission check | `test_subscribing_to_someone_elses_document_is_refused`, `test_a_refused_subscribe_really_does_not_join_the_group` |
| Event names and payloads match upstream exactly | `test_the_event_name_and_payload_match_upstream`, `test_a_comment_sends_the_payload_the_frontend_destructures`, `test_a_like_uses_its_own_docinfo_key`, `test_a_missing_message_is_an_empty_dict_not_null`, `test_publish_takes_the_message_second_like_frappe` |
| Celery tasks can publish | `test_a_celery_task_can_publish`, `test_the_sync_complete_event_reaches_the_session_user` |
| Client reconnects with backoff and re-subscribes | `frontend/tests/unit/socket.test.js` — `backs off…`, `caps the backoff…`, `re-subscribes to open documents on reconnect` |
| Nothing breaks when Channels is switched off | `test_the_flag_stops_publishers_reaching_the_transport`, `test_publish_swallows_a_broken_layer`, `test_creating_a_notification_still_works_with_realtime_off`, `test_the_asgi_application_drops_the_websocket_route_when_realtime_is_off` |

## The two rules that carry the phase

**Reject unauthenticated connects — before `accept()`.** Not downgraded to anonymous,
not accepted-and-filtered-later. An accepted anonymous socket is one that can ask to join
groups, and from that point every subsequent guard is the only thing between a stranger
and other people's leads.

**`doc_subscribe` runs the phase-2 check.** The client chooses the document name.
Without the check, realtime is a permission bypass with a pleasant API: subscribe to a
lead you cannot read and wait for its updates to arrive. `_may_read` applies the list
filter *and* the object rule — the same pair the HTTP detail route applies — so the two
cannot drift. A refusal is worded identically for "no permission" and "does not exist",
because a distinguishable refusal is an existence oracle.

Both are tested from the failing side.
`test_a_refused_subscribe_really_does_not_join_the_group` exists because the error
message is not the guarantee: a consumer that replied `"error"` and joined the group
anyway would pass the more obvious test.

## The protocol change

Frappe pushes over **socket.io**; Channels speaks **raw WebSocket**. There is no
configuration that makes one talk to the other, so `src/socket.js` is rewritten — the
second and last sanctioned frontend deviation, documented beside the first in
`frontend/JWT_PATCH.md`.

**No component changed.** The replacement reproduces `on` / `off(event)` /
`off(event, handler)` / `emit` exactly, so all seven `$socket` call sites are untouched.

Two things socket.io did for free had to be written:

* **Backoff**, exponential with full jitter, capped at 30 s. The jitter matters: without
  it every tab in every browser reconnects on the same tick after a backend restart.
* **Re-subscribe on reconnect.** Server-side group membership dies with the connection.
  Skip this and a reconnected client looks live and receives nothing — the failure mode
  that is hardest to notice and hardest to attribute.

The token rides in the **query string**, because a browser cannot set headers on a
WebSocket handshake. That puts it in access logs, which is the argument for the
five-minute access lifetime rather than an argument against it.

---

## Review — tier 1 (Codex, PowerShell 7), three passes

Ran clean each time, reading the repo itself. **Five findings, all real, all fixed.**

**High — `docinfo_update` went out with a null body.** `Activities.vue:590` is
`function handleDocinfoUpdate({ doc, key })` — it *destructures*. So live document
refresh did not merely fail to work; it threw on every comment. And an empty `{}` would
not have helped either: the handler returns early unless `key === 'comments'`. The
payload is now `{doc, key, action}`, matching `comment.py`'s `notify_change`, with the
comment-type → key map upstream uses.

This is the phase's own lesson: **an event nobody consumes correctly is not a feature.**
I had tested that the frame arrived. The frontend was the acceptance reference all along,
and reading it is what made the payload's shape non-negotiable.

**Medium — a missing message body was `null`.** `frappe.publish_realtime` normalises it to
`{}`. Same root cause as the High, one layer down.

**Medium — `crm_product_sync_complete` was broadcast, and announced a sync that never
ran.** `run_product_reconciliation(user=None)` fell through to a `None` user, which in
this port means *broadcast* — so every connected browser learned that somebody else's
ERPNext sync had finished. It also published on the skip path, where upstream returns
first (`reconcile_job.py:24-25`). Phase 5 had published unconditionally so phase 6 would
have an emitter to wire up; that was backwards, and the fix put the phase-7 body behind a
named seam (`_reconcile_products`) so the surrounding control flow can be tested without
a provider.

**Medium — `ENABLE_REALTIME` only dropped the route.** Clients could not reach the layer,
but every *publisher* still opened a Redis connection and waited for it to time out. That
turns "realtime is off" into "every comment write pauses" — the opposite of §4's last
criterion. The gate now sits in `get_channel_layer()`, where the transport is actually
reached.

**Medium — the publish signature was `(event, user, message)`.**
`frappe.publish_realtime` is `(event, message, user=...)`, and the sites still to be
ported pass the payload positionally (`crm/api/whatsapp.py:50`,
`integrations/exotel/handler.py:41`). Under the old order, a phase-7 agent writing
`publish("exotel_call", payload)` would have hashed the payload into a group name nobody
is in — and got `True` back. The reorder is one line; the test that pins it
(`test_publish_takes_the_message_second_like_frappe`) is the point.

**Low, and taken as a fix to the client rather than the server.** Codex noted that
`CLOSE_UNAUTHENTICATED = 4001` never reaches a browser: closing before `accept()` produces
an HTTP handshake failure and a generic 1006. Accepting-then-closing would deliver the
code but weakens "reject before accept", so the server is unchanged and the client now
treats *any close that never opened* as possibly-auth — refresh once, then fall through to
normal backoff, because that is also what a restarting backend looks like.

## Found while verifying, not by review

The subscription set was keyed on `` `${doctype} ${name}` `` and split back on the space.
**Every CRM doctype name contains a space**, so replaying a subscription to
`CRM Lead / CRM-LEAD-0001` would have subscribed to a doctype called `CRM`. It is keyed on
JSON now, which has no separator to get wrong. A stray NUL byte in the same position —
a writing artefact — had been masking it, since add and split agreed with each other.

---

## Still open

* ~~**The frontend test suite has not been executed here.**~~ **Run, and passing.** The
  recorded blocker - "there is no network to install it" - had stopped being true. **8
  files, 152 tests, all green**, and the socket file has 23 tests rather than the 22
  claimed below. A mutation check confirms they bite: removing the re-subscribe replay
  loop fails exactly one test, the criterion §4 names. Installing needs a workaround for
  upstream's `link:../../frappe/ui` line - `specs/KNOWN_ISSUES.md` #5.

  The original note follows, because its compensating measure was the right instinct: To compensate, the
  same 22 cases were executed against the real `src/socket.js` through a standalone Node
  harness (`backend/scratch/socket_check.mjs`, gitignored) that stubs the two imports and
  drives a fake WebSocket: **22 passed**, and a mutation check confirmed the
  re-subscribe case fails when the replay loop is removed. That is verification of the
  logic, not of the test file. **Run `yarn test:run` before trusting it.**
* **No ASGI server in the test run**, and `InMemoryChannelLayer` per RUNBOOK.md - but
  **cross-process delivery is now proven**. A subscriber in one process and a publisher in
  another, over real `channels_redis` on Memurai, using the real `publish()`:
  `specs/KNOWN_ISSUES.md` #5. daphne and a real browser socket remain untested, and no
  Celery *task* publishes today - the only one that would is gated behind phase 7.
* **Phase-6 tests run `transaction=True`** and are therefore slow (~2 min of the suite's
  ~3¾). `database_sync_to_async` uses a second connection, which cannot see an
  uncommitted transaction. `conftest.builtin_users` already existed to re-seed
  Administrator and Guest after the flush this implies.
* **A blacklisted refresh token does not close a live socket.** SimpleJWT blacklists
  refresh tokens, not access tokens, so an access token issued before logout keeps working
  until it expires. `test_a_blacklisted_token_is_rejected` documents the window rather
  than asserting it is closed — it is the same window the HTTP API has, and closing it
  means a blacklist check per connect.
* **Three events remain unported** — `crm_customer_created`, `exotel_call`,
  `whatsapp_message` — all phase 7, all listed in `PHASE_6_REALTIME.md` §2 as out of
  scope. The plumbing they need exists. `AS_BUILT.md` records that `whatsapp_message` is
  a **broadcast**, not a doc-room event, so phase 7 does not have to rediscover it.
* **`ENABLE_REALTIME` off still ships `channels` and `daphne` in `INSTALLED_APPS`.** They
  are unconditional requirements, so this is only a concern for a deployment that removes
  the packages — `realtime.get_channel_layer` already handles the ImportError, but Django
  startup would not.
