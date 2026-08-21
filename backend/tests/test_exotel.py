"""Exotel — webhook authentication, call logging, outbound calls.

No live Exotel. `RUNBOOK_PHASE_7.md`: *"Never wait on an external service… Stub at the
seam and test the control flow."* The seam here is `crm_app.integrations.http.request`, so
every outbound test replaces that one function and asserts on what would have been sent.

The webhook tests are the important ones. `handle_request` is `allow_guest=True` — an
unauthenticated write path reachable from the public internet — and Exotel does not sign
its requests, so a shared secret in the query string is the entire authentication.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from crm_app.integrations import call_log as call_log_path
from crm_app.integrations.exotel import client, handler
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

TOKEN = "s3cret-webhook-token"


@pytest.fixture
def exotel_on(settings, administrator):
    """Flag on, settings row configured. Both are needed — divergence #22."""
    from crm_app.models import CRMExotelSettings

    settings.ENABLE_EXOTEL = True
    with session_user(administrator.name):
        row = CRMExotelSettings.load()
        row.enabled = True
        row.account_sid = "acct-123"
        row.api_key = "key-123"
        row.api_token = "token-123"
        row.subdomain = "api.exotel.com"
        row.webhook_verify_token = TOKEN
        row.record_call = True
        row.save()
    return row


@pytest.fixture
def lead_status(administrator):
    from crm_app.models import CRMLeadStatus

    with session_user(administrator.name):
        status, _ = CRMLeadStatus.objects.get_or_create(
            lead_status="New", defaults={"type": "Open"}
        )
    return status


@pytest.fixture
def lead(alice, lead_status):
    from crm_app.models import CRMLead

    with session_user(alice.name):
        return CRMLead.objects.create(
            first_name="Ada", lead_owner=alice, mobile_no="+919876543210"
        )


def _incoming(**overrides):
    payload = {
        "key": TOKEN,
        "CallSid": "EX-call-1",
        "CallFrom": "+919876543210",
        "DialWhomNumber": "+911111111111",
        "To": "+912222222222",
        "Direction": "incoming",
        "CallType": "completed",
        "Status": "completed",
        "DialCallDuration": "42",
    }
    payload.update(overrides)
    return payload


class _Response:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


# ---------------------------------------------------------------------------
# validate_request — the whole of the webhook's authentication
# ---------------------------------------------------------------------------


def test_a_request_with_no_key_is_refused(exotel_on):
    with pytest.raises(FrappePermissionError):
        handler.validate_request(None)


def test_a_request_with_the_wrong_key_is_refused(exotel_on):
    with pytest.raises(FrappePermissionError):
        handler.validate_request("not-the-token")


def test_a_request_with_the_right_key_is_accepted(exotel_on):
    handler.validate_request(TOKEN)  # does not raise


def test_an_unset_token_refuses_everything(settings, administrator):
    """A deployment that enabled Exotel without setting a token must accept nothing.

    Upstream's ``key and key == token`` happens to do this too; making it explicit means
    the operator gets a log line naming the real problem instead of a silent 403.
    """
    from crm_app.models import CRMExotelSettings

    settings.ENABLE_EXOTEL = True
    with session_user(administrator.name):
        row = CRMExotelSettings.load()
        row.enabled = True
        row.webhook_verify_token = ""
        row.save()

    with pytest.raises(FrappePermissionError):
        handler.validate_request("")
    with pytest.raises(FrappePermissionError):
        handler.validate_request("anything")


def test_the_comparison_is_constant_time(exotel_on):
    """Upstream uses ``==``, which short-circuits on the first differing byte and leaks the
    token one byte at a time to anyone who can time the response.

    Timing cannot be asserted reliably in a test, so this asserts the *mechanism*: the
    function must reach `hmac.compare_digest`. A regression to `==` fails here.
    """
    with patch("crm_app.integrations.exotel.handler.hmac.compare_digest") as compare:
        compare.return_value = False
        with pytest.raises(FrappePermissionError):
            handler.validate_request("guess")
    assert compare.called, "validate_request must compare in constant time"


