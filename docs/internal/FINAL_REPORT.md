# Final report — phases 3, 4, 5, 6

Written on `phase-6-realtime`, the last branch reached. All four phases requested were
built, gated and reviewed. **Stopped at phase 6 as instructed** — phase 7 (integrations)
and phase 8 (parked) were not started.

Read `PROGRESS_PHASE_<N>.md` for the detail of each phase; this is the cross-phase view.

---

## 1. What landed

| Phase | Branch | Commit | Tests after | New | Review |
|---|---|---|---|---|---|
| 3 — Endpoints | `phase-3-endpoints` | `762b0ac` | 952 | 139 | **Tier 1** (Codex, pwsh7) |
| 4 — Metadata | `phase-4-metadata` | `169cfc4` (+`5c180bc`) | 1024 | 72 | **Tier 1** |
| 5 — Async | `phase-5-async` | `dc774e6` (+`839be0e`) | 1073 | 49 | **Tier 1** |
| 6 — Realtime | `phase-6-realtime` | `7693bfb` | 1106 | 30 backend + 22 frontend | **Tier 1**, three passes |

Each branch was cut from the previous phase's completed tip, so `phase-6-realtime`
contains all four. **No phase was reviewed at tier 2 or 3.** Codex worked on every
attempt; the phases 0–2 spawn failure did not recur.

Gate results on the final branch: **1106 passed, 31 skipped, 0 failed**;
`makemigrations --check --dry-run` reports **no changes detected**.

## 2. Skipped tests

**Nothing is skipped for want of a service.** All 31 skips are parametrisation guards in
one pre-existing file:

| Count | Location | Reason |
|---|---|---|
| 28 | `tests/test_crm_models.py:220` | the case is not a child table |
| 3 | `tests/test_crm_models.py:244` | singletons are pinned to a fixed name |

Both come from tests that sweep every registered doctype and skip the rows a given
assertion does not apply to. The count has been 31 since phase 2 and none was added by
phases 3–6.

The infrastructure that looked like it would force skips did not: Celery runs eagerly,
Beat is asserted structurally, mail lands in `locmem`, and the WebSocket tests run on
`InMemoryChannelLayer` through `WebsocketCommunicator`.

**One suite was not executed** — see §5, first item. It is not a skip; it is an unrun
test file, and it is the single thing in this report most in need of a human.

## 3. Decisions taken without you

Gathered here because each one is a place where the source was ambiguous, silent, or
wrong, and I chose rather than stopped.

**Read from the source, not invented:**

1. **Error envelope shape** (phase 3) — settled by reading what the frontend consumes
   rather than guessing: `exc_type`, `_server_messages`, and the HTTP status the
   interceptor keys on.
2. **SLA is computed on write; no scheduler entry exists** (phase 5 §4). `grep -n
   "sla\|service_level" crm/hooks.py` returns nothing. The consequence is
   counter-intuitive — a lead that breaches while nobody touches it keeps showing
   `First Response Due` — and it is upstream behaviour. A periodic sweep would make our
   list views disagree with upstream's for identical data.
   `test_no_sla_job_exists_in_the_beat_schedule` makes adding one a failing build.
3. **`whatsapp_message` is a broadcast, not a document-room event**
   (`crm/api/whatsapp.py:49-56`). Recorded in `AS_BUILT.md` so phase 7 does not have to
   rediscover it.

**Deliberate deviations, each with a reason:**

4. **`capture_feature_state` is not scheduled** (phase 5). It reports to Frappe's
   analytics, which is not this deployment's business.
5. **`crm.flush_expired_tokens` is scheduled, and upstream has no equivalent.** Upstream
   issues no JWTs. Without it `token_blacklist` grows forever.
6. **A lead-sync task with its flag *on* raises `NotImplementedError`** rather than
   returning success. A flag that is on with nothing behind it is a config error, not a
   silent no-op. Same for `run_product_reconciliation`.
7. **`delete_bulk_docs` is one transaction and refuses the whole batch** if any item is
   denied. Upstream deletes row by row and logs failures; a half-applied bulk delete is
   worse than a rejected one.
8. **Bulk delete authorizes twice** — at request time so the caller gets a refusal instead
   of a silent background failure, and again in the worker because a queued message is an
   argument list like any other.
9. **The invitation email retries only `SMTPException` and `OSError`.** The spec says
   "a Celery task with retry"; `autoretry_for=(Exception,)` would replay a bug three times
   before surfacing it.
10. **`SITE_URL` was added as a setting.** Upstream's `frappe.utils.get_url()` has one
    origin because it serves the SPA and the API together; this port is split, and the
    invitation accept link points at `/api/method/...` on the backend.
11. **`registry.has_permission_batch` is new machinery with no upstream counterpart.**
    It exists because fixing a phase-5 security finding reintroduced the N+1 that C9
    forbids. It is an optimisation only, and
    `test_the_batched_object_rule_agrees_with_the_single_object_one` pins it to the
    single-object answer.
12. **WebSocket rejection stays *before* `accept()`**, which means the `4001` close code
    never reaches a browser. Codex flagged the dead code path; I fixed the **client**
    (treat any close that never opened as possibly-auth) rather than weaken the server.
13. **`docinfo_update` is emitted at all.** `PHASE_6_REALTIME.md` §2 lists only two events
    in scope, and this is a third. Without it §3's per-document groups are decorative —
    `doc_subscribe` would join a group nothing ever sends to. The event and payload are
    Frappe's own.
