"""``crm/install.py:after_install``, ported as ``crm_app.setup`` and
``manage.py seed_defaults``: docs/FINDINGS.md 43.

The frontend assumes these rows: the create dialogs read the Quick Entry layouts, the
lead and deal pages show their status dropdown only once a form script has run, the
Source and Industry pickers list the rows, the quick filters come from CRM Global
Settings and the user menu from FCRM Settings.
"""

import io
import json

import pytest
from django.core.management import call_command

from crm_app import setup
from crm_app.models import (
    CRMCommunicationStatus,
    CRMDashboard,
    CRMDealStatus,
    CRMFieldsLayout,
    CRMFormScript,
    CRMGlobalSettings,
    CRMIndustry,
    CRMLeadSource,
    CRMLeadStatus,
    CRMLostReason,
    FCRMSettings,
)
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

LAYOUT_NAMES = sorted(
    list(setup.QUICK_ENTRY_LAYOUTS) + list(setup.SIDE_PANEL_LAYOUTS) + list(setup.DATA_FIELDS_LAYOUTS)
)


@pytest.fixture
def seeded(administrator):
    with session_user(administrator.name):
        return setup.after_install()


def test_the_first_run_writes_every_group(seeded):
    assert seeded == {
        "lead_statuses": 7,
        "countries": 250,
        "languages": 82,
        # Written by frappe_platform migration 0014, so the install step finds them.
        "genders": 0,
        "salutations": 0,
        "deal_statuses": 7,
        "communication_statuses": 2,
        "fields_layouts": 14,
        "industries": 51,
        "lead_sources": 14,
        "lost_reasons": 9,
        "quick_filters": 6,
        "dropdown_items": 6,
        "form_scripts": 3,
        "dashboard": 1,
    }


def test_lead_and_deal_statuses_match_upstream(seeded):
def test_the_countries_come_from_the_frameworks_list(seeded):
    """``country.py:import_country_and_currency`` over ``country_info.json``: the Link
    target of ``Address.country`` (FINDINGS.md 45)."""
    from frappe_platform.models import Country

    assert Country.objects.count() == 250
    india = Country.objects.get(pk="India")
    assert india.code == "in"
    assert "Asia/Kolkata" in india.time_zones
    assert india.date_format and india.time_format


    ordered = CRMLeadStatus.objects.order_by("position").values_list("lead_status", flat=True)
    assert list(ordered) == ["New", "Contacted", "Nurture", "Qualified", "Converted", "Unqualified", "Junk"]
    qualified = CRMLeadStatus.objects.get(pk="Qualified")
    assert (qualified.color, qualified.type, qualified.position) == ("green", "Won", 4)

    deals = {s.deal_status: s for s in CRMDealStatus.objects.all()}
    assert deals["Ready to Close"].probability == 90
    assert (deals["Lost"].probability, deals["Lost"].type, deals["Lost"].position) == (0, "Lost", 7)
    assert deals["Negotiation"].color == "yellow"

    assert sorted(CRMCommunicationStatus.objects.values_list("status", flat=True)) == ["Open", "Replied"]


def test_the_fourteen_field_layouts_are_named_as_upstream_names_them(seeded):
    rows = {row.pk: row for row in CRMFieldsLayout.objects.all()}
    assert sorted(rows) == LAYOUT_NAMES
    assert rows["CRM Lead-Quick Entry"].type == "Quick Entry"
    assert rows["CRM Lead-Side Panel"].type == "Side Panel"
    assert rows["CRM Deal-Data Fields"].type == "Data Fields"
    sections = json.loads(rows["CRM Lead-Quick Entry"].layout)
    assert [s["name"] for s in sections] == ["person_section", "organization_section", "lead_section"]


