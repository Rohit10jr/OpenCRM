# Phase 5 — Background Jobs

> **BUILT** — phase 5 landed on `phase-5-async`, 1073 tests passing, reviewed.
> See `docs/internal/PROGRESS_PHASE_5.md` for what was built and what is still open, and
> `specs/AS_BUILT.md` for the seam it added.
>
> **§4 is settled from source: SLA is computed on write and there is no beat entry for
> it.** A test asserts the schedule contains nothing SLA-shaped, so adding one later is a
> failing build rather than a silent divergence.
>
> **Read `specs/AS_BUILT.md` first.** It lists what phases 0-4 actually built; where it
> and this spec disagree, it wins.

**Fan out.** Needs phase 1. Celery + Redis (Redis is already required by phase 6).

Upstream uses RQ via `frappe.enqueue` and a `scheduler_events` dict in `hooks.py`.
Map RQ queues to Celery queues: `short` → `default`, `long` → `long`.

---

## 1. Scheduled jobs — verified from `hooks.py`

Use Celery Beat. Schedules are exact:

| Schedule | Job | Source |
|---|---|---|
| daily | expire pending invitations | `crm_invitation.expire_invitations` |
| daily | clear old view-setting versions | `crm_view_settings.clear_old_versions` |
| daily | telemetry feature state | `telemetry.capture_feature_state` — **skip**, upstream analytics |
| daily (long) | lead sync — daily sources | `lead_syncing.background_sync` |
| hourly (long) | lead sync — hourly sources | `lead_syncing.background_sync` |
| monthly (long) | lead sync — monthly sources | `lead_syncing.background_sync` |
| `*/5 * * * *` | lead sync — 5-minute sources | `lead_syncing.background_sync` |
| `*/10 * * * *` | lead sync — 10-minute sources | `lead_syncing.background_sync` |
| `*/15 * * * *` | lead sync — 15-minute sources | `lead_syncing.background_sync` |

All six lead-sync jobs are **phase 7 (deferred)** — register the beat entries now,
leave the tasks as no-ops behind a feature flag.

---

## 2. Enqueued jobs — verified call sites

| Job | Source | Notes |
|---|---|---|
| Bulk delete | `api/doc.py:834` | Backs `delete_bulk_docs`. Permission-check **per item**, inside the task |
| Invitation email | `crm_invitation.py:45` | `frappe.sendmail` → Django email backend |
| Product reconcile | `crm_product/reconcile_job.py:12` | Emits `crm_product_sync_complete` on finish |
| `update_modified_background` | `utils/__init__.py:249` | Fires on `Communication`/`Comment` insert; touches the parent's `modified` so lists re-sort |
| Lead sync | `lead_sync_source.py:62` | `queue="long"` — phase 7 |

`update_modified_background` looks trivial and is not: it is why a lead jumps to the
top of the list when someone comments. Skip it and the UI feels broken in a way that is
hard to trace back.

---

## 2a. Flush expired JWTs — new, and not optional

Not in upstream (Frappe uses session cookies); it exists because of our JWT decision.

`token_blacklist` records **every** rotated and revoked refresh token, and nothing
removes them. With `ROTATE_REFRESH_TOKENS` on and a 5-minute access token, each active
user rotates ~12 times an hour, so the table grows by roughly *12 rows per user per hour*
and never shrinks.

SimpleJWT ships the cleanup: `manage.py flushexpiredtokens`. Register it as a **daily
Beat job**. It only deletes tokens already past their expiry, so it cannot log anyone out.

Deleting nothing is the failure mode to watch: if the job silently stops, the symptom is
a slowly growing table and slower blacklist lookups, not an error.

## 2b. What already exists

Several things this phase would otherwise build were done during the phase 0-2 review:

- **`assignment.rebuild_assign_cache`** and **`doc_caches.rebuild_comment_cache`** already
  maintain `_assign` and `_comments` by signal. Both write with a bare `update()`, never
  `save()` — copy that pattern for `update_modified_background`, which exists precisely so
  a comment does not re-stamp `modified_by` while still reordering the list.
- **`doc_caches.add_tag` / `remove_tag`** maintain `_user_tags`.
- **`children.delete_polymorphic_children`** cascades child rows on parent delete.
- **`crm_app.conversion.convert_to_deal`** is complete, in one transaction.

## 3. Email

Frappe has its own queue with retry and per-account config (`Email Account`, ported in
phase 1 cluster 1). Use Django's email backend plus a Celery task with retry.
Outbound identity comes from the configured `Email Account`, not `DEFAULT_FROM_EMAIL`.

---

## 4. SLA timers

`crm_service_level_agreement` + `crm_rolling_response_time` + `crm_status_change_log`
drive first-response and resolution tracking against business hours
(`crm_service_day`) and holidays (`crm_holiday_list`).

> **ANSWERED — SLA is computed entirely on write. There is no scheduled job. Do not
> invent one.**
>
> Evidence from source:
>
> | Fact | Location |
> |---|---|
> | `before_validate()` → `set_sla()` picks the applicable SLA | `crm_lead.py:78-79`, `crm_deal.py:80-81` |
> | `before_save()` → `apply_sla()` recomputes every SLA field | `crm_lead.py:99-100`, `crm_deal.py:104-105` |
> | `apply(doc)` mutates the doc in place — `sla_creation`, `first_responded_on`, `first_response_time`, `response_by`, `sla_status` | `crm_service_level_agreement.py:74-79` |
> | `scheduler_events` contains **no** SLA entry — only invitations, view-settings cleanup, telemetry and lead sync | `hooks.py:217-231` |
>
> A `grep` for `sla|service_level` across `hooks.py` returns nothing at all.
>
> **The consequence is counter-intuitive and must be preserved.** `handle_sla_status`
> decides "Failed" by comparing `response_by < now_datetime()` *at save time*
> (`crm_service_level_agreement.py:173-187`). A lead that breaches its SLA while nobody
> touches it therefore keeps showing `First Response Due` until the next write. That is
> upstream behaviour, not a bug to fix here: adding a periodic sweep would make our list
> views disagree with upstream's for the same data. If a product decision later wants
> live breach detection, that is a **new feature**, and it belongs in its own spec with
> the divergence stated explicitly.

Timezone handling is the risk. Business hours are local; store UTC, compute in the
site timezone.

---

## 5. Acceptance criteria

- [ ] Beat schedules match the table in §1 exactly
- [ ] Deferred lead-sync tasks are registered but no-op behind a flag
- [ ] Bulk delete permission-checks each item inside the task, not only at request time
- [ ] Invitation email sends via the configured `Email Account`
- [ ] `update_modified_background` fires on Communication and Comment insert
- [ ] Product reconcile emits its completion event (phase 6 consumes it)
- [ ] Tasks are idempotent — a retry must not double-apply
- [ ] Test mode runs tasks eagerly (upstream patches enqueue to run inline; do the same with `CELERY_TASK_ALWAYS_EAGER`)
- [ ] **No** SLA beat entry exists — §4. A test should assert the beat schedule contains
      nothing SLA-related, so a later agent cannot quietly add one
- [ ] `update_modified_background` uses a bare `UPDATE`, not `.save()` — phase 0's
      `assignment.rebuild_assign_cache` is the worked example of a cache write that must
      not re-stamp `modified_by`
