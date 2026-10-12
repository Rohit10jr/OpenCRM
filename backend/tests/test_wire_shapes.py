"""The three JSON caches are strings on the wire: FINDINGS.md 40.

Upstream keeps ``_assign``, ``_liked_by`` and ``_comments`` in Text columns holding JSON
and hands them over as-is; the frontend parses them (``Leads.vue:490``: ``JSON.parse(
lead._assign || '[]')``; ``isLiked(item)`` in every list view: ``JSON.parse(item)``). The
port stores them as ``JSONField`` and used to hand over the decoded list, which those
``JSON.parse`` calls throw on - the leads and deals lists never rendered.
"""

import json
from urllib.parse import quote

import pytest

from frappe_core.assignment import assign_to_user
from frappe_core.session import session_user
from tests_support.models import Widget

pytestmark = pytest.mark.django_db

WIDGETS = "/api/resource/" + quote("Phase Zero Widget")


@pytest.fixture
def widget(alice):
    with session_user(alice.name):
        return Widget.objects.create(widget_name="ZZ Wire")


def test_the_resource_route_sends_json_strings(auth_api, widget, alice, bob):
    with session_user(alice.name):
        assign_to_user("Phase Zero Widget", widget.pk, bob.name)

    data = auth_api.get(f"{WIDGETS}/{widget.pk}").json()["data"]
    assert isinstance(data["_assign"], str)
    assert json.loads(data["_assign"]) == [bob.name]
    assert data["_liked_by"] == "[]"
    assert data["_comments"] == "[]"


def test_list_rows_send_json_strings_too(auth_api, widget, alice, bob):
    """``fetch_rows`` feeds ``get_data``, ``frappe.client.get_list`` and the resource list."""
    with session_user(alice.name):
        assign_to_user("Phase Zero Widget", widget.pk, bob.name)

    response = auth_api.post(
        "/api/method/frappe.client.get_list",
        {"doctype": "Phase Zero Widget", "fields": ["name", "_assign", "_liked_by"]},
        format="json",
    )
    row = next(r for r in response.json()["message"] if r["name"] == widget.pk)
    assert json.loads(row["_assign"]) == [bob.name]
    assert row["_liked_by"] == "[]"

    rows = auth_api.get(f'{WIDGETS}?fields=["name","_assign"]').json()["data"]
    row = next(r for r in rows if r["name"] == widget.pk)
    assert json.loads(row["_assign"]) == [bob.name]


def test_the_frontend_parse_round_trips_an_empty_cache(auth_api, widget):
    """``JSON.parse(x || '[]')`` and the unguarded ``JSON.parse(item)`` both need a string
    that parses; ``"[]"`` satisfies both, ``""`` only the first."""
    data = auth_api.get(f"{WIDGETS}/{widget.pk}").json()["data"]
    assert json.loads(data["_assign"]) == []
    assert json.loads(data["_liked_by"]) == []


def test_the_column_is_still_filterable_as_text(auth_api, widget, alice, bob):
    """The ``@me`` filter is ``_assign like %user%`` (``filters.py``), a text match on the
    stored JSON; the wire encoding must not change what the filter sees."""
    with session_user(alice.name):
        assign_to_user("Phase Zero Widget", widget.pk, bob.name)

    rows = auth_api.get(
        f'{WIDGETS}?fields=["name"]&filters=[["_assign","like","%{bob.name}%"]]'
    ).json()["data"]
    assert [r["name"] for r in rows] == [widget.pk]
