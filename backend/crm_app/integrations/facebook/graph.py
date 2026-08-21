"""The Facebook Graph API client.

Ports `facebook.py:1-17` and its `make_get_request` call sites. Every request goes through
`crm_app.integrations.http`, so it has a timeout and a retry policy — upstream's
`make_get_request` has neither.
"""

from __future__ import annotations

import logging

from crm_app.integrations import http

logger = logging.getLogger(__name__)

FB_GRAPH_API_BASE = "https://graph.facebook.com"
FB_GRAPH_API_VERSION = "v23.0"

#: `facebook.py:73` — upstream asks for 100,000 leads and leaves a `# TODO: pagination`.
#: Kept as the page size, but this port **does** follow the cursor; see :func:`get_paged`.
PAGE_SIZE = 500


def api_url(endpoint: str) -> str:
    """`facebook.py:13-17`."""
    return f"{FB_GRAPH_API_BASE}/{FB_GRAPH_API_VERSION}/{endpoint.lstrip('/')}"


def get(endpoint: str, params: dict) -> dict:
    """One Graph call.

    Raises on transport failure and on a Graph error body. The callers differ in what they
    do about it — a sync logs and continues, a user-facing token check throws — so this
    does not decide.
    """
    response = http.request("GET", api_url(endpoint), params=params)
    body = {}
    try:
        body = response.json() or {}
    except ValueError:
        pass

    if response.status_code >= 400 or "error" in body:
        error = (body.get("error") or {}).get("message") or f"HTTP {response.status_code}"
        raise FacebookApiError(error)
    return body


def get_paged(endpoint: str, params: dict, *, max_pages: int = 100) -> list[dict]:
    """Follow Graph's cursor pagination and return every row.

    **This is a divergence.** Upstream passes ``limit: 100000`` with a
    ``# TODO: pagination`` beside it (`facebook.py:73`) and reads only the first page.
    Graph caps a page well below 100,000 regardless of what is asked for, so a form with
    more leads than the cap silently syncs a prefix — no error, no log, just leads that
    never arrive. Following the cursor is the fix; `max_pages` stops a broken cursor from
    looping forever, and exhausting it is logged rather than passed over.
    """
    rows: list[dict] = []
    body = get(endpoint, params)
    rows.extend(body.get("data") or [])

    pages = 1
    while pages < max_pages:
        next_url = ((body.get("paging") or {}).get("next")) or ""
        if not next_url:
            return rows
        response = http.request("GET", next_url)
        try:
            body = response.json() or {}
        except ValueError:
            return rows
        if response.status_code >= 400 or "error" in body:
            return rows
        rows.extend(body.get("data") or [])
        pages += 1

    logger.warning(
        "facebook: stopped after %s pages for %s; there may be more leads", max_pages, endpoint
    )
    return rows


class FacebookApiError(Exception):
    """A Graph error, or a transport failure that reached the API layer."""
