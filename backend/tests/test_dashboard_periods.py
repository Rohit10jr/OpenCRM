"""B1 - the dashboard's comparison baseline.

Upstream derives "the previous period" with ``date_diff``, which returns the **gap**
between two dates rather than the number of days in the range. March 1st to March 31st
is a gap of 30, but March is a 31-day month - so upstream's baseline is always one day
shorter than the period being compared against, and every percentage on the dashboard is
inflated by roughly 3% before anything has actually changed.

Fixed rather than reproduced. See :func:`_period_before` for why this one departs from
the usual rule of reproducing user-visible upstream behaviour, and ``UPSTREAM_BUGS.md``
for the record.

These tests are pure date arithmetic - no database, no fixtures - because that is all the
defect ever was.
"""

import calendar
import datetime

import pytest

from crm_app.api.dashboard import _period_before, resolve_range
from frappe_core.exceptions import ValidationError


def _window_length(from_date, to_date) -> int:
    """Days in the baseline. The callers query ``>= prev_from`` and ``< from_date``, so
    the window is half-open and its length is simply the difference."""
    prev_from, _ = _period_before(from_date, to_date)
    return (from_date - prev_from).days


def _month(year: int, month: int):
    return (
        datetime.date(year, month, 1),
        datetime.date(year, month, calendar.monthrange(year, month)[1]),
    )


@pytest.mark.parametrize("month", range(1, 13))
def test_the_baseline_is_the_same_length_as_the_period(month):
    """The whole of B1 in one assertion, for every month of a year.

    Upstream fails this for eight months in twelve; the four it passes are the 31-day
    months that happen to follow a 30-day month.
    """
    from_date, to_date = _month(2026, month)
    period_length = (to_date - from_date).days + 1

    assert _window_length(from_date, to_date) == period_length, (
        f"{from_date:%B} has {period_length} days but is compared against "
        f"{_window_length(from_date, to_date)}"
    )


def test_a_leap_february_is_handled():
    from_date, to_date = _month(2028, 2)  # 29 days
    assert (to_date - from_date).days + 1 == 29
    assert _window_length(from_date, to_date) == 29


def test_march_baseline_reaches_into_january():
    """**Not a defect - the design choice we deliberately did not change.**

    Even with equal lengths, the baseline is "the previous 31 days", not "February".
    Comparing whole calendar months instead is option C in ``UPSTREAM_BUGS.md``: a
    product decision, not a bug fix.
    """
    from_date, to_date = _month(2026, 3)
    prev_from, prev_to = _period_before(from_date, to_date)

    assert prev_from == datetime.date(2026, 1, 29)
    assert prev_to == datetime.date(2026, 3, 1)
    assert prev_from.month == 1, "the baseline still spans two months, by design"


def test_the_baseline_never_overlaps_the_period():
    """The callers use ``< from_date``, so the two windows must abut, not overlap -
    otherwise a record would be counted on both sides of the comparison."""
    from_date, to_date = _month(2026, 3)
    _, prev_to = _period_before(from_date, to_date)
    assert prev_to == from_date


def test_a_single_day_range_still_gets_a_baseline():
    """Upstream forces ``diff = 1`` when the range is one day (``dashboard.py:96-97``),
    so the tile shows a comparison rather than dividing by an empty period."""
    day = datetime.date(2026, 3, 15)
    prev_from, prev_to = _period_before(day, day)

    assert (prev_to - prev_from).days == 1
    assert prev_from == datetime.date(2026, 3, 14)


def test_a_full_year_range():
    from_date = datetime.date(2026, 1, 1)
    to_date = datetime.date(2026, 12, 31)

    assert _window_length(from_date, to_date) == 365
    prev_from, _ = _period_before(from_date, to_date)
    assert prev_from == datetime.date(2025, 1, 1)


def test_upstreams_arithmetic_would_fail_this():
    """Pins the defect itself, so the fix cannot be silently reverted.

    This is upstream's calculation verbatim. If someone restores it, the parametrised
    test above starts failing for eight months - this one explains why.
    """
    from_date, to_date = _month(2026, 3)
    upstream_diff = (to_date - from_date).days  # date_diff: the gap, not the count
    upstream_baseline = from_date - datetime.timedelta(days=upstream_diff)

    assert upstream_diff == 30, "March 1 to March 31 is a 30-day gap"
    assert (from_date - upstream_baseline).days == 30
    assert (to_date - from_date).days + 1 == 31, "but March has 31 days"


# --- the dates themselves: frappe.utils.getdate (FINDINGS.md 21) ------------------


def test_an_unparseable_date_is_a_validation_error():
    """``getdate`` (data.py:87-107) throws ``"{} is not a valid date string."`` with
    the value in ``frappe.bold``, titled "Invalid Date". It was a bare ``ValueError``
    from ``date.fromisoformat``, a 500."""
    with pytest.raises(ValidationError) as caught:
        resolve_range("yesterday", None)
    assert caught.value.message == "<strong>yesterday</strong> is not a valid date string."
    assert caught.value.title == "Invalid Date"


def test_the_formats_getdate_takes_are_taken():
    """dateutil, as upstream: an ISO date, an ISO datetime, and a spelled-out date."""
    assert resolve_range("2026-03-05", "2026-03-09") == (
        datetime.date(2026, 3, 5),
        datetime.date(2026, 3, 9),
    )
    assert resolve_range("2026-03-05T10:20:30Z", "March 9, 2026")[1] == datetime.date(
        2026, 3, 9
    )
