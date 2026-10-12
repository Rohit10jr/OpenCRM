"""The dashboard's tile list is what the frontend renders: docs/FINDINGS.md 41.

``DashboardGrid.vue`` places each tile by its ``layout`` (x, y, w, h, i) and
``DashboardItem.vue`` draws only ``number_chart``, ``axis_chart``, ``donut_chart`` and
``spacer``. A tile of any other shape draws nothing, which is how the dashboard came to
be blank with every number in place.
"""

import importlib
import json
import pathlib

import pytest
from django.apps import apps

from crm_app.api.dashboard import (
    CHART_BUILDERS,
    DEFAULT_DASHBOARD_LAYOUT,
    DEFAULT_DASHBOARD_LAYOUT_JSON,
    MANAGER_DASHBOARD,
)
from crm_app.models import CRMDashboard

pytestmark = pytest.mark.django_db

RENDERED_TYPES = {"number_chart", "axis_chart", "donut_chart", "spacer"}

UPSTREAM = pathlib.Path(
    r"D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm\fcrm\doctype"
    r"\crm_dashboard\crm_dashboard.py"
)


def _migration():
    return importlib.import_module("crm_app.migrations.0009_dashboard_tiles_carry_a_layout")


def _row(layout: str) -> CRMDashboard:
    return CRMDashboard._default_manager.create(
        name=MANAGER_DASHBOARD, title=MANAGER_DASHBOARD, layout=layout
    )


def _stored() -> str:
    return CRMDashboard._default_manager.get(pk=MANAGER_DASHBOARD).layout


# --- the default ------------------------------------------------------------------------


def test_the_default_is_upstreams_verbatim():
    """The string is copied from ``default_manager_dashboard_layout``; when the upstream
    checkout is beside this repo, hold it to that."""
    if not UPSTREAM.exists():
        pytest.skip("upstream checkout not present")
    assert DEFAULT_DASHBOARD_LAYOUT_JSON in UPSTREAM.read_text(encoding="utf-8")


def test_every_default_tile_has_a_grid_position_and_a_type_the_frontend_draws():
    assert len(DEFAULT_DASHBOARD_LAYOUT) == 17
    for tile in DEFAULT_DASHBOARD_LAYOUT:
        assert set(tile["layout"]) == {"x", "y", "w", "h", "i"}, tile["name"]
        assert tile["layout"]["i"] == tile["name"]
        assert tile["type"] in RENDERED_TYPES, tile["name"]


def test_every_default_tile_but_the_spacer_has_a_builder():
    names = {tile["name"] for tile in DEFAULT_DASHBOARD_LAYOUT}
    assert names - set(CHART_BUILDERS) == {"spacer"}


def test_get_dashboard_places_and_fills_every_tile_but_the_spacer(auth_api):
    response = auth_api.post("/api/method/crm.api.dashboard.get_dashboard", {}, format="json")
    assert response.status_code == 200, response.content
    tiles = response.json()["message"]
    assert [tile["name"] for tile in tiles] == [tile["name"] for tile in DEFAULT_DASHBOARD_LAYOUT]
    for tile in tiles:
        assert tile["layout"]["i"] == tile["name"]
        if tile["name"] == "spacer":
            assert tile["data"] is None
        else:
            assert tile["data"] is not None, tile["name"]
    # The row the first call wrote holds upstream's string, byte for byte.
    assert _stored() == DEFAULT_DASHBOARD_LAYOUT_JSON


def test_the_migration_carries_the_same_default():
    """The migration keeps its own copy so it stays what it was when it ran; today the
    two agree, and a later change to one is a decision, not an accident."""
    assert _migration().DEFAULT_LAYOUT_JSON == DEFAULT_DASHBOARD_LAYOUT_JSON


# --- the repair -------------------------------------------------------------------------

OLD_SHAPE = json.dumps(
    [
        {"name": "total_leads", "type": "number", "width": 1},
        {"name": "deals_by_stage_donut", "type": "donut", "width": 2},
    ]
)

ARRANGED = json.dumps(
    [
        {
            "name": "won_deals",
            "type": "number_chart",
            "layout": {"x": 0, "y": 0, "w": 4, "h": 3, "i": "won_deals"},
        }
    ]
)


def test_the_migration_rewrites_the_old_tile_shape():
    _row(OLD_SHAPE)
    _migration().forwards(apps, None)
    assert _stored() == _migration().DEFAULT_LAYOUT_JSON


def test_the_migration_leaves_an_arranged_layout_alone():
    _row(ARRANGED)
    _migration().forwards(apps, None)
    assert _stored() == ARRANGED


def test_the_migration_is_a_no_op_without_the_row():
    _migration().forwards(apps, None)
    assert not CRMDashboard._default_manager.filter(pk=MANAGER_DASHBOARD).exists()
