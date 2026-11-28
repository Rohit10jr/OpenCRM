"""CONFIGURATION's restore writers for `restore_defaults` (specs/CONFIGURATION.md §10.3).

Upstream's `FCRMSettings.restore_defaults(force)` -> `after_install(force)`
(`crm/fcrm/doctype/fcrm_settings/fcrm_settings.py:46-48`, `crm/install.py:17-35`). Each
writer runs on live models with `save(user=...)`, adds what is missing by its key and
changes nothing that exists, with two exceptions: the two standard product-details scripts
are re-synced to their shipped text when they drifted (owner, 21 Nov 2026; upstream
`crm_products.py:90-105`), and `force` deletes and re-inserts the 14 default layouts
(`install.py:226-263`). Each returns its count: rows added plus rows rewritten.

The country, currency and language logic is copied from `configuration/0004`, the two
settings rows from `0002` and `0006`; the migrations keep their own frozen copies.
"""

from __future__ import annotations

import csv
import functools
import json
import pathlib

DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"
DATA_FILE = DATA_DIR / "default_rows.json"

PRODUCT_SCRIPT_DOCTYPES = ("CRM Lead", "CRM Deal")
FORECASTING_SCRIPT_NAME = "Forecasting Script"
QUICK_FILTERS = "Quick Filters"

#: `frappe/geo/doctype/currency/currency.py:9`, as `configuration/0004`.
DEFAULT_ENABLED_CURRENCIES = ("INR", "USD", "GBP", "EUR", "AED", "AUD", "JPY", "CNY", "CHF")


@functools.cache
def default_rows() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def product_details_script(doctype: str) -> str:
    """`crm_products.py:112-193`: the class is named after the doctype, spaces removed."""
    return "class " + doctype.replace(" ", "") + " {" + default_rows()["product_details_script_body"]


def product_script_name(doctype: str) -> str:
    return "Product Details Script for " + doctype


# --- layouts, quick filters, form scripts ---------------------------------------------------


def fields_layouts(user, force: bool = False) -> int:
    """The 14 default layouts by name. `force` deletes each default and inserts it again
    (upstream's way): its history goes with it and the new row is `user`'s. A layout an
    administrator made under another name is never touched."""
    from configuration.models import CRMFieldsLayout

    written = 0
    for spec in default_rows()["layouts"]:
        name = f"{spec['dt']}-{spec['type']}"
        existing = CRMFieldsLayout._default_manager.filter(pk=name).first()
        if existing is not None:
            if not force:
                continue
            existing.delete()
        CRMFieldsLayout(dt=spec["dt"], type=spec["type"], layout=spec["layout"]).save(user=user)
        written += 1
    return written


def quick_filters(user, force: bool = False) -> int:
    """The 6 quick filters, keyed by `(dt, type)` (not upstream's `dt` alone: CRM Global
    Settings holds several types here). Never forced."""
    from configuration.models import CRMGlobalSettings

    del force
    written = 0
    for doctype, fields in default_rows()["quick_filters"].items():
        if CRMGlobalSettings._default_manager.filter(dt=doctype, type=QUICK_FILTERS).exists():
            continue
        CRMGlobalSettings(dt=doctype, type=QUICK_FILTERS, json=list(fields)).save(user=user)
        written += 1
    return written


def form_scripts(user, force: bool = False) -> int:
    """The 3 standard scripts by their shipped name. A missing one is added; the two
    product-details scripts get their shipped text back when it drifted, and nothing
    else of theirs changes; the forecasting script is only ever added. A renamed
    standard script counts as missing: the renamed row is an administrator's."""
    from configuration.models import CRMFormScript

    del force
    written = 0
    scripts = [
        (product_script_name(doctype), doctype, product_details_script(doctype), True)
        for doctype in PRODUCT_SCRIPT_DOCTYPES
    ]
    scripts.append((FORECASTING_SCRIPT_NAME, "CRM Deal", default_rows()["forecasting_script"], False))
    for name, dt, script, resync in scripts:
        existing = CRMFormScript._default_manager.filter(pk=name).first()
        if existing is None:
            CRMFormScript(
                name=name, dt=dt, view="Form", script=script, enabled=True, is_standard=True
            ).save(user=user)
            written += 1
        elif resync and existing.script != script:
            existing.script = script
            existing.save(user=user)
            written += 1
    return written


