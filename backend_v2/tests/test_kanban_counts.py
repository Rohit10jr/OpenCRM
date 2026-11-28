"""A kanban card's badge counts (specs/CONFIGURATION.md 4.8, decision 6; temp A-40).

From ``backend/tests/test_kanban_counts.py``, the property "an invisible row gets no
counts" is twinned here; the count values wait for ACTIVITIES, whose models they count
(`all_count is ruled` is in `test_get_data_kanban.py`). New: the zero default, the
provider setting and its system check.
"""

import sys
import types

import pytest
from django.core.checks import run_checks

from configuration.kanban_counts import COUNT_KEYS
from tests_support.models import Widget

pytestmark = pytest.mark.django_db

URL = "/api/v1/test-widgets/list-view/"


def kanban(client):
    response = client.post(
        URL,
        {"view": {"view_type": "kanban"}, "column_field": "status", "kanban_columns": [{"name": "Open"}]},
        format="json",
    )
    assert response.status_code == 200, response.json()
    return response.json()["message"]["data"][0]["data"]


@pytest.fixture
def provider_module():
    module = types.ModuleType("fake_kanban_counts")
    module.calls = []

    def counts_for(doctype, names):
        module.calls.append((doctype, list(names)))
        return {name: dict.fromkeys(COUNT_KEYS, 3) for name in names}

    module.counts_for = counts_for
    sys.modules["fake_kanban_counts"] = module
    yield module
    del sys.modules["fake_kanban_counts"]


def test_every_card_has_the_four_counts_at_zero_by_default(alice, auth_api):
    Widget(widget_name="A", status="Open", widget_owner=alice).save(user=alice)
    [card] = kanban(auth_api)
    assert {key: card[key] for key in COUNT_KEYS} == dict.fromkeys(COUNT_KEYS, 0)


def test_the_provider_is_asked_once_per_column_for_the_visible_cards(alice, bob, api_as, settings, provider_module):
    settings.KANBAN_COUNTS_PROVIDER = "fake_kanban_counts"
    mine = Widget(widget_name="A", status="Open", widget_owner=alice)
    mine.save(user=alice)
    Widget(widget_name="B", status="Open", widget_owner=bob).save(user=bob)
    [card] = kanban(api_as(alice))
    assert card["_comment_count"] == 3
    # An invisible row gets no counts: only Alice's card is asked about.
    assert provider_module.calls == [("Foundation Widget", [mine.name])]


def test_a_provider_that_does_not_resolve_fails_the_check(settings):
    settings.KANBAN_COUNTS_PROVIDER = "no_such_module_for_counts"
    assert "configuration.E001" in {message.id for message in run_checks()}


def test_a_provider_without_counts_for_fails_the_check(settings):
    sys.modules["empty_counts_provider"] = types.ModuleType("empty_counts_provider")
    try:
        settings.KANBAN_COUNTS_PROVIDER = "empty_counts_provider"
        assert "configuration.E001" in {message.id for message in run_checks()}
    finally:
        del sys.modules["empty_counts_provider"]


def test_no_provider_passes_the_check(settings):
    settings.KANBAN_COUNTS_PROVIDER = ""
    assert "configuration.E001" not in {message.id for message in run_checks()}
