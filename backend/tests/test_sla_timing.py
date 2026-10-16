"""SLA deadlines, response status, and interval-based elapsed-time arithmetic."""

from datetime import datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.db import IntegrityError
from crm_app.models import (
    CRMCommunicationStatus,
    CRMDeal,
    CRMDealStatus,
    CRMHoliday,
    CRMHolidayList,
    CRMLead,
    CRMLeadStatus,
    CRMRollingResponseTime,
    CRMServiceDay,
    CRMServiceLevelAgreement,
    CRMServiceLevelPriority,
)
from crm_app.sla import SLAEngine
from frappe_core.models import BaseDocument

pytestmark = pytest.mark.django_db

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")


@pytest.fixture(autouse=True)
def kolkata_time_zone(settings):
    settings.TIME_ZONE = "Asia/Kolkata"


def aware_local(year, month, day, hour=0, minute=0, second=0, microsecond=0):
    return datetime(
        year, month, day, hour, minute, second, microsecond, tzinfo=IST
    ).astimezone(UTC)


@pytest.fixture
def sla_setup():
    lead_status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
    deal_status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
    open_status = CRMCommunicationStatus.objects.create(status="Open")
    replied = CRMCommunicationStatus.objects.create(status="Replied")
    holiday_list = CRMHolidayList.objects.create(
        holiday_list_name="India Holidays",
        from_date=datetime(2026, 1, 1).date(),
        to_date=datetime(2026, 12, 31).date(),
    )
    CRMHoliday.objects.create(
        parent_holiday_list=holiday_list,
        date=datetime(2026, 10, 15).date(),
        description="Holiday",
    )

    def make_sla(apply_on="CRM Lead", *, rolling=False):
        sla = CRMServiceLevelAgreement.objects.create(
            sla_name=f"{apply_on} SLA{' rolling' if rolling else ''}",
            apply_on=apply_on,
            enabled=True,
            default=True,
            holiday_list=holiday_list,
            rolling_responses=rolling,
        )
        CRMServiceLevelPriority.objects.create(
            parent_sla=sla,
            priority=open_status,
            default_priority=True,
            first_response_time=3600,
        )
        CRMServiceLevelPriority.objects.create(
            parent_sla=sla,
            priority=replied,
            first_response_time=3600,
            idx=2,
        )
        for index, workday in enumerate(
            ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"), start=1
        ):
            CRMServiceDay.objects.create(
                parent_sla=sla,
                workday=workday,
                start_time=time(9),
                end_time=time(17),
                idx=index,
            )
        return sla

    return {
        "lead_status": lead_status,
        "deal_status": deal_status,
        "open": open_status,
        "replied": replied,
        "make_sla": make_sla,
    }


@pytest.mark.parametrize(
    ("created", "expected"),
    [
        ((2026, 10, 14, 10, 0), (2026, 10, 14, 11, 0)),
        ((2026, 10, 14, 8, 0), (2026, 10, 14, 10, 0)),
        ((2026, 10, 13, 18, 0), (2026, 10, 14, 10, 0)),
        ((2026, 10, 16, 18, 0), (2026, 10, 19, 10, 0)),
        # Upstream's skip-day quirk preserves 15:00 through the holiday/weekend.
        ((2026, 10, 15, 15, 0), (2026, 10, 16, 16, 0)),
        ((2026, 10, 17, 15, 0), (2026, 10, 19, 16, 0)),
    ],
)
def test_response_by_across_working_time_and_skip_day_quirk(sla_setup, created, expected):
    sla_setup["make_sla"]()
    now = aware_local(*created)
    with patch("crm_app.sla.timezone.now", return_value=now):
        lead = CRMLead.objects.create(status=sla_setup["lead_status"], first_name="Ada")
    assert lead.response_by == aware_local(*expected)
    assert lead.sla_creation == now


def test_an_sla_with_no_working_hours_sets_no_deadline_instead_of_hanging(sla_setup):
    """UPSTREAM_BUGS.md 57: upstream's ``calc_time`` loops forever when no day has
    working time, hanging the save. Here it gives up and leaves ``response_by`` empty."""
    sla = sla_setup["make_sla"]()
    CRMServiceDay.objects.filter(parent_sla=sla).delete()
    now = aware_local(2026, 10, 14, 10, 0)
    with patch("crm_app.sla.timezone.now", return_value=now):
        lead = CRMLead.objects.create(status=sla_setup["lead_status"], first_name="Ada")
    assert lead.sla_id == sla.pk
    assert lead.response_by is None


def test_first_response_status_moves_from_due_to_failed_or_fulfilled(sla_setup):
    sla_setup["make_sla"]()
    created = aware_local(2026, 10, 14, 10)
    with patch("crm_app.sla.timezone.now", return_value=created):
        due = CRMLead.objects.create(status=sla_setup["lead_status"], first_name="Due")
        failed = CRMLead.objects.create(status=sla_setup["lead_status"], first_name="Failed")
        fulfilled = CRMLead.objects.create(
            status=sla_setup["lead_status"], first_name="Fulfilled"
        )
    assert due.sla_status == "First Response Due"

    with patch("crm_app.sla.timezone.now", return_value=aware_local(2026, 10, 14, 12)):
        failed.save()
    assert failed.sla_status == "Failed"

    replied_at = aware_local(2026, 10, 14, 10, 30)
    fulfilled.communication_status = sla_setup["replied"]
    with patch("crm_app.sla.timezone.now", return_value=replied_at):
        fulfilled.save()
    assert fulfilled.sla_status == "Fulfilled"
    assert fulfilled.first_responded_on == replied_at
    assert fulfilled.first_response_time == 1800


