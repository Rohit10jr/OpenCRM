"""Celery application and the explicit per-app Beat schedule assembly."""

import os

from celery import Celery

from accounts.tasks import BEAT_SCHEDULE as ACCOUNTS_BEAT_SCHEDULE
from activities.tasks import BEAT_SCHEDULE as ACTIVITIES_BEAT_SCHEDULE
from configuration.tasks import BEAT_SCHEDULE as CONFIGURATION_BEAT_SCHEDULE
from contacts.tasks import BEAT_SCHEDULE as CONTACTS_BEAT_SCHEDULE
from core.tasks import BEAT_SCHEDULE as CORE_BEAT_SCHEDULE
from dashboard.tasks import BEAT_SCHEDULE as DASHBOARD_BEAT_SCHEDULE
from integrations.tasks import BEAT_SCHEDULE as INTEGRATIONS_BEAT_SCHEDULE
from notifications.tasks import BEAT_SCHEDULE as NOTIFICATIONS_BEAT_SCHEDULE
from sales.tasks import BEAT_SCHEDULE as SALES_BEAT_SCHEDULE
from sla.tasks import BEAT_SCHEDULE as SLA_BEAT_SCHEDULE

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")


def merge_beat_schedules(schedules):
    """Merge schedules, refusing ambiguous task names."""
    merged = {}
    for schedule in schedules:
        duplicates = merged.keys() & schedule.keys()
        if duplicates:
            names = ", ".join(sorted(duplicates))
            raise ValueError(f"Duplicate Celery beat schedule key(s): {names}")
        merged.update(schedule)
    return merged


BEAT_SCHEDULES = [
    CORE_BEAT_SCHEDULE,
    ACCOUNTS_BEAT_SCHEDULE,
    CONFIGURATION_BEAT_SCHEDULE,
    CONTACTS_BEAT_SCHEDULE,
    SLA_BEAT_SCHEDULE,
    SALES_BEAT_SCHEDULE,
    ACTIVITIES_BEAT_SCHEDULE,
    NOTIFICATIONS_BEAT_SCHEDULE,
    DASHBOARD_BEAT_SCHEDULE,
    INTEGRATIONS_BEAT_SCHEDULE,
]

app = Celery("opencrm_v2")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.conf.beat_schedule = merge_beat_schedules(BEAT_SCHEDULES)
