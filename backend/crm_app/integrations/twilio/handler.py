"""`crm.integrations.twilio.api.*` — the Twilio endpoints.

Ports `crm/integrations/twilio/api.py` and the call-routing half of `twilio_handler.py`.

Three of the five endpoints are `allow_guest=True` webhooks. All three verify Twilio's
`X-Twilio-Signature`, which upstream does not — see the package docstring and
`UPSTREAM_BUGS` #27.
"""

from __future__ import annotations

import logging

from crm_app.integrations import call_log as call_log_path
from crm_app.integrations.twilio import client
from frappe_core.exceptions import (
    DoesNotExistError,
    PermissionError as FrappePermissionError,
)
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

logger = logging.getLogger(__name__)


def get_twilio_settings():
    from crm_app.models import CRMTwilioSettings

    return CRMTwilioSettings.load()


@whitelist("crm.integrations.twilio.api.is_enabled")
def is_enabled():
    """`api.py:29-31`. An `and` of the deployment flag and the checkbox — divergence #22."""
    from django.conf import settings

    if not getattr(settings, "ENABLE_TWILIO", False):
        return False
    return bool(get_twilio_settings().enabled)


def validate_twilio_request(
    params: dict, *, url: str, signature: str | None, require_application_sid: bool = False
):
    """`api.py:12-26`, **replaced rather than transcribed**.

    Upstream checks that the `AccountSid` in the payload equals the configured one. An
    Account SID is not a secret — it is in every webhook, in the Twilio console, and in any
    log that captured a request — so that check authenticates nothing: anyone who has seen
    one webhook can forge every subsequent one, and forging a webhook writes call logs into
    the CRM and can redirect an inbound call.

    Twilio signs every request with `X-Twilio-Signature` (HMAC-SHA1 over the URL plus the
    sorted POST parameters, keyed with the account auth token).
    `PHASE_7_INTEGRATIONS.md` §3 requires signature verification and says explicitly not to
    skip it. So the signature is the check, and the SID comparison is **kept as well** —
    it costs nothing and it catches a correctly-signed request from a different account.

    Upstream's `frappe.throw` messages are preserved, because they are user-facing copy.
    """
    if not is_enabled():
        raise FrappePermissionError("Twilio configuration is missing", title="Not Permitted")

    settings_row = get_twilio_settings()
    token = client.auth_token(settings_row)

    if not client.validate_signature(url, params, signature, token):
        logger.warning("twilio webhook rejected: bad or missing signature")
        raise FrappePermissionError("Invalid Twilio signature", title="Not Permitted")

    account_sid = str(params.get("AccountSid") or "")
    if not account_sid or account_sid != str(settings_row.account_sid or ""):
        raise FrappePermissionError("Invalid Twilio account", title="Not Permitted")

    if require_application_sid:
        application_sid = str(params.get("ApplicationSid") or "")
        if not application_sid or application_sid != str(settings_row.twiml_sid or ""):
            raise FrappePermissionError("Invalid Twilio application", title="Not Permitted")

    return settings_row


# ---------------------------------------------------------------------------
# Call routing
# ---------------------------------------------------------------------------


def get_twilio_number_owners(phone_number: str) -> dict:
    """`twilio_handler.py:152-172`.

    Upstream strips everything but digits and a leading `+` before matching, which is a
    plain equality against `CRM Telephony Agent.twilio_number` — not the fuzzy resolution
    `phone.get_contact` does. Kept as-is: this asks "which of our agents owns this Twilio
    number", and those are values we set ourselves.
    """
    from crm_app.models import CRMTelephonyAgent

    cleaned = "".join(c for c in str(phone_number or "") if c.isdigit() or c == "+")
    if not cleaned:
        return {}

    agents = CRMTelephonyAgent._default_manager.filter(twilio_number=cleaned).select_related(
        "user"
    )
    return {
        agent.user_id: {
            "name": agent.user_id,
            "call_receiving_device": agent.call_receiving_device,
            "mobile_no": agent.mobile_no or getattr(agent.user, "mobile_no", "") or "",
        }
        for agent in agents
    }


def get_the_call_attender(owners: dict, caller: str | None = None) -> dict | None:
    """`twilio_handler.py:192-211`.

    **One deliberate simplification.** Upstream narrows a multi-owner list to whoever is
    currently logged in, read from Frappe's `tabSessions` table. This port authenticates
    with stateless JWTs and has no server-side session table — `SECURITY_MODEL.md` and the
    JWT patch both record that as the sanctioned deviation — so "currently logged in" is
    not a question that can be answered here.

    The consequence is stated rather than hidden: with several agents sharing one Twilio
    number, upstream rings the one at their desk and this port rings the first whose device
    settings make them reachable. The deal/lead-owner preference below still applies, which
    is the part that matters most in practice.
    """
    if not owners:
        return None

    preferred = None
    if caller:
        preferred = _owner_for_caller(caller, owners)

    ordered = [owners[preferred]] if preferred else list(owners.values())
    if preferred:
        ordered += [v for k, v in owners.items() if k != preferred]

    for details in ordered:
        device = details.get("call_receiving_device")
        if device == "Phone" and details.get("mobile_no"):
            return details
        if device == "Computer":
            return details
    return None