# --- countries, currencies, languages ------------------------------------------------------


def _country_info() -> dict:
    return json.loads((DATA_DIR / "country_info.json").read_text(encoding="utf-8"))


def countries(user, force: bool = False) -> int:
    """`country.py:53-75`, as `configuration/0004`: one Country per missing entry."""
    from configuration.models import Country

    del force
    existing = set(Country._default_manager.values_list("pk", flat=True))
    written = 0
    for name, info in _country_info().items():
        if name in existing:
            continue
        Country(
            country_name=name,
            code=info.get("code") or "",
            date_format=info.get("date_format") or "dd-mm-yyyy",
            time_format=info.get("time_format") or "HH:mm:ss",
            time_zones="\n".join(info.get("timezones") or []),
        ).save(user=user)
        written += 1
    return written


def currencies(user, force: bool = False) -> int:
    """As `configuration/0004`: one Currency per missing distinct code, its details from
    the first country naming it; the nine defaults enabled."""
    from configuration.models import Currency

    del force
    existing = set(Currency._default_manager.values_list("pk", flat=True))
    written = 0
    for info in _country_info().values():
        code = info.get("currency")
        if not code or code in existing:
            continue
        Currency(
            currency_name=code,
            enabled=code in DEFAULT_ENABLED_CURRENCIES,
            fraction=info.get("currency_fraction") or "",
            fraction_units=info.get("currency_fraction_units") or 0,
            smallest_currency_fraction_value=info.get("smallest_currency_fraction_value"),
            symbol=info.get("currency_symbol") or "",
            number_format=info.get("number_format") or "",
        ).save(user=user)
        existing.add(code)
        written += 1
    return written


def languages(user, force: bool = False) -> int:
    """`language.py:sync_languages`, as `configuration/0004`: one Language per missing
    code, enabled as the file says."""
    from configuration.models import Language

    del force
    existing = set(Language._default_manager.values_list("pk", flat=True))
    written = 0
    with (DATA_DIR / "languages.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["language_code"] in existing:
                continue
            Language(
                language_code=row["language_code"],
                language_name=row["language_name"],
                enabled=str(row.get("enabled", "0")).strip() == "1",
            ).save(user=user)
            written += 1
    return written


# --- the two settings rows and the dropdown items -------------------------------------------


def system_settings(user, force: bool = False) -> int:
    """The System Settings row when missing, from the environment's formats (`0002`)."""
    from configuration.models import SystemSettings, sysdefaults_from_environment

    del force
    if SystemSettings._default_manager.filter(pk=SystemSettings.singleton_name()).exists():
        return 0
    SystemSettings(
        name=SystemSettings.singleton_name(), **sysdefaults_from_environment()
    ).save(user=user)
    return 1


def fcrm_settings(user, force: bool = False) -> int:
    """The FCRM Settings row when missing (`0006`); its items are `dropdown_items`'."""
    from configuration.models import FCRMSettings

    del force
    if FCRMSettings._default_manager.filter(pk=FCRMSettings.singleton_name()).exists():
        return 0
    FCRMSettings(name=FCRMSettings.singleton_name()).save(user=user)
    return 1


def dropdown_items(user, force: bool = False) -> int:
    """The six standard items, only when the row has none (`install.py:530-542`); no
    forced branch (upstream has none, temp A-59)."""
    from configuration.models import FCRMSettings, add_standard_dropdown_items

    del force
    row = FCRMSettings._default_manager.filter(pk=FCRMSettings.singleton_name()).first()
    if row is None:
        return 0
    return add_standard_dropdown_items(row, user=user)
