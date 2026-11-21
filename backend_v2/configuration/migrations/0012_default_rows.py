"""Write the default field layouts, quick filters and standard form scripts
(specs/CONFIGURATION.md §10.1-10.2; owner, temp A-48 group 4).

Rows a database is promised from its first migrate, no longer development data. The
rows come from the shared data file `configuration/data/default_rows.json`; the writing
code is frozen here and imports no live code, so a later change to it cannot break this
migration on a fresh install. Historical models only, `create` with every column. Each
writer skips a row that exists and never updates one. Numbered 0012: 0011 is the Email
Account secret width (temp A-75).
"""

import json
import pathlib
import secrets
from datetime import timedelta

from django.db import migrations
from django.utils import timezone

DATA_FILE = pathlib.Path(__file__).resolve().parents[1] / "data" / "default_rows.json"
PRODUCT_SCRIPT_DOCTYPES = ("CRM Lead", "CRM Deal")
FORECASTING_SCRIPT_NAME = "Forecasting Script"
QUICK_FILTERS = "Quick Filters"


class _Stamp:
    """`owner`/`modified_by` Administrator, `creation = modified = now + offset µs`, one
    offset per row in file order, as `configuration/0004` stamps its rows."""

    def __init__(self):
        self.now = timezone.now()
        self.offset = 0

    def __call__(self) -> dict:
        moment = self.now + timedelta(microseconds=self.offset)
        self.offset += 1
        return {
            "owner_id": "Administrator",
            "modified_by_id": "Administrator",
            "creation": moment,
            "modified": moment,
        }


def _layouts(apps, rows, stamp):
    CRMFieldsLayout = apps.get_model("configuration", "CRMFieldsLayout")
    for spec in rows["layouts"]:
        name = f"{spec['dt']}-{spec['type']}"
        values = stamp()
        if CRMFieldsLayout._default_manager.filter(pk=name).exists():
            continue
        CRMFieldsLayout._default_manager.create(
            name=name, dt=spec["dt"], type=spec["type"], layout=spec["layout"], **values
        )


def _quick_filters(apps, rows, stamp):
    CRMGlobalSettings = apps.get_model("configuration", "CRMGlobalSettings")
    for doctype, fields in rows["quick_filters"].items():
        values = stamp()
        if CRMGlobalSettings._default_manager.filter(dt=doctype, type=QUICK_FILTERS).exists():
            continue
        CRMGlobalSettings._default_manager.create(
            name=secrets.token_hex(5), dt=doctype, type=QUICK_FILTERS, json=list(fields), **values
        )


def _form_scripts(apps, rows, stamp):
    CRMFormScript = apps.get_model("configuration", "CRMFormScript")
    scripts = [
        (
            "Product Details Script for " + doctype,
            doctype,
            # Frozen copy of the composition in the old dev_data.product_details_script.
            "class " + doctype.replace(" ", "") + " {" + rows["product_details_script_body"],
        )
        for doctype in PRODUCT_SCRIPT_DOCTYPES
    ]
    scripts.append((FORECASTING_SCRIPT_NAME, "CRM Deal", rows["forecasting_script"]))
    for name, dt, script in scripts:
        values = stamp()
        if CRMFormScript._default_manager.filter(pk=name).exists():
            continue
        CRMFormScript._default_manager.create(
            name=name, dt=dt, view="Form", script=script, enabled=True, is_standard=True, **values
        )


def write_default_rows(apps, schema_editor):
    rows = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    stamp = _Stamp()
    _layouts(apps, rows, stamp)
    _quick_filters(apps, rows, stamp)
    _form_scripts(apps, rows, stamp)


class Migration(migrations.Migration):
    dependencies = [
        ("configuration", "0011_emailaccount_secret_length"),
        ("accounts", "0002_seed_roles_and_users"),
    ]

    operations = [migrations.RunPython(write_default_rows, migrations.RunPython.noop)]
