"""The six dashboard charts that came last: FINDINGS.md 20.

``crm/api/dashboard.py`` builds nineteen charts; these are the time-series and
duration-arithmetic ones. Each is checked against a small hand-built dataset whose
answer can be worked out on paper.
"""

import datetime

import pytest
from django.utils import timezone

from crm_app.api.dashboard import (
    CHART_BUILDERS,
    get_average_time_to_close_a_deal,
    get_average_time_to_close_a_lead,
    get_chart,
    get_deal_status_change_counts,
    get_forecasted_revenue,
    get_funnel_conversion,
    get_sales_trend,
)
from crm_app.models import CRMDeal, CRMDealStatus, CRMLead, CRMLeadStatus, CRMStatusChangeLog
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

FROM = datetime.date(2026, 3, 1)
TO = datetime.date(2026, 3, 31)


def _at(day: int, month: int = 3) -> datetime.datetime:
    """Midnight, so the day arithmetic is whole days."""
    return timezone.make_aware(datetime.datetime(2026, month, day, 0, 0))


def _stamp(instance, created: datetime.datetime, **columns):
    """Set ``creation`` (and, for a won deal, ``closed_date``, which the deal's own save
    stamps with today when the status is Won - crm_deal.py:91-93) behind the model's
    back, so the dataset has the dates the arithmetic is checked against."""
    type(instance)._default_manager.filter(pk=instance.pk).update(creation=created, **columns)
    instance.refresh_from_db()
    return instance


@pytest.fixture
def statuses(administrator):
    with session_user(administrator.name):
        CRMLeadStatus.objects.create(lead_status="New", type="Open")
        return {
            name: CRMDealStatus.objects.create(deal_status=name, type=kind, position=position)
            for name, kind, position in (
                ("Qualification", "Open", 1),
                ("Negotiation", "Ongoing", 2),
                ("Won", "Won", 3),
                ("Lost", "Lost", 4),
            )
        }


@pytest.fixture
def pipeline(alice, statuses):
    """Two won deals closed in March (5 and 15 days after creation, the first from a
    lead created 14 days before it closed), one won in February (20 days), one lost, one
    open; three leads created in March; status-change rows for the March deals."""
    with session_user(alice.name):
        lead = _stamp(CRMLead.objects.create(first_name="ZZ Origin", lead_owner=alice), _at(20, 2))
        for day in (2, 2, 9):
            _stamp(CRMLead.objects.create(first_name="ZZ March", lead_owner=alice), _at(day))

        won_a = CRMDeal.objects.create(
            deal_owner=alice, status=statuses["Won"], lead=lead,
            closed_date=datetime.date(2026, 3, 6), deal_value=1000, exchange_rate=1,
            expected_closure_date=datetime.date(2026, 3, 6),
        )
        _stamp(won_a, _at(1), closed_date=datetime.date(2026, 3, 6))  # 5 days; 14 from the lead
        won_b = CRMDeal.objects.create(
            deal_owner=alice, status=statuses["Won"],
            closed_date=datetime.date(2026, 3, 25), deal_value=500,
            expected_closure_date=datetime.date(2026, 4, 1),
        )
        _stamp(won_b, _at(10), closed_date=datetime.date(2026, 3, 25))  # 15 days
        won_feb = CRMDeal.objects.create(
            deal_owner=alice, status=statuses["Won"], closed_date=datetime.date(2026, 2, 21),
        )
        _stamp(won_feb, _at(1, 2), closed_date=datetime.date(2026, 2, 21))  # 20 days, previous window
        from crm_app.models import CRMLostReason

        churn = CRMLostReason.objects.create(lost_reason="ZZ Churn")
        lost = CRMDeal.objects.create(
            deal_owner=alice, status=statuses["Lost"], expected_deal_value=800,
            probability=50, expected_closure_date=datetime.date(2026, 3, 20),
            lost_reason=churn,
        )
        _stamp(lost, _at(9))
        open_deal = CRMDeal.objects.create(
            deal_owner=alice, status=statuses["Negotiation"], expected_deal_value=2000,
            probability=25, expected_closure_date=datetime.date(2026, 4, 15),
        )
        _stamp(open_deal, _at(9))

        for deal, reached in (
            (won_a, ("Qualification", "Negotiation", "Won")),
            (won_b, ("Qualification", "Won")),
            (lost, ("Qualification", "Lost")),
            (open_deal, ("Qualification", "Negotiation")),
        ):
            for status in reached:
                CRMStatusChangeLog.objects.create(
                    parenttype="CRM Deal", parentfield="status_change_log", parent=deal.name,
                    **{"to": status},
                )
    return locals()


