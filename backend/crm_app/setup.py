"""``crm/install.py:after_install``: the reference rows a site needs before its first screen.

Upstream writes these once, when the app is installed on a site (``bench install-app``
runs ``after_install``), and the frontend assumes they are there: every create dialog
reads its fields from the doctype's Quick Entry layout, the lead and deal pages show
their status dropdown only once a form script has run, the Source and Industry pickers
list the rows, the quick filters come from CRM Global Settings, and the user menu from
FCRM Settings' dropdown items (docs/FINDINGS.md 43). The port has no install step, so
the same rows are written by ``python manage.py seed_defaults``, which calls
:func:`after_install` here as Administrator.

Every function is idempotent, as upstream's are: a row that exists is kept, so a re-run
never overwrites an administrator's changes. ``force`` rewrites the field layouts and
the dashboard, as upstream's ``FCRMSettings.restore_defaults`` does. The two standard
product scripts are brought back in line with the code when they differ, as upstream's
``create_product_details_script`` does on every migrate.

Not ported, because the port has no such mechanism: the Property Setters and Custom
Fields upstream adds to Email Template, Email Account, Web Form and Assignment Rule
(``add_property_setter``, the three ``add_*_custom_fields`` and
``add_assignment_rule_property_setters``); the columns they add are part of the models
here. The data below is upstream's, verbatim, with the ``install.py`` line of each.
"""

from __future__ import annotations

import json
import pathlib