def test_the_webhook_authenticates_before_checking_whether_it_is_enabled(settings, administrator):
    """Order matters: validating second would let an unauthenticated caller learn whether
    this deployment has Exotel switched on."""
    from crm_app.models import CRMExotelSettings

    settings.ENABLE_EXOTEL = False
    with session_user(administrator.name):
        row = CRMExotelSettings.load()
        row.webhook_verify_token = TOKEN
        row.save()

    with pytest.raises(FrappePermissionError):
        handler.handle_request(**_incoming(key="wrong"))


def test_the_webhook_itself_refuses_a_forged_request(exotel_on):
    """The headline property, asserted through `handle_request` rather than
    `validate_request`.

    Mutation-checked: deleting the `validate_request(...)` line from `handle_request` must
    fail a test. Testing the validator in isolation does not cover that — the validator
    would still be correct and simply never called.
    """
    from crm_app.models import CRMCallLog

    with pytest.raises(FrappePermissionError):
        handler.handle_request(**_incoming(key="forged"))

    assert not CRMCallLog.objects.filter(pk="EX-call-1").exists()


def test_the_webhook_refuses_a_request_with_no_key_at_all(exotel_on):
    payload = _incoming()
    payload.pop("key")
    with pytest.raises(FrappePermissionError):
        handler.handle_request(**payload)


def test_the_endpoint_is_registered_as_guest_accessible():
    """Exotel is not a logged-in user. If this loses `allow_guest`, every webhook 401s and
    calls silently stop being logged."""
    from frappe_core.whitelist import get_method

    func = get_method("crm.integrations.exotel.handler.handle_request")
    assert getattr(func, "__frappe_allow_guest__", False) is True


# ---------------------------------------------------------------------------
# handle_request — logging the call
# ---------------------------------------------------------------------------


def test_an_incoming_call_is_logged(exotel_on):
    from crm_app.models import CRMCallLog

    result = handler.handle_request(**_incoming())

    assert result["ok"] is True
    log = CRMCallLog.objects.get(pk="EX-call-1")
    assert log.telephony_medium == "Exotel"
    assert log.type == "Incoming"
    assert log.status == "Completed"
    assert log.duration == 42
    assert getattr(log, "from") == "+919876543210"


def test_a_redelivered_webhook_does_not_duplicate(exotel_on):
    from crm_app.models import CRMCallLog

    handler.handle_request(**_incoming())
    handler.handle_request(**_incoming())

    assert CRMCallLog.objects.filter(pk="EX-call-1").count() == 1


def test_an_incoming_call_is_linked_to_the_lead_it_came_from(exotel_on, lead):
    from crm_app.models import CRMCallLog

    handler.handle_request(**_incoming())

    log = CRMCallLog.objects.get(pk="EX-call-1")
    assert log.reference_doctype == "CRM Lead"
    assert log.reference_docname == lead.pk


def test_a_free_status_is_acknowledged_without_logging(exotel_on):
    """`handler.py:42-44` — `free` is a keep-alive, not a call."""
    from crm_app.models import CRMCallLog

    result = handler.handle_request(**_incoming(Status="free"))

    assert result == {"ok": True, "skipped": "free"}
    assert not CRMCallLog.objects.filter(pk="EX-call-1").exists()


def test_the_disabled_integration_acknowledges_without_logging(settings, exotel_on):
    from crm_app.models import CRMCallLog

    settings.ENABLE_EXOTEL = False
    result = handler.handle_request(**_incoming())

    assert result["ok"] is False
    assert not CRMCallLog.objects.filter(pk="EX-call-1").exists()


def test_a_payload_with_no_call_id_does_not_raise(exotel_on):
    """Exotel retries a webhook that 500s. A malformed payload must not become a loop."""
    result = handler.handle_request(**_incoming(CallSid=""))
    assert result["ok"] is True
    assert result["call_log"] is None