14. **Two test edits that look like weakening and are not**, both recorded in their
    docstrings:
    - `test_the_cache_write_does_not_bump_modified` used a comment insert as its trigger;
      phase 5 deliberately reverses that. It now exercises `rebuild_comment_cache`
      directly, preserving "a cache refresh is not a document edit".
    - `test_delete_bulk_docs_permission_check_is_batched` now pins the enqueue threshold
      above its sample, because 12 items crossed it and — under `ALWAYS_EAGER` — the
      worker's re-authorization ran in the same process and doubled the count for a reason
      unrelated to C9. Same sizes, same assertion, plus a new test for the worker path.

**Upstream bugs found and recorded** in `UPSTREAM_BUGS.md`: entries 10–13 (assignment
removal exposing `ignore_permissions`; products money fields computed client-side only;
`create_email_account` with no permission check; metadata doctypes with no row-level
protection).

## 4. The recurring lesson

Across four phases the same defect class kept surfacing, in a different disguise each
time. It is worth stating plainly for whoever continues:

> **A doctype's endpoints are not its attack surface. The generic `/api/resource/` route
> is.**

Phase 3: `POST /api/resource/` never checked create permission. Phase 4: private saved
views were readable and `CRM Form Script` writable through the generic route — I had
gated the endpoints and left the route open. Phase 5: `delete_bulk_docs` authorized from
the *list* filter, which for the metadata doctypes is weaker than the write rule, so it
deleted what `DELETE /api/resource/<dt>/<name>` refuses. Phase 6: the same question again,
now over a WebSocket — `doc_subscribe` names a document the client chooses.

In every case my own tests passed, because they tested the endpoint I had just written.
**A registered doctype with no permission hook is world-readable and world-writable**,
and Codex found each one.

## 5. For a human, before the port continues

Roughly in order of how much I would want someone to look.

1. **Run the frontend test suite.** `frontend/tests/unit/socket.test.js` (22 cases) is
   **written and unrun** — `frontend/node_modules` does not exist here and there is no
   network to install it. I verified the same 22 cases against the real `src/socket.js`
   through a standalone Node harness with stubbed imports (22 passed; a mutation check
   confirmed the re-subscribe case fails when the replay loop is removed), but that
   verifies the *logic*, not the *test file*. `yarn install && yarn test:run`.
2. **Nothing has touched real Redis, a real worker, or a real ASGI server.** Beat is
   asserted structurally and never run; channel delivery is proven in-process only. The
   first thing to try in a live environment is a Celery worker publishing
   `crm_product_sync_complete` to a browser held by the web process — that crosses both
   boundaries at once.
3. **Confirm the two frontend deviations are acceptable as built.** `frontend/JWT_PATCH.md`
   now documents both. The socket rewrite touches `src/socket.js` and moves
   `refreshAccessToken` into `src/auth/tokens.js`; **no component changed**.
4. **`ENABLE_REALTIME=0` still ships `channels` and `daphne` in `INSTALLED_APPS`.** Fine
   as long as they stay in `requirements.txt`. A deployment that removes the packages
   would fail at Django startup, not at publish time.
5. **A blacklisted refresh token does not close a live WebSocket.** SimpleJWT blacklists
   refresh tokens, not access ones, so an access token issued before logout works until it
   expires. It is the same window the HTTP API has;
   `test_a_blacklisted_token_is_rejected` documents it rather than asserting it closed.
   Closing it costs a blacklist check per connect.
6. **This SPA still has no login page.** Flagged since phase 0 and unchanged: upstream
   redirects to the Frappe desk's, and nothing in phases 0–6 owns that. Nothing else in
   the port is blocked on it, but nobody can log in without it.
7. **Phase-6 tests need `transaction=True` and cost ~2 minutes** of the suite's ~3¾.
   `database_sync_to_async` uses a second connection, which cannot see an uncommitted
   transaction. Unavoidable for `WebsocketCommunicator`; worth knowing before someone
   tries to "fix" the slowdown.

## 6. What the next session should tackle first

**Phase 7 — integrations**, which is what every remaining flag is waiting for. In
dependency order, and all four flags currently default off:

- `ENABLE_ERPNEXT` — `_reconcile_products()` in `crm_app/tasks.py` is a named seam that
  raises; filling it in also lights up `crm_customer_created`.
- `ENABLE_FACEBOOK_LEAD_SYNC` — six registered no-op tasks, already on the right queues
  and cron intervals.
- `ENABLE_TWILIO` / `ENABLE_EXOTEL` — `exotel_call` is listed in
  `PHASE_6_REALTIME.md` §2 and needs no new plumbing.
- `ENABLE_WHATSAPP` — **use `realtime.publish`, not `publish_to_doc`**; see §3 item 3.

Two smaller things that are cheap and would pay off immediately:

- `clear_old_versions` is a registered no-op because `Version` was never modelled. The
  beat entry exists so the schedule matches `hooks.py`; the body is three lines once the
  model does.
- `Dynamic Link` landed in phase 3 for `CRM Call Log.links` (C5) and also unblocks
  `Contact.links`, which `Contact.autoname` reads —
  `frappe_platform.Contact.name_links_suffix` is the waiting seam.

**Do not start by rewriting the framework layer.** `specs/AS_BUILT.md` has an "Added by
phase N" section for each of 3, 4, 5 and 6; read it first. It is the single biggest
time-waster available, and it is why that file leads the reading order.