def test_deals_by_territory_and_salesperson_carry_count_and_value(alice, bob, statuses):
    """FINDINGS.md 88: ``dashboard.py:1029-1147``. Two series each, the count as bars
    and the value in the dashboard currency as a line on the second axis; most deals
    first, then most value; "Empty" for no territory; the owner's full name."""
    from crm_app.api.dashboard import get_deals_by_salesperson, get_deals_by_territory
    from crm_app.models import CRMTerritory

    qualification = statuses["Qualification"]
    with session_user(alice.name):
        europe = CRMTerritory.objects.create(territory_name="ZZ Europe")
        deals = [
            CRMDeal.objects.create(deal_owner=alice, status=qualification, territory=europe, deal_value=100),
            CRMDeal.objects.create(deal_owner=alice, status=qualification, territory=europe, deal_value=50),
            CRMDeal.objects.create(deal_owner=bob, status=qualification, deal_value=400),
        ]
    for deal in deals:
        _stamp(deal, _at(10))
    CRMDeal.objects.filter(pk=deals[0].pk).update(exchange_rate=2)

    with session_user("Administrator"):
        territory = get_deals_by_territory(FROM, TO)
        salesperson = get_deals_by_salesperson(FROM, TO)

    assert territory["data"] == [
        {"territory": europe.name, "deals": 2, "value": 250.0},
        {"territory": "Empty", "deals": 1, "value": 400.0},
    ]
    assert salesperson["data"] == [
        {"salesperson": "Alice", "deals": 2, "value": 250.0},
        {"salesperson": "Bob", "deals": 1, "value": 400.0},
    ]
    for chart in (territory, salesperson):
        assert chart["yAxis"] == {"title": "Number of deals"}
        assert chart["y2Axis"] == {"title": "Deal value ($)"}
        assert chart["series"] == [
            {"name": "deals", "type": "bar"},
            {"name": "value", "type": "line", "showDataPoints": True, "axis": "y2"},
        ]
    assert territory["subtitle"] == "Geographic distribution of deals and revenue"
    assert salesperson["subtitle"] == "Number of deals and total value per salesperson"


def test_every_upstream_chart_is_registered():
    for name in (
        "sales_trend", "forecasted_revenue", "funnel_conversion",
        "average_time_to_close_a_lead", "average_time_to_close_a_deal",
        "deal_status_change_counts",
    ):
        assert name in CHART_BUILDERS


def test_average_time_to_close_a_deal(alice, pipeline):
    with session_user(alice.name):
        chart = get_average_time_to_close_a_deal(FROM, TO)
    assert chart["value"] == 10  # (5 + 15) / 2
    assert chart["suffix"] == " days"
    assert chart["delta"] == 10 - 20  # the February deal took 20
    assert chart["negativeIsBetter"] is True


def test_average_time_to_close_a_lead_starts_at_the_leads_creation(alice, pipeline):
    with session_user(alice.name):
        chart = get_average_time_to_close_a_lead(FROM, TO)
    assert chart["value"] == 14.5  # (14 from the lead + 15) / 2
    assert chart["tooltip"] == "Average time taken from lead creation to deal closure"