def test_a_broken_payload_is_contained(exotel_on):
    """§3: a provider problem must never break CRUD."""
    with patch.object(handler, "_record", side_effect=RuntimeError("boom")):
        result = handler.handle_request(**_incoming())
    assert result == {"ok": False, "reason": "error"}


def test_the_key_is_not_stored_on_the_call_log(exotel_on):
    """The shared secret arrives as a query parameter; it must not end up in the payload
    that is broadcast or in anything persisted."""
    published = []
    with patch("crm_app.realtime.publish", lambda *a, **kw: published.append((a, kw)) or True):
        handler.handle_request(**_incoming())

    (event, payload), _ = published[0]
    assert event == "exotel_call"
    assert "key" not in payload


def test_the_call_event_is_broadcast_not_sent_to_one_user(exotel_on):
    """`handler.py:40` publishes with no user. `AS_BUILT.md` (phase 6): the argument order
    is `(event, message, user=...)`, so the payload is the *second* positional."""
    published = []
    with patch("crm_app.realtime.publish", lambda *a, **kw: published.append((a, kw)) or True):
        handler.handle_request(**_incoming())

    args, kwargs = published[0]
    assert args[0] == "exotel_call"
    assert isinstance(args[1], dict)
    assert kwargs.get("user") is None


# ---------------------------------------------------------------------------
# status mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"CallType": "completed"}, "Completed"),
        ({"CallType": "incomplete", "Status": "no-answer"}, "No Answer"),
        ({"CallType": "client-hangup", "Status": "canceled"}, "Canceled"),
        ({"CallType": "incomplete", "Status": "failed"}, "Failed"),
        ({"Status": "busy"}, "Ringing"),
    ],
)
def test_inbound_status_mapping(payload, expected):
    assert handler.get_call_log_status(payload) == expected


@pytest.mark.parametrize(
    "status,expected",
    [
        ("completed", "Completed"),
        ("in-progress", "In Progress"),
        ("busy", "Ringing"),
        ("no-answer", "No Answer"),
        ("failed", "Failed"),
    ],
)
def test_outbound_status_mapping(status, expected):
    assert handler.get_call_log_status({"Status": status}, "outbound-api") == expected


def test_busy_maps_to_ringing_deliberately():
    """It looks wrong and it is upstream's (`handler.py:232-233`, `:248-249`).

    The value is rendered in the activity timeline, so 'correcting' it would make this port
    disagree with upstream for the same call. `UPSTREAM_BUGS` #26.
    """
    assert handler.get_call_log_status({"Status": "busy"}) == "Ringing"
    assert handler.get_call_log_status({"Status": "busy"}, "outbound-api") == "Ringing"


# ---------------------------------------------------------------------------
# The client — credentials, timeouts, and what actually goes on the wire
# ---------------------------------------------------------------------------


def test_the_endpoint_url_carries_no_credentials(exotel_on):
    """Upstream embeds `api_key:api_token@` in the URL; a URL ends up in tracebacks and
    logs. Divergence #23."""
    url = client.endpoint("Calls/connect.json")
    assert "@" not in url
    assert "token-123" not in url
    assert url.startswith("https://api.exotel.com/v1/Accounts/acct-123/")


def test_the_token_is_sent_as_basic_auth(exotel_on):
    captured = {}

    def fake(method, url, **kwargs):
        captured.update(kwargs)
        captured["url"] = url
        return _Response({"Call": {"Sid": "EX-out-1", "From": "+91a", "To": "+91b"}})

    with patch.object(client.http, "request", fake):
        client.connect_call(
            from_number="+911", to_number="+912", caller_id="+913", record=False
        )

    assert captured["auth"] == ("key-123", "token-123")


def test_the_decrypted_token_is_used_not_the_ciphertext(exotel_on):
    """`ENCRYPTED_FIELDS` means the attribute holds ciphertext once saved. Sending that
    would fail as 'wrong credential' rather than as 'wrong read'."""
    key, token = client._credentials()
    assert token == "token-123"
    assert exotel_on.api_token != "token-123", "the stored attribute should be ciphertext"


