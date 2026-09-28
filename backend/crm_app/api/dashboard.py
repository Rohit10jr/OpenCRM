"""``crm.api.dashboard.*`` - Group D. Ported from ``crm/api/dashboard.py`` (1204 LOC).

Three whitelisted endpoints - ``reset_to_default``, ``get_dashboard``, ``get_chart`` -
dispatching by name to ~18 internal chart builders. The dispatch contract is what the
frontend depends on; the chart bodies are independent of each other.

**Every chart is ported.** :data:`CHART_BUILDERS` is the dispatch table; a name that
is not there answers ``{"error": "Invalid chart name"}``, which is exactly what
upstream does for a name it cannot find (``crm/api/dashboard.py:57-59``). The six
time-series and duration-arithmetic charts came last (FINDINGS.md 20) and aggregate in
Python over small result sets rather than in SQL, because MariaDB's ``TIMESTAMPDIFF``
and ``DATE_FORMAT`` have no one-to-one ORM spelling and the numbers must match.

**Sales-User scoping is load-bearing.** Upstream forces ``user = session.user`` for a
plain Sales User (``dashboard.py:38-40``), so a rep's dashboard only counts their own
records. Every builder additionally reads through ``base_queryset``, so the phase-2 row
rules apply on top - upstream's raw ``frappe.qb`` does not, which means our numbers are
*narrower* than upstream's for a user whose visibility is restricted. That is the safer
direction and is recorded as a deliberate divergence.
"""

from __future__ import annotations

import datetime
import json

from dateutil import parser as date_parser
from dateutil.parser import ParserError
from dateutil.relativedelta import relativedelta
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.exceptions import ValidationError
from frappe_core.query import base_queryset
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

MANAGER_DASHBOARD = "Manager Dashboard"

#: ``crm/fcrm/doctype/crm_dashboard/crm_dashboard.py:default_manager_dashboard_layout``,
#: verbatim, and stored in the CRM Dashboard row as upstream stores it. The frontend's
#: grid places each tile by its ``layout`` (x, y, w, h, i) and ``DashboardItem.vue``
#: draws only the types ``number_chart``, ``axis_chart``, ``donut_chart`` and
#: ``spacer``; a tile of any other shape draws nothing (FINDINGS.md 41). ``name`` is
#: what ``get_dashboard`` looks up in :data:`CHART_BUILDERS`; the spacer has none.
#: Migration ``crm_app/0009`` carries its own copy for the rows written before it.
DEFAULT_DASHBOARD_LAYOUT_JSON = (
    '[{"name":"total_leads","type":"number_chart","tooltip":"Total number of leads",'
    '"layout":{"x":0,"y":0,"w":4,"h":3,"i":"total_leads"}},'
    '{"name":"ongoing_deals","type":"number_chart","tooltip":"Total number of ongoing deals",'
    '"layout":{"x":8,"y":0,"w":4,"h":3,"i":"ongoing_deals"}},'
    '{"name":"won_deals","type":"number_chart","tooltip":"Total number of won deals",'
    '"layout":{"x":12,"y":0,"w":4,"h":3,"i":"won_deals"}},'
    '{"name":"average_won_deal_value","type":"number_chart","tooltip":"Average value of won deals",'
    '"layout":{"x":16,"y":0,"w":4,"h":3,"i":"average_won_deal_value"}},'
    '{"name":"average_deal_value","type":"number_chart",'
    '"tooltip":"Average deal value of ongoing and won deals",'
    '"layout":{"x":0,"y":2,"w":4,"h":3,"i":"average_deal_value"}},'
    '{"name":"average_time_to_close_a_lead","type":"number_chart",'
    '"tooltip":"Average time taken to close a lead",'
    '"layout":{"x":4,"y":0,"w":4,"h":3,"i":"average_time_to_close_a_lead"}},'
    '{"name":"average_time_to_close_a_deal","type":"number_chart",'
    '"layout":{"x":4,"y":2,"w":4,"h":3,"i":"average_time_to_close_a_deal"}},'
    '{"name":"spacer","type":"spacer","layout":{"x":8,"y":2,"w":12,"h":3,"i":"spacer"}},'
    '{"name":"sales_trend","type":"axis_chart","layout":{"x":0,"y":4,"w":10,"h":9,"i":"sales_trend"}},'
    '{"name":"forecasted_revenue","type":"axis_chart",'
    '"layout":{"x":10,"y":4,"w":10,"h":9,"i":"forecasted_revenue"}},'
    '{"name":"funnel_conversion","type":"axis_chart",'
    '"layout":{"x":0,"y":11,"w":10,"h":9,"i":"funnel_conversion"}},'
    '{"name":"deals_by_stage_donut","type":"donut_chart",'
    '"layout":{"x":10,"y":11,"w":10,"h":9,"i":"deals_by_stage_donut"}},'
    '{"name":"lost_deal_reasons","type":"axis_chart",'
    '"layout":{"x":0,"y":32,"w":20,"h":9,"i":"lost_deal_reasons"}},'
    '{"name":"leads_by_source","type":"donut_chart",'
    '"layout":{"x":0,"y":18,"w":10,"h":9,"i":"leads_by_source"}},'
    '{"name":"deals_by_source","type":"donut_chart",'
    '"layout":{"x":10,"y":18,"w":10,"h":9,"i":"deals_by_source"}},'
    '{"name":"deals_by_territory","type":"axis_chart",'
    '"layout":{"x":0,"y":25,"w":10,"h":9,"i":"deals_by_territory"}},'
    '{"name":"deals_by_salesperson","type":"axis_chart",'
    '"layout":{"x":10,"y":25,"w":10,"h":9,"i":"deals_by_salesperson"}}]'
)
#: The same, parsed, for anything that wants to read it; never handed out mutable.
DEFAULT_DASHBOARD_LAYOUT = json.loads(DEFAULT_DASHBOARD_LAYOUT_JSON)


