"""Exchange rates: ``crm.api.exchange_rate`` and the deal and organization rate update
(docs/FINDINGS.md 63, second half).

Settings -> Dashboard picks a provider; a deal or an organization in a currency other
than the dashboard one asks it for a rate on save, and the dashboard counts the deal's
value times that rate. Until now the endpoint was a stub that answered 1 and nothing
called it. Shapes follow ``crm/api/exchange_rate.py``, ``crm_deal.py:273-280`` and
``crm_organization.py:34-41``.

No test here reaches the network: the switch is off in the test settings, and the tests
that turn it on replace the one HTTP call with :class:`FakeHTTP`.
"""

import pytest
from django.utils import timezone

from crm_app.api import exchange_rate
from crm_app.api.dashboard import get_average_deal_value
from crm_app.models import CRMDeal, CRMDealStatus, CRMOrganization, FCRMSettings
from frappe_core.exceptions import LinkValidationError, ValidationError
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

ENDPOINT = "/api/method/crm.api.exchange_rate.get_exchange_rate"


class Response:
    def __init__(self, payload, ok=True):
        self.ok, self._payload = ok, payload

    def json(self):
        return self._payload


class FakeHTTP:
    """Answers by URL prefix; records every call. An unmatched URL is a failed request."""

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.calls: list[tuple[str, dict | None]] = []

    def __call__(self, url, params=None):
        self.calls.append((url, params))
        for prefix, payload in self.answers.items():
            if url.startswith(prefix):
                return Response(payload)
        raise ConnectionError(url)


FRANKFURTER = "https://api.frankfurter.app/latest?from=EUR&to=USD"
FAWAZ = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/eur.json"
FAWAZ_MIRROR = "https://latest.currency-api.pages.dev/v1/currencies/eur.json"


@pytest.fixture
def http(monkeypatch, settings):
    settings.ENABLE_EXCHANGE_RATE_API = True
    fake = FakeHTTP()
    monkeypatch.setattr(exchange_rate, "_get", fake)
    return fake


def provider(name, access_key=""):
    FCRMSettings.load()
    FCRMSettings.objects.update(service_provider=name, access_key=access_key)


def test_switched_off_a_rate_is_one_and_nobody_is_asked(monkeypatch):
    """The test settings' default, and a site with no outbound internet's choice."""
    fake = FakeHTTP()
    monkeypatch.setattr(exchange_rate, "_get", fake)
    assert exchange_rate.get_exchange_rate("EUR", "USD") == 1
    assert fake.calls == []


def test_the_default_provider_answers_and_the_rate_is_kept_for_the_day(http):
    http.answers = {FRANKFURTER: {"rates": {"USD": 1.09}}}
    assert exchange_rate.get_exchange_rate("EUR", "USD") == 1.09
    assert exchange_rate.get_exchange_rate("EUR", "USD") == 1.09
    assert [url for url, _ in http.calls] == [FRANKFURTER], "the second answer is the cached one"


def test_a_free_provider_that_is_down_falls_back_to_the_other(http):
    http.answers = {FAWAZ_MIRROR: {"eur": {"usd": 1.1}}}
    assert exchange_rate.get_exchange_rate("EUR", "USD") == 1.1
    assert [url for url, _ in http.calls] == [FRANKFURTER, FAWAZ, FAWAZ_MIRROR]


def test_both_free_providers_down_is_upstreams_refusal(http, alice, administrator):
    """Primary frankfurter: the fallback was fawaz, so the generic message. Primary fawaz:
    the fallback was frankfurter, which tells a rep to ask a manager and a manager to
    pick a paid provider - upstream's own wording, keyed on the API last tried."""
    with pytest.raises(ValidationError) as refused:
        exchange_rate.get_exchange_rate("EUR", "USD")
    assert refused.value.message == (
        "Failed to fetch exchange rate from EUR to USD on latest. Please check your internet "
        "connection or try again later."
    )

    provider("fawazahmed-exchange-api")
    with session_user(alice.name), pytest.raises(ValidationError) as refused:
        exchange_rate.get_exchange_rate("EUR", "USD")
    assert refused.value.message.startswith("Ask your manager to set up the Exchange Rate Provider")
    with session_user(administrator.name), pytest.raises(ValidationError) as refused:
        exchange_rate.get_exchange_rate("EUR", "USD")
    assert refused.value.message == (
        "Setup the Exchange Rate Provider other than 'Frankfurter' in settings, as default "
        "provider does not support currency conversion for EUR to USD."
    )


