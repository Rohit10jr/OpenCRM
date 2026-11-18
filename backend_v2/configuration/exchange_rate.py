"""`crm.api.exchange_rate.get_exchange_rate` (specs/CONFIGURATION.md 4.3).

Ported from `backend/crm_app/api/exchange_rate.py`. The rate a deal or an organization in
another currency is converted by, from the provider chosen on FCRM Settings:
`frankfurter.app` (the default) and `fawazahmed-exchange-api` are free and fall back to
each other; `exchangerate.host` and `exchangerate-api` need the access key and have no
fallback. A rate is cached for the day it is for; a failure is never cached. Calls go
through `core.http` with a five-second timeout and no retry. `ENABLE_EXCHANGE_RATE_API`
off answers 1 for any pair.

Differences from `backend/` (PARITY_EXCEPTIONS.md): PE-10 (the accepted shapes of
`date` and the currencies) and PE-12 (a missing currency answers 1; a paid provider's
transport or JSON failure answers the generic sentence).
"""

from __future__ import annotations

import logging
import re

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from accounts.roles import ADMINISTRATOR, ROLE_SALES_MANAGER, ROLE_SYSTEM_MANAGER
from core.exceptions import ValidationError

logger = logging.getLogger(__name__)

#: `exchange_rate.py` passes `timeout=5` to every request.
TIMEOUT = 5

_CURRENCY_RE = re.compile(r"[A-Za-z]{3}")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def fx_enabled() -> bool:
    """On unless `ENABLE_EXCHANGE_RATE_API` is set false."""
    return bool(getattr(settings, "ENABLE_EXCHANGE_RATE_API", True))


def get_exchange_rate(from_currency, to_currency, date=None, *, user):
    """`exchange_rate.py:9-27`. Same currency, or a missing one, is 1 without asking."""
    if not from_currency or not to_currency or from_currency == to_currency:
        return 1
    if not fx_enabled():
        return 1

    if not date:
        date = "latest"

    if not _accepted(from_currency, to_currency, date):
        _generic_failure(from_currency, to_currency, date)

    # "latest" is keyed by today's date, so tomorrow's call misses the cache.
    cache_date = _today() if date == "latest" else date
    cache_key = f"exchange_rate_{from_currency}_{to_currency}_{cache_date}"

    cached_rate = cache.get(cache_key)
    if cached_rate is not None:
        return cached_rate

    rate, api_used = _fetch_exchange_rate(from_currency, to_currency, date, user=user)

    if rate is not None:
        cache.set(cache_key, rate, timeout=60 * 60 * 24)
        return rate

    _raise_exchange_rate_error(from_currency, to_currency, date, api_used, user=user)


def _accepted(from_currency, to_currency, date) -> bool:
    """PE-10: `latest` or an ISO date; three-letter currency codes."""
    return (
        isinstance(from_currency, str)
        and isinstance(to_currency, str)
        and isinstance(date, str)
        and bool(_CURRENCY_RE.fullmatch(from_currency))
        and bool(_CURRENCY_RE.fullmatch(to_currency))
        and (date == "latest" or bool(_DATE_RE.fullmatch(date)))
    )


def _today() -> str:
    return timezone.localdate().isoformat()


def _fetch_exchange_rate(from_currency, to_currency, date, *, user):
    from configuration.models import FCRMSettings

    settings_doc = FCRMSettings.load_or_create(user=user)
    provider = settings_doc.service_provider

    # Paid providers: no fallback.
    if provider == "exchangerate.host":
        return _fetch_from_exchangerate_host(settings_doc, from_currency, to_currency, date), provider

    if provider == "exchangerate-api":
        return _fetch_from_exchangerate_api(settings_doc, from_currency, to_currency), provider

    # Free providers fall back to each other, whichever is primary.
    if provider == "frankfurter.app":
        rate = _fetch_from_frankfurter(from_currency, to_currency, date)
        if rate is not None:
            return rate, provider
        rate = _fetch_from_fawaz_api(from_currency, to_currency, date)
        return rate, "fawazahmed-exchange-api"

    if provider == "fawazahmed-exchange-api":
        rate = _fetch_from_fawaz_api(from_currency, to_currency, date)
        if rate is not None:
            return rate, provider
        rate = _fetch_from_frankfurter(from_currency, to_currency, date)
        return rate, "frankfurter"

    # Unknown provider: try both free ones.
    rate = _fetch_from_frankfurter(from_currency, to_currency, date)
    if rate is not None:
        return rate, "frankfurter"
    return _fetch_from_fawaz_api(from_currency, to_currency, date), "fawazahmed-exchange-api"


