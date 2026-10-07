"""``crm.api.onboarding.*``, ported from ``crm/api/onboarding.py``, and the framework's
``frappe.onboarding.*`` pair that frappe-ui's ``useOnboarding`` calls from inside the
package (``frappe-ui/frappe/Onboarding/onboarding.js``), which no scan of
``frontend/src`` could see (FINDINGS.md 39)."""

from __future__ import annotations

import json

from frappe_core.exceptions import ValidationError
from frappe_core.query import by_name, fetch_rows, parse_json_param
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist
from frappe_platform.models import User


@whitelist("crm.api.onboarding.get_first_lead")
def get_first_lead():
    """``crm/api/onboarding.py:5-14``. Returns the name, or None."""
    rows = fetch_rows(
        "CRM Lead",
        fields=["name"],
        filters={"converted": 0},
        order_by="creation asc",
        limit_page_length=1,
    )
    return rows[0]["name"] if rows else None


@whitelist("crm.api.onboarding.get_first_deal")
def get_first_deal():
    """``crm/api/onboarding.py:17-24``."""
    rows = fetch_rows(
        "CRM Deal", fields=["name"], order_by="creation asc", limit_page_length=1
    )
    return rows[0]["name"] if rows else None


# --- frappe.onboarding: the per-user status behind frappe-ui's onboarding panel ---------


def _status_of_current_user() -> dict:
    """The caller's ``User.onboarding_status`` as a dict; ``{}`` when unset or unreadable."""
    raw = by_name(User, get_current_user()).values_list("onboarding_status", flat=True).first()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


@whitelist("frappe.onboarding.get_onboarding_status")
def get_onboarding_status():
    """``frappe/onboarding.py:6-9`` - the JSON object off the caller's User row, ``{}``
    when there is none yet. Read once per session by ``useOnboarding`` and cached in
    the browser under ``onboardingStatus[user]``."""
    return _status_of_current_user()


@whitelist("frappe.onboarding.update_user_onboarding_status")
def update_user_onboarding_status(steps: str = "", appName: str = "", **extra):
    """``frappe/onboarding.py:12-25`` - store ``steps`` under ``<appName>_onboarding_status``.

    ``steps`` arrives as a JSON string (``onboarding.js:121-126`` stringifies it), a list
    of ``{name, completed, skipped, ...}`` objects; other apps' keys are kept.

    Divergence, deliberate: upstream reads the column with ``frappe.parse_json``, which
    returns ``None`` for an unset column, then subscripts it - so the very first update
    for a user with no status answers 500 (``UPSTREAM_BUGS.md`` 40). Here an
    unset status is ``{}``. ``update_modified=False`` upstream; a queryset ``update``
    likewise leaves the row's timestamps alone.
    """
    if not appName:
        raise ValidationError("appName is required")
    parsed = parse_json_param(steps, None) if isinstance(steps, str) else steps
    # `parse_json_param` hands a string that is not JSON back unchanged (a bare
    # `order_by=modified` is legitimate elsewhere); here only a JSON array or object is.
    if not isinstance(parsed, (list, dict)):
        raise ValidationError("steps must be JSON")
    status = _status_of_current_user()
    status[f"{appName}_onboarding_status"] = parsed
    by_name(User, get_current_user()).update(onboarding_status=json.dumps(status))
    return None