def _roles(user: str) -> set[str]:
    from frappe_platform.models import User

    obj = User._default_manager.filter(pk=user).first()
    return obj.get_roles() if obj else set()


def sales_user_only(user: str | None = None) -> None:
    """``crm.utils.sales_user_only`` - the decorator guarding both endpoints."""
    user = user or get_current_user()
    if not _roles(user).intersection({"System Manager", "Sales Manager", "Sales User"}):
        raise FrappePermissionError("Not permitted")


def _first_day(value: datetime.date) -> datetime.date:
    return value.replace(day=1)


def _last_day(value: datetime.date) -> datetime.date:
    if value.month == 12:
        return value.replace(day=31)
    return value.replace(month=value.month + 1, day=1) - datetime.timedelta(days=1)


def _parse_date(value) -> datetime.date | None:
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    # ``frappe.utils.getdate`` (data.py:87-107): dateutil's parser, so the formats it
    # takes are the ones upstream takes, and a string it cannot read is a
    # ValidationError titled "Invalid Date" - verbatim, ``frappe.bold`` included - not
    # the 500 that ``date.fromisoformat`` raised (FINDINGS.md 21).
    try:
        return date_parser.parse(str(value)).date()
    except (ParserError, ValueError, OverflowError):
        raise ValidationError(
            f"<strong>{value}</strong> is not a valid date string.", title="Invalid Date"
        ) from None


def resolve_range(from_date, to_date) -> tuple[datetime.date, datetime.date]:
    """``dashboard.py:32-34`` - default to the current calendar month."""
    parsed_from = _parse_date(from_date)
    parsed_to = _parse_date(to_date)
    if not parsed_from or not parsed_to:
        today = datetime.date.today()
        parsed_from = _first_day(parsed_from or today)
        parsed_to = _last_day(parsed_to or today)
    return parsed_from, parsed_to


def resolve_scope(user: str | None) -> str | None:
    """``dashboard.py:36-40`` - a plain Sales User only ever sees their own numbers."""
    session_user = get_current_user()
    roles = _roles(session_user)
    is_manager = "Sales Manager" in roles or "System Manager" in roles
    if "Sales User" in roles and not is_manager:
        return session_user
    return user


def _delta(current: float, previous: float) -> float:
    """``dashboard.py:121-123`` - percentage change, 0 when there is no baseline."""
    if not previous:
        return 0
    return (current - previous) / previous * 100


