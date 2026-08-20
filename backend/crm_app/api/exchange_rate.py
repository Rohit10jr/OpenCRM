"""``crm.api.exchange_rate.get_exchange_rate``. Ported from ``crm/api/exchange_rate.py``.

The spec's instruction is explicit: *"calls an external FX service; stub behind a feature
flag"* (PHASE_3_ENDPOINTS.md section 2, Group D). So the shape, caching and same-currency
short circuit are ported; the network call is not made unless the flag is on, and there
is no provider implementation behind it in phases 3-6.

Returning ``1`` for an unavailable rate is deliberate and matches
``CRMOrganization.update_exchange_rate``, which phase 1 ported with the same default -
a missing rate must not make a deal value zero.
"""

from __future__ import annotations

import datetime

from django.conf import settings

from frappe_core.whitelist import whitelist


def fx_enabled() -> bool:
    """Off unless explicitly enabled. There is no provider wired in phases 3-6."""
    return bool(getattr(settings, "ENABLE_EXCHANGE_RATE_API", False))


@whitelist("crm.api.exchange_rate.get_exchange_rate")
def get_exchange_rate(from_currency: str, to_currency: str, date: str | None = None):
    """``crm/api/exchange_rate.py``.

    Same currency returns ``1`` without consulting anything, which is both upstream's
    behaviour and the only branch reachable in a default deployment.
    """
    if not from_currency or not to_currency:
        return 1
    if from_currency == to_currency:
        return 1

    if not fx_enabled():
        # No provider configured. 1 keeps values comparable rather than zeroing them.
        return 1

    # Phase 7 owns the provider integrations (PORT_PLAN.md section 7). Reaching here
    # with the flag on but nothing implemented is a configuration error worth surfacing
    # rather than silently returning a wrong number.
    raise NotImplementedError(
        "ENABLE_EXCHANGE_RATE_API is set but no FX provider is implemented; "
        "provider integrations are phase 7"
    )
