# Phase 5 — Background Jobs

> **PROVISIONAL** — the phase-0 agent must revise and flip to Authoritative.

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

## 3. Email

Frappe has its own queue with retry and per-account config (`Email Account`, ported in
phase 1 cluster 1). Use Django's email backend plus a Celery task with retry.
Outbound identity comes from the configured `Email Account`, not `DEFAULT_FROM_EMAIL`.

---

## 4. SLA timers

`crm_service_level_agreement` + `crm_rolling_response_time` + `crm_status_change_log`
drive first-response and resolution tracking against business hours
(`crm_service_day`) and holidays (`crm_holiday_list`).

> **VERIFY:** whether upstream computes SLA state on write (in the Deal/Lead
> controller) or on a schedule. Read `crm_service_level_agreement.py` before choosing
> — if it is write-time, do **not** invent a periodic job.

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