def _period_before(from_date, to_date) -> tuple[datetime.date, datetime.date]:
    """The preceding window, of **genuinely** equal length.

    ### Deliberate divergence - upstream's baseline is one day short

    ``dashboard.py:95-99`` computes it as::

        diff = date_diff(to_date, from_date)     # Mar 1 -> Mar 31 == 30
        prev_from_date = add_days(from_date, -diff)

    ``date_diff`` returns the **gap** between two dates, not the number of days in the
    range. March 1st to March 31st is a gap of 30, but March is a 31-day month - so the
    baseline window is always one day shorter than the period it is compared against:

        viewing March    (31 days)  ->  baseline Jan 30 - Feb 28  (30 days)
        viewing February (28 days)  ->  baseline Jan  5 - Jan 31  (27 days)
        viewing August   (31 days)  ->  baseline Jul  2 - Jul 31  (30 days)

    Every percentage on the dashboard is therefore inflated by roughly 3%, purely from
    the shorter baseline, before anything has actually changed. Eight months in twelve
    are affected.

    **Fixed here rather than reproduced**, which is a departure from the usual rule of
    reproducing user-visible upstream behaviour. That rule exists to avoid overriding
    decisions people rely on - and nobody relies on an inflation they cannot see. This is
    not a design choice being overruled; it is a sum that is wrong, and a manager reads
    it to judge whether the month went well. Recorded in ``UPSTREAM_BUGS.md``.

    ### What is *not* fixed: calendar alignment

    Even corrected, the baseline is "the previous N days", not "the previous calendar
    month" - so March still compares against a window reaching into late January.

    That one **is** a design choice, and upstream's is defensible: a dashboard may
    legitimately mean "the last 31 days". Changing it to compare whole calendar months is
    a product decision, not a bug fix. It is a small change if wanted - take the first
    and last day of the preceding month instead of counting back - and it is recorded as
    option C in ``UPSTREAM_BUGS.md``.

    ``diff == 0`` is forced to 1, as upstream does, so a single-day range still has a
    baseline rather than comparing against nothing.
    """
    # +1 where upstream has none: the range is inclusive of both ends, so a 31-day month
    # is 31 days, not the 30-day gap between its first and last dates.
    length = (to_date - from_date).days + 1 or 1
    return from_date - datetime.timedelta(days=length), from_date


# ---------------------------------------------------------------------------
# Number charts
# ---------------------------------------------------------------------------


def get_total_leads(from_date, to_date, user=None):
    """``dashboard.py:91-135``. Counts on ``creation``, scoped by ``lead_owner``."""
    queryset = base_queryset("CRM Lead", get_current_user())
    if user:
        queryset = queryset.filter(lead_owner=user)

    prev_from, prev_to = _period_before(from_date, to_date)

    aggregate = queryset.aggregate(
        current=Count("pk", filter=Q(creation__date__gte=from_date, creation__date__lte=to_date)),
        previous=Count(
            "pk", filter=Q(creation__date__gte=prev_from, creation__date__lt=from_date)
        ),
    )
    current, previous = aggregate["current"] or 0, aggregate["previous"] or 0
    return {
        "title": "Total leads",
        "tooltip": "Total number of leads",
        "value": current,
        "delta": _delta(current, previous),
        "deltaSuffix": "%",
    }


def _deal_queryset(user):
    queryset = base_queryset("CRM Deal", get_current_user())
    if user:
        queryset = queryset.filter(deal_owner=user)
    return queryset


def get_ongoing_deals(from_date, to_date, user=None):
    """``dashboard.py:138-194``. "Ongoing" is any status whose type is not Won or Lost."""
    queryset = _deal_queryset(user).exclude(status__type__in=["Won", "Lost"])
    prev_from, prev_to = _period_before(from_date, to_date)

    aggregate = queryset.aggregate(
        current=Count("pk", filter=Q(creation__date__gte=from_date, creation__date__lte=to_date)),
        previous=Count(
            "pk", filter=Q(creation__date__gte=prev_from, creation__date__lt=from_date)
        ),
    )
    current, previous = aggregate["current"] or 0, aggregate["previous"] or 0
    return {
        "title": "Ongoing deals",
        "tooltip": "Total number of ongoing deals",
        "value": current,
        "delta": _delta(current, previous),
        "deltaSuffix": "%",
    }


