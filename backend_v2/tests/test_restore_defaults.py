"""`restore_defaults` (specs/CONFIGURATION.md §10.3, §10.6 "Restore plain" and
"Restore --force"; owner, temp A-61 item 1, A-62 item 1). New: the old backend's
`seed_defaults` has no ported test of these.
"""

import io

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from configuration import restore
from configuration.models import (
    Country,
    CRMDropdownItem,
    CRMFieldsLayout,
    CRMFormScript,
    CRMGlobalSettings,
    Currency,
    FCRMSettings,
    Language,
    SystemSettings,
)
from contacts.models import CRMIndustry, Gender, Salutation

pytestmark = pytest.mark.django_db

KEYS = [
    "fields_layouts",
    "quick_filters",
    "form_scripts",
    "countries",
    "currencies",
    "languages",
    "system_settings",
    "fcrm_settings",
    "dropdown_items",
    "salutations",
    "genders",
    "industries",
]


def run(*args):
    out = io.StringIO()
    call_command("restore_defaults", *args, stdout=out)
    lines = out.getvalue().strip().splitlines()
    counts = dict(line.split(": ") for line in lines[:-1])
    return {k: int(v) for k, v in counts.items()}, lines[-1]


def test_a_migrated_database_needs_nothing():
    counts, total = run()
    assert list(counts) == KEYS
    assert set(counts.values()) == {0}
    assert total == "0 row(s) written"


@pytest.mark.parametrize(
    "key,remove",
    [
        ("fields_layouts", lambda: CRMFieldsLayout.objects.filter(pk="CRM Deal-Side Panel").delete()),
        ("quick_filters", lambda: CRMGlobalSettings.objects.filter(dt="CRM Task", type="Quick Filters").delete()),
        ("form_scripts", lambda: CRMFormScript.objects.filter(pk="Forecasting Script").delete()),
        ("countries", lambda: Country.objects.filter(pk="India").delete()),
        ("currencies", lambda: Currency.objects.filter(pk="XAF").delete()),
        ("languages", lambda: Language.objects.filter(pk="fr").delete()),
        ("salutations", lambda: Salutation.objects.filter(pk="Prof").delete()),
        ("genders", lambda: Gender.objects.filter(pk="Other").delete()),
        ("industries", lambda: CRMIndustry.objects.filter(pk="Banking").delete()),
    ],
)
def test_a_deleted_default_comes_back_and_a_second_run_writes_nothing(key, remove):
    remove()
    counts, total = run()
    assert counts[key] == 1
    assert sum(counts.values()) == 1
    assert total == "1 row(s) written"
    again, _ = run()
    assert set(again.values()) == {0}


def test_a_missing_fcrm_settings_row_comes_back_with_its_six_items():
    FCRMSettings.objects.all().delete()
    counts, _ = run()
    assert counts["fcrm_settings"] == 1
    assert counts["dropdown_items"] == 6
    assert CRMDropdownItem.objects.count() == 6


def test_a_missing_system_settings_row_comes_back():
    SystemSettings.objects.all().delete()
    counts, _ = run()
    assert counts["system_settings"] == 1
    assert SystemSettings.objects.filter(pk="System Settings").exists()


def test_an_edited_default_stays_edited():
    CRMFieldsLayout.objects.filter(pk="CRM Lead-Quick Entry").update(layout="[]")
    CRMGlobalSettings.objects.filter(dt="CRM Lead", type="Quick Filters").update(json=["status"])
    CRMFormScript.objects.filter(pk="Forecasting Script").update(script="mine()")
    run()
    assert CRMFieldsLayout.objects.get(pk="CRM Lead-Quick Entry").layout == "[]"
    assert CRMGlobalSettings.objects.get(dt="CRM Lead", type="Quick Filters").json == ["status"]
    assert CRMFormScript.objects.get(pk="Forecasting Script").script == "mine()"


def test_a_drifted_product_script_is_resynced_and_nothing_else_of_it():
    """Owner, temp A-62 item 1: as upstream's crm_products.py:90-105."""
    name = restore.product_script_name("CRM Deal")
    CRMFormScript.objects.filter(pk=name).update(script="changed()", enabled=False)
    counts, _ = run()
    assert counts["form_scripts"] == 1
    script = CRMFormScript.objects.get(pk=name)
    assert script.script == restore.product_details_script("CRM Deal")
    assert script.enabled is False


def test_a_renamed_standard_script_is_added_again_and_the_renamed_one_kept(administrator):
    name = restore.product_script_name("CRM Lead")
    from core.rename import rename_document

    rename_document(CRMFormScript, name, "My Lead Script")
    counts, _ = run()
    assert counts["form_scripts"] == 1
    assert CRMFormScript.objects.filter(pk=name).exists()
    assert CRMFormScript.objects.filter(pk="My Lead Script").exists()


def test_an_administrators_own_rows_are_untouched(administrator):
    CRMFieldsLayout(dt="CRM Task", type="Side Panel", layout="[]").save(user=administrator)
    CRMIndustry(industry="Handmade").save(user=administrator)
    run("--force")
    assert CRMFieldsLayout.objects.get(pk="CRM Task-Side Panel").layout == "[]"
    assert CRMIndustry.objects.filter(pk="Handmade").exists()


def test_force_rewrites_an_edited_default_layout_owned_by_administrator(make_user):
    other = make_user("editor@example.com")
    CRMFieldsLayout.objects.filter(pk="CRM Lead-Quick Entry").update(layout="[]", owner=other)
    counts, total = run("--force")
    assert counts["fields_layouts"] == 14
    row = CRMFieldsLayout.objects.get(pk="CRM Lead-Quick Entry")
    assert row.layout != "[]"
    assert row.owner_id == "Administrator"
    assert total == "14 row(s) written"


def test_force_leaves_an_edited_quick_filter():
    CRMGlobalSettings.objects.filter(dt="CRM Lead", type="Quick Filters").update(json=["status"])
    run("--force")
    assert CRMGlobalSettings.objects.get(dt="CRM Lead", type="Quick Filters").json == ["status"]


@override_settings(DEV_DATA_ALLOWED=False)
def test_it_runs_without_dev_data_allowed():
    Salutation.objects.filter(pk="Prof").delete()
    counts, _ = run()
    assert counts["salutations"] == 1


def test_a_failing_writer_rolls_everything_back(monkeypatch):
    from core import defaults

    def fail(user, force):
        raise RuntimeError("forced")

    Salutation.objects.filter(pk="Prof").delete()
    CRMIndustry.objects.filter(pk="Banking").delete()
    restorers = list(defaults.RESTORERS)
    restorers.insert(len(restorers) - 1, ("broken", fail))  # after genders, before industries
    monkeypatch.setattr(
        "core.management.commands.restore_defaults.RESTORERS", tuple(restorers)
    )
    with pytest.raises(CommandError):
        call_command("restore_defaults", stdout=io.StringIO())
    assert not Salutation.objects.filter(pk="Prof").exists()
    assert not CRMIndustry.objects.filter(pk="Banking").exists()
