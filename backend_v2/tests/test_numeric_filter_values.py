import json

import pytest

from tests_support.models import Widget


pytestmark = pytest.mark.django_db
WIDGETS = "/api/v1/test-widgets/"


@pytest.fixture
def widgets(alice):
    documents = []
    for label, amount in (("Five", 500000), ("Seven", 700000), ("Zero", 0)):
        document = Widget(widget_name=label, amount=amount, widget_owner=alice)
        document.save(user=alice)
        documents.append(document)
    return documents


def names(client, filters):
    response = client.get(
        WIDGETS,
        {
            "filters": json.dumps(filters),
            "fields": json.dumps(["name"]),
            "order_by": "modified desc",
            "limit_page_length": 20,
        },
    )
    assert response.status_code == 200, response.content[:300]
    return sorted(row["name"] for row in response.json()["message"])


def test_the_amount_a_list_cell_shows_filters_on_that_amount(auth_api, widgets):
    assert names(auth_api, {"amount": "$ 500,000.00"}) == [widgets[0].name]
    assert names(auth_api, {"amount": "₹ 7,00,000.00"}) == [widgets[1].name]


def test_comparisons_and_lists_take_formatted_amounts_too(auth_api, widgets):
    assert names(auth_api, {"amount": [">", "$ 600,000.00"]}) == [widgets[1].name]
    assert names(
        auth_api,
        {"amount": ["in", ["$ 500,000.00", "$ 700,000.00"]]},
    ) == sorted([widgets[0].name, widgets[1].name])
    assert names(
        auth_api,
        {"amount": ["between", ["$ 100,000.00", "$ 600,000.00"]]},
    ) == [widgets[0].name]


def test_a_plain_number_still_works_and_a_string_with_no_number_is_zero(
    auth_api, widgets
):
    assert names(auth_api, {"amount": 700000}) == [widgets[1].name]
    assert names(auth_api, {"amount": "700000"}) == [widgets[1].name]
    assert names(auth_api, {"amount": "abc"}) == [widgets[2].name]


def test_like_on_a_numeric_column_and_text_columns_are_left_alone(auth_api, widgets):
    assert names(auth_api, {"amount": ["like", "%7000%"]}) == [widgets[1].name]
    assert names(auth_api, {"status": "Open"}) == sorted(
        document.name for document in widgets
    )