def get_won_deals(from_date, to_date, user=None):
    """``dashboard.py:259-310``.

    Counts on ``closed_date``, not ``creation`` - a deal won this month may have been
    created last year, and the tooltip says so.
    """
    queryset = _deal_queryset(user).filter(status__type="Won")
    prev_from, prev_to = _period_before(from_date, to_date)

    # closed_date is a DateField, so these compare cleanly without a __date lookup.
    aggregate = queryset.aggregate(
        current=Count("pk", filter=Q(closed_date__gte=from_date, closed_date__lte=to_date)),
        previous=Count("pk", filter=Q(closed_date__gte=prev_from, closed_date__lt=from_date)),
    )
    current, previous = aggregate["current"] or 0, aggregate["previous"] or 0
    return {
        "title": "Won deals",
        "tooltip": "Total number of won deals based on its closure date",
        "value": current,
        "delta": _delta(current, previous),
        "deltaSuffix": "%",
    }


def _average_value(queryset, from_date, to_date, date_field: str, title: str, tooltip: str):
    """``date_field`` is either ``creation`` (a DateTimeField, so it needs the ``__date``
    lookup to compare against a date without a naive-datetime warning) or ``closed_date``
    (already a DateField)."""
    prev_from, _prev_to = _period_before(from_date, to_date)
    prefix = f"{date_field}__date" if date_field == "creation" else date_field

    aggregate = queryset.aggregate(
        current=Avg(
            "deal_value",
            filter=Q(**{f"{prefix}__gte": from_date, f"{prefix}__lte": to_date}),
        ),
        previous=Avg(
            "deal_value",
            filter=Q(**{f"{prefix}__gte": prev_from, f"{prefix}__lt": from_date}),
        ),
    )
    current = float(aggregate["current"] or 0)
    previous = float(aggregate["previous"] or 0)
    return {
        "title": title,
        "tooltip": tooltip,
        "value": current,
        "delta": _delta(current, previous),
        "deltaSuffix": "%",
        "prefix": get_base_currency_symbol(),
    }


def get_average_deal_value(from_date, to_date, user=None):
    """``dashboard.py:372-424``."""
    return _average_value(
        _deal_queryset(user), from_date, to_date, "creation",
        "Average deal value", "Average value of all deals",
    )


def get_average_won_deal_value(from_date, to_date, user=None):
    """``dashboard.py:314-369``."""
    return _average_value(
        _deal_queryset(user).filter(status__type="Won"), from_date, to_date, "closed_date",
        "Average won deal value", "Average value of won deals based on its closure date",
    )


def get_average_ongoing_deal_value(from_date, to_date, user=None):
    """``dashboard.py:197-256``."""
    return _average_value(
        _deal_queryset(user).exclude(status__type__in=["Won", "Lost"]), from_date, to_date,
        "creation", "Average ongoing deal value", "Average value of ongoing deals",
    )


def get_base_currency_symbol():
    """``dashboard.py:1150-1156`` - the currency configured on FCRM Settings."""
    from crm_app.models import FCRMSettings

    return (
        FCRMSettings._default_manager.values_list("currency", flat=True).first() or ""
    )


# ---------------------------------------------------------------------------
# Category charts
# ---------------------------------------------------------------------------


def _grouped(queryset, from_date, to_date, field: str, alias: str, empty_label="Empty"):
    """The shape every group-by chart shares: count per value, biggest first."""
    rows = (
        queryset.filter(creation__date__gte=from_date, creation__date__lte=to_date)
        .values(field)
        .annotate(count=Count("pk"))
        .order_by("-count")
    )
    return [{alias: row[field] or empty_label, "count": row["count"]} for row in rows]


