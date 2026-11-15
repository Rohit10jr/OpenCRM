import datetime

from celery import shared_task
from celery.schedules import crontab
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.module_loading import import_string

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


@shared_task(name="core.bulk_update_docs")
def bulk_update_docs(
    viewset_path, docnames, action="submit", data=None, user_name=None
):
    """Re-run an opted-in resource's bulk update as its requesting user."""

    from core.mixins import BulkUpdateMixin
    from core.mixins.bulk_update import bulk_update_documents
    from core.query import by_name
    from core.views import DocumentViewSet

    viewset_class = import_string(viewset_path)
    if not (
        isinstance(viewset_class, type)
        and issubclass(viewset_class, DocumentViewSet)
        and issubclass(viewset_class, BulkUpdateMixin)
    ):
        raise TypeError("Bulk-update task requires an opted-in DocumentViewSet")

    user = by_name(get_user_model(), user_name).first() if user_name else None
    if user is None or not user.enabled:
        return list(docnames)
    return bulk_update_documents(viewset_class, docnames, action, data, user)


@shared_task(name="core.delete_bulk_docs")
def delete_bulk_docs(
    viewset_path, items, delete_linked=False, user_name=None, urlconf=None
):
    """Reauthorize and bulk-delete as the requesting user without re-enqueueing."""

    from core.resources import PRODUCTION_URLCONF

    if urlconf is None:
        urlconf = PRODUCTION_URLCONF
    elif urlconf not in (PRODUCTION_URLCONF, settings.ROOT_URLCONF):
        raise ValueError(f"Bulk-delete task received unknown URLconf {urlconf!r}")

    from core.mixins import BulkDeleteMixin
    from core.mixins.bulk_delete import authorize_bulk_delete, perform_bulk_delete
    from core.query import by_name
    from core.views import DocumentViewSet

    viewset_class = import_string(viewset_path)
    if not (
        isinstance(viewset_class, type)
        and issubclass(viewset_class, DocumentViewSet)
        and issubclass(viewset_class, BulkDeleteMixin)
    ):
        raise TypeError("Bulk-delete task requires an opted-in DocumentViewSet")

    user = by_name(get_user_model(), user_name).first() if user_name else None
    targets = authorize_bulk_delete(
        viewset_class, [str(item) for item in items], user
    )
    perform_bulk_delete(viewset_class, targets, user, delete_linked, urlconf)
    return "success"


BEAT_SCHEDULE = {
    "clear-old-view-setting-versions": {
        "task": "core.clear_old_versions",
        "schedule": crontab(hour=0, minute=10),
    }
}