def _get(url, params=None):
    from core import http

    return http.request("GET", url, params=params, timeout=TIMEOUT, attempts=1)


def _fetch_from_frankfurter(from_currency, to_currency, date):
    try:
        res = _get(f"https://api.frankfurter.app/{date}?from={from_currency}&to={to_currency}")
        if res.ok:
            return res.json().get("rates", {}).get(to_currency)
    except Exception:  # noqa: BLE001 - as upstream: every failure falls back
        pass
    return None


def _fetch_from_fawaz_api(from_currency, to_currency, date):
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
        raise ValidationError(
            "Access Key is required for Service Provider: {0}".format(
                f"<strong>{settings_doc.service_provider}</strong>"
            )
        )
    return access_key


def _fetch_from_exchangerate_host(settings_doc, from_currency, to_currency, date):
    access_key = _require_access_key(settings_doc)
    params = {"access_key": access_key, "from": from_currency, "to": to_currency, "amount": 1}
    if date != "latest":
        params["date"] = date
    # PE-12: a transport or JSON failure answers as a failed fetch, not a 500.
    try:
        res = _get("https://api.exchangerate.host/convert", params=params)
        if res.ok:
            return res.json()["result"]
    except Exception:  # noqa: BLE001
        logger.warning("exchangerate.host request failed")
    return None


def _fetch_from_exchangerate_api(settings_doc, from_currency, to_currency):
    access_key = _require_access_key(settings_doc)
    # PE-12, as above. The key is in this URL's path, so nothing about the request is logged.
    try:
        res = _get(f"https://v6.exchangerate-api.com/v6/{access_key}/pair/{from_currency}/{to_currency}")
        if res.ok:
            data = res.json()
            if data["result"] == "success":
                return data["conversion_rate"]
    except Exception:  # noqa: BLE001
        logger.warning("exchangerate-api request failed")
    return None


def _raise_exchange_rate_error(from_currency, to_currency, date, api_used, *, user):
    logger.error(
        "Exchange Rate Fetch Error: Failed to fetch exchange rate from %s to %s using %s API.",
        from_currency,
        to_currency,
        api_used,
    )

    if api_used == "frankfurter":
        if not _is_manager(user):
            raise ValidationError(
                "Ask your manager to set up the Exchange Rate Provider, as default provider does "
                "not support currency conversion for {0} to {1}.".format(from_currency, to_currency)
            )
        raise ValidationError(
            "Setup the Exchange Rate Provider other than 'Frankfurter' in settings, as default "
            "provider does not support currency conversion for {0} to {1}.".format(
                from_currency, to_currency
            )
        )

    _generic_failure(from_currency, to_currency, date)


def _generic_failure(from_currency, to_currency, date):
    raise ValidationError(
        "Failed to fetch exchange rate from {0} to {1} on {2}. Please check your internet "
        "connection or try again later.".format(from_currency, to_currency, date)
    )


def _is_manager(user) -> bool:
    """`"System Manager" in roles or "Sales Manager" in roles or user == "Administrator"`."""
    if user is None:
        return False
    if user.name == ADMINISTRATOR:
        return True
    return user.has_role(ROLE_SYSTEM_MANAGER) or user.has_role(ROLE_SALES_MANAGER)
