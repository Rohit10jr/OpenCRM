"""The ERPNext REST client — this port's `FrappeClient`.

Upstream uses `frappe.frappeclient.FrappeClient`, which is part of the framework and not
available here. The two calls it actually makes are `get_list` and `post_api`, both plain
REST against a Frappe site, so this implements those two and nothing else.

## Authentication

`Authorization: token <api_key>:<api_secret>` — Frappe's own header scheme, and what the
settings doctype's field pair is for. The header is built per request and never logged;
`http.redact` exists for the URL half of the same problem.
"""

from __future__ import annotations

import json
import logging

from crm_app.integrations import http

logger = logging.getLogger(__name__)


class ERPNextError(Exception):
    """A remote-site failure. Callers turn this into a user-facing message."""


def _settings():
    from crm_app.models import ERPNextCRMSettings

    return ERPNextCRMSettings.load()


def is_enabled() -> bool:
    """The deployment flag **and** the settings checkbox — divergence #22."""
    from django.conf import settings

    if not getattr(settings, "ENABLE_ERPNEXT", False):
        return False
    return bool(_settings().enabled)


def _credentials(settings_row=None) -> tuple[str, str]:
    settings_row = settings_row or _settings()
    return (
        settings_row.api_key or "",
        settings_row.get_password("api_secret") or "",
    )


def _headers(settings_row=None) -> dict:
    key, secret = _credentials(settings_row)
    return {"Authorization": f"token {key}:{secret}", "Accept": "application/json"}


def site_url(settings_row=None) -> str:
    settings_row = settings_row or _settings()
    return (settings_row.erpnext_site_url or "").rstrip("/")


def is_configured() -> bool:
    """`erpnext_crm_settings.py:209-210` — the guard `get_external_companies` makes."""
    settings_row = _settings()
    key, secret = _credentials(settings_row)
    return bool(settings_row.erpnext_site_url and key and secret)


def get_list(doctype: str, fields: list[str] | None = None, filters: dict | None = None,
             limit: int = 100) -> list[dict]:
    """`FrappeClient.get_list` — `GET /api/resource/<doctype>`.

    Returns `[]` on failure rather than raising. Every caller uses it to decide whether a
    remote record exists, and a network blip should not become a 500 on a screen that is
    only asking "does this company exist there?".
    """
    settings_row = _settings()
    base = site_url(settings_row)
    if not base:
        return []

    params = {"limit_page_length": limit}
    if fields:
        params["fields"] = json.dumps(fields)
    if filters:
        params["filters"] = json.dumps(filters)

    try:
        response = http.request(
            "GET",
            f"{base}/api/resource/{doctype}",
            params=params,
            headers=_headers(settings_row),
        )
        response.raise_for_status()
        return (response.json() or {}).get("data") or []
    except Exception:
        logger.warning(
            "erpnext: get_list(%s) failed against %s", doctype, http.redact(base), exc_info=True
        )
        return []


def post_api(method: str, payload: dict) -> object:
    """`FrappeClient.post_api` — `POST /api/method/<dotted.path>`.

    **Raises** on failure, unlike :func:`get_list`. Its callers are creating something on
    the remote site, and a silent failure there means a deal that believes it has a
    Customer which does not exist.
    """
    settings_row = _settings()
    base = site_url(settings_row)
    if not base:
        raise ERPNextError("ERPNext site URL is not configured")

    try:
        response = http.request(
            "POST",
            f"{base}/api/method/{method}",
            json=payload,
            headers=_headers(settings_row),
        )
    except Exception as exc:
        raise ERPNextError(f"could not reach {http.redact(base)}") from exc

    if response.status_code >= 400:
        raise ERPNextError(f"{method} failed with HTTP {response.status_code}")

    try:
        return (response.json() or {}).get("message")
    except ValueError as exc:
        raise ERPNextError(f"{method} returned a non-JSON body") from exc
