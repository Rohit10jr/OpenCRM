"""The default layouts, quick filters and form scripts, as `seed_dev_data` steps
(specs/CONFIGURATION.md section 4.6; temp A-37).

Ported from `backend/crm_app/setup.py:448-553` (upstream `install.py`, `crm_products.py`,
`fcrm_settings.py`); the rows themselves are in `data/default_rows.json`, copied from
`setup.py`'s literals. Whether these rows belong in a data migration instead is parked
for the owner (DECISIONS 44); until then they are development data: each step writes
as Administrator, leaves an existing row alone, and records what it creates in
`DevDataRecord`, so `clear_dev_data` deletes only those rows.
"""

from __future__ import annotations

import functools
import json
import pathlib

from core import dev_records

from .models import CRMFieldsLayout, CRMFormScript, CRMGlobalSettings
from .quick_filters import QUICK_FILTERS

DATA_FILE = pathlib.Path(__file__).resolve().parent / "data" / "default_rows.json"

LAYOUTS_STEP = "fields_layouts"
QUICK_FILTERS_STEP = "quick_filters"
FORM_SCRIPTS_STEP = "form_scripts"

PRODUCT_SCRIPT_DOCTYPES = ("CRM Lead", "CRM Deal")
FORECASTING_SCRIPT_NAME = "Forecasting Script"


@functools.cache
def default_rows() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def product_details_script(doctype: str) -> str:
    """`crm_products.py:112-193`: the class is named after the doctype, spaces removed."""
    return "class " + doctype.replace(" ", "") + " {" + default_rows()["product_details_script_body"]


def product_script_name(doctype: str) -> str:
    return "Product Details Script for " + doctype


# --- layouts -----------------------------------------------------------------------------


def write_default_layouts(user, force: bool = False) -> int:
    """`setup.py:448-465`: the 14 default layouts. `force` deletes a layout that exists
    and writes it again; a replaced row stays on the record only if it was on it."""
    created = 0
    recorded = set(dev_records.recorded_pks(LAYOUTS_STEP, CRMFieldsLayout))
    for spec in default_rows()["layouts"]:
        name = f"{spec['dt']}-{spec['type']}"
        existing = CRMFieldsLayout.objects.filter(pk=name).first()
        if existing is not None:
            if not force:
                continue
            existing.delete()
        row = CRMFieldsLayout(dt=spec["dt"], type=spec["type"], layout=spec["layout"])
        row.save(user=user)
        if existing is None:
            dev_records.record_created(LAYOUTS_STEP, row)
            created += 1
        elif name in recorded:
            dev_records.refresh_record(LAYOUTS_STEP, row)
    return created


def clear_default_layouts(user, force: bool = False) -> int:
    del user, force
    return _clear(LAYOUTS_STEP, CRMFieldsLayout)


# --- quick filters -----------------------------------------------------------------------


def write_quick_filters(user, force: bool = False) -> int:
    """`setup.py:498-505`: one row per doctype unless the doctype has one."""
    del force
    created = 0
    for doctype, fields in default_rows()["quick_filters"].items():
        if CRMGlobalSettings.first_row(doctype, QUICK_FILTERS) is not None:
            continue
        row = CRMGlobalSettings(dt=doctype, type=QUICK_FILTERS, json=list(fields))
        row.save(user=user)
        dev_records.record_created(QUICK_FILTERS_STEP, row)
        created += 1
    return created


def clear_quick_filters(user, force: bool = False) -> int:
    del user, force
    return _clear(QUICK_FILTERS_STEP, CRMGlobalSettings)


# --- form scripts ------------------------------------------------------------------------


def _write_script(user, name: str, dt: str, script: str, *, resync: bool) -> int:
    """Creates the script when missing (1). With `resync`, a script whose text drifted
    gets its text back, nothing else changed (`setup.py:518-532`); not a creation."""
    existing = CRMFormScript.objects.filter(pk=name).first()
    if existing is not None:
        if resync and existing.script != script:
            existing.script = script
            existing.save(user=user)
        return 0
    row = CRMFormScript(
        name=name, dt=dt, view="Form", script=script, enabled=True, is_standard=True
    )
    row.save(user=user)
    dev_records.record_created(FORM_SCRIPTS_STEP, row)
    return 1


def sync_standard_form_scripts(user, force: bool = False) -> int:
    """`setup.py:550-553`: the product details scripts for CRM Lead and CRM Deal,
    re-synced when drifted, and the forecasting script, written only when missing."""
    del force
    created = sum(
        _write_script(
            user,
            product_script_name(doctype),
            doctype,
            product_details_script(doctype),
            resync=True,
        )
        for doctype in PRODUCT_SCRIPT_DOCTYPES
    )
    return created + _write_script(
        user,
        FORECASTING_SCRIPT_NAME,
        "CRM Deal",
        default_rows()["forecasting_script"],
        resync=False,
    )


def clear_standard_form_scripts(user, force: bool = False) -> int:
    del user, force
    return _clear(FORM_SCRIPTS_STEP, CRMFormScript)


def _clear(step: str, model) -> int:
    """Deletes only the rows this step created and recorded (DECISIONS 9, A-26)."""
    recorded = dev_records.recorded_pks(step, model)
    seeded = dev_records.still_seeded(step, model, model.objects.filter(pk__in=recorded))
    model.objects.filter(pk__in=[row.pk for row in seeded]).delete()
    dev_records.forget(step, model)
    return len(seeded)
