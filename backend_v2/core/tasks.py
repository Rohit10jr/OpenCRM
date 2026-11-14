import datetime

from celery import shared_task
from celery.schedules import crontab
from django.utils import timezone

VERSION_RETENTION_DAYS = 14
VERSION_CHURN_DOCTYPE = "CRM View Settings"


@shared_task(name="core.clear_old_versions")
def clear_old_versions(days: int = VERSION_RETENTION_DAYS) -> int:
    """Delete old saved-view churn without pruning any timeline history."""
    from core.models import Version

    cutoff = timezone.now() - datetime.timedelta(days=days)
    deleted, _ = Version.objects.filter(
        ref_doctype=VERSION_CHURN_DOCTYPE,
        creation__lt=cutoff,
    ).delete()
    return deleted


BEAT_SCHEDULE = {
    "clear-old-view-setting-versions": {
        "task": "core.clear_old_versions",
        "schedule": crontab(hour=0, minute=10),
    }
}
