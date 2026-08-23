"""The Exotel HTTP client.

Ports `handler.py:131-148` (`get_exotel_endpoint`, `get_all_exophones`) and the request
half of `make_a_call`.

## Credentials go in `auth=`, not in the URL

Upstream builds every endpoint as::

    https://{api_key}:{api_token}@{subdomain}/v1/Accounts/{sid}/{action}

so the API token is *part of the URL string*. A URL is the one component of a failed
request that reliably ends up somewhere it should not be — a traceback, a log line, an
error page, a `Referer` header on any redirect. `requests` sends exactly the same
`Authorization: Basic` header when the pair is passed as `auth=`, so this costs nothing and
is recorded as divergence #23.

## Timeouts

Upstream passes none (`handler.py:99`, `:145`). `PHASE_7_INTEGRATIONS.md` §3 requires one
on every outbound call, and `UPSTREAM_BUGS` #15 is the local precedent for why. Divergence
#24.
"""

from __future__ import annotations

import logging

from crm_app.integrations import http

logger = logging.getLogger(__name__)


def _settings():
    from crm_app.models import CRMExotelSettings

    return CRMExotelSettings.load()


def _credentials(settings_row=None) -> tuple[str, str]:
    """``(api_key, api_token)`` — the token read back through `get_password`.

    `ENCRYPTED_FIELDS` means the *attribute* holds ciphertext once saved; reading
    `settings.api_token` directly would send the ciphertext to Exotel, which fails in a way
    that looks like a wrong credential rather than a wrong read.
    """
    settings_row = settings_row or _settings()
    return (settings_row.api_key or "", settings_row.get_password("api_token") or "")


def endpoint(action: str, version: str = "v1") -> str:
    """`handler.py:131-140`, minus the credentials — those travel in `auth=`."""
    settings_row = _settings()
    subdomain = (settings_row.subdomain or "").strip().rstrip("/")
    return f"https://{subdomain}/{version}/Accounts/{settings_row.account_sid}/{action}"


def get_all_exophones() -> list[str]:
    """`handler.py:143-146`.

    Returns an empty list on any transport failure rather than raising. The single caller
    uses it to validate a caller id, and upstream's behaviour on an unreachable Exotel is
    an unhandled exception; returning empty turns that into the *user-facing* error
    "Exotel Number ... is not valid", which is wrong in wording but is a dialog rather than
    a 500. Recorded in the progress file as a judgement call.
    """
    settings_row = _settings()
    try:
        response = http.request(
            "GET",
            endpoint("IncomingPhoneNumbers", "v2_beta"),
            auth=_credentials(settings_row),
        )
        response.raise_for_status()
        body = response.json()
    except Exception:
        logger.warning("exotel: could not list exophones", exc_info=True)
        return []

    return [
        phone.get("friendly_name")
        for phone in (body.get("incoming_phone_numbers") or [])
        if phone.get("friendly_name")
    ]


def status_callback_url() -> str:
    """`handler.py:150-155`.

    The webhook URL Exotel calls back on, carrying the shared secret as `?key=`. That is
    the whole of the webhook's authentication — Exotel does not sign requests — so this
    URL **is** a credential and must not be logged.
    """
    from django.conf import settings as django_settings

    settings_row = _settings()
    # Read directly: `webhook_verify_token` is `RESTRICTED_FIELDS`, not `ENCRYPTED_FIELDS`,
    # so it is plaintext in the column and `get_password` would raise for it. See
    # `handler.validate_request` for why it is not encrypted, and the progress file for the
    # residual gap that leaves.
    token = settings_row.webhook_verify_token or ""
    base = (getattr(django_settings, "SITE_URL", "") or "").rstrip("/")
    return f"{base}/api/method/crm.integrations.exotel.handler.handle_request?key={token}"


def connect_call(*, from_number: str, to_number: str, caller_id: str, record: bool) -> dict:
    """`handler.py:96-119` — POST `Calls/connect.json`.

    Raises through `throw` on an Exotel-reported error, preserving upstream's message, and
    on a transport failure — the caller is a user pressing "call", so silence would be
    worse than an error.
    """
    from frappe_core.exceptions import throw

    url = endpoint("Calls/connect.json?details=true")
    try:
        response = http.request(
            "POST",
            url,
            auth=_credentials(),
            data={
                "From": from_number,
                "To": to_number,
                "CallerId": caller_id,
                "Record": "true" if record else "false",
                "StatusCallback": status_callback_url(),
                "StatusCallbackEvents[0]": "terminal",
                "StatusCallbackEvents[1]": "answered",
            },
        )
    except Exception:
        # `http.redact` rather than the raw url: this one carries no userinfo, but the
        # message is user-facing and the habit is the point.
        logger.warning("exotel: connect failed for %s", http.redact(url), exc_info=True)
        throw("Could not reach Exotel", title="Exotel Unreachable")

    if response.status_code >= 400:
        # `handler.py:111-113` — Exotel reports its own errors in a RestException body.
        try:
            exception = (response.json() or {}).get("RestException") or {}
        except ValueError:
            exception = {}
        message = exception.get("Message")
        if message:
            throw(message, title="Exotel Exception")
        throw("Exotel request failed", title="Exotel Exception")

    try:
        return response.json() or {}
    except ValueError:
        return {}
