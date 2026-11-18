"""Write the countries, currencies and languages (spec section 4.2, decision 13).

Rows the application cannot run without, as accounts' 0002 writes roles: not dev data,
so `DEV_DATA_ALLOWED` does not gate them. The mechanism differs from `backend/`, where
countries and languages come from the `seed_defaults` command (`crm_app/setup.py:374-416`)
and currencies from migration 0017 (`frappe_platform/reference_data.py:add_currencies`).
The data files are copies of `backend/crm_app/data/` (version-15's `country_info.json`
and `languages.csv`). Existing rows are left alone; the owner is Administrator.
"""

import csv
import json
from pathlib import Path

from django.db import migrations
from django.utils import timezone

DATA = Path(__file__).resolve().parents[1] / "data"

#: `frappe/geo/doctype/currency/currency.py:9`.
DEFAULT_ENABLED_CURRENCIES = ("INR", "USD", "GBP", "EUR", "AED", "AUD", "JPY", "CNY", "CHF")


def _stamp():
    now = timezone.now()
    return {
        "owner_id": "Administrator",
        "modified_by_id": "Administrator",
        "creation": now,
        "modified": now,
    }


def add_countries(apps):
    """`country.py:53-75`: one Country per entry, with the framework's two fallbacks."""
    Country = apps.get_model("configuration", "Country")
    data = json.loads((DATA / "country_info.json").read_text(encoding="utf-8"))
    existing = set(Country.objects.values_list("pk", flat=True))
    stamp = _stamp()
    rows = Country.objects.bulk_create(
        [
            Country(
                name=name,
                country_name=name,
                code=info.get("code") or "",
                date_format=info.get("date_format") or "dd-mm-yyyy",
                time_format=info.get("time_format") or "HH:mm:ss",
                time_zones="\n".join(info.get("timezones") or []),
                **stamp,
            )
            for name, info in data.items()
            if name not in existing
        ]
    )
    return len(rows)


def add_currencies(apps):
    """One Currency per distinct `currency` in the file, its details from the first
    country naming it; the nine defaults enabled (old `reference_data.py:add_currencies`)."""
    Currency = apps.get_model("configuration", "Currency")
    data = json.loads((DATA / "country_info.json").read_text(encoding="utf-8"))
    existing = set(Currency.objects.values_list("pk", flat=True))
    stamp = _stamp()
    rows = {}
    for info in data.values():
        code = info.get("currency")
        if not code or code in existing or code in rows:
            continue
        rows[code] = Currency(
            name=code,
            currency_name=code,
            enabled=code in DEFAULT_ENABLED_CURRENCIES,
            fraction=info.get("currency_fraction") or "",
            fraction_units=info.get("currency_fraction_units") or 0,
            smallest_currency_fraction_value=info.get("smallest_currency_fraction_value"),
            symbol=info.get("currency_symbol") or "",
            number_format=info.get("number_format") or "",
            **stamp,
        )
    Currency.objects.bulk_create(rows.values())
    return len(rows)


def add_languages(apps):
    """`language.py:sync_languages`: one Language per row, named after its code, enabled
    as the file says."""
    Language = apps.get_model("configuration", "Language")
    existing = set(Language.objects.values_list("pk", flat=True))
    stamp = _stamp()
    with (DATA / "languages.csv").open(encoding="utf-8", newline="") as handle:
        rows = [
            Language(
                name=row["language_code"],
                language_code=row["language_code"],
                language_name=row["language_name"],
                enabled=str(row.get("enabled", "0")).strip() == "1",
                **stamp,
            )
            for row in csv.DictReader(handle)
            if row["language_code"] not in existing
        ]
    Language.objects.bulk_create(rows)
    return len(rows)


def write_rows(apps, schema_editor):
    add_countries(apps)
    add_currencies(apps)
    add_languages(apps)


def remove_rows(apps, schema_editor):
    for model in ("Country", "Currency", "Language"):
        apps.get_model("configuration", model).objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("configuration", "0003_country_currency_language"),
        ("accounts", "0002_seed_roles_and_users"),
    ]

    operations = [migrations.RunPython(write_rows, remove_rows)]
