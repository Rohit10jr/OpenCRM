"""The Twilio API client — signatures, tokens, TwiML, REST.

No SDK; see the package docstring for why. Every piece here is a documented public format.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from xml.sax.saxutils import quoteattr

from crm_app.integrations import http

logger = logging.getLogger(__name__)

API_ROOT = "https://api.twilio.com/2010-04-01"

#: Voice access tokens are short-lived by design — the browser asks for a new one when it
#: needs to dial. Upstream uses one hour (`twilio_handler.py:39`).
ACCESS_TOKEN_TTL = 60 * 60


def _settings():
    from crm_app.models import CRMTwilioSettings

    return CRMTwilioSettings.load()


def auth_token(settings_row=None) -> str:
    """The account auth token, decrypted.

    `ENCRYPTED_FIELDS` means the attribute is ciphertext once saved. This is also the key
    Twilio signs webhooks with, so reading it wrong makes every inbound request look forged.
    """
    settings_row = settings_row or _settings()
    return settings_row.get_password("auth_token") or ""


def api_secret(settings_row=None) -> str:
    settings_row = settings_row or _settings()
    return settings_row.get_password("api_secret") or ""


# ---------------------------------------------------------------------------
# Request signatures
# ---------------------------------------------------------------------------


def expected_signature(url: str, params: dict, token: str) -> str:
    """Twilio's documented scheme.

    Take the full request URL, append every POST parameter as ``key + value`` **sorted by
    key**, HMAC-SHA1 the result with the account auth token, base64 the digest.

    The sort is the part that is easy to get wrong and impossible to notice: an
    unsorted concatenation produces a valid-looking signature that never matches, so
    every webhook is rejected and the symptom reads as a wrong auth token.
    """
    payload = url
    for key in sorted(params or {}):
        payload += f"{key}{params[key]}"

    digest = hmac.new(
        token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def validate_signature(url: str, params: dict, signature: str | None, token: str) -> bool:
    """Constant-time comparison against the expected signature.

    Returns False rather than raising, so the caller decides the response — a webhook that
    fails validation should 403, not 500.
    """
    if not signature or not token:
        return False
    return hmac.compare_digest(expected_signature(url, params, token), str(signature))


# ---------------------------------------------------------------------------
# Voice access token (a JWT)
# ---------------------------------------------------------------------------


def safe_identity(identity: str) -> str:
    """`twilio_handler.py:55-61`.

    Twilio Client JS fails to connect when the identity contains `@` (error 31105), and
    our identities are email addresses. Upstream's substitution, kept exactly — the
    reverse mapping has to agree with it, and `(at)` is what already-issued tokens carry.
    """
    return identity.replace("@", "(at)")


def emailid_from_identity(identity: str) -> str:
    """`twilio_handler.py:63-66` — the inverse of :func:`safe_identity`."""
    return identity.replace("(at)", "@")


def generate_voice_access_token(identity: str, ttl: int = ACCESS_TOKEN_TTL) -> str:
    """The JWT the browser SDK authenticates with.

    Twilio's documented structure: signed with the **API secret**, `iss` is the API key,
    `sub` is the account SID, and the voice grant names the TwiML application. `cty` in the
    header is what tells Twilio this is an access token rather than an ordinary JWT.
    """
    import time

    import jwt

    settings_row = _settings()
    now = int(time.time())
    identity = safe_identity(identity)

    payload = {
        "jti": f"{settings_row.api_key}-{now}",
        "iss": settings_row.api_key,
        "sub": settings_row.account_sid,
        "iat": now,
        "exp": now + ttl,
        "grants": {
            "identity": identity,
            "voice": {
                "outgoing": {"application_sid": settings_row.twiml_sid},
                "incoming": {"allow": True},
            },
        },
    }
    return jwt.encode(
        payload,
        api_secret(settings_row),
        algorithm="HS256",
        headers={"cty": "twilio-fpa;v=1", "typ": "JWT"},
    )


# ---------------------------------------------------------------------------
# TwiML
# ---------------------------------------------------------------------------


def _attrs(pairs: dict) -> str:
    return "".join(
        f" {k}={quoteattr(str(v))}" for k, v in pairs.items() if v not in (None, "")
    )


def dial_number_response(
    *, caller_id: str, to_number: str, record: bool, recording_callback: str, status_callback: str
) -> str:
    """`twilio_handler.py:75-92` — forward an incoming call to an agent's phone.

    Built as XML rather than through `VoiceResponse`. Attribute values are escaped with
    `quoteattr`, which matters because `caller_id` and `to_number` come from a webhook
    payload: an unescaped quote would let a caller inject TwiML verbs and redirect the call.
    """
    dial_attrs = _attrs(
        {
            "callerId": caller_id,
            "record": "record-from-answer-dual" if record else "do-not-record",
            "recordingStatusCallback": recording_callback,
            "recordingStatusCallbackEvent": "completed",
        }
    )
    number_attrs = _attrs(
        {
            "statusCallbackEvent": "initiated ringing answered completed",
            "statusCallback": status_callback,
            "statusCallbackMethod": "POST",
        }
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Dial{dial_attrs}>"
        f"<Number{number_attrs}>{_escape_text(to_number)}</Number>"
        "</Dial></Response>"
    )


def dial_client_response(
    *, client: str, record: bool, recording_callback: str, status_callback: str, ring_tone: str = "at"
) -> str:
    """`twilio_handler.py:97-113` — forward an incoming call to the agent's browser."""
    dial_attrs = _attrs(
        {
            "ringTone": ring_tone,
            "record": "record-from-answer-dual" if record else "do-not-record",
            "recordingStatusCallback": recording_callback,
            "recordingStatusCallbackEvent": "completed",
        }
    )
    client_attrs = _attrs(
        {
            "statusCallbackEvent": "initiated ringing answered completed",
            "statusCallback": status_callback,
            "statusCallbackMethod": "POST",
        }
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Dial{dial_attrs}>"
        f"<Client{client_attrs}>{_escape_text(client)}</Client>"
        "</Dial></Response>"
    )


