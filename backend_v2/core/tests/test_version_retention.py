import datetime

import pytest
from django.utils import timezone

from core.models import Version
from core.tasks import (
    VERSION_CHURN_DOCTYPE,
    VERSION_RETENTION_DAYS,
    clear_old_versions,
)

pytestmark = pytest.mark.django_db


def _aged_version(administrator, ref_doctype: str, days_old: int) -> Version:
    row = Version(ref_doctype=ref_doctype, docname="record-1", data="{}")
    row.save(user=administrator)
    Version.objects.filter(pk=row.pk).update(
        creation=timezone.now() - datetime.timedelta(days=days_old)
    )
    return row


def test_it_deletes_nothing_today_because_we_do_not_track_saved_views(administrator):
    old = _aged_version(
        administrator,
        VERSION_CHURN_DOCTYPE,
        days_old=VERSION_RETENTION_DAYS + 1,
    )
    recent = _aged_version(
        administrator,
        VERSION_CHURN_DOCTYPE,
        days_old=VERSION_RETENTION_DAYS - 1,
    )

    assert clear_old_versions() == 1
    assert not Version.objects.filter(pk=old.pk).exists()
    assert Version.objects.filter(pk=recent.pk).exists()


def test_the_window_is_configurable(administrator):
    row = _aged_version(administrator, VERSION_CHURN_DOCTYPE, days_old=5)

    assert clear_old_versions(days=30) == 0
    assert Version.objects.filter(pk=row.pk).exists()
    assert clear_old_versions(days=3) == 1


@pytest.mark.parametrize("ref_doctype", ["CRM Lead", "CRM Deal"])
def test_lead_and_deal_history_is_never_pruned(administrator, ref_doctype):
    row = _aged_version(administrator, ref_doctype, days_old=365)

    assert clear_old_versions() == 0
    assert Version.objects.filter(pk=row.pk).exists()
