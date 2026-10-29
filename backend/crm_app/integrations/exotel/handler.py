"""`crm.integrations.exotel.handler.*` — inbound webhook and outbound call.

Ports `crm/integrations/exotel/handler.py`.

## The webhook is an unauthenticated write path from the public internet

`handle_request` is `allow_guest=True` — it has to be, Exotel is calling it. Everything
that keeps it safe is in :func:`validate_request`, and the differences from upstream are
all in that one function; see its docstring.

## Status mapping

`get_call_log_status` is transcribed from `handler.py:224-250` including its oddities —
`busy` maps to ``Ringing``, not ``Busy``. That looks like a bug and is not worth
"fixing": the value is rendered in the activity timeline, so changing it would make this
port disagree with upstream for the same call. `UPSTREAM_BUGS` #26 records it.
"""

from __future__ import annotations

import hmac
import logging

from crm_app.integrations import call_log as call_log_path
from crm_app.integrations.exotel import client
from frappe_core.exceptions import PermissionError as FrappePermissionError, throw
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

logger = logging.getLogger(__name__)

#: `handler.py:224-250`, transcribed. The mapping is keyed on `(CallType, status)` where
#: upstream branches, and on `status` alone for the outbound directions.
_OUTBOUND_STATUS = {
    "completed": "Completed",
    "in-progress": "In Progress",
    "busy": "Ringing",
    "no-answer": "No Answer",
    "failed": "Failed",
}

_OUTBOUND_DIRECTIONS = ("outbound-api", "outbound-dial")


def get_exotel_settings():
    from crm_app.models import CRMExotelSettings

    return CRMExotelSettings.load()


@whitelist("crm.integrations.exotel.handler.is_integration_enabled")
def is_integration_enabled():
    """`handler.py:170-172`.

    An `and` of the deployment flag and the settings checkbox — divergence #22, the same
    shape `is_call_integration_enabled` uses.
    """
    from django.conf import settings

    if not getattr(settings, "ENABLE_EXOTEL", False):
        return False
    return bool(get_exotel_settings().enabled)


def validate_request(key: str | None) -> None:
    """`handler.py:161-168` — the whole of the webhook's authentication.

    Upstream's comment says it plainly: *"workaround security since exotel does not support
    request signature"*. A shared secret in the query string is what is available.

    **Three differences from upstream, all stricter, none observable to Exotel:**

    1. **Constant-time comparison.** Upstream uses ``key == webhook_verify_token``. String
       equality short-circuits on the first differing byte, so response time leaks a prefix
       and the token is recoverable byte by byte from outside. `hmac.compare_digest` does
       not. This is the same class of defect as the `like`-filter password recovery in
       `SECURITY_MODEL.md`, reached through timing instead of filters.
    2. **An unset token rejects everything.** Upstream's ``key and key == token`` already
       refuses an empty *key*, but a deployment that has enabled Exotel without setting a
       token would accept nothing anyway — this makes that explicit and logs it, rather
       than looking like an authentication failure.
    3. **The token is never logged**, and no part of it appears in the error.

    The error message is upstream's verbatim, because it is user-facing copy.

    **The token is `RESTRICTED_FIELDS`, not `ENCRYPTED_FIELDS`, and that is a real residual
    gap** — it sits in the column in plain text. It is not encrypted because the settings
    screen has to *show* it: an administrator copies it into Exotel's console, and an
    encrypted field reads back as ciphertext for want of a decrypt-on-read path for
    managers. Phase 4 chose `RESTRICTED` for that reason (`SECURITY_MODEL.md` divergence
    #9) and phase 7 has kept it rather than inventing the missing mechanism in passing.
    Recorded in the progress file as the item most worth a human's attention.
    """
    token = get_exotel_settings().webhook_verify_token

    if not token:
        logger.warning("exotel webhook rejected: no webhook_verify_token is configured")
        raise FrappePermissionError("Unauthorized request", title="Unauthorized")

    if not key or not hmac.compare_digest(str(key), str(token)):
        raise FrappePermissionError("Unauthorized request", title="Unauthorized")


def get_call_log_status(payload: dict, direction: str = "inbound") -> str:
    """`handler.py:224-250`, transcribed including the `busy` -> `Ringing` oddity."""
    if direction in _OUTBOUND_DIRECTIONS:
        mapped = _OUTBOUND_STATUS.get(payload.get("Status"))
        if mapped:
            return mapped

    call_type = payload.get("CallType")
    status = payload.get("DialCallStatus") or payload.get("Status")

    if call_type == "incomplete" and status == "no-answer":
        return "No Answer"
    if call_type == "client-hangup" and status == "canceled":
        return "Canceled"
    if call_type == "incomplete" and status == "failed":
        return "Failed"
    if call_type == "completed":
        return "Completed"
    if status == "busy":
        return "Ringing"
    return status or "Ringing"


def _agent_user(email: str | None):
    """Resolve an agent email to a User row, or None.

    Exotel sends `AgentEmail`; a value that does not match a user must not fail the
    webhook, because the call still happened and losing it is worse than losing the
    attribution.
    """
    if not email:
        return None
    from frappe_platform.models import User

    return User._default_manager.filter(pk=str(email).strip().lower()).first()


