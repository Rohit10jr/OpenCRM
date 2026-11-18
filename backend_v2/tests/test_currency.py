"""Ported from ``backend/tests/test_currency.py`` (REBUILD_PLAN S14).

`frappe.desk.search.search_link` on Currency is `GET /api/v1/currencies/search/`; the
resource routes are `/api/v1/currencies/` (specs/CONFIGURATION.md 4.2). Expected answers
are unchanged. The rows come from `configuration`'s data migration, whose
`add_currencies` stands in for `frappe_platform.reference_data.add_currencies`.

Waiting for later work: `test_a_currency_that_names_nothing_is_refused` (an organization,
SALES; its System Settings half is in test_system_settings.py),
`test_the_dashboard_currency_can_be_chosen` (FCRM Settings, milestone 3),
`test_the_dashboard_shows_the_currencys_symbol` (DASHBOARD).
"""

import importlib
import json

import pytest
from django.apps import apps

from configuration.models import DEFAULT_ENABLED_CURRENCIES, Currency

pytestmark = pytest.mark.django_db

SEARCH = "/api/v1/currencies/search/"
CURRENCIES = "/api/v1/currencies/"

reference_rows = importlib.import_module("configuration.migrations.0004_reference_rows")


def source_currencies() -> set[str]:
    data = json.loads((reference_rows.DATA / "country_info.json").read_text(encoding="utf-8"))
    return {info["currency"] for info in data.values() if info.get("currency")}


def search(client, **params):
    response = client.get(SEARCH, {"txt": "", **params})
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]


def test_every_database_has_the_frameworks_currencies_with_nine_enabled():
    assert set(Currency.objects.values_list("pk", flat=True)) == source_currencies()
    enabled = set(Currency.objects.filter(enabled=True).values_list("pk", flat=True))
    assert enabled == set(DEFAULT_ENABLED_CURRENCIES)

    dollar = Currency.objects.get(pk="USD")
    assert (dollar.symbol, dollar.fraction, dollar.fraction_units) == ("$", "Cent", 100)
    assert dollar.number_format == "#,###.##"
    assert Currency.objects.get(pk="INR").symbol == "₹"
    assert reference_rows.add_currencies(apps) == 0, "a second run writes nothing"


def test_a_disabled_currency_stays_disabled_on_a_reseed():
    Currency.objects.filter(pk="GBP").update(enabled=False)
    Currency.objects.filter(pk="NZD").update(enabled=True)
    assert reference_rows.add_currencies(apps) == 0
    assert Currency.objects.get(pk="GBP").enabled is False
    assert Currency.objects.get(pk="NZD").enabled is True


def test_the_picker_offers_the_enabled_currencies(auth_api):
    offered = {row["value"] for row in search(auth_api, page_length=500)}
    assert offered == set(DEFAULT_ENABLED_CURRENCIES)
    assert [row["value"] for row in search(auth_api, txt="EU")] == ["EUR"]


def test_everyone_reads_the_list_and_only_an_admin_changes_it(
    auth_api, api_as, administrator, make_user
):
    grace = make_user("grace@example.com", roles=["Sales Manager", "Sales User"])
    for client in (auth_api, api_as(grace)):
        assert client.get(f"{CURRENCIES}USD/").status_code == 200
        refused = client.patch(f"{CURRENCIES}NZD/", {"enabled": 1}, format="json")
        assert refused.status_code == 403
        created = client.post(CURRENCIES, {"currency_name": "ZZZ"}, format="json")
        assert created.status_code == 403
    allowed = api_as(administrator).patch(f"{CURRENCIES}NZD/", {"enabled": 1}, format="json")
    assert allowed.status_code == 200, allowed.content[:300]
    assert Currency.objects.get(pk="NZD").enabled is True


def test_the_rows_are_version_15s():
    assert Currency.objects.filter(pk="TMM").exists()
    assert not Currency.objects.filter(pk="TMT").exists()


def test_a_user_with_no_crm_role_cannot_read_it(api_as, make_user):
    outsider = make_user("outsider@example.com", first_name="Out")
    response = api_as(outsider).get(f"{CURRENCIES}USD/")
    assert response.status_code in (403, 404), response.content[:300]


# --- new: no old test covers these (specs/CONFIGURATION.md section 4.2) -------------------


def test_a_user_with_no_crm_role_lists_nothing(api_as, make_user):
    outsider = make_user("outsider@example.com", first_name="Out")
    response = api_as(outsider).get(CURRENCIES)
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"] == []


def test_an_accounting_role_reads_it(api_as, make_user):
    clerk = make_user("clerk@example.com", roles=["Accounts User"])
    assert api_as(clerk).get(f"{CURRENCIES}USD/").status_code == 200


def test_a_disabled_currency_shows_only_when_asked_for(auth_api):
    included = search(auth_api, txt="NZD", filters=json.dumps({"include_disabled": 1}))
    assert [row["value"] for row in included] == ["NZD"]
    assert search(auth_api, txt="NZD") == []


def test_enabled_is_filterable(auth_api):
    response = auth_api.get(CURRENCIES, {"filters": json.dumps({"enabled": 1}), "limit_page_length": 50})
    assert response.status_code == 200, response.content[:300]
    names = {row["name"] for row in response.json()["message"]}
    assert names == set(DEFAULT_ENABLED_CURRENCIES)