def test_every_outbound_call_has_a_timeout(exotel_on):
    """§3, and `UPSTREAM_BUGS` #15. Upstream passes none at all."""
    captured = {}

    def fake(method, url, **kwargs):
        captured.update(kwargs)
        return _Response({"incoming_phone_numbers": []})

    with patch.object(client.http, "request", fake):
        client.get_all_exophones()

    # http.request applies the default; assert the default is real rather than None.
    from crm_app.integrations.http import DEFAULT_TIMEOUT

    assert DEFAULT_TIMEOUT is not None
    connect, read = DEFAULT_TIMEOUT
    assert connect > 0 and read > 0


def test_the_status_callback_url_carries_the_shared_secret(exotel_on):
    """It is what authenticates the webhook, so the URL itself is a credential."""
    url = client.status_callback_url()
    assert url.endswith(f"key={TOKEN}")
    assert "crm.integrations.exotel.handler.handle_request" in url


def test_an_unreachable_exotel_does_not_break_the_caller_id_check(exotel_on):
    """Returning [] turns an unreachable provider into a dialog rather than a 500."""
    with patch.object(client.http, "request", side_effect=RuntimeError("network")):
        assert client.get_all_exophones() == []


def test_a_rest_exception_is_surfaced_with_upstream_wording(exotel_on):
    from frappe_core.exceptions import ValidationError

    response = _Response({"RestException": {"Message": "Invalid caller id"}}, status_code=400)
    with patch.object(client.http, "request", return_value=response):
        with pytest.raises(ValidationError) as excinfo:
            client.connect_call(
                from_number="+911", to_number="+912", caller_id="+913", record=False
            )
    assert "Invalid caller id" in str(excinfo.value)


# ---------------------------------------------------------------------------
# make_a_call
# ---------------------------------------------------------------------------


def test_calling_with_the_integration_off_refuses_with_upstream_wording(settings, alice):
    from frappe_core.exceptions import ValidationError

    settings.ENABLE_EXOTEL = False
    with session_user(alice.name):
        with pytest.raises(ValidationError) as excinfo:
            handler.make_a_call("+919999999999")
    assert "Please setup Exotel intergration" in str(excinfo.value)


def test_an_agent_without_an_exotel_number_is_refused(exotel_on, alice):
    from frappe_core.exceptions import ValidationError

    with session_user(alice.name):
        with pytest.raises(ValidationError) as excinfo:
            handler.make_a_call("+919999999999")
    assert "Exotel Number set in your Telephony Agent" in str(excinfo.value)


def test_an_outbound_call_is_logged_against_the_caller(exotel_on, alice, administrator):
    from crm_app.models import CRMCallLog, CRMTelephonyAgent

    with session_user(administrator.name):
        CRMTelephonyAgent.objects.create(
            user=alice, mobile_no="+911111111111", exotel_number="+912222222222"
        )

    payload = {"Call": {"Sid": "EX-out-9", "From": "+911111111111", "To": "+919999999999"}}
    with patch.object(client, "get_all_exophones", return_value=["+912222222222"]):
        with patch.object(client.http, "request", return_value=_Response(payload)):
            with session_user(alice.name):
                result = handler.make_a_call("+919999999999")

    assert result["CallSid"] == "EX-out-9"
    log = CRMCallLog.objects.get(pk="EX-out-9")
    assert log.type == "Outgoing"
    assert log.caller_id == alice.name
    assert log.telephony_medium == "Exotel"


def test_an_invalid_caller_id_is_refused(exotel_on, alice, administrator):
    from crm_app.models import CRMTelephonyAgent
    from frappe_core.exceptions import ValidationError

    with session_user(administrator.name):
        CRMTelephonyAgent.objects.create(
            user=alice, mobile_no="+911111111111", exotel_number="+915555555555"
        )

    with patch.object(client, "get_all_exophones", return_value=["+912222222222"]):
        with session_user(alice.name):
            with pytest.raises(ValidationError) as excinfo:
                handler.make_a_call("+919999999999")
    assert "is not valid" in str(excinfo.value)
