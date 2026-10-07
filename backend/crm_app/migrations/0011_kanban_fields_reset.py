"""Reset the kanban card fields the port's fallback wrote into saved views (docs/FINDINGS.md 53).

Upstream's CRM Lead, CRM Deal and CRM Task declare ``default_kanban_settings``: the
column field, the card's title field and the fields a card shows. The port's models
did not, so ``get_data`` fell back to ``["name"]`` for the cards and ``name`` for the
title - and the frontend, which saves the kanban settings it was given the moment a
column is reordered (``create_or_update_standard_view``), wrote that fallback into the
standard kanban view. The models now carry upstream's defaults; this migration repairs
the rows the fallback reached. Only the fallback's exact values are touched: a view a
person configured keeps its fields. Nothing to undo backwards.
"""

import json

from django.db import migrations

#: doctype -> (title_field, kanban_fields), as the three models now declare them.
KANBAN_DEFAULTS = {
    "CRM Lead": ("lead_name", ["organization", "email", "mobile_no", "_assign", "modified"]),
    "CRM Deal": ("organization", ["annual_revenue", "email", "mobile_no", "_assign", "modified"]),
    "CRM Task": ("title", ["description", "priority", "creation"]),
}

FALLBACK_FIELDS = json.dumps(["name"])


def forwards(apps, schema_editor):
    view_settings = apps.get_model("crm_app", "CRMViewSettings")
    for doctype, (title_field, fields) in KANBAN_DEFAULTS.items():
        kanban_views = view_settings.objects.filter(dt=doctype, type="kanban")
        kanban_views.filter(kanban_fields=FALLBACK_FIELDS).update(kanban_fields=json.dumps(fields))
        kanban_views.filter(title_field="name").update(title_field=title_field)


class Migration(migrations.Migration):
    dependencies = [
        ("crm_app", "0010_standard_dropdown_items"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