def test_rolling_responses_append_and_restart_the_deadline(sla_setup):
    sla_setup["make_sla"](rolling=True)
    with patch(
        "crm_app.sla.timezone.now", return_value=aware_local(2026, 10, 14, 10)
    ):
        lead = CRMLead.objects.create(status=sla_setup["lead_status"], first_name="Ada")

    lead.communication_status = sla_setup["replied"]
    with patch(
        "crm_app.sla.timezone.now", return_value=aware_local(2026, 10, 14, 10, 30)
    ):
        lead.save()
    assert list(
        CRMRollingResponseTime.objects.filter(parent=lead.pk).values_list("status", flat=True)
    ) == ["Fulfilled"]

    lead.communication_status = sla_setup["open"]
    with patch(
        "crm_app.sla.timezone.now", return_value=aware_local(2026, 10, 14, 11)
    ):
        lead.save()
    assert lead.response_by == aware_local(2026, 10, 14, 12)
    assert lead.sla_status == "Rolling Response Due"

    lead.communication_status = sla_setup["replied"]
    with patch(
        "crm_app.sla.timezone.now", return_value=aware_local(2026, 10, 14, 11, 45)
    ):
        lead.save()
    rows = list(
        CRMRollingResponseTime.objects.filter(parent=lead.pk).order_by("idx")
    )
    assert [row.status for row in rows] == ["Fulfilled", "Fulfilled"]
    assert rows[1].response_time == 4500
    assert lead.sla_status == "Fulfilled"


def upstream_elapsed_oracle(engine, start, end):
    current = start
    total = 0
    holidays = engine.get_holidays()
    workdays = engine.get_working_days()
    working_hours = engine.get_working_hours()
    while current < end:
        if (
            current.date() not in holidays
            and current.strftime("%A") in workdays
            and engine.is_working_time(current, working_hours)
        ):
            total += 1
        current += timedelta(seconds=1)
    return total


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ((2026, 10, 14, 8, 0, 0, 0), (2026, 10, 14, 9, 0, 2, 0)),
        ((2026, 10, 14, 16, 59, 58, 0), (2026, 10, 14, 17, 0, 2, 0)),
        ((2026, 10, 14, 8, 59, 59, 500000), (2026, 10, 14, 9, 0, 2, 0)),
        ((2026, 10, 14, 16, 59, 59, 500000), (2026, 10, 14, 17, 0, 1, 0)),
        ((2026, 10, 14, 16, 0, 0, 0), (2026, 10, 16, 10, 0, 0, 0)),
        ((2026, 10, 16, 16, 0, 0, 250000), (2026, 10, 19, 10, 0, 1, 0)),
    ],
)
def test_interval_elapsed_time_equals_upstream_second_loop(sla_setup, start, end):
    sla = sla_setup["make_sla"]()
    engine = SLAEngine(sla)
    local_start = datetime(*start)
    local_end = datetime(*end)
    assert engine.calc_elapsed_time(
        local_start.replace(tzinfo=IST), local_end.replace(tzinfo=IST)
    ) == upstream_elapsed_oracle(engine, local_start, local_end)


def test_deal_uses_the_same_sla_engine(sla_setup):
    sla_setup["make_sla"]("CRM Deal")
    with patch(
        "crm_app.sla.timezone.now", return_value=aware_local(2026, 10, 14, 10)
    ):
        deal = CRMDeal.objects.create(
            status=sla_setup["deal_status"], first_name="Ada"
        )
    assert deal.response_by == aware_local(2026, 10, 14, 11)
    assert deal.sla_status == "First Response Due"


def test_partial_save_does_not_run_the_sla_engine(sla_setup):
    sla_setup["make_sla"]()
    with patch(
        "crm_app.sla.timezone.now", return_value=aware_local(2026, 10, 14, 10)
    ):
        lead = CRMLead.objects.create(status=sla_setup["lead_status"], first_name="Ada")
    original = lead.response_by
    lead.communication_status = sla_setup["replied"]
    lead.save(update_fields=["communication_status"])
    assert lead.response_by == original
    assert lead.first_responded_on is None


def test_rolling_response_is_rolled_back_when_the_parent_save_fails(sla_setup):
    sla_setup["make_sla"](rolling=True)
    with patch(
        "crm_app.sla.timezone.now", return_value=aware_local(2026, 10, 14, 10)
    ):
        lead = CRMLead.objects.create(status=sla_setup["lead_status"], first_name="Ada")
    lead.communication_status = sla_setup["replied"]
    original_save = BaseDocument.save

    def fail_parent_save(instance, *args, **kwargs):
        if isinstance(instance, CRMLead):
            raise IntegrityError("parent write failed")
        return original_save(instance, *args, **kwargs)

    with (
        patch(
            "crm_app.sla.timezone.now",
            return_value=aware_local(2026, 10, 14, 10, 30),
        ),
        patch("frappe_core.models.BaseDocument.save", new=fail_parent_save),
        pytest.raises(IntegrityError),
    ):
        lead.save()
    assert not CRMRollingResponseTime.objects.filter(parent=lead.pk).exists()
