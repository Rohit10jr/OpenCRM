# Known issues

Things that are wrong, or not yet trustworthy, and are **not** recorded elsewhere.

Not a substitute for the per-phase progress files — those record what a phase built and
what it left. This is for problems that outlive a phase: flaky tests, half-built features,
and anything a future agent would otherwise rediscover the hard way.

| # | Issue | Status |
|---|---|---|
| 1 | A WebSocket test fails intermittently under full-suite load | **Unexplained** — do not paper over |
| 2 | `crm.api.accept_invitation` is not implemented; invitation links 404 | **Open** — phase 8; the security half is disarmed |

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