def _owner_for_caller(caller: str, owners: dict) -> str | None:
    """`twilio_handler.py:199-206` — prefer the agent who owns the deal or lead calling."""
    from crm_app.models import CRMDeal, CRMLead

    owner = (
        CRMDeal._default_manager.filter(mobile_no=caller)
        .values_list("deal_owner", flat=True)
        .first()
    )
    if not owner:
        owner = (
            CRMLead._default_manager.filter(mobile_no=caller, converted=False)
            .values_list("lead_owner", flat=True)
            .first()
        )
    return owner if owner in owners else None


# ---------------------------------------------------------------------------
# Call details
# ---------------------------------------------------------------------------


def call_status(twilio_status: str | None) -> str:
    """`twilio_handler.py:238-242` — ``no-answer`` -> ``No Answer``."""
    return " ".join(str(twilio_status or "").split("-")).title()


def call_details(params: dict, call_from: str | None = None, call_to: str | None = None) -> dict:
    """`twilio_handler.py:213-266` — the dict a call log is built from."""
    caller_field = str(params.get("Caller") or "")
    direction = "Outgoing" if caller_field.lower().startswith("client") else "Incoming"

    from_number = call_from or params.get("From") or ""
    to_number = call_to or params.get("To") or ""

    caller = ""
    receiver = ""
    if direction == "Outgoing":
        identity = caller_field.replace("client:", "").strip()
        caller = client.emailid_from_identity(identity) if identity else ""
    else:
        attender = get_the_call_attender(get_twilio_number_owners(to_number), from_number)
        receiver = attender["name"] if attender else ""

    return {
        "type": direction,
        "status": call_status(params.get("CallStatus")),
        "id": params.get("CallSid"),
        "from": from_number,
        "to": to_number,
        "receiver": receiver,
        "caller": caller,
    }


def _user(email: str):
    if not email:
        return None
    from frappe_platform.models import User

    return User._default_manager.filter(pk=str(email).strip().lower()).first()


def create_call_log(details: dict):
    """`api.py:86-97` — through the shared path, so both providers agree."""
    if not details.get("id"):
        logger.warning("twilio payload with no CallSid; ignoring")
        return None

    log, created = call_log_path.record_call(
        call_id=str(details["id"]),
        medium=call_log_path.MEDIUM_TWILIO,
        call_type=details["type"],
        status=details["status"],
        from_number=details.get("from") or "",
        to_number=details.get("to") or "",
        caller=_user(details.get("caller")),
        receiver=_user(details.get("receiver")),
    )

    contact_number = details.get("from") if details["type"] == "Incoming" else details.get("to")
    if created and contact_number:
        call_log_path.resolve_and_link(log, contact_number)
    return log


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@whitelist("crm.integrations.twilio.api.generate_access_token")
def generate_access_token():
    """`api.py:34-50` — the token the browser SDK dials with."""
    from crm_app.models import CRMTelephonyAgent

    if not is_enabled():
        return {}

    user = get_current_user()
    from_number = (
        CRMTelephonyAgent._default_manager.filter(user_id=user)
        .values_list("twilio_number", flat=True)
        .first()
    )
    if not from_number:
        # Upstream's exact shape and wording - the frontend branches on `error`.
        return {
            "ok": False,
            "error": "caller_phone_identity_missing",
            "detail": "Phone number is not mapped to the caller",
        }

    return {"token": client.generate_voice_access_token(identity=user)}


def _callback_url(path: str) -> str:
    from django.conf import settings as django_settings

    base = (getattr(django_settings, "SITE_URL", "") or "").rstrip("/")
    return f"{base}{path}"


def recording_callback_url() -> str:
    return _callback_url("/api/method/crm.integrations.twilio.api.update_recording_info")


def status_callback_url() -> str:
    return _callback_url("/api/method/crm.integrations.twilio.api.update_call_status_info")


