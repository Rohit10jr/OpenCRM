"""A formatted amount as a filter value: docs/FINDINGS.md 77, upstream bug 46.

Clicking a currency cell in a list files the cell's display string as the filter
(``ViewControls.vue:applyFilter`` takes the row's formatted value), and the standard
view saves it per user. Upstream's database casts "$ 500,000.00" to 0 and shows an
empty list; the port refused it with 417 and, replaying the saved filter on every
load, the Deals page stopped opening. The port reads the number out of the string.
"""

import pytest

from crm_app.models import CRMDeal, CRMDealStatus
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

GET_DATA = "/api/method/crm.api.doc.get_data"


@pytest.fixture
def deals(administrator, alice):
    with session_user(administrator.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
    with session_user(alice.name):
        return [
            CRMDeal.objects.create(status=status, deal_owner=alice, annual_revenue=amount)
            for amount in (500000, 700000, 0)
        ]


def names(client, filters):
    payload = {
        "doctype": "CRM Deal",
        "filters": filters,
        "order_by": "modified desc",
        "page_length": 20,
        "columns": [],
        "rows": [],
        "view": {"view_type": "list"},
    }
    response = client.post(GET_DATA, payload, format="json")
    assert response.status_code == 200, response.content[:300]
    return sorted(row["name"] for row in response.json()["message"]["data"])


def test_the_amount_a_list_cell_shows_filters_on_that_amount(auth_api, deals):
    """Exactly what the saved standard view held: the display string of the cell."""
    assert names(auth_api, {"annual_revenue": "$ 500,000.00"}) == [deals[0].name]
    assert names(auth_api, {"annual_revenue": "₹ 7,00,000.00"}) == [deals[1].name]


def test_comparisons_and_lists_take_formatted_amounts_too(auth_api, deals):
    assert names(auth_api, {"annual_revenue": [">", "$ 600,000.00"]}) == [deals[1].name]
    assert names(auth_api, {"annual_revenue": ["in", ["$ 500,000.00", "$ 700,000.00"]]}) == sorted(
        [deals[0].name, deals[1].name]
    )
    assert names(auth_api, {"annual_revenue": ["between", ["$ 100,000.00", "$ 600,000.00"]]}) == [
        deals[0].name
    ]


def test_a_plain_number_still_works_and_a_string_with_no_number_is_zero(auth_api, deals):
    """Upstream's database makes "abc" 0; so does the port, rather than refusing."""
    assert names(auth_api, {"annual_revenue": 700000}) == [deals[1].name]
    assert names(auth_api, {"annual_revenue": "700000"}) == [deals[1].name]
    assert names(auth_api, {"annual_revenue": "abc"}) == [deals[2].name]


def test_like_on_a_numeric_column_and_text_columns_are_left_alone(auth_api, deals):
    assert names(auth_api, {"annual_revenue": ["like", "%7000%"]}) == [deals[1].name]
    assert names(auth_api, {"status": "Qualification"}) == sorted(deal.name for deal in deals)
