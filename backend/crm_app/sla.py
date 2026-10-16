"""Service Level Agreement selection and business-hours timing."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from crm_app.conditions import ConditionError, evaluate, is_empty
from crm_app.models.sla import (
    CRMRollingResponseTime,
    CRMServiceLevelAgreement,
)

logger = logging.getLogger(__name__)


def get_sla(doc) -> CRMServiceLevelAgreement | None:
    """Return the first applicable SLA, with a default policy considered last.

    Unlike upstream's ``safe_eval``, a stored condition that can no longer be evaluated
    is logged at warning level and treated as a non-match. One stale policy therefore
    cannot prevent every lead or deal from being saved.
    """

    now = timezone.now()
    local_date = timezone.localtime(now).date()
    slas = CRMServiceLevelAgreement._default_manager.filter(
        apply_on=doc.get_doctype(),
        enabled=True,
    ).filter(
        Q(start_date__isnull=True) | Q(start_date__lte=local_date),
        Q(end_date__isnull=True) | Q(end_date__gte=local_date),
    )

    priority = getattr(doc, "communication_status_id", None)
    if priority:
        slas = slas.filter(priorities__priority_id=priority)

    # The upstream query declares no ordering. Clear this model's list-screen ordering
    # (``-modified``), which must not silently turn "first" into "most recently edited".
    candidates = list(slas.order_by().distinct())
    candidates.sort(key=lambda sla: bool(sla.default))

    for sla in candidates:
        try:
            if is_empty(sla.condition_json) or evaluate(sla.condition_json, doc):
                return sla
        except ConditionError as exc:
            logger.warning(
                "SLA %s condition could not be evaluated: %s",
                sla.pk,
                exc,
            )
    return None


def _convert_datetime(value: datetime | None, *, for_storage: bool = False) -> datetime:
    """Cross the one boundary between Django's aware UTC and upstream's local-naive time."""

    if value is None:
        value = timezone.now()
    zone = ZoneInfo(settings.TIME_ZONE)
    if for_storage:
        if timezone.is_aware(value):
            return value.astimezone(zone)
        return timezone.make_aware(value, zone)
    if timezone.is_naive(value):
        return value
    return value.astimezone(zone).replace(tzinfo=None)


def _now_local() -> datetime:
    return _convert_datetime(timezone.now())


def _time_to_seconds(value: time | timedelta) -> int:
    if isinstance(value, timedelta):
        return int(value.total_seconds())
    return value.hour * 3600 + value.minute * 60 + value.second


def _timedelta_microseconds(value: timedelta) -> int:
    return ((value.days * 86_400 + value.seconds) * 1_000_000) + value.microseconds


def _ceil_seconds(value: timedelta) -> int:
    microseconds = _timedelta_microseconds(value)
    return -(-microseconds // 1_000_000)


class SLAEngine:
    """The methods of upstream's ``CRMServiceLevelAgreement`` controller."""

    def __init__(self, sla: CRMServiceLevelAgreement):
        self.sla = sla
        self._priorities = list(sla.priorities.all())
        self._working_hours = list(sla.working_hours.all())
        self._holidays: list[date] | None = None
        self._rolling_rows: list[CRMRollingResponseTime] | None = None

    def apply(self, doc) -> None:
        self.handle_creation(doc)
        self.handle_communication_status(doc)
        self.handle_targets(doc)
        self.handle_sla_status(doc)
        self.handle_rolling_sla_status(doc)

    def handle_creation(self, doc) -> None:
        doc.sla_creation = doc.sla_creation or _convert_datetime(
            _now_local(), for_storage=True
        )

    @staticmethod
    def _communication_status_changed(doc) -> bool:
        if doc._state.adding or not doc.pk:
            return False
        previous = (
            type(doc)
            ._default_manager.filter(pk=doc.pk)
            .values_list("communication_status_id", flat=True)
            .first()
        )
        return previous != doc.communication_status_id

    def handle_communication_status(self, doc) -> None:
        if not self._communication_status_changed(doc):
            return
        self.set_first_responded_on(doc)
        self.set_first_response_time(doc)
        if self.sla.rolling_responses:
            self.set_rolling_responses(doc)

    def set_first_responded_on(self, doc) -> None:
        if doc.communication_status_id != self.get_default_priority():
            now = _convert_datetime(_now_local(), for_storage=True)
            doc.first_responded_on = doc.first_responded_on or now
            doc.last_responded_on = doc.last_responded_on or doc.first_responded_on

    def set_first_response_time(self, doc) -> None:
        if not doc.sla_creation or not doc.first_responded_on:
            return
        if doc.first_response_time is None:
            doc.first_response_time = self.calc_elapsed_time(
                doc.sla_creation, doc.first_responded_on
            )
        if doc.last_response_time is None and doc.first_response_time is not None:
            doc.last_response_time = doc.first_response_time

    def rolling_responses(self, doc) -> list[CRMRollingResponseTime]:
        if self._rolling_rows is None:
            self._rolling_rows = list(
                CRMRollingResponseTime._default_manager.filter(
                    parenttype=doc.get_doctype(), parent=str(doc.pk)
                ).order_by("idx")
            )
        return self._rolling_rows

    def append_rolling_response(self, doc, *, status: str) -> None:
        rows = self.rolling_responses(doc)
        row = CRMRollingResponseTime._default_manager.create(
            parenttype=doc.get_doctype(),
            parentfield="rolling_responses",
            parent=str(doc.pk),
            idx=len(rows) + 1,
            response_time=doc.last_response_time,
            responded_on=doc.last_responded_on,
            status=status,
        )
        rows.append(row)

    def set_rolling_responses(self, doc) -> None:
        if doc.last_response_time is None or not doc.last_responded_on:
            return
        rows = self.rolling_responses(doc)
        if not rows:
            self.append_rolling_response(
                doc,
                status="Failed" if self.is_first_response_failed(doc) else "Fulfilled",
            )
        elif doc.communication_status_id != self.get_default_priority():
            current_time = _convert_datetime(_now_local(), for_storage=True)
            doc.last_response_time = self.calc_elapsed_time(
                doc.last_responded_on, current_time
            )
            doc.last_responded_on = current_time
            self.append_rolling_response(
                doc,
                status="Failed" if self.is_rolling_response_failed(doc) else "Fulfilled",
            )

    def handle_targets(self, doc) -> None:
        self.set_response_by(doc)
        if self.sla.rolling_responses and self.rolling_responses(doc):
            self.set_rolling_response_by(doc)

    def set_response_by(self, doc) -> None:
        priority = self.get_priorities().get(doc.communication_status_id)
        if not priority or doc.response_by:
            return
        end_time = self.calc_time(doc.sla_creation, priority.first_response_time or 0)
        if end_time:
            doc.response_by = end_time

    def _update_rolling_response_by(self, doc) -> None:
        default_priority = self.get_default_priority()
        if doc.communication_status_id != default_priority:
            return
        priority = self.get_priorities().get(default_priority)
        if not priority:
            return
        end_time = self.calc_time(timezone.now(), priority.first_response_time or 0)
        if end_time:
            doc.response_by = end_time

    def set_rolling_response_by(self, doc) -> None:
        if doc.response_by and doc.last_responded_on:
            self._update_rolling_response_by(doc)

    def handle_sla_status(self, doc) -> None:
        options = {
            "Fulfilled": True,
            "First Response Due": not doc.first_responded_on,
            "Failed": self.is_first_response_failed(doc),
        }
        for status, applies in options.items():
            if applies:
                doc.sla_status = status

    def is_first_response_failed(self, doc) -> bool:
        response_by = _convert_datetime(doc.response_by)
        compared_with = (
            _convert_datetime(doc.first_responded_on)
            if doc.first_responded_on
            else _now_local()
        )
        return response_by < compared_with

    def handle_rolling_sla_status(self, doc) -> None:
        if not self.sla.rolling_responses or not self.rolling_responses(doc):
            return
        options = {
            "Fulfilled": True,
            "Rolling Response Due": (
                doc.communication_status_id == self.get_default_priority()
            ),
            "Failed": self.is_rolling_response_failed(doc),
        }
        for status, applies in options.items():
            if applies:
                doc.sla_status = status

    def is_rolling_response_failed(self, doc) -> bool:
        if not doc.response_by:
            return False
        response_by = _convert_datetime(doc.response_by)
        if doc.communication_status_id == self.get_default_priority():
            return response_by < _now_local()
        if not doc.last_responded_on:
            return response_by < _now_local()
        return response_by < _convert_datetime(doc.last_responded_on)

    #: Days ``calc_time`` may step over before it gives up (UPSTREAM_BUGS.md 57).
    MAX_DAYS_SKIPPED = 3660

    def calc_time(self, start_at: datetime, duration_seconds: int) -> datetime | None:
        """``crm_service_level_agreement.py:224-261``.

        Returns ``None`` where upstream loops forever: an SLA with no working hours, or a
        holiday list covering every working day, never finds time to count, and
        upstream's ``while time_needed`` then never ends, hanging the save
        (``UPSTREAM_BUGS.md`` 57, diverged). ``set_response_by`` already treats a falsy
        end time as "no deadline".
        """
        result = _convert_datetime(start_at)
        time_needed = int(duration_seconds)
        holidays = self.get_holidays()
        workdays = self.get_workdays()
        if time_needed and not workdays:
            return None
        days_skipped = 0
        while time_needed:
            if days_skipped > self.MAX_DAYS_SKIPPED:
                return None
            weekday = result.strftime("%A")
            if result.date() in holidays or weekday not in workdays:
                # UPSTREAM_BUGS.md 56: this deliberately keeps the time of day.
                result += timedelta(days=1)
                days_skipped += 1
                continue
            workday = workdays[weekday]
            now_in_seconds = (
                result.hour * 3600 + result.minute * 60 + result.second
                + result.microsecond / 1_000_000
            )
            start_seconds = _time_to_seconds(workday.start_time)
            end_seconds = _time_to_seconds(workday.end_time)
            start_time = max(start_seconds, now_in_seconds)
            till_start_time = max(start_time - now_in_seconds, 0)
            end_time = max(end_seconds, now_in_seconds)
            time_left = max(end_time - start_time, 0)
            if not time_left:
                result = datetime.combine(result.date() + timedelta(days=1), time.min)
                days_skipped += 1
                continue
            time_taken = min(time_needed, time_left)
            time_needed -= time_taken
            result += timedelta(seconds=till_start_time + time_taken)
        return _convert_datetime(result, for_storage=True)

    def calc_elapsed_time(self, start_time: datetime, end_time: datetime) -> int:
        """Count upstream's one-second samples by intersecting daily work windows."""

        start = _convert_datetime(start_time)
        end = _convert_datetime(end_time)
        if end <= start:
            return 0
        holidays = self.get_holidays()
        working_hours = self.get_working_hours()
        total = 0
        current_date = start.date()
        while current_date <= end.date():
            if current_date not in holidays:
                hours = working_hours.get(current_date.strftime("%A"))
                if hours:
                    window_start = datetime.combine(current_date, hours[0])
                    window_end = datetime.combine(current_date, hours[1])
                    lower = max(start, window_start)
                    upper = min(end, window_end)
                    if lower < upper:
                        first_tick = max(0, _ceil_seconds(lower - start))
                        tick_limit = _ceil_seconds(upper - start)
                        total += max(0, tick_limit - first_tick)
            current_date += timedelta(days=1)
        return total

    def get_priorities(self) -> dict[str, object]:
        return {row.priority_id: row for row in self._priorities}

    def get_default_priority(self) -> str:
        for row in self._priorities:
            if row.default_priority:
                return row.priority_id
        return self._priorities[0].priority_id

    def get_workdays(self) -> dict[str, object]:
        return {row.workday: row for row in self._working_hours}

    def get_working_days(self) -> list[str]:
        return [row.workday for row in self._working_hours]

    def get_working_hours(self) -> dict[str, tuple[time, time]]:
        return {
            row.workday: (row.start_time, row.end_time)
            for row in self._working_hours
        }

    def is_working_time(
        self, date_time: datetime, working_hours: dict[str, tuple[time, time]]
    ) -> bool:
        hours = working_hours.get(date_time.strftime("%A"))
        if not hours:
            return False
        seconds = date_time.hour * 3600 + date_time.minute * 60 + date_time.second
        return _time_to_seconds(hours[0]) <= seconds < _time_to_seconds(hours[1])

    def get_holidays(self) -> list[date]:
        if self._holidays is None:
            if not self.sla.holiday_list_id:
                self._holidays = []
            else:
                self._holidays = list(
                    self.sla.holiday_list.holidays.values_list("date", flat=True)
                )
        return self._holidays


def apply_sla(doc) -> None:
    """Apply the selected policy to a lead or deal before its row is written."""

    if doc.sla_id:
        SLAEngine(doc.sla).apply(doc)


def calc_time(sla: CRMServiceLevelAgreement, start_at: datetime, seconds: int) -> datetime:
    return SLAEngine(sla).calc_time(start_at, seconds)


def calc_elapsed_time(
    sla: CRMServiceLevelAgreement, start_time: datetime, end_time: datetime
) -> int:
    return SLAEngine(sla).calc_elapsed_time(start_time, end_time)