@whitelist("crm.integrations.twilio.api.voice", allow_guest=True)
def voice(_twilio_url: str = "", _twilio_signature: str | None = None, **kwargs):
    """`api.py:53-71` — outbound: the browser dials, Twilio asks us what to do.

    Returns TwiML. The transport wrapper is responsible for serving it as `text/xml`;
    returning the string keeps this testable without a request object.
    """
    from crm_app.models import CRMTelephonyAgent

    settings_row = validate_twilio_request(
        kwargs, url=_twilio_url, signature=_twilio_signature, require_application_sid=True
    )

    identity = str(kwargs.get("Caller") or "").replace("client:", "").strip()
    user = client.emailid_from_identity(identity)
    from_number = (
        CRMTelephonyAgent._default_manager.filter(user_id=user)
        .values_list("twilio_number", flat=True)
        .first()
        or ""
    )

    create_call_log(call_details(kwargs, call_from=from_number))

    return client.dial_number_response(
        caller_id=from_number,
        to_number=str(kwargs.get("To") or ""),
        record=bool(settings_row.record_calls),
        recording_callback=recording_callback_url(),
        status_callback=status_callback_url(),
    )


@whitelist("crm.integrations.twilio.api.twilio_incoming_call_handler", allow_guest=True)
def twilio_incoming_call_handler(_twilio_url: str = "", _twilio_signature: str | None = None, **kwargs):
    """`api.py:74-83` — inbound: someone dialled our Twilio number."""
    settings_row = validate_twilio_request(kwargs, url=_twilio_url, signature=_twilio_signature)

    create_call_log(call_details(kwargs))

    from_number = str(kwargs.get("From") or "")
    to_number = str(kwargs.get("To") or "")
    attender = get_the_call_attender(get_twilio_number_owners(to_number), from_number)

    if not attender:
        # `twilio_handler.py:144-146`, verbatim.
        return client.say_response(
            "Agent is unavailable to take the call, please call after some time."
        )

    if attender["call_receiving_device"] == "Phone":
        return client.dial_number_response(
            caller_id=from_number,
            to_number=attender["mobile_no"],
            record=bool(settings_row.record_calls),
            recording_callback=recording_callback_url(),
            status_callback=status_callback_url(),
        )

    return client.dial_client_response(
        client=client.safe_identity(attender["name"]),
        record=bool(settings_row.record_calls),
        recording_callback=recording_callback_url(),
        status_callback=status_callback_url(),
    )


def update_call_log(call_sid: str, status: str | None = None):
    """`api.py:113-133` — enrich a call log from Twilio's own record of the call."""
    from crm_app.models import CRMCallLog

    if not CRMCallLog._default_manager.filter(pk=call_sid).exists():
        return None

    info = client.fetch_call(call_sid)
    duration = info.get("duration")
    try:
        duration = int(duration) if duration not in (None, "") else None
    except (TypeError, ValueError):
        duration = None

    log, _ = call_log_path.record_call(
        call_id=call_sid,
        medium=call_log_path.MEDIUM_TWILIO,
        call_type="",
        status=call_status(status or info.get("status")),
        duration=duration,
        start_time=info.get("start_time") or None,
        end_time=info.get("end_time") or None,
    )
    return log


@whitelist("crm.integrations.twilio.api.update_recording_info", allow_guest=True)
def update_recording_info(_twilio_url: str = "", _twilio_signature: str | None = None, **kwargs):
    """`api.py:139-156`."""
    from crm_app.models import CRMCallLog

    validate_twilio_request(kwargs, url=_twilio_url, signature=_twilio_signature)

    call_sid = str(kwargs.get("CallSid") or "")
    log = update_call_log(call_sid)
    if not log:
        raise DoesNotExistError("Call log not found")

    CRMCallLog._default_manager.filter(pk=call_sid).update(
        recording_url=kwargs.get("RecordingUrl") or ""
    )
    return {"ok": True}


@whitelist("crm.integrations.twilio.api.update_call_status_info", allow_guest=True)
def update_call_status_info(_twilio_url: str = "", _twilio_signature: str | None = None, **kwargs):
    """`api.py:158-183`.

    Upstream also posts a `user_defined_message` back to Twilio so the browser SDK learns
    the status. That is left out — see the progress file — because it needs the
    parent-call websocket relay the SDK provides, and this port pushes status to the
    browser over its own Channels layer instead.
    """
    validate_twilio_request(kwargs, url=_twilio_url, signature=_twilio_signature)

    parent_sid = str(kwargs.get("ParentCallSid") or "")
    log = update_call_log(parent_sid, status=kwargs.get("CallStatus"))
    if not log:
        raise DoesNotExistError("Call log not found")

    from crm_app import realtime

    realtime.publish(
        "twilio_call_status",
        {
            "ParentCallSid": parent_sid,
            "CallSid": kwargs.get("CallSid"),
            "CallStatus": kwargs.get("CallStatus"),
            "CallDuration": kwargs.get("CallDuration"),
            "From": kwargs.get("From"),
            "To": kwargs.get("To"),
        },
    )
    return {"ok": True}
