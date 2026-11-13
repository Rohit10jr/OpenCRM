from types import SimpleNamespace

import pytest
from django.http import QueryDict

from core.filter_backends import FilterBackend
from core.pagination import LimitStartPagination
from tests_support.models import Widget

pytestmark = pytest.mark.django_db


def request_for(user, query):
    return SimpleNamespace(user=user, query_params=QueryDict(query))


def test_filter_backend_passes_user_filters_and_view_allowlists(alice):
    for label, status in (("alpha", "Open"), ("beta", "Closed")):
        Widget.objects.create_for_user(user=alice, widget_name=label, status=status)
    view = SimpleNamespace(
        selectable_fields=("name", "widget_name"),
        filterable_fields=("status",),
        sortable_fields=("widget_name",),
    )
    request = request_for(
        alice,
        'fields=["widget_name"]&filters={"status":"Open"}&order_by=widget_name desc',
    )
    queryset = FilterBackend().filter_queryset(request, Widget.objects.all(), view)
    assert list(queryset.values_list("widget_name", flat=True)) == ["alpha"]
    assert view.resolved_list_fields == ["widget_name"]


@pytest.mark.parametrize(
    "query,expected",
    [
        ("", list(range(20))),
        ("limit_start=3&limit_page_length=2", [3, 4]),
        ("limit_start=-2&limit_page_length=0", list(range(25))),
        ("limit_page_length=501", list(range(25))),
    ],
)
def test_paginator_uses_frappe_parameters(alice, query, expected):
    paginator = LimitStartPagination()
    assert paginator.paginate_queryset(range(25), request_for(alice, query)) == expected


def test_paginator_response_is_the_bare_list():
    response = LimitStartPagination().get_paginated_response([{"name": "A"}])
    assert response.data == [{"name": "A"}]