from crm_app.api.dashboard import create_default_manager_dashboard
from crm_app.models import (
    CRMCommunicationStatus,
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
from crm_app.models.metadata import add_standard_dropdown_items as _seed_dropdown_items
from frappe_platform.models import Country, Language

# The two lookup lists live with the framework doctypes they fill; a migration writes
# them and this install step puts back any that were deleted (FINDINGS.md 66).
from frappe_platform.reference_data import (  # noqa: F401 - re-exported for callers
    GENDERS,
    SALUTATIONS,
    add_genders,
    add_salutations,
)

# --- countries (frappe/geo/doctype/country/country.py:import_country_and_currency) ---------
# The framework seeds these when a site is set up, before any app installs, from
# ``frappe/geo/country_info.json``; a copy of that file sits in ``crm_app/data``. They are
# the Link target of ``Address.country`` (FINDINGS.md 45). The Currency rows the same
# import writes are not ported: nothing in the CRM reads them.

COUNTRY_INFO = pathlib.Path(__file__).resolve().parent / "data" / "country_info.json"

# --- statuses (install.py:38-158) ----------------------------------------------------------

LEAD_STATUSES = {
    "New": {"color": "gray", "type": "Open", "position": 1},
    "Contacted": {"color": "orange", "type": "Ongoing", "position": 2},
    "Nurture": {"color": "blue", "type": "Ongoing", "position": 3},
    "Qualified": {"color": "green", "type": "Won", "position": 4},
    "Converted": {"color": "teal", "type": "Won", "position": 5},
    "Unqualified": {"color": "red", "type": "Lost", "position": 6},
    "Junk": {"color": "purple", "type": "Lost", "position": 7},
}

DEAL_STATUSES = {
    "Qualification": {"color": "gray", "type": "Open", "probability": 10, "position": 1},
    "Demo/Making": {"color": "orange", "type": "Ongoing", "probability": 25, "position": 2},
    "Proposal/Quotation": {"color": "blue", "type": "Ongoing", "probability": 50, "position": 3},
    "Negotiation": {"color": "yellow", "type": "Ongoing", "probability": 70, "position": 4},
    "Ready to Close": {"color": "purple", "type": "Ongoing", "probability": 90, "position": 5},
    "Won": {"color": "green", "type": "Won", "probability": 100, "position": 6},
    "Lost": {"color": "red", "type": "Lost", "probability": 0, "position": 7},
}

COMMUNICATION_STATUSES = ("Open", "Replied")

# --- field layouts (install.py:160-264) ----------------------------------------------------
# Keyed by the row's name, which ``CRMFieldsLayout``'s ``{dt}-{type}`` naming reproduces.

QUICK_ENTRY_LAYOUTS = {
    "CRM Lead-Quick Entry": {
        "doctype": "CRM Lead",
        "layout": '[{"name": "person_section", "columns": [{"name": "column_5jrk", "fields": ["salutation", "email"]}, {"name": "column_5CPV", "fields": ["first_name", "mobile_no"]}, {"name": "column_gXOy", "fields": ["last_name", "gender"]}]}, {"name": "organization_section", "columns": [{"name": "column_GHfX", "fields": ["organization", "territory"]}, {"name": "column_hXjS", "fields": ["website", "annual_revenue"]}, {"name": "column_RDNA", "fields": ["no_of_employees", "industry"]}]}, {"name": "lead_section", "columns": [{"name": "column_EO1H", "fields": ["status"]}, {"name": "column_RWBe", "fields": ["lead_owner"]}]}]',
    },
    "CRM Deal-Quick Entry": {
        "doctype": "CRM Deal",
        "layout": '[{"name": "organization_section", "hidden": true, "editable": false, "columns": [{"name": "column_GpMP", "fields": ["organization"]}, {"name": "column_FPTn", "fields": []}]}, {"name": "organization_details_section", "editable": false, "columns": [{"name": "column_S3tQ", "fields": ["organization_name", "territory"]}, {"name": "column_KqV1", "fields": ["website", "annual_revenue"]}, {"name": "column_1r67", "fields": ["no_of_employees", "industry"]}]}, {"name": "contact_section", "hidden": true, "editable": false, "columns": [{"name": "column_CeXr", "fields": ["contact"]}, {"name": "column_yHbk", "fields": []}]}, {"name": "contact_details_section", "editable": false, "columns": [{"name": "column_ZTWr", "fields": ["salutation", "email"]}, {"name": "column_tabr", "fields": ["first_name", "mobile_no"]}, {"name": "column_Qjdx", "fields": ["last_name", "gender"]}]}, {"name": "deal_section", "columns": [{"name": "column_mdps", "fields": ["status"]}, {"name": "column_H40H", "fields": ["deal_owner"]}]}]',
    },
    "Contact-Quick Entry": {
        "doctype": "Contact",
        "layout": '[{"name": "salutation_section", "columns": [{"name": "column_eXks", "fields": ["salutation"]}]}, {"name": "full_name_section", "hideBorder": true, "columns": [{"name": "column_cSxf", "fields": ["first_name"]}, {"name": "column_yBc7", "fields": ["last_name"]}]}, {"name": "email_section", "hideBorder": true, "columns": [{"name": "column_tH3L", "fields": ["email_id"]}]}, {"name": "mobile_gender_section", "hideBorder": true, "columns": [{"name": "column_lrfI", "fields": ["mobile_no"]}, {"name": "column_Tx3n", "fields": ["gender"]}]}, {"name": "organization_section", "hideBorder": true, "columns": [{"name": "column_S0J8", "fields": ["company_name"]}]}, {"name": "designation_section", "hideBorder": true, "columns": [{"name": "column_bsO8", "fields": ["designation"]}]}, {"name": "address_section", "hideBorder": true, "columns": [{"name": "column_W3VY", "fields": ["address"]}]}]',
    },
    "CRM Organization-Quick Entry": {
        "doctype": "CRM Organization",
        "layout": '[{"name": "organization_section", "columns": [{"name": "column_zOuv", "fields": ["organization_name"]}]}, {"name": "website_revenue_section", "hideBorder": true, "columns": [{"name": "column_I5Dy", "fields": ["website"]}, {"name": "column_Rgss", "fields": ["annual_revenue"]}]}, {"name": "territory_section", "hideBorder": true, "columns": [{"name": "column_w6ap", "fields": ["territory"]}]}, {"name": "employee_industry_section", "hideBorder": true, "columns": [{"name": "column_u5tZ", "fields": ["no_of_employees"]}, {"name": "column_FFrT", "fields": ["industry"]}]}, {"name": "address_section", "hideBorder": true, "columns": [{"name": "column_O2dk", "fields": ["address"]}]}]',
    },
    "Address-Quick Entry": {
        "doctype": "Address",
        "layout": '[{"name": "details_section", "columns": [{"name": "column_uSSG", "fields": ["address_title", "address_type", "address_line1", "address_line2"]}]}, {"name": "location_section", "hideBorder": true, "columns": [{"name": "column_TCoZ", "fields": ["country", "city"]}, {"name": "column_PqrK", "fields": ["state", "pincode"]}]}]',
    },
    "CRM Call Log-Quick Entry": {
        "doctype": "CRM Call Log",
        "layout": '[{"name":"details_section","columns":[{"name":"column_uMSG","fields":["type","from","duration"]},{"name":"column_wiZT","fields":["to","status","caller","receiver"]}]}]',
    },
    "FCRM Note-Quick Entry": {
        "doctype": "FCRM Note",
        "layout": '[{"name":"details_section","columns":[{"name":"column_o2s9","fields":["title", "content"]}]}]',
    },
    "CRM Task-Quick Entry": {
        "doctype": "CRM Task",
        "layout": '[{"name":"first_tab","sections":[{"name":"details_section","columns":[{"name":"column_X9sG","fields":["title","description"]}]},{"name":"assignment_section","columns":[{"name":"column_9XjK","fields":["priority","due_date"]},{"name":"column_7s8n","fields":["assigned_to","status"]}],"hideBorder":true}]}]',
    },
}

SIDE_PANEL_LAYOUTS = {
    "CRM Lead-Side Panel": {
        "doctype": "CRM Lead",
        "layout": '[{"label": "Details", "name": "details_section", "opened": true, "columns": [{"name": "column_kl92", "fields": ["organization", "website", "territory", "industry", "job_title", "source", "lead_owner"]}]}, {"label": "Person", "name": "person_section", "opened": true, "columns": [{"name": "column_XmW2", "fields": ["salutation", "first_name", "last_name", "email", "mobile_no"]}]}]',
    },
    "CRM Deal-Side Panel": {
        "doctype": "CRM Deal",
        "layout": '[{"label": "Contacts", "name": "contacts_section", "opened": true, "editable": false, "contacts": []}, {"label": "Organization Details", "name": "organization_section", "opened": true, "columns": [{"name": "column_na2Q", "fields": ["organization", "website", "territory", "annual_revenue", "closed_date", "probability", "next_step", "deal_owner"]}]}]',
    },
    "Contact-Side Panel": {
        "doctype": "Contact",
        "layout": '[{"label": "Details", "name": "details_section", "opened": true, "columns": [{"name": "column_eIWl", "fields": ["salutation", "first_name", "last_name", "email_id", "mobile_no", "gender", "company_name", "designation", "address"]}]}]',
    },
    "CRM Organization-Side Panel": {
        "doctype": "CRM Organization",
        "layout": '[{"label": "Details", "name": "details_section", "opened": true, "columns": [{"name": "column_IJOV", "fields": ["organization_name", "website", "territory", "industry", "no_of_employees", "address"]}]}]',
    },
}

DATA_FIELDS_LAYOUTS = {
    "CRM Lead-Data Fields": {
        "doctype": "CRM Lead",
        "layout": '[{"label": "Details", "name": "details_section", "opened": true, "columns": [{"name": "column_ZgLG", "fields": ["organization", "industry", "lead_owner"]}, {"name": "column_TbYq", "fields": ["website", "job_title"]}, {"name": "column_OKSX", "fields": ["territory", "source"]}]}, {"label": "Person", "name": "person_section", "opened": true, "columns": [{"name": "column_6c5g", "fields": ["salutation", "email"]}, {"name": "column_1n7Q", "fields": ["first_name", "mobile_no"]}, {"name": "column_cT6C", "fields": ["last_name"]}]}]',
    },
    "CRM Deal-Data Fields": {
        "doctype": "CRM Deal",
        "layout": '[{"name":"first_tab","sections":[{"label":"Details","name":"details_section","opened":true,"columns":[{"name":"column_z9XL","fields":["organization","annual_revenue","next_step"]},{"name":"column_gM4w","fields":["website","closed_date","deal_owner"]},{"name":"column_gWmE","fields":["territory","probability"]}]},{"label":"Products","name":"section_jHhQ","opened":true,"columns":[{"name":"column_xiNF","fields":["products"]}],"editingLabel":false,"hideLabel":true},{"label":"New Section","name":"section_WNOQ","opened":true,"columns":[{"name":"column_ziBW","fields":["total"]},{"label":"","name":"column_wuwA","fields":["net_total"]}],"hideBorder":true,"hideLabel":true}]}]',
    },
}

# --- reference lists (install.py:381-509) --------------------------------------------------

INDUSTRIES = (
    "Accounting",
    "Advertising",
    "Aerospace",
    "Agriculture",
    "Airline",
    "Apparel & Accessories",
    "Automotive",
    "Banking",
    "Biotechnology",
    "Broadcasting",
    "Brokerage",
    "Chemical",
    "Computer",
    "Consulting",
    "Consumer Products",
    "Cosmetics",
    "Defense",
    "Department Stores",
    "Education",
    "Electronics",
    "Energy",
    "Entertainment & Leisure, Executive Search",
    "Financial Services",
    "Food",
    "Beverage & Tobacco",
    "Grocery",
    "Health Care",
    "Internet Publishing",
    "Investment Banking",
    "Legal",
    "Manufacturing",
    "Motion Picture & Video",
    "Music",
    "Newspaper Publishers",
    "Online Auctions",
    "Pension Funds",
    "Pharmaceuticals",
    "Private Equity",
    "Publishing",
    "Real Estate",
    "Retail & Wholesale",
    "Securities & Commodity Exchanges",
    "Service",
    "Soap & Detergent",
    "Software",
    "Sports",
    "Technology",
    "Telecommunications",
    "Television",
    "Transportation",
    "Venture Capital",
)

LEAD_SOURCES = (
    "Email",
    "Existing Customer",
    "Reference",
    "Advertisement",
    "Cold Calling",
    "Exhibition",
    "Supplier Reference",
    "Mass Mailing",
    "Customer's Vendor",
    "Campaign",
    "Walk In",
    "Facebook",
    "Website",
    "Web Form",
)

LOST_REASONS = (
    {
        "reason": "Pricing",
        "description": "The prospect found the pricing to be too high or not competitive.",
    },
    {"reason": "Competition", "description": "The prospect chose a competitor's product or service."},
    {
        "reason": "Budget Constraints",
        "description": "The prospect did not have the budget to proceed with the purchase.",
    },
    {
        "reason": "Missing Features",
        "description": "The prospect felt that the product or service was missing key features they needed.",
    },
    {
        "reason": "Long Sales Cycle",
        "description": "The sales process took too long, leading to loss of interest.",
    },
    {
        "reason": "No Decision-Maker",
        "description": "The prospect was not the decision-maker and could not proceed.",
    },
    {"reason": "Unresponsive Prospect", "description": "The prospect did not respond to follow-ups."},
    {"reason": "Poor Fit", "description": "The prospect was not a good fit for the product or service."},
    {"reason": "Other", "description": ""},
)

# install.py:510-527. The port's ``get_quick_filters`` reads the row by dt and the type
# "Quick Filters" (crm_app/api/doc.py), so the row is matched on both.
QUICK_FILTERS = {
    "CRM Lead": ["lead_name", "email", "organization", "status", "source"],
    "CRM Deal": ["organization", "status", "probability", "email"],
    "Contact": ["status", "email_id", "phone"],
    "CRM Organization": ["organization_name", "no_of_employees", "territory", "industry"],
    "CRM Task": ["title", "priority", "assigned_to", "status", "due_date"],
    "CRM Call Log": ["telephony_medium", "type", "status", "from", "to"],
}

# --- the standard form scripts (crm_products.py:91-193, fcrm_settings.py:217-246) ----------

PRODUCT_DETAILS_SCRIPT_BODY = """
  update_total() {
    let total = 0
    let total_qty = 0
    let net_total = 0
    let discount_applied = false

    this.doc.products.forEach((d) => {
      total += d.amount
      net_total += d.net_amount
      if (d.discount_percentage > 0) {
        discount_applied = true
      }
    })

    this.doc.total = total
    this.doc.net_total = net_total || total

    if (!net_total && discount_applied) {
      this.doc.net_total = net_total
    }
  }
}

class CRMProducts {
  products_add() {
    let row = this.doc.getRow('products')
    row.trigger('qty')
    this.doc.trigger('update_total')
  }

  products_remove() {
    this.doc.trigger('update_total')
  }

  async product_code(idx) {
    let row = this.doc.getRow('products', idx)
    let productCode = row.product_code

    let a = await call("crm.fcrm.doctype.crm_products.crm_products.get_product_rate_details", {
        product_code: productCode,
        deal: this.doc.name,
    })
    if (!a || row.product_code !== productCode) return

    row.product_name = a.product_name
    row.rate = a.rate ?? 0
    row.trigger("rate")
  }

  qty(idx) {
    let row = this.doc.getRow('products', idx)
    row.amount = row.qty * row.rate
    row.trigger('discount_percentage', idx)
  }

  rate() {
    let row = this.doc.getRow('products')
    row.amount = row.qty * row.rate
    row.trigger('discount_percentage')
  }

  discount_percentage(idx) {
    let row = this.doc.getRow('products', idx)
    if (!row.discount_percentage) {
      row.net_amount = row.amount
      row.discount_amount = 0
    }
    if (row.discount_percentage && row.amount) {
      row.discount_amount = (row.discount_percentage / 100) * row.amount
      row.net_amount = row.amount - row.discount_amount
    }
    this.doc.trigger('update_total')
  }
}"""

FORECASTING_SCRIPT = """class CRMDeal {
    async status() {
        await this.doc.trigger('updateProbability')
    }
    async updateProbability() {
        let status = await call("frappe.client.get_value", {
            doctype: "CRM Deal Status",
            fieldname: "probability",
            filters: { name: this.doc.status },
        })

        this.doc.probability = status.probability
    }
}"""


def get_product_details_script(doctype: str) -> str:
    """``crm_products.py:112-193``: the class is named after the doctype, spaces removed."""
    return "class " + doctype.replace(" ", "") + " {" + PRODUCT_DETAILS_SCRIPT_BODY


# --- the functions, one per upstream function -----------------------------------------------


def _exists(model, name: str) -> bool:
    return model._default_manager.filter(pk=name).exists()


def add_countries() -> int:
    """``country.py:53-75``: one Country per entry of ``country_info.json``, named after
    the country, with the framework's fallbacks for the two formats."""
    data = json.loads(COUNTRY_INFO.read_text(encoding="utf-8"))
    existing = set(Country._default_manager.values_list("pk", flat=True))
    written = 0
    for name, info in data.items():
        if name in existing:
            continue
        Country(
            country_name=name,
            code=info.get("code") or "",
            date_format=info.get("date_format") or "dd-mm-yyyy",
            time_format=info.get("time_format") or "HH:mm:ss",
            time_zones="\n".join(info.get("timezones") or []),
        ).save()
        written += 1
    return written


LANGUAGES = pathlib.Path(__file__).resolve().parent / "data" / "languages.csv"


def add_languages() -> int:
    """``language.py:sync_languages``: one Language per row of ``languages.csv``, named
    after its code, enabled as the file says. The Link target of ``User.language``
    (FINDINGS.md 58)."""
    import csv

    existing = set(Language._default_manager.values_list("pk", flat=True))
    written = 0
    with LANGUAGES.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["language_code"] in existing:
                continue
            Language(
                language_code=row["language_code"],
                language_name=row["language_name"],
                enabled=str(row.get("enabled", "0")).strip() == "1",
            ).save()
            written += 1
    return written


def add_default_lead_statuses() -> int:
    written = 0
    for status, spec in LEAD_STATUSES.items():
        if _exists(CRMLeadStatus, status):
            continue
        CRMLeadStatus(lead_status=status, **spec).save()
        written += 1
    return written


def add_default_deal_statuses() -> int:
    written = 0
    for status, spec in DEAL_STATUSES.items():
        if _exists(CRMDealStatus, status):
            continue
        CRMDealStatus(deal_status=status, **spec).save()
        written += 1
    return written


def add_default_communication_statuses() -> int:
    written = 0
    for status in COMMUNICATION_STATUSES:
        if _exists(CRMCommunicationStatus, status):
            continue
        CRMCommunicationStatus(status=status).save()
        written += 1
    return written


def add_default_fields_layout(force: bool = False) -> int:
    """``install.py:160-264``. ``force`` deletes and rewrites a layout that exists."""
    written = 0
    groups = (
        ("Quick Entry", QUICK_ENTRY_LAYOUTS),
        ("Side Panel", SIDE_PANEL_LAYOUTS),
        ("Data Fields", DATA_FIELDS_LAYOUTS),
    )
    for layout_type, layouts in groups:
        for name, spec in layouts.items():
            existing = CRMFieldsLayout._default_manager.filter(pk=name).first()
            if existing is not None:
                if not force:
                    continue
                existing.delete()
            CRMFieldsLayout(dt=spec["doctype"], type=layout_type, layout=spec["layout"]).save()
            written += 1
    return written


def add_default_industries() -> int:
    written = 0
    for industry in INDUSTRIES:
        if _exists(CRMIndustry, industry):
            continue
        CRMIndustry(industry=industry).save()
        written += 1
    return written


def add_default_lead_sources() -> int:
    written = 0
    for source in LEAD_SOURCES:
        if _exists(CRMLeadSource, source):
            continue
        CRMLeadSource(source_name=source).save()
        written += 1
    return written


def add_default_lost_reasons() -> int:
    written = 0
    for reason in LOST_REASONS:
        if _exists(CRMLostReason, reason["reason"]):
            continue
        CRMLostReason(lost_reason=reason["reason"], description=reason["description"]).save()
        written += 1
    return written


def add_default_quick_filters() -> int:
    written = 0
    for doctype, fields in QUICK_FILTERS.items():
        if CRMGlobalSettings._default_manager.filter(dt=doctype, type="Quick Filters").exists():
            continue
        CRMGlobalSettings(dt=doctype, type="Quick Filters", json=list(fields)).save()
        written += 1
    return written


def add_standard_dropdown_items(force: bool = False) -> int:
    """``install.py:530-542``. ``FCRMSettings.load`` seeds a row it creates itself.
    ``force`` restores the standard rows (FINDINGS.md 78); custom rows stay."""
    existed = _exists(FCRMSettings, FCRMSettings.singleton_name())
    settings = FCRMSettings.load()
    if not existed:
        return settings.dropdown_items.count()
    return _seed_dropdown_items(settings, force=force)


def create_product_details_script(doctype: str) -> int:
    """``crm_products.py:91-109``: app-owned, so a script that drifted is rewritten."""
    name = "Product Details Script for " + doctype
    script = get_product_details_script(doctype)
    rows = CRMFormScript._default_manager.filter(pk=name)
    current = rows.values_list("script", flat=True).first()
    if current is not None:
        if current == script:
            return 0
        rows.update(script=script)
        return 1
    CRMFormScript(
        name=name, dt=doctype, view="Form", script=script, enabled=True, is_standard=True
    ).save()
    return 1


def create_forecasting_script() -> int:
    """``fcrm_settings.py:217-230``."""
    if _exists(CRMFormScript, "Forecasting Script"):
        return 0
    CRMFormScript(
        name="Forecasting Script",
        dt="CRM Deal",
        view="Form",
        script=FORECASTING_SCRIPT,
        enabled=True,
        is_standard=True,
    ).save()
    return 1


def add_default_scripts() -> int:
    """``install.py:545-550``."""
    written = sum(create_product_details_script(doctype) for doctype in ("CRM Lead", "CRM Deal"))
    return written + create_forecasting_script()


def after_install(force: bool = False) -> dict[str, int]:
    """``install.py:17-35``, in upstream's order. Returns the rows written per group."""
    _layout, dashboard_written = create_default_manager_dashboard(force)
    return {
        "countries": add_countries(),
        "languages": add_languages(),
        "genders": add_genders(),
        "salutations": add_salutations(),
        "lead_statuses": add_default_lead_statuses(),
        "deal_statuses": add_default_deal_statuses(),
        "communication_statuses": add_default_communication_statuses(),
        "fields_layouts": add_default_fields_layout(force),
        "industries": add_default_industries(),
        "lead_sources": add_default_lead_sources(),
        "lost_reasons": add_default_lost_reasons(),
        "quick_filters": add_default_quick_filters(),
        "dropdown_items": add_standard_dropdown_items(force),
        "form_scripts": add_default_scripts(),
        "dashboard": int(dashboard_written),
    }
