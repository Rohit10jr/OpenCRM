"""The lookup lists every site has: salutations, genders and currencies.

The framework's setup wizard writes them when a site is created
(``frappe/desk/page/setup_wizard/install_fixtures.py:20-49``), before any app installs,
so upstream code can rely on ``Mr`` and ``Male`` existing. Here a migration writes them
(``0014``), for the same reason: a Link to either is validated on save
(:mod:`frappe_core.links`), so a database without the rows would refuse every lead that
carries a salutation. ``manage.py seed_defaults`` calls the same functions, which puts
back a row someone deleted.

The currencies are written earlier still upstream, by the framework's own install
(``country.py:import_country_and_currency``), and are here for the same reason: a deal,
an organization and FCRM Settings each Link to one (FINDINGS.md 63). Migration ``0017``.
"""

from __future__ import annotations

import json
from pathlib import Path

#: ``install_fixtures.py:20-49``, in upstream's order.
GENDERS = (
    "Male",
    "Female",
    "Other",
    "Transgender",
    "Genderqueer",
    "Non-Conforming",
    "Prefer not to say",
)
SALUTATIONS = ("Mr", "Ms", "Mx", "Dr", "Mrs", "Madam", "Miss", "Master", "Prof")


def add_genders() -> int:
    """``install_fixtures.py:update_genders``. Returns how many rows were written."""
    from frappe_platform.models import Gender

    existing = set(Gender._default_manager.values_list("pk", flat=True))
    written = 0
    for gender in GENDERS:
        if gender not in existing:
            Gender(gender=gender).save()
            written += 1
    return written


def add_salutations() -> int:
    """``install_fixtures.py:update_salutations``. Returns how many rows were written."""
    from frappe_platform.models import Salutation

    existing = set(Salutation._default_manager.values_list("pk", flat=True))
    written = 0
    for salutation in SALUTATIONS:
        if salutation not in existing:
            Salutation(salutation=salutation).save()
            written += 1
    return written


#: ``frappe/geo/doctype/currency/currency.py:9``: the currencies a new site has enabled,
#: and so the ones the Currency picker offers until someone enables another.
DEFAULT_ENABLED_CURRENCIES = ("INR", "USD", "GBP", "EUR", "AED", "AUD", "JPY", "CNY", "CHF")

#: The framework's ``frappe/geo/country_info.json``, the copy the countries are seeded
#: from too (``crm_app/setup.py:add_countries``).
COUNTRY_INFO = Path(__file__).resolve().parents[1] / "crm_app" / "data" / "country_info.json"


def add_currencies() -> int:
    """``country.py:get_countries_and_currencies`` and ``currency.py:enable_default_currencies``.

    One Currency per distinct ``currency`` in ``country_info.json``, its details taken
    from the first country that names it, as upstream's ``added_currencies`` set does;
    then the nine defaults enabled. Rows that exist are left alone, enabled or not.

    Upstream passes ``number_format`` through ``frappe.db.escape(...)[1:-1]``, which
    stores the Swiss ``#'###.##`` with its quote escaped (``#\\'###.##`` on MariaDB,
    ``#''###.##`` on Postgres), a value outside the field's own options. Stored as the
    file has it here; nothing in the CRM reads the column.

    Written with ``bulk_create``, as upstream's ``bulk_insert`` writes them, since a
    ``transaction=True`` test empties the table and the next one re-seeds all of it
    (``tests/conftest.py:builtin_users``). Stamped with Administrator, the install user.
    """
    from django.utils import timezone

    from frappe_platform.models import Currency

    data = json.loads(COUNTRY_INFO.read_text(encoding="utf-8"))
    existing = set(Currency._default_manager.values_list("pk", flat=True))
    now = timezone.now()
    rows: dict[str, Currency] = {}
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
            owner_id="Administrator",
            modified_by_id="Administrator",
            creation=now,
            modified=now,
        )
    Currency._default_manager.bulk_create(rows.values(), ignore_conflicts=True)
    return len(rows)


def ensure_reference_rows() -> None:
    """The three lists, written only when a table is empty. One cheap query each otherwise."""
    from frappe_platform.models import Currency, Gender, Salutation

    if not Gender._default_manager.exists():
        add_genders()
    if not Salutation._default_manager.exists():
        add_salutations()
    if not Currency._default_manager.exists():
        add_currencies()