def test_sales_trend_counts_per_day(alice, pipeline):
    with session_user(alice.name):
        chart = get_sales_trend(FROM, TO)
    rows = {row["date"]: row for row in chart["data"]}
    assert rows["2026-03-02"] == {"date": "2026-03-02", "leads": 2, "deals": 0, "won_deals": 0}
    assert rows["2026-03-01"] == {"date": "2026-03-01", "leads": 0, "deals": 1, "won_deals": 1}
    assert rows["2026-03-09"] == {"date": "2026-03-09", "leads": 1, "deals": 2, "won_deals": 0}
    assert rows["2026-03-10"]["won_deals"] == 1
    assert [row["date"] for row in chart["data"]] == sorted(rows)
    assert chart["xAxis"]["timeGrain"] == "day"
    assert [s["name"] for s in chart["series"]] == ["leads", "deals", "won_deals"]


def test_forecasted_revenue_by_month(alice, pipeline, monkeypatch):
    monkeypatch.setattr("crm_app.api.dashboard._today", lambda: datetime.date(2026, 4, 1))
    with session_user(alice.name):
        chart = get_forecasted_revenue(FROM, TO)
    rows = {row["month"]: row for row in chart["data"]}
    # March: the lost deal at its full 800, the won deal has no expected value; actual
    # is that won deal's 1000. April: 2000 * 25% = 500 forecast, and won_b's 500 actual.
    assert rows["2026-03-01"] == {"month": "2026-03-01", "forecasted": 800.0, "actual": 1000.0}
    assert rows["2026-04-01"] == {"month": "2026-04-01", "forecasted": 500.0, "actual": 500.0}
    assert list(rows) == ["2026-03-01", "2026-04-01"]
    assert chart["xAxis"]["timeGrain"] == "month"


def test_a_month_with_nothing_plots_empty_strings(alice, statuses, monkeypatch):
    monkeypatch.setattr("crm_app.api.dashboard._today", lambda: datetime.date(2026, 4, 1))
    with session_user(alice.name):
        CRMDeal.objects.create(
            deal_owner=alice, status=statuses["Negotiation"],
            expected_closure_date=datetime.date(2026, 5, 1),
        )
        chart = get_forecasted_revenue(FROM, TO)
    assert chart["data"] == [{"month": "2026-05-01", "forecasted": "", "actual": ""}]


def test_deal_status_change_counts_in_position_order(alice, pipeline):
    with session_user(alice.name):
        rows = get_deal_status_change_counts(FROM, TO)
    # The lost deal is excluded outright (current status Lost), so its Qualification row
    # does not count either.
    assert rows == [
        {"stage": "Qualification", "count": 3},
        {"stage": "Negotiation", "count": 2},
        {"stage": "Won", "count": 2},
    ]


def test_a_status_without_a_position_sorts_first(alice, pipeline, statuses, administrator):
    """``ORDER BY st.position`` ascending, and MariaDB sorts NULL before every number."""
    with session_user(administrator.name):
        CRMDealStatus.objects.create(deal_status="Unranked", type="Open", position=None)
    with session_user(alice.name):
        CRMStatusChangeLog.objects.create(
            parenttype="CRM Deal", parentfield="status_change_log",
            parent=pipeline["open_deal"].name, **{"to": "Unranked"},
        )
        rows = get_deal_status_change_counts(FROM, TO)
    assert rows[0] == {"stage": "Unranked", "count": 1}
    assert [row["stage"] for row in rows[1:]] == ["Qualification", "Negotiation", "Won"]


def test_funnel_conversion_starts_with_the_leads(alice, pipeline):
    with session_user(alice.name):
        chart = get_funnel_conversion(FROM, TO)
    assert chart["data"][0] == {"stage": "Leads", "count": 3}
    assert chart["data"][1]["stage"] == "Qualification"
    assert chart["swapXY"] is True
    assert chart["series"][0]["echartOptions"] == {"colorBy": "data"}


def test_the_six_answer_through_get_chart(alice, pipeline):
    with session_user(alice.name):
        for name in (
            "sales_trend", "forecasted_revenue", "funnel_conversion",
            "average_time_to_close_a_lead", "average_time_to_close_a_deal",
        ):
            chart = get_chart(name=name, type="axis", from_date="2026-03-01", to_date="2026-03-31")
            assert "error" not in chart, name