def get_deals_by_stage_donut(from_date, to_date, user=None):
    """``dashboard.py:859-899``."""
    rows = (
        _deal_queryset(user)
        .filter(creation__date__gte=from_date, creation__date__lte=to_date)
        .values("status", "status__type")
        .annotate(count=Count("pk"))
        .order_by("-count")
    )
    return {
        "data": [
            {"stage": r["status"], "count": r["count"], "status_type": r["status__type"]}
            for r in rows
        ],
        "title": "Deals by stage",
        "subtitle": "Current pipeline distribution",
        "categoryColumn": "stage",
        "valueColumn": "count",
    }


def get_deals_by_stage_axis(from_date, to_date, user=None):
    """``dashboard.py:810-856`` - same data, axis-chart envelope."""
    donut = get_deals_by_stage_donut(from_date, to_date, user)
    return {
        "data": donut["data"],
        "title": "Deals by stage",
        "subtitle": "Current pipeline distribution",
        "xAxis": {"title": "Stage", "key": "stage", "type": "category"},
        "yAxis": {"title": "Count"},
        "series": [{"name": "count", "type": "bar"}],
    }


def get_leads_by_source(from_date, to_date, user=None):
    """``dashboard.py:953-988``. Null sources collapse to ``"Empty"``, as upstream."""
    queryset = base_queryset("CRM Lead", get_current_user())
    if user:
        queryset = queryset.filter(lead_owner=user)
    return {
        "data": _grouped(queryset, from_date, to_date, "source", "source"),
        "title": "Leads by source",
        "subtitle": "Lead generation channel analysis",
        "categoryColumn": "source",
        "valueColumn": "count",
    }


def get_deals_by_source(from_date, to_date, user=None):
    """``dashboard.py:991-1026``."""
    return {
        "data": _grouped(_deal_queryset(user), from_date, to_date, "source", "source"),
        "title": "Deals by source",
        "subtitle": "Deal generation channel analysis",
        "categoryColumn": "source",
        "valueColumn": "count",
    }


def get_deals_by_territory(from_date, to_date, user=None):
    """``dashboard.py:1029-1084``."""
    return {
        "data": _grouped(_deal_queryset(user), from_date, to_date, "territory", "territory"),
        "title": "Deals by territory",
        "subtitle": "Territory-wise deal distribution",
        "xAxis": {"title": "Territory", "key": "territory", "type": "category"},
        "yAxis": {"title": "Count"},
        "series": [{"name": "count", "type": "bar"}],
    }


def get_deals_by_salesperson(from_date, to_date, user=None):
    """``dashboard.py:1087-1147``."""
    return {
        "data": _grouped(
            _deal_queryset(user), from_date, to_date, "deal_owner", "salesperson"
        ),
        "title": "Deals by salesperson",
        "subtitle": "Deals owned per salesperson",
        "xAxis": {"title": "Salesperson", "key": "salesperson", "type": "category"},
        "yAxis": {"title": "Count"},
        "series": [{"name": "count", "type": "bar"}],
    }


def get_lost_deal_reasons(from_date, to_date, user=None):
    """``dashboard.py:902-950``.

    Upstream's ``HAVING lost_reason IS NOT NULL AND != ''`` drops the unexplained
    losses rather than bucketing them as "Empty" - so this one does **not** use the
    shared ``_grouped`` helper.
    """
    rows = (
        _deal_queryset(user)
        .filter(
            status__type="Lost",
            creation__date__gte=from_date,
            creation__date__lte=to_date,
        )
        .exclude(lost_reason__isnull=True)
        .exclude(lost_reason="")
        .values("lost_reason")
        .annotate(count=Count("pk"))
        .order_by("-count")
    )
    return {
        "data": [{"reason": r["lost_reason"], "count": r["count"]} for r in rows],
        "title": "Lost deal reasons",
        "subtitle": "Common reasons for losing deals",
        "xAxis": {"title": "Reason", "key": "reason", "type": "category"},
        "yAxis": {"title": "Count"},
        "series": [{"name": "count", "type": "bar"}],
    }


# ---------------------------------------------------------------------------
# Time-series and duration charts (FINDINGS.md 20)
# ---------------------------------------------------------------------------


def _today() -> datetime.date:
    return datetime.date.today()


