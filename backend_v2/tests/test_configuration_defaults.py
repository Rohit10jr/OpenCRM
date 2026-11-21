"""CONFIGURATION's default rows by migration (specs/CONFIGURATION.md §10.1, §10.2, §10.6).

The 14 layouts, 6 quick filters and 3 standard form scripts are written by
`configuration/0012_default_rows` (owner, temp A-48 group 4), not by `seed_dev_data`.
The two data-file tests are kept from the old file; the step tests are replaced by
these, as §10.6's table says. The restore cases come with `restore_defaults` (step 3).
Ported cases: ``backend/tests/test_seed_defaults.py:132-134`` (quick filter rows) and
`:138-147` (the form scripts, exact text).
"""

import importlib
import json

import pytest
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from configuration import restore
from configuration.layouts import check_fieldnames_only
from configuration.models import CRMFieldsLayout, CRMFormScript, CRMGlobalSettings
from core.models import DevDataRecord

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _dev_data_allowed(settings):
    """The upgrade test runs clear_dev_data; the test settings leave the flag off."""
    settings.DEV_DATA_ALLOWED = True

SCRIPT_NAMES = [
    "Forecasting Script",
    "Product Details Script for CRM Deal",
    "Product Details Script for CRM Lead",
]


def _assert_stamp(row):
    """§10.2's common columns on a row the migration's own function wrote."""
    assert row.owner_id == row.modified_by_id == "Administrator"
    assert row.creation == row.modified
    assert (row.idx, row.docstatus) == (0, 0)
    assert (row._assign, row._liked_by, row._comments, row._user_tags) == ([], [], [], "")


def _historical(app, migration):
    return MigrationLoader(connection).project_state((app, migration)).apps


def _module(path):
    return importlib.import_module(path)


# --- the data file (kept) ------------------------------------------------------------------


def test_the_data_file_holds_the_old_defaults():
    rows = restore.default_rows()
    names = [f"{s['dt']}-{s['type']}" for s in rows["layouts"]]
    assert len(names) == 14 == len(set(names))
    assert sorted(rows["quick_filters"]) == sorted(
        ["CRM Lead", "CRM Deal", "Contact", "CRM Organization", "CRM Task", "CRM Call Log"]
    )
    assert rows["quick_filters"]["CRM Task"] == ["title", "priority", "assigned_to", "status", "due_date"]


def test_every_default_layout_is_json_with_fieldnames_only():
    for spec in restore.default_rows()["layouts"]:
        check_fieldnames_only(json.loads(spec["layout"]))


# --- what the migration wrote ----------------------------------------------------------------


def test_the_migration_wrote_the_14_layouts_by_name():
    expected = {f"{s['dt']}-{s['type']}": s for s in restore.default_rows()["layouts"]}
    rows = {row.pk: row for row in CRMFieldsLayout.objects.all()}
    assert set(rows) == set(expected)
    for name, spec in expected.items():
        row = rows[name]
        assert (row.dt, row.type, row.layout) == (spec["dt"], spec["type"], spec["layout"])
        assert row.owner_id == row.modified_by_id == "Administrator"


def test_the_migration_wrote_the_6_quick_filters_from_the_file():
    """Ported from `backend/tests/test_seed_defaults.py:132-134`."""
    rows = {row.dt: row for row in CRMGlobalSettings.objects.filter(type="Quick Filters")}
    assert sorted(rows) == sorted(restore.default_rows()["quick_filters"])
    assert rows["CRM Lead"].json == ["lead_name", "email", "organization", "status", "source"]
    for doctype, fields in restore.default_rows()["quick_filters"].items():
        assert rows[doctype].json == fields
        assert len(rows[doctype].pk) == 10


def test_the_migration_wrote_the_3_form_scripts():
    """Ported from `backend/tests/test_seed_defaults.py:138-147`, exact text."""
    scripts = {s.pk: s for s in CRMFormScript.objects.all()}
    assert sorted(scripts) == SCRIPT_NAMES
    assert all(s.enabled and s.is_standard and s.view == "Form" for s in scripts.values())
    lead = scripts["Product Details Script for CRM Lead"]
    assert lead.script.startswith("class CRMLead {\n  update_total()")
    assert lead.script == restore.product_details_script("CRM Lead")
    deal = scripts["Product Details Script for CRM Deal"]
    assert deal.dt == "CRM Deal"
    assert deal.script == restore.product_details_script("CRM Deal")
    forecasting = scripts["Forecasting Script"]
    assert forecasting.dt == "CRM Deal"
    assert forecasting.script == restore.default_rows()["forecasting_script"]