def _record(payload: dict, *, call_type: str, direction: str = "inbound"):
    """Create or update one call log from an Exotel payload.

    Both directions funnel through `call_log.record_call`, so the dedupe and the
    non-empty-overwrite rule apply identically — which is what `PHASE_7_INTEGRATIONS.md` §4
    means by "call logs land in `crm_call_log` identically for both providers".
    """
    call_id = payload.get("CallSid") or payload.get("Sid")
    if not call_id:
        logger.warning("exotel payload with no CallSid; ignoring")
        return None

    agent = _agent_user(payload.get("AgentEmail"))
    to_number = payload.get("DialWhomNumber") or payload.get("To") or ""
    from_number = payload.get("CallFrom") or payload.get("From") or ""

    duration = payload.get("DialCallDuration") or payload.get("ConversationDuration")
    try:
        duration = int(duration) if duration not in (None, "") else None
    except (TypeError, ValueError):
        duration = None

    log, created = call_log_path.record_call(
        call_id=str(call_id),
        medium=call_log_path.MEDIUM_EXOTEL,
        call_type=call_type,
        status=get_call_log_status(payload, direction),
        from_number=from_number,
        to_number=to_number,
        duration=duration,
        recording_url=payload.get("RecordingUrl") or "",
        start_time=payload.get("StartTime") or None,
        end_time=payload.get("EndTime") or None,
        receiver=agent if call_type == "Incoming" else None,
        caller=agent if call_type == "Outgoing" else None,
    )

    # `handler.py:207-209` — the number to resolve is the *other* party.
    contact_number = from_number if call_type == "Incoming" else to_number
    if created and contact_number:
        call_log_path.resolve_and_link(log, contact_number)

    return log


@whitelist("crm.integrations.exotel.handler.handle_request", allow_guest=True)
def handle_request(**kwargs):
    """`handler.py:19-64` — the inbound webhook.

    Order is load-bearing and is upstream's: **authenticate first**, then check the
    integration is on, then do work. Validating after the enabled-check would let a
    deployment with Exotel switched off be probed for whether it is switched off.

    Failures are contained. `PHASE_7_INTEGRATIONS.md` §3 requires that a provider problem
    never break CRUD, and a webhook that 500s is a webhook Exotel will retry — so a
    malformed payload is logged and acknowledged rather than raised.
    """
    from crm_app import realtime

    validate_request(kwargs.get("key"))

    if not is_integration_enabled():
        return {"ok": False, "reason": "integration disabled"}

    payload = {k: v for k, v in kwargs.items() if k != "key"}

    # `handler.py:40` — broadcast, no user. The frontend filters client-side.
    realtime.publish("exotel_call", payload)

    if payload.get("Status") == "free":
        return {"ok": True, "skipped": "free"}

    try:
        direction = payload.get("Direction") or "inbound"
        call_type = "Outgoing" if direction in _OUTBOUND_DIRECTIONS else "Incoming"
        log = _record(payload, call_type=call_type, direction=direction)
    except Exception:
        # Upstream logs and commits rather than re-raising, for the same reason.
        logger.exception("exotel: error while creating/updating call record")
        return {"ok": False, "reason": "error"}

    return {"ok": True, "call_log": getattr(log, "pk", None)}


@whitelist("crm.integrations.exotel.handler.make_a_call")
def make_a_call(to_number: str, from_number: str | None = None, caller_id: str | None = None):
    """`handler.py:68-129` — place an outbound call.

    Every `throw` message is upstream's verbatim; they are user-facing copy shown in a
    dialog.
    """
    from crm_app.models import CRMTelephonyAgent

    if not is_integration_enabled():
        throw("Please setup Exotel intergration", title="Integration Not Enabled")

    user = get_current_user()
    agent = CRMTelephonyAgent._default_manager.filter(user_id=user).first()

    if not from_number:
        from_number = getattr(agent, "mobile_no", "") or ""
    if not caller_id:
        caller_id = getattr(agent, "exotel_number", "") or ""

    if not caller_id:
        throw(
            "You do not have Exotel Number set in your Telephony Agent",
            title="Exotel Number Missing",
        )

    if caller_id not in client.get_all_exophones():
        throw(f"Exotel Number {caller_id} is not valid", title="Invalid Exotel Number")

    if not from_number:
        throw(
            "You do not have mobile number set in your Telephony Agent",
            title="Mobile Number Missing",
        )

    settings_row = get_exotel_settings()
    payload = client.connect_call(
        from_number=from_number,
        to_number=to_number,
        caller_id=caller_id,
        record=bool(settings_row.record_call),
    )

    call = payload.get("Call", {}) or {}
    if call.get("Sid"):
        _record(
            {**call, "CallSid": call.get("Sid"), "AgentEmail": user},
            call_type="Outgoing",
            direction="outbound-api",
        )

    # `handler.py:127-129` — the frontend reads `CallSid`, which Exotel calls `Sid`.
    call["CallSid"] = call.get("Sid", "")
    return call