def test_the_quick_entry_layout_is_what_the_create_dialog_receives(seeded, api_as, alice):
    """``LeadModal.vue`` asks ``get_fields_layout`` for the Quick Entry layout; without a
    stored one the endpoint falls back to every field of the doctype in unlabeled tabs."""
    response = api_as(alice).post(
        "/api/method/crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout",
        {"doctype": "CRM Lead", "type": "Quick Entry"},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    tabs = response.json()["message"]
    sections = tabs[0]["sections"]
    assert [s["name"] for s in sections] == ["person_section", "organization_section", "lead_section"]
    first_column = sections[0]["columns"][0]["fields"]
    assert [f["fieldname"] for f in first_column] == ["salutation", "email"]


def test_the_reference_lists(seeded):
    assert CRMIndustry.objects.count() == 51
    assert CRMIndustry.objects.filter(pk="Software").exists()
    assert CRMLeadSource.objects.count() == 14
    assert CRMLeadSource.objects.filter(pk="Web Form").exists()
    assert CRMLostReason.objects.count() == 9
    assert CRMLostReason.objects.get(pk="Pricing").description.startswith("The prospect found the pricing")
    assert CRMLostReason.objects.get(pk="Other").description == ""


def test_quick_filters_menu_scripts_and_dashboard(seeded):
    rows = {row.dt: row for row in CRMGlobalSettings.objects.filter(type="Quick Filters")}
    assert sorted(rows) == sorted(setup.QUICK_FILTERS)
    assert rows["CRM Lead"].json == ["lead_name", "email", "organization", "status", "source"]

    assert FCRMSettings.load().dropdown_items.count() == 6

    scripts = {s.pk: s for s in CRMFormScript.objects.all()}
    assert sorted(scripts) == [
        "Forecasting Script",
        "Product Details Script for CRM Deal",
        "Product Details Script for CRM Lead",
    ]
    assert all(s.enabled and s.is_standard and s.view == "Form" for s in scripts.values())
    assert scripts["Product Details Script for CRM Lead"].script.startswith("class CRMLead {\n  update_total()")
    assert scripts["Product Details Script for CRM Deal"].dt == "CRM Deal"
    assert scripts["Forecasting Script"].script == setup.FORECASTING_SCRIPT

    assert CRMDashboard.objects.filter(pk="Manager Dashboard").exists()


def test_the_quick_filters_endpoint_serves_the_seeded_selection(seeded, api_as, alice):
    response = api_as(alice).post(
        "/api/method/crm.api.doc.get_quick_filters", {"doctype": "CRM Deal"}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
    assert [f["fieldname"] for f in response.json()["message"]] == [
        "organization", "status", "probability", "email",
    ]


def test_running_it_again_writes_nothing(seeded, administrator):
    with session_user(administrator.name):
        again = setup.after_install()
    assert all(count == 0 for count in again.values()), again


def test_a_plain_rerun_keeps_an_edited_layout_and_force_rewrites_it(seeded, administrator):
    with session_user(administrator.name):
        CRMFieldsLayout.objects.filter(pk="CRM Lead-Quick Entry").update(layout="[]")
        setup.after_install()
        assert CRMFieldsLayout.objects.get(pk="CRM Lead-Quick Entry").layout == "[]"

        forced = setup.after_install(force=True)
    assert forced["fields_layouts"] == 14
    assert forced["dashboard"] == 1
    restored = json.loads(CRMFieldsLayout.objects.get(pk="CRM Lead-Quick Entry").layout)
    assert restored[0]["name"] == "person_section"


def test_a_standard_product_script_that_drifted_is_brought_back(seeded, administrator):
    name = "Product Details Script for CRM Lead"
    CRMFormScript.objects.filter(pk=name).update(script="// edited by hand")
    with session_user(administrator.name):
        again = setup.after_install()
    assert again["form_scripts"] == 1
    assert CRMFormScript.objects.get(pk=name).script == setup.get_product_details_script("CRM Lead")


def test_the_management_command_runs_it_as_administrator(administrator):
    out = io.StringIO()
    call_command("seed_defaults", stdout=out)
    assert "lead_statuses: 7" in out.getvalue()
    assert "row(s) written" in out.getvalue()
    assert CRMLeadStatus.objects.get(pk="New").owner_id == "Administrator"
    assert CRMIndustry.objects.count() == 51
