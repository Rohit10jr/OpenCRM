"""``crm.api.exchange_rate.get_exchange_rate``. Ported from ``crm/api/exchange_rate.py``.

The rate a deal or an organization in another currency is converted by, into the
dashboard currency on FCRM Settings (FINDINGS.md 63). The provider is the one chosen in
Settings -> Dashboard (``FCRM Settings.service_provider``), as upstream:

* ``frankfurter.app`` (the default) and ``fawazahmed-exchange-api`` are free and keyless,
  and each falls back to the other when it does not answer;
* ``exchangerate.host`` and ``exchangerate-api`` need the access key from the same page
  and have no fallback.

A rate is cached for the day it is for, so "latest" is fetched once a day per pair.

Two differences from upstream, both about the network rather than the answer:

* **Calls go through** :mod:`crm_app.integrations.http`, the one outbound helper, with
  upstream's five-second timeout and no retry: a deal save waits on this, and upstream
  does not retry either.
* **A switch to turn it off**, ``ENABLE_EXCHANGE_RATE_API`` (on unless set false). Off, a
  rate between two different currencies is 1, which was this port's only behaviour until
  the providers were ported: a site with no outbound internet can still save a deal in
  another currency. The test settings turn it off, as they turn off the mail server.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from frappe_core.exceptions import throw
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

logger = logging.getLogger(__name__)

#: ``exchange_rate.py`` passes ``timeout=5`` to every ``requests.get``.
TIMEOUT = 5


def fx_enabled() -> bool:
    """On unless ``ENABLE_EXCHANGE_RATE_API`` is set false (``config/settings/base.py``)."""
    return bool(getattr(settings, "ENABLE_EXCHANGE_RATE_API", True))


@whitelist("crm.api.exchange_rate.get_exchange_rate")
def get_exchange_rate(from_currency: str, to_currency: str, date: str | None = None):
    """``exchange_rate.py:9-27``.

    Same currency is 1 without asking anybody. That branch is the port's: upstream's
    callers only ask when the two differ, and a provider asked for EUR to EUR answers 1
    or nothing, so answering 1 here saves the call and changes no result.
    """
    if not from_currency or not to_currency or from_currency == to_currency:
        return 1
    if not fx_enabled():
        return 1

    if not date:
        date = "latest"

    # "latest" is keyed by today's date so tomorrow's call automatically misses the cache
    cache_date = _today() if date == "latest" else date
    cache_key = f"exchange_rate_{from_currency}_{to_currency}_{cache_date}"

    cached_rate = cache.get(cache_key)
    if cached_rate is not None:
        return cached_rate

    rate, api_used = _fetch_exchange_rate(from_currency, to_currency, date)

    if rate is not None:
        # frappe.cache().set_value with no expiry; a day is enough, the key moves daily.
        cache.set(cache_key, rate, timeout=60 * 60 * 24)
        return rate

    _raise_exchange_rate_error(from_currency, to_currency, date, api_used)


def _today() -> str:
    return timezone.localdate().isoformat()


def _fetch_exchange_rate(from_currency: str, to_currency: str, date: str):
    from crm_app.models import FCRMSettings

    settings_doc = FCRMSettings.load()
    provider = settings_doc.service_provider

    # Paid providers — no fallback, fail explicitly
    if provider == "exchangerate.host":
        return _fetch_from_exchangerate_host(settings_doc, from_currency, to_currency, date), provider

    if provider == "exchangerate-api":
        return _fetch_from_exchangerate_api(settings_doc, from_currency, to_currency), provider

    # Free providers — try both as fallbacks, regardless of which is "primary"
    if provider == "frankfurter.app":
        rate = _fetch_from_frankfurter(from_currency, to_currency, date)
        if rate is not None:
            return rate, provider
        # Frankfurter is down — silently fall back to fawaz
        rate = _fetch_from_fawaz_api(from_currency, to_currency, date)
        return rate, "fawazahmed-exchange-api"

    if provider == "fawazahmed-exchange-api":
        rate = _fetch_from_fawaz_api(from_currency, to_currency, date)
        if rate is not None:
            return rate, provider
        # fawaz is down — silently fall back to frankfurter
        rate = _fetch_from_frankfurter(from_currency, to_currency, date)
        return rate, "frankfurter"

    # Unknown provider — try both free ones
    rate = _fetch_from_frankfurter(from_currency, to_currency, date)
    if rate is not None:
        return rate, "frankfurter"
    return _fetch_from_fawaz_api(from_currency, to_currency, date), "fawazahmed-exchange-api"


def _get(url: str, params: dict | None = None):
    from crm_app.integrations import http

    return http.request("GET", url, params=params, timeout=TIMEOUT, attempts=1)


def _fetch_from_frankfurter(from_currency: str, to_currency: str, date: str):
    try:
        res = _get(f"https://api.frankfurter.app/{date}?from={from_currency}&to={to_currency}")
        if res.ok:
            return res.json().get("rates", {}).get(to_currency)
    except Exception:  # noqa: BLE001 - upstream swallows every failure and falls back
        pass
    return None


def _fetch_from_fawaz_api(from_currency: str, to_currency: str, date: str):
    from_lower = from_currency.lower()
    to_lower = to_currency.lower()
    date_str = "latest" if date == "latest" else date
    urls = [
        f"https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{date_str}/v1/currencies/{from_lower}.json",
        f"https://{date_str}.currency-api.pages.dev/v1/currencies/{from_lower}.json",
    ]
    for url in urls:
        try:
            res = _get(url)
            if res.ok:
                return res.json()[from_lower][to_lower]
        except Exception:  # noqa: BLE001 - as upstream: try the next mirror
            continue
    return None


def _require_access_key(settings_doc) -> str:
    access_key = settings_doc.access_key
    if not access_key:
        throw(
            "Access Key is required for Service Provider: {0}".format(
                f"<strong>{settings_doc.service_provider}</strong>"
            )
        )
    return access_key


def _fetch_from_exchangerate_host(settings_doc, from_currency: str, to_currency: str, date: str):
    access_key = _require_access_key(settings_doc)
    params = {"access_key": access_key, "from": from_currency, "to": to_currency, "amount": 1}
    if date != "latest":
        params["date"] = date
    res = _get("https://api.exchangerate.host/convert", params=params)
    if res.ok:
        return res.json()["result"]
    return None


def _fetch_from_exchangerate_api(settings_doc, from_currency: str, to_currency: str):
    access_key = _require_access_key(settings_doc)
    res = _get(f"https://v6.exchangerate-api.com/v6/{access_key}/pair/{from_currency}/{to_currency}")
    if res.ok:
        data = res.json()
        if data["result"] == "success":
            return data["conversion_rate"]
    return None


def _raise_exchange_rate_error(from_currency: str, to_currency: str, date: str, api_used: str):
    # frappe.log_error: an Error Log row upstream, the application log here.
    logger.error(
        "Exchange Rate Fetch Error: Failed to fetch exchange rate from %s to %s using %s API.",
        from_currency,
        to_currency,
        api_used,
    )

    if api_used == "frankfurter":
        if not _is_manager(get_current_user()):
            throw(
                "Ask your manager to set up the Exchange Rate Provider, as default provider does "
                "not support currency conversion for {0} to {1}.".format(from_currency, to_currency)
            )
        throw(
            "Setup the Exchange Rate Provider other than 'Frankfurter' in settings, as default "
            "provider does not support currency conversion for {0} to {1}.".format(
                from_currency, to_currency
            )
        )

    throw(
        "Failed to fetch exchange rate from {0} to {1} on {2}. Please check your internet "
        "connection or try again later.".format(from_currency, to_currency, date)
    )


def _is_manager(user: str) -> bool:
    """``"System Manager" in roles or "Sales Manager" in roles or user == "Administrator"``."""
    from frappe_core.query import by_name
    from frappe_platform.models import User

    if user == "Administrator":
        return True
    found = by_name(User, user).first()
    roles = found.get_roles() if found is not None else set()
    return bool(roles & {"System Manager", "Sales Manager"})
