"""Celery app and Beat schedule.

Upstream runs RQ through ``frappe.enqueue`` and a ``scheduler_events`` dict in
``crm/hooks.py``. The queue mapping is the spec's (`PHASE_5_ASYNC.md` intro):
``short`` -> ``default``, ``long`` -> ``long``.

**The schedule is transcribed from `crm/hooks.py:217-231`, and there is no SLA entry.**
`PHASE_5_ASYNC.md` §4 settles that from source: SLA is computed on write, and adding a
sweep here would make our list views disagree with upstream's for the same data.
`test_no_sla_job_exists_in_the_beat_schedule` exists so a later agent cannot add one
quietly.
"""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("crm")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

#: RQ queue -> Celery queue.
QUEUE_DEFAULT = "default"
QUEUE_LONG = "long"

#: One entry per `crm/hooks.py:scheduler_events` row, minus telemetry.
#:
#: ``crm.telemetry.capture_feature_state`` is deliberately absent — it reports feature
#: usage to Frappe's analytics, which is upstream's business and not this deployment's.
#: `PHASE_5_ASYNC.md` §1 marks it **skip**.
app.conf.beat_schedule = {
    # daily
    "expire-invitations": {
        "task": "crm.expire_invitations",
        "schedule": crontab(hour=0, minute=0),
        "options": {"queue": QUEUE_DEFAULT},
    },
    "clear-old-view-setting-versions": {
        "task": "crm.clear_old_versions",
        "schedule": crontab(hour=0, minute=10),
        "options": {"queue": QUEUE_DEFAULT},
    },
    # Not upstream — see PHASE_5_ASYNC.md §2a. Exists because we chose JWT, and
    # `token_blacklist` grows by ~12 rows per active user per hour with nothing
    # removing them.
    "flush-expired-tokens": {
        "task": "crm.flush_expired_tokens",
        "schedule": crontab(hour=1, minute=0),
        "options": {"queue": QUEUE_DEFAULT},
    },
    # lead sync — phase 7. Registered now, no-op behind a flag (§1).
    "lead-sync-daily": {
        "task": "crm.sync_leads_daily",
        "schedule": crontab(hour=0, minute=30),
        "options": {"queue": QUEUE_LONG},
    },
    "lead-sync-hourly": {
        "task": "crm.sync_leads_hourly",
        "schedule": crontab(minute=0),
        "options": {"queue": QUEUE_LONG},
    },
    "lead-sync-monthly": {
        "task": "crm.sync_leads_monthly",
        "schedule": crontab(hour=0, minute=45, day_of_month=1),
        "options": {"queue": QUEUE_LONG},
    },
    "lead-sync-5-minutes": {
        "task": "crm.sync_leads_5_minutes",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": QUEUE_LONG},
    },
    "lead-sync-10-minutes": {
        "task": "crm.sync_leads_10_minutes",
        "schedule": crontab(minute="*/10"),
        "options": {"queue": QUEUE_LONG},
    },
    "lead-sync-15-minutes": {
        "task": "crm.sync_leads_15_minutes",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": QUEUE_LONG},
    },
}
