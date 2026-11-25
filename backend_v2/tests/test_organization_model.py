"""CRM Organization's model: naming, the Link checks and the exchange rate (specs/CONTACTS.md
§4 "CRM Organization"; milestone 5).

Ported (REBUILD_PLAN S14): ``backend/tests/test_crm_behaviour.py:252-259`` (the rate is 1
in the dashboard currency), ``test_currency.py:71-79`` (a currency that names nothing is
refused, another spelling is stored as the Currency's), and
``test_exchange_rate.py:144-174`` (the rate on save and on a currency change, an unknown
currency refused before any provider, a partial save asks nobody). The deal cases and the
refresh command wait for SALES.
"""

import pytest

from configuration import exchange_rate
from configuration.models import FCRMSettings
from contacts.models import CRMOrganization
from core.exceptions import LinkValidationError, ValidationError

pytestmark = pytest.mark.django_db

FRANKFURTER = "https://api.frankfurter.app/latest?from=EUR&to=USD"


class Response:
    def __init__(self, payload):
        self.ok, self._payload = True, payload

    def json(self):
        return self._payload


class FakeHTTP:
    """As `tests/test_exchange_rate.py`'s: answers by URL prefix, records every call, and
    an unmatched URL is a failed request."""

    def __init__(self):
        self.answers = {}
        self.calls = []

    def __call__(self, url, params=None):
        self.calls.append((url, params))
        for prefix, payload in self.answers.items():
            if url.startswith(prefix):
                return Response(payload)
        raise ConnectionError(url)


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


def organization(user, **fields):
    org = CRMOrganization(**fields)
    org.save(user=user)
    return org


# --- naming ---------------------------------------------------------------------------------


def test_the_name_is_the_organization_name_verbatim(alice):
    """`autoname: field:organization_name`, not slugified (old `core_sales.py:100-106`)."""
    assert organization(alice, organization_name="ScaleUp Labs").pk == "ScaleUp Labs"


# --- ported ---------------------------------------------------------------------------------


def test_organization_exchange_rate_defaults_to_one(alice):
    """`test_crm_behaviour.py:252-259`: in the dashboard currency the rate is 1."""
    assert organization(alice, organization_name="Acme", currency="USD").exchange_rate == 1


def test_a_currency_that_names_nothing_is_refused(administrator):
    """`test_currency.py:71-79`."""
    with pytest.raises(LinkValidationError, match="Could not find Currency: XYZ"):
        organization(administrator, organization_name="ZZ Nowhere", currency="XYZ")
    org = organization(administrator, organization_name="ZZ Somewhere", currency="eur")
    assert org.currency == "EUR", "the stored spelling"


def test_an_organization_takes_the_rate_on_save_and_again_when_its_currency_changes(http, alice):
    """`test_exchange_rate.py:144-154`."""
    http.answers = {FRANKFURTER: {"rates": {"USD": 1.09}}}
    org = organization(alice, organization_name="ZZ Euro", currency="EUR")
    assert org.exchange_rate == 1.09
    org.website = "https://example.com"
    org.save(user=alice)
    assert len(http.calls) == 1, "same currency, rate held: nobody is asked again"
    org.currency = "USD"
    org.save(user=alice)
    assert CRMOrganization.objects.get(pk=org.pk).exchange_rate == 1


def test_an_unknown_currency_is_refused_before_any_provider_is_asked(http, alice):
    """`test_exchange_rate.py:157-160`."""
    with pytest.raises(LinkValidationError):
        organization(alice, organization_name="ZZ Nowhere", currency="XYZ")
    assert http.calls == []


def test_a_partial_save_asks_nobody(http, alice):
    """`test_exchange_rate.py:163-174`: `save(update_fields=...)` is upstream's
    `db.set_value`, which runs no validate."""
    org = organization(alice, organization_name="ZZ Partial", currency="USD")
    CRMOrganization.objects.filter(pk=org.pk).update(currency="EUR", exchange_rate=None)
    org = CRMOrganization.objects.get(pk=org.pk)
    org.organization_logo = "/files/logo.png"
    org.save(user=alice, update_fields=["organization_logo"])
    assert http.calls == []


# --- new ------------------------------------------------------------------------------------


def test_no_currency_is_one_and_asks_nobody(http, alice):
    assert organization(alice, organization_name="ZZ Plain").exchange_rate == 1
    assert http.calls == []


def test_the_dashboard_currency_is_read_from_fcrm_settings(http, alice):
    """In the FCRM Settings currency the rate is 1 without asking; USD is then foreign."""
    FCRMSettings.objects.update(currency="EUR")
    assert organization(alice, organization_name="ZZ Home", currency="EUR").exchange_rate == 1
    assert http.calls == []


def test_a_held_rate_is_kept_and_a_missing_one_recomputed(http, alice):
    http.answers = {FRANKFURTER: {"rates": {"USD": 1.09}}}
    org = organization(alice, organization_name="ZZ Held", currency="EUR")
    CRMOrganization.objects.filter(pk=org.pk).update(exchange_rate=2.5)
    org = CRMOrganization.objects.get(pk=org.pk)
    org.save(user=alice)
    assert org.exchange_rate == 2.5, "held, currency unchanged"
    CRMOrganization.objects.filter(pk=org.pk).update(exchange_rate=None)
    org = CRMOrganization.objects.get(pk=org.pk)
    org.save(user=alice)
    assert org.exchange_rate == 1.09


def test_a_provider_failure_refuses_the_save(http, alice):
    """No provider answers: upstream's `frappe.throw`, so nothing is saved."""
    with pytest.raises(ValidationError):
        organization(alice, organization_name="ZZ Offline", currency="EUR")
    assert not CRMOrganization.objects.filter(pk="ZZ Offline").exists()


def test_a_provider_failure_answers_its_sentence_at_the_route(http, auth_api):
    """The message is user-facing copy (hard rule 14). Every provider down: the default
    falls back to fawazahmed, which fails too, so the answer is the generic sentence
    (`exchange_rate.py` `_raise_exchange_rate_error`, `_generic_failure`)."""
    response = auth_api.post(
        "/api/v1/organizations/", {"organization_name": "ZZ Offline", "currency": "EUR"}, format="json"
    )
    assert response.status_code == 417
    assert response.json()["message"] == (
        "Failed to fetch exchange rate from EUR to USD on latest. Please check your internet "
        "connection or try again later."
    )
    assert not CRMOrganization.objects.filter(pk="ZZ Offline").exists()


def test_with_the_api_off_a_foreign_currency_stores_one_and_asks_nobody(monkeypatch, settings, alice):
    """The test settings' default (`ENABLE_EXCHANGE_RATE_API` off)."""
    settings.ENABLE_EXCHANGE_RATE_API = False
    fake = FakeHTTP()
    monkeypatch.setattr(exchange_rate, "_get", fake)
    assert organization(alice, organization_name="ZZ Off", currency="EUR").exchange_rate == 1
    assert fake.calls == []


def test_a_missing_name_is_refused_before_any_provider_is_asked(http, auth_api):
    """A-85 finding 4: the name is set first, as upstream's `insert` does
    (v15 `document.py:304`)."""
    response = auth_api.post("/api/v1/organizations/", {"organization_name": "", "currency": "EUR"}, format="json")
    assert response.status_code == 417
    assert response.json()["message"] == "Organization Name is required"
    assert http.calls == []


def test_an_address_that_names_nothing_is_refused(alice):
    with pytest.raises(LinkValidationError, match="Could not find Address: Nowhere-Office"):
        organization(alice, organization_name="ZZ Lost", address="Nowhere-Office")
