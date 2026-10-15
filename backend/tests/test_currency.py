"""The ``Currency`` doctype: docs/FINDINGS.md 63.

Settings -> Dashboard has a Dashboard Currency picker, a Link to ``Currency``, and so do
a deal and an organization. The port had no such doctype, so the search answered 404,
the picker was empty, and the Dashboard section could not be saved at all once
forecasting was on ("Please select a currency before saving", BROWSER_TESTING.md S4 and
S21). Shapes follow ``frappe/geo/doctype/currency`` and
``country.py:import_country_and_currency``.
"""

import json

import pytest

from crm_app.api.dashboard import get_base_currency_symbol
from crm_app.models import CRMOrganization, FCRMSettings
from frappe_core.exceptions import LinkValidationError
from frappe_core.session import session_user
from frappe_platform.models import Currency
from frappe_platform.reference_data import (
    COUNTRY_INFO,
    DEFAULT_ENABLED_CURRENCIES,
    add_currencies,
)

pytestmark = pytest.mark.django_db

SEARCH = "/api/method/frappe.desk.search.search_link"
SET_VALUE = "/api/method/frappe.client.set_value"


def source_currencies() -> set[str]:
    data = json.loads(COUNTRY_INFO.read_text(encoding="utf-8"))
    return {info["currency"] for info in data.values() if info.get("currency")}


def search(client, **params):
    response = client.post(SEARCH, {"doctype": "Currency", "txt": "", **params}, format="json")
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]


def test_every_database_has_the_frameworks_currencies_with_nine_enabled():
    """Written by migration 0017, so nothing has to seed them first."""
    assert set(Currency.objects.values_list("pk", flat=True)) == source_currencies()
    enabled = set(Currency.objects.filter(enabled=True).values_list("pk", flat=True))
    assert enabled == set(DEFAULT_ENABLED_CURRENCIES)

    dollar = Currency.objects.get(pk="USD")
    assert (dollar.symbol, dollar.fraction, dollar.fraction_units) == ("$", "Cent", 100)
    assert dollar.number_format == "#,###.##"
    assert Currency.objects.get(pk="INR").symbol == "₹"
    assert add_currencies() == 0, "a second run writes nothing"


def test_a_disabled_currency_stays_disabled_on_a_reseed(administrator):
    Currency.objects.filter(pk="GBP").update(enabled=False)
    Currency.objects.filter(pk="NZD").update(enabled=True)
    with session_user(administrator.name):
        assert add_currencies() == 0
    assert Currency.objects.get(pk="GBP").enabled is False
    assert Currency.objects.get(pk="NZD").enabled is True


def test_the_picker_offers_the_enabled_currencies(auth_api):
    offered = {row["value"] for row in search(auth_api, page_length=500)}
    assert offered == set(DEFAULT_ENABLED_CURRENCIES)
    assert [row["value"] for row in search(auth_api, txt="EU")] == ["EUR"]


def test_a_currency_that_names_nothing_is_refused(administrator):
    """``currency`` is a Link on an organization (and a deal, and FCRM Settings): the
    text-Link check applies to it now that the target exists (``frappe_core/links.py``)."""
    with session_user(administrator.name):
        with pytest.raises(LinkValidationError, match="Could not find Currency: XYZ"):
            CRMOrganization(organization_name="ZZ Nowhere", currency="XYZ").save()
        org = CRMOrganization(organization_name="ZZ Somewhere", currency="eur")
        org.save()
    assert org.currency == "EUR", "the stored spelling, as MariaDB's lookup gives"


def test_the_dashboard_currency_can_be_chosen(api_as, administrator):
    """S21: the Dashboard section saves the picked currency on FCRM Settings."""
    client = api_as(administrator)
    FCRMSettings.load()
    response = client.post(
        SET_VALUE,
        {"doctype": "FCRM Settings", "name": "FCRM Settings", "fieldname": {"currency": "EUR"}},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    assert FCRMSettings.load().currency == "EUR"

    response = client.post(
        SET_VALUE,
        {"doctype": "FCRM Settings", "name": "FCRM Settings", "fieldname": {"currency": "XYZ"}},
        format="json",
    )
    assert response.status_code == 417, response.content[:300]
    assert FCRMSettings.load().currency == "EUR"


def test_the_dashboard_shows_the_currencys_symbol():
    """``dashboard.py:1150-1156``: USD's when none is set, the chosen one's otherwise."""
    settings = FCRMSettings.load()
    assert get_base_currency_symbol() == "$"
    FCRMSettings.objects.filter(pk=settings.pk).update(currency="EUR")
    assert get_base_currency_symbol() == "€"


def test_everyone_reads_the_list_and_only_an_admin_changes_it(auth_api, api_as, administrator, make_user):
    grace = make_user("grace@example.com", roles=["Sales Manager", "Sales User"])
    for client in (auth_api, api_as(grace)):
        assert client.get("/api/resource/Currency/USD").status_code == 200
        refused = client.put("/api/resource/Currency/NZD", {"enabled": 1}, format="json")
        assert refused.status_code == 403
        created = client.post("/api/resource/Currency", {"currency_name": "ZZZ"}, format="json")
        assert created.status_code == 403
    allowed = api_as(administrator).put("/api/resource/Currency/NZD", {"enabled": 1}, format="json")
    assert allowed.status_code == 200, allowed.content[:300]
    assert Currency.objects.get(pk="NZD").enabled is True