# --- the migration's function on its own historical apps (§10.6 "New") ----------------------


def test_the_function_rewrites_only_what_is_missing_with_every_column(administrator):
    CRMFieldsLayout.objects.filter(pk="CRM Task-Quick Entry").delete()
    CRMFieldsLayout.objects.filter(pk="CRM Lead-Quick Entry").update(layout="[]")
    CRMGlobalSettings.objects.filter(dt="CRM Task", type="Quick Filters").delete()
    CRMFormScript.objects.filter(pk="Forecasting Script").delete()
    module = _module("configuration.migrations.0012_default_rows")

    module.write_default_rows(_historical("configuration", "0012_default_rows"), None)

    spec = next(
        s for s in restore.default_rows()["layouts"] if (s["dt"], s["type"]) == ("CRM Task", "Quick Entry")
    )
    restored = CRMFieldsLayout.objects.get(pk="CRM Task-Quick Entry")
    _assert_stamp(restored)
    assert (restored.dt, restored.type, restored.layout) == ("CRM Task", "Quick Entry", spec["layout"])
    assert CRMFieldsLayout.objects.get(pk="CRM Lead-Quick Entry").layout == "[]"

    task = CRMGlobalSettings.objects.get(dt="CRM Task", type="Quick Filters")
    _assert_stamp(task)
    assert task.json == restore.default_rows()["quick_filters"]["CRM Task"]
    assert len(task.pk) == 10 and all(c in "0123456789abcdef" for c in task.pk)

    script = CRMFormScript.objects.get(pk="Forecasting Script")
    _assert_stamp(script)
    assert (script.dt, script.view, script.enabled, script.is_standard) == ("CRM Deal", "Form", True, True)
    assert script.script == restore.default_rows()["forecasting_script"]
    assert CRMFieldsLayout.objects.count() == 14
    assert CRMGlobalSettings.objects.filter(type="Quick Filters").count() == 6


def test_an_administrators_own_row_is_untouched(administrator):
    CRMFieldsLayout(dt="CRM Task", type="Data Fields", layout="[]").save(user=administrator)
    module = _module("configuration.migrations.0012_default_rows")
    module.write_default_rows(_historical("configuration", "0012_default_rows"), None)
    assert CRMFieldsLayout.objects.get(pk="CRM Task-Data Fields").layout == "[]"


# --- the DevDataRecord tidy-up and an upgrade from the old seed ------------------------------


def _record(step, model_label, pk):
    DevDataRecord.objects.create(step=step, model_label=model_label, object_pk=pk)


def test_the_tidy_up_forgets_the_four_retired_steps():
    for index, step in enumerate(
        ("fields_layouts", "quick_filters", "form_scripts", "industries", "users")
    ):
        _record(step, "x.Y", str(index))
    module = _module("core.migrations.0004_retire_default_row_steps")
    module.forget_retired_steps(_historical("core", "0004_retire_default_row_steps"), None)
    assert list(DevDataRecord.objects.values_list("step", flat=True)) == ["users"]


def test_an_upgrade_from_a_database_the_old_seed_filled(administrator, monkeypatch):
    """Rows with their old records: unchanged by the migrations, the records gone, and
    clear_dev_data leaves every row."""
    import io

    from django.core.management import call_command

    from tests.test_dev_data_commands import PASSWORDS

    for row in CRMFieldsLayout.objects.all():
        _record("fields_layouts", "configuration.crmfieldslayout", row.pk)
    for row in CRMFormScript.objects.all():
        _record("form_scripts", "configuration.crmformscript", row.pk)
    layouts = dict(CRMFieldsLayout.objects.values_list("pk", "layout"))

    _module("configuration.migrations.0012_default_rows").write_default_rows(
        _historical("configuration", "0012_default_rows"), None
    )
    _module("core.migrations.0004_retire_default_row_steps").forget_retired_steps(
        _historical("core", "0004_retire_default_row_steps"), None
    )
    assert dict(CRMFieldsLayout.objects.values_list("pk", "layout")) == layouts
    assert not DevDataRecord.objects.exclude(step="users").exists()

    for variable, value in PASSWORDS.items():
        monkeypatch.setenv(variable, value)
    call_command("clear_dev_data", stdout=io.StringIO())
    assert CRMFieldsLayout.objects.count() == 14
    assert sorted(CRMFormScript.objects.values_list("pk", flat=True)) == SCRIPT_NAMES
    assert CRMGlobalSettings.objects.filter(type="Quick Filters").count() == 6
