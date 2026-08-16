"""``crm.api.onboarding.*``. Ported from ``crm/api/onboarding.py``."""

from __future__ import annotations

from frappe_core.query import fetch_rows
from frappe_core.whitelist import whitelist


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
