# Phase 5 — PASS   [branch: phase-5-async]
Started: 2026-08-16   Finished: 2026-08-16   Commit: `dc774e6`

**Built:** The background-jobs layer. A Celery app with a Beat schedule transcribed from
`crm/hooks.py:scheduler_events`, the tasks behind the `frappe.enqueue` call sites, the
signals that fire them, and `crm_app/realtime.publish` as a stub for phase 6 to fill in.

**Tests:** **1073 passing**, 31 skipped (all pre-existing), 0 failing. 49 new.
Nothing skipped or weakened in this phase.

| Criterion (`PHASE_5_ASYNC.md` §5) | Covered by |
|---|---|
| Beat schedules match the table in §1 exactly | `test_beat_schedule_matches_hooks_py`, `test_cron_intervals_match_the_source`, `test_lead_sync_jobs_use_the_long_queue`, `test_telemetry_is_not_scheduled` |
| Deferred lead-sync tasks registered but no-op behind a flag | `test_lead_sync_tasks_are_registered_and_no_op` (×6), `test_lead_sync_raises_rather_than_lying_when_the_flag_is_on` |
| Bulk delete permission-checks inside the task | `test_bulk_delete_task_checks_permission_as_the_requesting_user`, `test_bulk_delete_re_authorizes_the_queued_arguments`, `test_bulk_delete_without_a_user_is_denied_rather_than_unfiltered` |
| Invitation email sends via the configured `Email Account` | `test_the_invitation_email_uses_the_default_outgoing_account`, `…_falls_back_when_no_account_is_configured` |
| `update_modified_background` fires on Communication and Comment insert | `test_commenting_bumps_modified_so_the_lead_rises`, `test_a_communication_also_bumps`, `test_non_comment_types_do_not_bump`, `test_only_leads_and_deals_bump`, `test_the_bump_is_off_when_the_setting_is_off` |
| Product reconcile emits its completion event | `test_product_reconciliation_publishes_its_completion_event` |
| Tasks are idempotent | `test_expire_invitations_is_idempotent`, `test_the_invitation_email_is_idempotent`, `test_bulk_delete_task_is_idempotent` |
| Test mode runs tasks eagerly | `test_tasks_run_eagerly_in_tests` |
| **No** SLA beat entry exists | `test_no_sla_job_exists_in_the_beat_schedule` |
| `update_modified_background` uses a bare `UPDATE` | `test_the_bump_does_not_rewrite_modified_by` |

## Two decisions taken from source

**No SLA sweep, and a test that says so.** `grep -n "sla\|service_level" crm/hooks.py`
returns nothing: SLA is computed at save time by `handle_sla_status`
(`crm_service_level_agreement.py:173-187`). The consequence is counter-intuitive — a lead
that breaches while nobody touches it keeps showing `First Response Due` until the next
write — and it is upstream behaviour. A periodic recompute would make our list views
disagree with upstream's for the same data, and nobody debugging that would think to look
at a scheduler entry. `test_no_sla_job_exists_in_the_beat_schedule` greps the schedule for
`sla`, `service_level`, `response_by` and `breach`, so adding one later is a failing build.

**Commenting bumps `modified`, and that is a feature.** The default list sort is
`modified desc`, so `update_modified_background` (`crm/utils/__init__.py:238-253`) is what
makes a lead rise to the top when someone comments on it. It writes a bare `update()`, so
`modified_by` keeps naming the last person who actually edited the document rather than
the worker — which is exactly what `assignment.rebuild_assign_cache` does, and why
`.save()` is wrong here.