def _days_between(start: datetime.datetime, end) -> int:
    """``TIMESTAMPDIFF(DAY, start, end)``: whole days, truncated toward zero. A
    ``closed_date`` is a Date and stands for its midnight, in the site's time zone."""
    if isinstance(end, datetime.date) and not isinstance(end, datetime.datetime):
        end = timezone.make_aware(datetime.datetime.combine(end, datetime.time.min))
    return int((end - start).total_seconds() / 86400)


def _average_days_to_close(from_date, to_date, user, *, from_lead: bool, title, tooltip):
    """``dashboard.py:427-554``: the two average-time charts share everything but where
    the clock starts - the lead's creation when the deal came from one
    (``Coalesce(Lead.creation, Deal.creation)``), or the deal's own. Won deals by
    ``closed_date``, the current window against the one before it, the delta in days."""
    prev_from, prev_to = _period_before(from_date, to_date)
    rows = (
        _deal_queryset(user)
        .filter(
            status__type="Won",
            closed_date__isnull=False,
            closed_date__gte=prev_from,
            closed_date__lte=to_date,
        )
        .order_by()
        .values("creation", "closed_date", "lead__creation")
    )
    current: list[int] = []
    previous: list[int] = []
    for row in rows:
        start = row["creation"]
        if from_lead and row["lead__creation"]:
            start = row["lead__creation"]
        days = _days_between(start, row["closed_date"])
        if from_date <= row["closed_date"] <= to_date:
            current.append(days)
        elif prev_from <= row["closed_date"] < from_date:
            previous.append(days)
    current_avg = sum(current) / len(current) if current else 0
    previous_avg = sum(previous) / len(previous) if previous else 0
    return {
        "title": title,
        "tooltip": tooltip,
        "value": current_avg,
        "suffix": " days",
        "delta": current_avg - previous_avg if previous_avg else 0,
        "deltaSuffix": " days",
        "negativeIsBetter": True,
    }


def get_average_time_to_close_a_lead(from_date, to_date, user=None):
    """``dashboard.py:427-489``."""
    return _average_days_to_close(
        from_date, to_date, user, from_lead=True,
        title="Avg. time to close a lead",
        tooltip="Average time taken from lead creation to deal closure",
    )


def get_average_time_to_close_a_deal(from_date, to_date, user=None):
    """``dashboard.py:492-552``."""
    return _average_days_to_close(
        from_date, to_date, user, from_lead=False,
        title="Avg. time to close a deal",
        tooltip="Average time taken from deal creation to deal closure",
    )


def get_sales_trend(from_date, to_date, user=None):
    """``dashboard.py:555-656`` - leads, deals and won deals created per day."""
    leads = base_queryset("CRM Lead", get_current_user())
    if user:
        leads = leads.filter(lead_owner=user)
    in_range = {"creation__date__gte": from_date, "creation__date__lte": to_date}

    by_day: dict[str, dict] = {}

    def bucket(day):
        key = day.strftime("%Y-%m-%d")
        return by_day.setdefault(key, {"date": key, "leads": 0, "deals": 0, "won_deals": 0})

    lead_rows = (
        leads.filter(**in_range)
        .order_by()
        .annotate(day=TruncDate("creation"))
        .values("day")
        .annotate(count=Count("pk"))
    )
    for row in lead_rows:
        bucket(row["day"])["leads"] += row["count"]
    deal_rows = (
        _deal_queryset(user)
        .filter(**in_range)
        .order_by()
        .annotate(day=TruncDate("creation"))
        .values("day")
        .annotate(count=Count("pk"), won=Count("pk", filter=Q(status__type="Won")))
    )
    for row in deal_rows:
        day = bucket(row["day"])
        day["deals"] += row["count"]
        day["won_deals"] += row["won"]

    return {
        "data": [by_day[key] for key in sorted(by_day)],
        "title": "Sales trend",
        "subtitle": "Daily performance of leads, deals, and wins",
        "xAxis": {"title": "Date", "key": "date", "type": "time", "timeGrain": "day"},
        "yAxis": {"title": "Count"},
        "series": [
            {"name": "leads", "type": "line", "showDataPoints": True},
            {"name": "deals", "type": "line", "showDataPoints": True},
            {"name": "won_deals", "type": "line", "showDataPoints": True},
        ],
    }


