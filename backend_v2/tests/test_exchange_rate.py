"""Ported from ``backend/tests/test_exchange_rate.py:1-141`` (REBUILD_PLAN S14).

`crm.api.exchange_rate.get_exchange_rate` is `GET /api/v1/exchange-rate/`
(specs/CONFIGURATION.md 4.3); the service is `configuration.exchange_rate`, which takes
the caller as `user` (S16) where the old code read the session. Expected answers are
unchanged. The organization, refresh-command and dashboard cases (`:144-241`) are SALES'
and DASHBOARD's.

No test here reaches the network: the switch is off in the test settings, and the tests
that turn it on replace the one HTTP call with `FakeHTTP`.
"""

import pytest

from configuration import exchange_rate
from configuration.models import FCRMSettings
from core.exceptions import ValidationError

pytestmark = pytest.mark.django_db

ENDPOINT = "/api/v1/exchange-rate/"


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


@pytest.fixture(autouse=True)
def _empty_cache():
    from django.core.cache import cache

    cache.clear()


def provider(name, access_key=""):
    FCRMSettings.objects.update(service_provider=name, access_key=access_key)


def rate(*args, user, **kwargs):
    return exchange_rate.get_exchange_rate(*args, user=user, **kwargs)


def test_switched_off_a_rate_is_one_and_nobody_is_asked(monkeypatch, alice):
    fake = FakeHTTP()
    monkeypatch.setattr(exchange_rate, "_get", fake)
    assert rate("EUR", "USD", user=alice) == 1
    assert fake.calls == []


def test_the_default_provider_answers_and_the_rate_is_kept_for_the_day(http, alice):
    http.answers = {FRANKFURTER: {"rates": {"USD": 1.09}}}
    assert rate("EUR", "USD", user=alice) == 1.09
    assert rate("EUR", "USD", user=alice) == 1.09
    assert [url for url, _ in http.calls] == [FRANKFURTER], "the second answer is the cached one"


def test_a_free_provider_that_is_down_falls_back_to_the_other(http, alice):
    http.answers = {FAWAZ_MIRROR: {"eur": {"usd": 1.1}}}
    assert rate("EUR", "USD", user=alice) == 1.1
    assert [url for url, _ in http.calls] == [FRANKFURTER, FAWAZ, FAWAZ_MIRROR]


def test_both_free_providers_down_is_upstreams_refusal(http, alice, administrator):
    with pytest.raises(ValidationError) as refused:
        rate("EUR", "USD", user=alice)
    assert refused.value.message == (
        "Failed to fetch exchange rate from EUR to USD on latest. Please check your internet "
        "connection or try again later."
    )

    provider("fawazahmed-exchange-api")
    with pytest.raises(ValidationError) as refused:
        rate("EUR", "USD", user=alice)
    assert refused.value.message.startswith("Ask your manager to set up the Exchange Rate Provider")
    with pytest.raises(ValidationError) as refused:
        rate("EUR", "USD", user=administrator)
    assert refused.value.message == (
        "Setup the Exchange Rate Provider other than 'Frankfurter' in settings, as default "
        "provider does not support currency conversion for EUR to USD."
    )


def test_a_paid_provider_needs_its_key_and_sends_it(http, alice):
    provider("exchangerate.host")
    with pytest.raises(ValidationError) as refused:
        rate("EUR", "USD", user=alice)
    assert refused.value.message == (
        "Access Key is required for Service Provider: <strong>exchangerate.host</strong>"
    )

    provider("exchangerate.host", access_key="host-key")
    http.answers = {"https://api.exchangerate.host/convert": {"result": 1.2}}
    assert rate("EUR", "USD", date="2026-10-01", user=alice) == 1.2
    assert http.calls[-1][1] == {
        "access_key": "host-key",
        "from": "EUR",
        "to": "USD",
        "amount": 1,
        "date": "2026-10-01",
    }

    provider("exchangerate-api", access_key="api-key")
    http.answers = {
        "https://v6.exchangerate-api.com/v6/api-key/pair/EUR/GBP": {
            "result": "success",
            "conversion_rate": 0.87,
        }
    }
    assert rate("EUR", "GBP", user=alice) == 0.87


def test_the_endpoint_answers_the_same(http, auth_api):
    http.answers = {"https://api.frankfurter.app/latest?from=GBP&to=USD": {"rates": {"USD": 1.3}}}
    response = auth_api.get(ENDPOINT, {"from_currency": "GBP", "to_currency": "USD"})
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"] == 1.3


# --- new: no old test covers these (specs/CONFIGURATION.md 4.3, PE-10, PE-12) ------------

GENERIC = "Failed to fetch exchange rate from {0} to {1} on {2}. Please check your internet connection or try again later."


@pytest.mark.parametrize(
    ("from_currency", "to_currency", "date"),
    [
        ("EU", "USD", None),
        ("EURO", "USD", None),
        ("EUR", "US/", None),
        ("EUR", "USD", "yesterday"),
        ("EUR", "USD", "2026-10-01/../x"),
        ("E1R", "USD", None),
        ("EUR", "USD", "２０２６-１０-０１"),
        ("EUR", "USD", "2026-99-99"),
    ],
)
def test_pe10_an_unaccepted_shape_asks_nobody_and_is_not_cached(
    http, alice, from_currency, to_currency, date
):
    from django.core.cache import cache

    with pytest.raises(ValidationError) as refused:
        rate(from_currency, to_currency, date=date, user=alice)
    assert refused.value.message == GENERIC.format(from_currency, to_currency, date or "latest")
    assert http.calls == []
    assert cache.get(f"exchange_rate_{from_currency}_{to_currency}_{date}") is None