That collided with an existing test. `test_the_cache_write_does_not_bump_modified`
asserted that commenting does *not* bump `modified` — true before phase 5, and the
opposite of upstream after it. It used a comment insert only as a convenient trigger, so
it now calls `rebuild_comment_cache` directly: the property it protects ("a cache refresh
is not a document edit") is unchanged, and the new behaviour has its own test, named in
the old test's docstring so the pair stay legible together.

**One deviation from upstream's schedule, in each direction.** `capture_feature_state` is
absent — it reports to Frappe's analytics, which is not this deployment's business. And
`crm.flush_expired_tokens` is new, because upstream issues no JWTs and so has nothing to
flush; without it `token_blacklist` grows forever.

---

## Review — tier 1 (Codex, PowerShell 7)

Ran clean, with the repo genuinely read (findings cite `file:line` throughout). Three
findings, **all real, all fixed**, and all in the same function.

**High — `delete_bulk_docs` authorized from the list filter alone.** It resolved the
batch through `base_queryset`, which applies `permission_query_conditions` — the **read**
rule. For CRM Lead and CRM Deal that happens to be the same rule the object hook applies,
so the tests passed. For the metadata doctypes it is not: a public `CRM View Settings`
row is readable by everyone and deletable only by its owner or an admin
(`permissions/metadata_docs.py`), and `CRM Form Script` is readable by everyone and
writable by admins. So this route deleted what `DELETE /api/resource/<dt>/<name>`
refuses.

This is phase 4's lesson wearing different clothes. There the blind spot was *a route I
had not thought about*; here it is *a rule I had not thought about* — I checked whether
the user can see the row and called that permission. `test_bulk_delete_respects_a_write_
rule_stricter_than_the_read_rule` pins it, and `AS_BUILT.md` now states the general form:
a write path needs both the list filter and the object rule, because they are allowed to
differ and deliberately do.

**Medium — the enqueue threshold was decoration.** Phase 3 defined
`BULK_DELETE_ENQUEUE_THRESHOLD = 10` with a comment saying phase 5 would turn it into a
real task, and phase 5 wrote `delete_bulk_docs_task` — but nothing ever called `.delay()`.
Upstream enqueues over ten items (`crm/api/doc.py:833`). Fixed by splitting the function
into `authorize_bulk_delete` / `perform_bulk_delete`, so the request path and the worker
can each run the same two halves. The task calls them directly rather than re-entering
`delete_bulk_docs`, which would enqueue the batch again and never terminate.

Authorization now runs twice for a large batch: once at request time so the caller gets a
refusal instead of a silent background failure, and once in the worker because **a queued
message is an argument list like any other** — replayed, hand-crafted, or simply delayed
past a permission change, it must not delete more than the user may delete now.

**Low — no retry on the invitation email.** §3 asks for "a Celery task with retry", and
Frappe's own Email Queue retries a failed send. Dropping an invite on the first refused
connection leaves someone unable to sign in with no trace. The retry list is narrow
(`SMTPException`, `OSError`) on purpose: `autoretry_for=(Exception,)` would replay a bug
in the task three times before surfacing it, turning one traceback into four.

Re-reviewed after the fixes: **no issues found**.

---

## C9, re-opened and re-closed

Fixing the High finding reintroduced exactly the N+1 that C9 exists to prevent — one
`has_permission` query per item. The fix could not be to drop the check, so the object
rule grew a batched form:

* `registry.DocTypeEntry.has_permission_batch`, registered through
  `register_permission_hooks` — the same shape phase 4 used for its metadata providers.
* `frappe_core.permissions.filter_object_permitted(doctype, instances, ptype, user)`,
  which uses the batch hook when present and falls back to the per-object hook otherwise.
* `org_hierarchy._has_permission_batch`, which mirrors `_has_permission` step for step and
  replaces its per-row `filter(pk=doc.pk)` with one `pk__in` over the batch.
* `metadata_docs._roles` is now memoised per request, the way `org_hierarchy._get_roles`
  already was. Every rule there is a role test, so with the roles cached a whole batch
  costs one query and needs no batch hook at all.

**It is a cost optimisation and nothing else** — a doctype without the hook gets the same
answer more slowly. That is a claim worth testing rather than asserting, so
`test_the_batched_object_rule_agrees_with_the_single_object_one` runs both implementations
over owned / someone-else's / third-party / unsaved rows, for five users and four ptypes,
and requires identical results. It caught a real discrepancy on its first run (the batch
version returned unsaved rows first instead of preserving input order).

The C9 query-count test needed one honest adjustment. It measures `delete_bulk_docs` at 2
and 12 items — and 12 now crosses the enqueue threshold, so under
`CELERY_TASK_ALWAYS_EAGER` the worker's re-authorization runs in the same process and
doubles the count for a reason that has nothing to do with C9. The test now pins the
threshold above its sample so it measures one execution, with the same sizes and the same
ratio assertion as before, and `test_delete_bulk_docs_worker_path_is_batched_too` measures
the worker path on its own.

---

## Still open

* ~~**`clear_old_versions` is a registered no-op.**~~ **Resolved, and the stated reason was
  wrong.** `Version` was modelled during the phase-4 review, but implementing this as "the
  body is three lines" would have been a general audit-table pruner — which deletes the
  timeline. Upstream prunes **only** `CRM View Settings` churn. Now implemented against
  that doctype, and idle because this port deliberately does not track saved views. Full
  reasoning: `specs/VERSION_HISTORY.md`.
* **The six lead-sync tasks are no-ops behind `ENABLE_FACEBOOK_LEAD_SYNC`.** Phase 7 owns
  the integration. With the flag *on* they raise `NotImplementedError` rather than
  returning success, because a flag that is on with nothing behind it is a config error,
  not a silent no-op.
* **`run_product_reconciliation` is flag-gated on `ENABLE_ERPNEXT`** and still publishes
  `crm_product_sync_complete`, because `PHASE_6_REALTIME.md` §2 lists that event as in
  scope and phase 6 needs a real emitter to test against.
* ~~**`crm_app/realtime.publish` returns `False`.**~~ **Resolved** — phase 6 supplied the
  transport.
* **No worker or broker runs in the test suite.** Still true, and now **smoke-tested
  manually** rather than untested: a worker and beat were run against Memurai on
  2026-08-20 and the whole chain passed, including the one thing eager mode cannot check —
  that the worker rebinds the caller's identity rather than running as `Guest`. Results
  and the four things still unexercised: `specs/KNOWN_ISSUES.md` #4.
* ~~**Beat is configured, never run.**~~ **Run** — 9 entries loaded, and
  `lead-sync-5-minutes` observed firing through to execution in the worker.
