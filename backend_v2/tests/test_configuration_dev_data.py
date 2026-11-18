"""The default layouts, quick filters and form scripts as `seed_dev_data` steps
(specs/CONFIGURATION.md 4.6; temp A-37; DECISIONS 44 parked). The functions are called
directly; the command runs them in `core.dev_data.STEPS`.
"""

import json

import pytest

from configuration import dev_data
from configuration.layouts import check_fieldnames_only
from configuration.models import CRMFieldsLayout, CRMFormScript, CRMGlobalSettings
from core.dev_data import STEPS
from core.models import DevDataRecord

pytestmark = pytest.mark.django_db


def test_the_data_file_holds_the_old_defaults():
    rows = dev_data.default_rows()
    names = [f"{s['dt']}-{s['type']}" for s in rows["layouts"]]
    assert len(names) == 14 == len(set(names))
    assert sorted(rows["quick_filters"]) == sorted(
        ["CRM Lead", "CRM Deal", "Contact", "CRM Organization", "CRM Task", "CRM Call Log"]
    )
    assert rows["quick_filters"]["CRM Task"] == ["title", "priority", "assigned_to", "status", "due_date"]


def test_every_default_layout_is_json_with_fieldnames_only():
    for spec in dev_data.default_rows()["layouts"]:
        check_fieldnames_only(json.loads(spec["layout"]))


def test_the_steps_run_after_users_in_order():
    assert [step.key for step in STEPS] == ["users", "fields_layouts", "quick_filters", "form_scripts"]


def test_layouts_are_written_once_and_recorded(administrator):
    assert dev_data.write_default_layouts(administrator) == 14
    assert dev_data.write_default_layouts(administrator) == 0
    assert CRMFieldsLayout.objects.count() == 14
    assert DevDataRecord.objects.filter(step="fields_layouts").count() == 14
    row = CRMFieldsLayout.objects.get(pk="CRM Task-Quick Entry")
    assert row.owner == administrator


def test_an_existing_layout_is_left_alone_and_off_the_record(administrator):
    CRMFieldsLayout(dt="CRM Lead", type="Quick Entry", layout="[]").save(user=administrator)
    assert dev_data.write_default_layouts(administrator) == 13
    assert CRMFieldsLayout.objects.get(pk="CRM Lead-Quick Entry").layout == "[]"
    assert dev_data.clear_default_layouts(administrator) == 13
    assert list(CRMFieldsLayout.objects.values_list("pk", flat=True)) == ["CRM Lead-Quick Entry"]


def test_force_rewrites_a_layout_and_keeps_the_record_as_it_was(administrator):
    CRMFieldsLayout(dt="CRM Lead", type="Quick Entry", layout="[]").save(user=administrator)
    dev_data.write_default_layouts(administrator)
    CRMFieldsLayout.objects.filter(pk="CRM Task-Quick Entry").update(layout="[]")

    assert dev_data.write_default_layouts(administrator, force=True) == 0
    assert CRMFieldsLayout.objects.get(pk="CRM Lead-Quick Entry").layout != "[]"
    assert CRMFieldsLayout.objects.get(pk="CRM Task-Quick Entry").layout != "[]"
    # The rewritten seed row is still the seed's; the hand-made one never was.
    assert dev_data.clear_default_layouts(administrator) == 13
    assert CRMFieldsLayout.objects.filter(pk="CRM Lead-Quick Entry").exists()


def test_quick_filters_skip_a_doctype_with_a_row(administrator):
    CRMGlobalSettings(dt="CRM Task", type="Quick Filters", json=["title"]).save(user=administrator)
    assert dev_data.write_quick_filters(administrator) == 5
    assert dev_data.write_quick_filters(administrator) == 0
    assert CRMGlobalSettings.first_row("CRM Task", "Quick Filters").json == ["title"]
    assert dev_data.clear_quick_filters(administrator) == 5
    assert CRMGlobalSettings.objects.count() == 1


def test_form_scripts_are_written_once(administrator):
    assert dev_data.sync_standard_form_scripts(administrator) == 3
    assert dev_data.sync_standard_form_scripts(administrator) == 0
    lead = CRMFormScript.objects.get(pk="Product Details Script for CRM Lead")
    assert lead.script.startswith("class CRMLead {")
    assert (lead.dt, lead.view, lead.enabled, lead.is_standard) == ("CRM Lead", "Form", True, True)
    forecasting = CRMFormScript.objects.get(pk="Forecasting Script")
    assert forecasting.dt == "CRM Deal"
    assert forecasting.script.startswith("class CRMDeal {")


def test_a_drifted_product_script_gets_its_text_back_and_nothing_else(administrator):
    dev_data.sync_standard_form_scripts(administrator)
    CRMFormScript.objects.filter(pk="Product Details Script for CRM Deal").update(
        script="changed()", enabled=False
    )
    CRMFormScript.objects.filter(pk="Forecasting Script").update(script="changed()")

    assert dev_data.sync_standard_form_scripts(administrator) == 0
    deal = CRMFormScript.objects.get(pk="Product Details Script for CRM Deal")
    assert deal.script == dev_data.product_details_script("CRM Deal")
    assert deal.enabled is False
    assert CRMFormScript.objects.get(pk="Forecasting Script").script == "changed()"


def test_clear_removes_only_the_scripts_the_seed_created(administrator):
    CRMFormScript(name="Forecasting Script", dt="CRM Deal", script="mine()").save(user=administrator)
    assert dev_data.sync_standard_form_scripts(administrator) == 2
    assert dev_data.clear_standard_form_scripts(administrator) == 2
    assert list(CRMFormScript.objects.values_list("pk", flat=True)) == ["Forecasting Script"]