def say_response(message: str) -> str:
    """`twilio_handler.py:143-146` — nobody is available to take the call."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Say>{_escape_text(message)}</Say></Response>"
    )


def _escape_text(value: str) -> str:
    from xml.sax.saxutils import escape

    return escape(str(value or ""))


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------


def fetch_call(call_sid: str) -> dict:
    """`twilio_handler.py:94-95` — `GET /Calls/{sid}.json`.

    Returns ``{}`` on any failure. The caller uses it to enrich a call log that already
    exists; losing the enrichment is better than losing the webhook.
    """
    settings_row = _settings()
    url = f"{API_ROOT}/Accounts/{settings_row.account_sid}/Calls/{call_sid}.json"
    try:
        response = http.request(
            "GET", url, auth=(settings_row.account_sid, auth_token(settings_row))
        )
        response.raise_for_status()
        return response.json() or {}
    except Exception:
        logger.warning("twilio: could not fetch call %s", call_sid, exc_info=True)
        return {}


def list_phone_numbers() -> list[str]:
    """`twilio_handler.py:34-36` — `GET /IncomingPhoneNumbers.json`."""
    settings_row = _settings()
    url = f"{API_ROOT}/Accounts/{settings_row.account_sid}/IncomingPhoneNumbers.json"
    try:
        response = http.request(
            "GET", url, auth=(settings_row.account_sid, auth_token(settings_row))
        )
        response.raise_for_status()
        body = response.json() or {}
    except Exception:
        logger.warning("twilio: could not list phone numbers", exc_info=True)
        return []

    return [n.get("phone_number") for n in body.get("incoming_phone_numbers", []) if n.get("phone_number")]