def get_forecasted_revenue(from_date, to_date, user=None):
    """``dashboard.py:657-735`` - by month of ``expected_closure_date``, over the twelve
    months before today whatever the dashboard's range (upstream ignores it here).
    Forecast: a lost deal counts its full expected value, any other its expected value
    weighted by probability; actual: a won deal's value. Both in base currency, and an
    empty string rather than 0 where there is nothing, which is what the chart plots."""
    twelve_months_ago = _today() - relativedelta(months=12)
    rows = (
        _deal_queryset(user)
        .filter(expected_closure_date__gte=twelve_months_ago)
        .order_by()
        .values(
            "expected_closure_date", "expected_deal_value", "deal_value",
            "probability", "exchange_rate", "status__type",
        )
    )
    months: dict[str, dict] = {}
    for row in rows:
        key = row["expected_closure_date"].strftime("%Y-%m-01")
        month = months.setdefault(key, {"forecasted": 0.0, "actual": 0.0})
        rate = row["exchange_rate"] if row["exchange_rate"] is not None else 1
        expected = float(row["expected_deal_value"] or 0)
        if row["status__type"] == "Lost":
            month["forecasted"] += expected * rate
        else:
            month["forecasted"] += expected * (row["probability"] or 0) / 100 * rate
        if row["status__type"] == "Won":
            month["actual"] += float(row["deal_value"] or 0) * rate
    data = [
        {
            "month": key,
            "forecasted": months[key]["forecasted"] or "",
            "actual": months[key]["actual"] or "",
        }
        for key in sorted(months)
    ]
    return {
        "data": data,
        "title": "Forecasted revenue",
        "subtitle": "Projected vs actual revenue based on deal probability",
        "xAxis": {"title": "Month", "key": "month", "type": "time", "timeGrain": "month"},
        "yAxis": {"title": f"Revenue ({get_base_currency_symbol()})"},
        "series": [
            {"name": "forecasted", "type": "line", "showDataPoints": True},
            {"name": "actual", "type": "line", "showDataPoints": True},
        ],
    }


def get_deal_status_change_counts(from_date, to_date, user=None):
    """``dashboard.py:1158-1204`` - how many deals created in the range reached each
    status, from the status-change log, deals currently Lost excluded, in the order of
    the statuses' ``position``. A bare list: the funnel appends it after its leads
    count. Upstream's dispatch hands ``user`` to this function's ``deal_conds`` slot,
    where it is never read; the scope is applied here, as the funnel applies it."""
    from crm_app.models import CRMDealStatus, CRMStatusChangeLog

    deals = list(
        _deal_queryset(user)
        .filter(creation__date__gte=from_date, creation__date__lte=to_date)
        .exclude(status__type="Lost")
        .values_list("pk", flat=True)
    )
    if not deals:
        return []
    positions = dict(CRMDealStatus._default_manager.values_list("pk", "position"))
    rows = (
        CRMStatusChangeLog._default_manager.filter(parenttype="CRM Deal", parent__in=deals)
        .exclude(to="")
        .exclude(to__isnull=True)
        .order_by()
        .values("to")
        .annotate(count=Count("pk"))
    )
    result = [{"stage": row["to"], "count": row["count"]} for row in rows if row["to"] in positions]
    # ORDER BY position ascending, and MariaDB sorts NULL before every number.
    result.sort(key=lambda row: (positions[row["stage"]] is not None, positions[row["stage"]] or 0))
    return result


def get_funnel_conversion(from_date, to_date, user=None):
    """``dashboard.py:736-809``."""
    leads = base_queryset("CRM Lead", get_current_user())
    if user:
        leads = leads.filter(lead_owner=user)
    total_leads = leads.filter(creation__date__gte=from_date, creation__date__lte=to_date).count()
    data = [{"stage": "Leads", "count": total_leads}]
    data += get_deal_status_change_counts(from_date, to_date, user)
    return {
        "data": data,
        "title": "Funnel conversion",
        "subtitle": "Lead to deal conversion pipeline",
        "xAxis": {"title": "Stage", "key": "stage", "type": "category"},
        "yAxis": {"title": "Count"},
        "swapXY": True,
        "series": [{"name": "count", "type": "bar", "echartOptions": {"colorBy": "data"}}],
    }