def test_a_paid_provider_needs_its_key_and_sends_it(http):
    provider("exchangerate.host")
    with pytest.raises(ValidationError) as refused:
        exchange_rate.get_exchange_rate("EUR", "USD")
    assert refused.value.message == (
        "Access Key is required for Service Provider: <strong>exchangerate.host</strong>"
    )

    provider("exchangerate.host", access_key="host-key")
    http.answers = {"https://api.exchangerate.host/convert": {"result": 1.2}}
    assert exchange_rate.get_exchange_rate("EUR", "USD", date="2026-10-01") == 1.2
    assert http.calls[-1][1] == {
        "access_key": "host-key", "from": "EUR", "to": "USD", "amount": 1, "date": "2026-10-01",
    }

    provider("exchangerate-api", access_key="api-key")
    http.answers = {
        "https://v6.exchangerate-api.com/v6/api-key/pair/EUR/GBP": {
            "result": "success", "conversion_rate": 0.87,
        }
    }
    assert exchange_rate.get_exchange_rate("EUR", "GBP") == 0.87


def test_the_endpoint_answers_the_same(http, auth_api):
    http.answers = {"https://api.frankfurter.app/latest?from=GBP&to=USD": {"rates": {"USD": 1.3}}}
    response = auth_api.post(ENDPOINT, {"from_currency": "GBP", "to_currency": "USD"}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"] == 1.3


def test_an_organization_takes_the_rate_on_save_and_again_when_its_currency_changes(http, alice):
    http.answers = {FRANKFURTER: {"rates": {"USD": 1.09}}}
    with session_user(alice.name):
        org = CRMOrganization.objects.create(organization_name="ZZ Euro", currency="EUR")
        assert org.exchange_rate == 1.09
        org.website = "https://example.com"
        org.save()
        assert len(http.calls) == 1, "same currency, rate held: nobody is asked again"
        org.currency = "USD"
        org.save()
    assert CRMOrganization.objects.get(pk=org.pk).exchange_rate == 1


def test_an_unknown_currency_is_refused_before_any_provider_is_asked(http, alice):
    with session_user(alice.name), pytest.raises(LinkValidationError):
        CRMOrganization.objects.create(organization_name="ZZ Nowhere", currency="XYZ")
    assert http.calls == []


def test_a_partial_save_asks_nobody(http, alice):
    """``save(update_fields=...)`` is upstream's ``db.set_value``, which runs no validate:
    the file-attach path saves an organization that way (``frappe_platform/models.py``)."""
    with session_user(alice.name):
        org = CRMOrganization.objects.create(organization_name="ZZ Partial", currency="USD")
    CRMOrganization.objects.filter(pk=org.pk).update(currency="EUR", exchange_rate=None)
    org = CRMOrganization.objects.get(pk=org.pk)
    with session_user(alice.name):
        org.organization_logo = "/files/logo.png"
        org.save(update_fields=["organization_logo"])
    assert http.calls == []


def test_the_refresh_command_rates_rows_saved_before_the_rule(http, alice):
    """A deal saved before FINDINGS.md 63 holds 1 in any currency, an organization holds
    nothing; the command writes what upstream's save would have, one call per currency."""
    from django.core.management import call_command

    http.answers = {FRANKFURTER: {"rates": {"USD": 1.09}}}
    with session_user(alice.name):
        status, _ = CRMDealStatus.objects.get_or_create(deal_status="Qualification", defaults={"type": "Open"})
        deal = CRMDeal.objects.create(deal_owner=alice, status=status, currency="USD")
        org = CRMOrganization.objects.create(organization_name="ZZ Old", currency="USD")
    CRMDeal.objects.filter(pk=deal.pk).update(currency="EUR", exchange_rate=1)
    CRMOrganization.objects.filter(pk=org.pk).update(currency="EUR", exchange_rate=None)
    http.calls.clear()

    call_command("refresh_exchange_rates", stdout=None)

    assert CRMDeal.objects.get(pk=deal.pk).exchange_rate == 1.09
    assert CRMOrganization.objects.get(pk=org.pk).exchange_rate == 1.09
    assert [url for url, _ in http.calls] == [FRANKFURTER], "one call, the second from the cache"


def test_the_average_cards_are_upstreams(http, alice):
    """``dashboard.py:197-424``: "Avg. deal value" leaves lost deals out; the delta is the
    difference of the averages, with ``%`` on that card alone (UPSTREAM_BUGS.md 51)."""
    from crm_app.api.dashboard import get_average_ongoing_deal_value, get_average_won_deal_value

    with session_user(alice.name):
        open_, _ = CRMDealStatus.objects.get_or_create(deal_status="Qualification", defaults={"type": "Open"})
        CRMDeal.objects.create(deal_owner=alice, status=open_, currency="USD", deal_value=100)
        today = timezone.localdate()
        all_deals = get_average_deal_value(today, today)
        won = get_average_won_deal_value(today, today)
        ongoing = get_average_ongoing_deal_value(today, today)
    assert all_deals["title"] == "Avg. deal value"
    assert all_deals["tooltip"] == "Average deal value of ongoing & won deals"
    assert all_deals["deltaSuffix"] == "%" and all_deals["delta"] == 0
    assert (won["title"], ongoing["title"]) == ("Avg. won deal value", "Avg. ongoing deal value")
    assert "deltaSuffix" not in won and "deltaSuffix" not in ongoing


def test_a_lost_deal_is_left_out_of_the_average(http, alice):
    with session_user(alice.name):
        open_, _ = CRMDealStatus.objects.get_or_create(deal_status="Qualification", defaults={"type": "Open"})
        CRMDeal.objects.create(deal_owner=alice, status=open_, currency="USD", deal_value=100)
        lost_deal = CRMDeal.objects.create(deal_owner=alice, status=open_, currency="USD", deal_value=900)
    lost, _ = CRMDealStatus.objects.get_or_create(deal_status="ZZ Lost", defaults={"type": "Lost"})
    CRMDeal.objects.filter(pk=lost_deal.pk).update(status=lost)
    with session_user(alice.name):
        today = timezone.localdate()
        assert get_average_deal_value(today, today)["value"] == 100


def test_a_deal_is_converted_into_the_dashboard_currency(http, alice):
    """The dashboard currency is FCRM Settings', USD when unset; a deal in it is rate 1,
    one in another is the provider's rate, and the average counts the converted value."""
    FCRMSettings.load()
    FCRMSettings.objects.update(currency="GBP")
    http.answers = {"https://api.frankfurter.app/latest?from=EUR&to=GBP": {"rates": {"GBP": 0.5}}}
    with session_user(alice.name):
        status, _ = CRMDealStatus.objects.get_or_create(deal_status="Qualification", defaults={"type": "Open"})
        euro = CRMDeal.objects.create(deal_owner=alice, status=status, currency="EUR", deal_value=300)
        pound = CRMDeal.objects.create(deal_owner=alice, status=status, currency="GBP", deal_value=100)
        today = timezone.localdate()
        average = get_average_deal_value(today, today)
    assert (euro.exchange_rate, pound.exchange_rate) == (0.5, 1)
    assert average["value"] == pytest.approx((300 * 0.5 + 100) / 2)