def test_pe10_lowercase_codes_are_accepted_as_given(http, alice):
    """As backend/: a lowercase code is passed through, and cached under its own key."""
    http.answers = {"https://api.frankfurter.app/latest?from=eur&to=usd": {"rates": {"usd": 1.2}}}
    assert rate("eur", "usd", user=alice) == 1.2


@pytest.mark.parametrize("answer", [0, -1.5, "1.2", {"x": 1}, True, None])
def test_pe12_a_rate_that_is_not_a_positive_number_is_a_failed_fetch(http, alice, answer):
    from django.core.cache import cache

    provider("exchangerate.host", access_key="k")
    http.answers = {"https://api.exchangerate.host/convert": {"result": answer}}
    with pytest.raises(ValidationError) as refused:
        rate("EUR", "USD", user=alice)
    assert refused.value.message == GENERIC.format("EUR", "USD", "latest")
    assert cache.get(f"exchange_rate_EUR_USD_{exchange_rate._today()}") is None


def test_a_free_providers_bad_answer_falls_back(http, alice):
    http.answers = {FRANKFURTER: {"rates": {"USD": 0}}, FAWAZ: {"eur": {"usd": 1.07}}}
    assert rate("EUR", "USD", user=alice) == 1.07


def test_the_call_uses_a_five_second_timeout_and_no_retry(monkeypatch):
    from core import http as core_http

    seen = {}

    def fake_request(method, url, **kwargs):
        seen.update(kwargs, method=method, url=url)
        return Response({})

    monkeypatch.setattr(core_http, "request", fake_request)
    exchange_rate._get("https://api.frankfurter.app/latest?from=EUR&to=USD")
    assert (seen["method"], seen["timeout"], seen["attempts"]) == ("GET", 5, 1)


@pytest.mark.parametrize("name", ["exchangerate.host", "exchangerate-api"])
def test_the_access_key_never_reaches_a_log(http, alice, caplog, name):
    provider(name, access_key="secret-key-123")
    with caplog.at_level("DEBUG"), pytest.raises(ValidationError) as refused:
        rate("EUR", "USD", user=alice)
    assert "secret-key-123" not in caplog.text
    assert "secret-key-123" not in refused.value.message


@pytest.mark.parametrize("missing", ["from_currency", "to_currency"])
def test_pe12_a_missing_currency_is_one(http, auth_api, missing):
    params = {"from_currency": "EUR", "to_currency": "USD"}
    params.pop(missing)
    response = auth_api.get(ENDPOINT, params)
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"] == 1
    assert http.calls == []


@pytest.mark.parametrize("name", ["exchangerate.host", "exchangerate-api"])
def test_pe12_a_paid_providers_transport_failure_is_the_generic_refusal(http, alice, name):
    provider(name, access_key="k")
    with pytest.raises(ValidationError) as refused:
        rate("EUR", "USD", user=alice)
    assert refused.value.message == GENERIC.format("EUR", "USD", "latest")


def test_pe12_a_paid_providers_malformed_json_is_the_generic_refusal(http, alice):
    provider("exchangerate-api", access_key="k")
    http.answers = {"https://v6.exchangerate-api.com/v6/k/pair/EUR/USD": {"unexpected": 1}}
    with pytest.raises(ValidationError) as refused:
        rate("EUR", "USD", user=alice)
    assert refused.value.message == GENERIC.format("EUR", "USD", "latest")


def test_a_failure_is_not_cached(http, alice):
    with pytest.raises(ValidationError):
        rate("EUR", "USD", user=alice)
    http.answers = {FRANKFURTER: {"rates": {"USD": 1.05}}}
    assert rate("EUR", "USD", user=alice) == 1.05


def test_a_rate_is_kept_for_a_day(http, alice, monkeypatch):
    from django.core.cache import cache

    seen = {}
    real_set = cache.set
    monkeypatch.setattr(cache, "set", lambda key, value, timeout=None: seen.update({key: timeout}) or real_set(key, value, timeout))
    http.answers = {FRANKFURTER: {"rates": {"USD": 1.09}}}
    rate("EUR", "USD", user=alice)
    (key, timeout), = seen.items()
    assert key.startswith("exchange_rate_EUR_USD_") and timeout == 60 * 60 * 24


def test_the_same_currency_is_one_without_asking(http, alice):
    assert rate("EUR", "EUR", user=alice) == 1
    assert http.calls == []


def test_a_sales_manager_gets_the_manager_wording(http, make_user):
    manager = make_user("mgr@example.com", roles=["Sales Manager"])
    provider("fawazahmed-exchange-api")
    with pytest.raises(ValidationError) as refused:
        rate("EUR", "USD", user=manager)
    assert refused.value.message.startswith("Setup the Exchange Rate Provider")


def test_a_guest_is_refused(api):
    assert api.get(ENDPOINT, {"from_currency": "EUR", "to_currency": "USD"}).status_code == 401


def test_post_is_not_served(auth_api):
    assert auth_api.post(ENDPOINT, {}, format="json").status_code == 405