#: Name -> builder. ``get_dashboard`` and ``get_chart`` dispatch through this; a name
#: that is not here yields ``None``, matching upstream's unknown-name branch.
CHART_BUILDERS = {
    "total_leads": get_total_leads,
    "ongoing_deals": get_ongoing_deals,
    "won_deals": get_won_deals,
    "average_deal_value": get_average_deal_value,
    "average_won_deal_value": get_average_won_deal_value,
    "average_ongoing_deal_value": get_average_ongoing_deal_value,
    "deals_by_stage_donut": get_deals_by_stage_donut,
    "deals_by_stage_axis": get_deals_by_stage_axis,
    "leads_by_source": get_leads_by_source,
    "deals_by_source": get_deals_by_source,
    "deals_by_territory": get_deals_by_territory,
    "deals_by_salesperson": get_deals_by_salesperson,
    "lost_deal_reasons": get_lost_deal_reasons,
    "average_time_to_close_a_lead": get_average_time_to_close_a_lead,
    "average_time_to_close_a_deal": get_average_time_to_close_a_deal,
    "sales_trend": get_sales_trend,
    "forecasted_revenue": get_forecasted_revenue,
    "funnel_conversion": get_funnel_conversion,
    "deal_status_change_counts": get_deal_status_change_counts,
}


def create_default_manager_dashboard(force: bool = False) -> tuple[str, bool]:
    """``crm_dashboard.py:19-33``: the Manager Dashboard row, created with the default
    layout when missing and reset to it when ``force``. Returns the layout it holds and
    whether the row was written. Shared by the two endpoints below and by
    ``crm_app.setup`` (``manage.py seed_defaults``)."""
    from crm_app.models import CRMDashboard

    dashboard, created = CRMDashboard._default_manager.get_or_create(
        pk=MANAGER_DASHBOARD,
        defaults={"title": MANAGER_DASHBOARD, "layout": DEFAULT_DASHBOARD_LAYOUT_JSON},
    )
    if force and not created:
        dashboard.layout = DEFAULT_DASHBOARD_LAYOUT_JSON
        dashboard.save()
    return dashboard.layout, created or force


@whitelist("crm.api.dashboard.reset_to_default", methods=("POST",))
def reset_to_default():
    """``dashboard.py:19-23``. System Manager only, as upstream."""
    if "System Manager" not in _roles(get_current_user()):
        raise FrappePermissionError("Not permitted")

    layout, _written = create_default_manager_dashboard(force=True)
    return layout


@whitelist("crm.api.dashboard.get_dashboard")
def get_dashboard(from_date: str | None = None, to_date: str | None = None, user: str | None = None):
    """``dashboard.py:25-61``. Returns the layout with a ``data`` key per tile."""
    sales_user_only()
    resolved_from, resolved_to = resolve_range(from_date, to_date)
    scope = resolve_scope(user)

    layout_json, _written = create_default_manager_dashboard()
    layout = json.loads(layout_json or "[]")

    for tile in layout:
        builder = CHART_BUILDERS.get(tile.get("name"))
        tile["data"] = builder(resolved_from, resolved_to, scope) if builder else None

    return layout


@whitelist("crm.api.dashboard.get_chart")
def get_chart(
    name: str,
    type: str,
    from_date: str | None = None,
    to_date: str | None = None,
    user: str | None = None,
):
    """``dashboard.py:64-88``.

    The unknown-name response is ``{"error": "Invalid chart name"}`` - a dict, not a
    raise, because the dashboard renders one broken tile rather than failing whole.
    """
    sales_user_only()
    resolved_from, resolved_to = resolve_range(from_date, to_date)
    scope = resolve_scope(user)

    builder = CHART_BUILDERS.get(name)
    if builder is None:
        return {"error": "Invalid chart name"}
    return builder(resolved_from, resolved_to, scope)
