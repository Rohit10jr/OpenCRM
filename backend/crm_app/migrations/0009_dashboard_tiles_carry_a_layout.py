"""Give the saved Manager Dashboard the tile shape the frontend renders (docs/FINDINGS.md 41).

Until now the port's default layout was ten tiles of ``{"name", "type", "width"}`` with
the types ``number``, ``donut`` and ``bar``. The frontend's grid places a tile by its
``layout`` object (x, y, w, h, i) and renders only ``number_chart``, ``axis_chart``,
``donut_chart`` and ``spacer``, so every tile of the old shape drew nothing and the
dashboard was blank with all its numbers in place. ``get_dashboard`` wrote that default
into the "Manager Dashboard" row the first time it ran, so the row has to be rewritten,
not just the constant.

Only a row whose tiles all lack ``layout`` is touched: that shape can only have come
from the old default, since nothing the frontend saves lacks the key, so a layout an
administrator arranged in the app is left alone. The replacement is upstream's default
(``crm_dashboard.py:default_manager_dashboard_layout``), copied here rather than
imported so the migration stays what it was when it ran, as a data migration should;
``crm_app.api.dashboard.DEFAULT_DASHBOARD_LAYOUT_JSON`` is the live copy. Nothing to
undo backwards: the old shape is worth nothing to anyone.
"""

import json

from django.db import migrations

MANAGER_DASHBOARD = "Manager Dashboard"

DEFAULT_LAYOUT_JSON = (
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


def tiles_lack_a_layout(layout_json: str | None) -> bool:
    """True for the old port shape: at least one tile, and none carries ``layout``."""
    try:
        tiles = json.loads(layout_json or "[]")
    except ValueError:
        return False
    return bool(tiles) and all(isinstance(tile, dict) and "layout" not in tile for tile in tiles)


def forwards(apps, schema_editor):
    CRMDashboard = apps.get_model("crm_app", "CRMDashboard")
    rows = CRMDashboard._default_manager.filter(pk=MANAGER_DASHBOARD)
    current = rows.values_list("layout", flat=True).first()
    if current is None or not tiles_lack_a_layout(current):
        return
    rows.update(layout=DEFAULT_LAYOUT_JSON)


class Migration(migrations.Migration):
    dependencies = [
        ("crm_app", "0008_singletons_named_after_their_doctype"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
