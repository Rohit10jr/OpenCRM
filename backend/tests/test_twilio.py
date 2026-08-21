"""Twilio — signature verification, call routing, TwiML, call logs.

The signature tests are the centre of this file. Upstream authenticates its Twilio webhooks
by comparing the `AccountSid` in the payload — a value that is not secret and appears in
every request Twilio sends — so anyone who has seen one webhook can forge the rest. This
port verifies `X-Twilio-Signature` instead, and these tests are what keep that true.

No SDK and no live Twilio. The signature is computed here independently of the
implementation where it matters, so the test would catch the implementation agreeing with
itself.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from unittest.mock import patch

import pytest

from crm_app.integrations.twilio import client, handler
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

AUTH_TOKEN = "twilio-auth-token-abc"
ACCOUNT_SID = "AC-account-123"
TWIML_SID = "AP-app-456"
URL = "https://crm.example.com/api/method/crm.integrations.twilio.api.voice"


@pytest.fixture
def twilio_on(settings, administrator):
    from crm_app.models import CRMTwilioSettings

    settings.ENABLE_TWILIO = True
    settings.SITE_URL = "https://crm.example.com"
    with session_user(administrator.name):
        row = CRMTwilioSettings.load()
        row.enabled = True
        row.account_sid = ACCOUNT_SID
        row.api_key = "SK-key-789"
        row.api_secret = "api-secret-0123456789abcdef0123456789ab"
        row.auth_token = AUTH_TOKEN
        row.twiml_sid = TWIML_SID
        row.record_calls = True
        row.save()
    return row


def sign(url: str, params: dict, token: str = AUTH_TOKEN) -> str:
    """Twilio's scheme, computed here rather than by calling the implementation.

    Written out longhand on purpose: importing `client.expected_signature` would let the
    implementation agree with itself and prove nothing.
    """
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    return base64.b64encode(
        hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    ).decode()


def _params(**overrides):
    params = {
        "AccountSid": ACCOUNT_SID,
        "ApplicationSid": TWIML_SID,
        "CallSid": "CA-twilio-1",
        "CallStatus": "in-progress",
        "Caller": "client:alice(at)example.com",
        "From": "+911111111111",
        "To": "+919876543210",
    }
    params.update(overrides)
    return params


# ---------------------------------------------------------------------------
# Signature verification — what upstream does not do
# ---------------------------------------------------------------------------


def test_the_signature_matches_twilios_documented_scheme(twilio_on):
    params = _params()
    assert client.expected_signature(URL, params, AUTH_TOKEN) == sign(URL, params)


def test_parameters_are_sorted_before_signing(twilio_on):
    """The sort is the part that is easy to get wrong and impossible to notice: an
    unsorted concatenation makes every real webhook fail, and the symptom reads as a wrong
    auth token."""
    params = {"z": "1", "a": "2", "m": "3"}
    unsorted = URL + "".join(f"{k}{v}" for k, v in params.items())
    unsorted_sig = base64.b64encode(
        hmac.new(AUTH_TOKEN.encode(), unsorted.encode(), hashlib.sha1).digest()
    ).decode()

    assert client.expected_signature(URL, params, AUTH_TOKEN) == sign(URL, params)
    assert client.expected_signature(URL, params, AUTH_TOKEN) != unsorted_sig


def test_a_valid_signature_is_accepted(twilio_on):
    params = _params()
    assert client.validate_signature(URL, params, sign(URL, params), AUTH_TOKEN) is True


def test_a_missing_signature_is_refused(twilio_on):
    assert client.validate_signature(URL, _params(), None, AUTH_TOKEN) is False
    assert client.validate_signature(URL, _params(), "", AUTH_TOKEN) is False


def test_a_signature_from_a_different_token_is_refused(twilio_on):
    params = _params()
    forged = sign(URL, params, token="somebody-elses-token")
    assert client.validate_signature(URL, params, forged, AUTH_TOKEN) is False


def test_a_tampered_parameter_invalidates_the_signature(twilio_on):
    """The point of signing: a forwarded-but-edited webhook must not validate."""
    params = _params()
    signature = sign(URL, params)
    params["To"] = "+910000000000"
    assert client.validate_signature(URL, params, signature, AUTH_TOKEN) is False


def test_a_signature_for_a_different_url_is_refused(twilio_on):
    """The URL is part of the signed string, so a signature cannot be replayed onto another
    endpoint."""
    params = _params()
    signature = sign(URL, params)
    other = URL.replace("voice", "update_recording_info")
    assert client.validate_signature(other, params, signature, AUTH_TOKEN) is False


def test_the_comparison_is_constant_time(twilio_on):
    with patch("crm_app.integrations.twilio.client.hmac.compare_digest") as compare:
        compare.return_value = False
        client.validate_signature(URL, _params(), "guess", AUTH_TOKEN)
    assert compare.called


def test_a_correct_account_sid_alone_does_not_authenticate(twilio_on):
    """The upstream check, in isolation, and why it is not enough.

    An Account SID is in every webhook Twilio sends. Upstream accepts a request on the
    strength of it; here the request still needs a valid signature.
    """
    params = _params()
    with pytest.raises(FrappePermissionError):
        handler.validate_twilio_request(params, url=URL, signature=None)


def test_a_signed_request_from_another_account_is_refused(twilio_on):
    """The SID check is kept as well as the signature — it catches a correctly-signed
    request that belongs to a different Twilio account."""
    params = _params(AccountSid="AC-someone-else")
    with pytest.raises(FrappePermissionError) as excinfo:
        handler.validate_twilio_request(params, url=URL, signature=sign(URL, params))
    assert "Invalid Twilio account" in str(excinfo.value)


def test_the_application_sid_is_checked_when_required(twilio_on):
    params = _params(ApplicationSid="AP-wrong")
    with pytest.raises(FrappePermissionError) as excinfo:
        handler.validate_twilio_request(
            params, url=URL, signature=sign(URL, params), require_application_sid=True
        )
    assert "Invalid Twilio application" in str(excinfo.value)


def test_a_disabled_integration_refuses_webhooks(settings, twilio_on):
    settings.ENABLE_TWILIO = False
    params = _params()
    with pytest.raises(FrappePermissionError) as excinfo:
        handler.validate_twilio_request(params, url=URL, signature=sign(URL, params))
    assert "Twilio configuration is missing" in str(excinfo.value)


@pytest.mark.parametrize(
    "endpoint",
    [
        "voice",
        "twilio_incoming_call_handler",
        "update_recording_info",
        "update_call_status_info",
    ],
)
def test_every_webhook_endpoint_refuses_an_unsigned_request(twilio_on, endpoint):
    """Each of the four, through the endpoint rather than through the validator.

    Mutation-checked, and the first version was not enough: disabling the signature check
    in `validate_twilio_request` failed only the one isolation test, because every endpoint
    test passed a *valid* signature. An attacker does not. These are the tests that make
    removing the check fail loudly.
    """
    from crm_app.models import CRMCallLog

    params = _params(Caller="+919876543210")
    with pytest.raises(FrappePermissionError):
        getattr(handler, endpoint)(_twilio_url=URL, _twilio_signature=None, **params)

    assert not CRMCallLog.objects.filter(pk="CA-twilio-1").exists()


@pytest.mark.parametrize(
    "endpoint",
    [
        "voice",
        "twilio_incoming_call_handler",
        "update_recording_info",
        "update_call_status_info",
    ],
)
def test_every_webhook_endpoint_refuses_a_forged_signature(twilio_on, endpoint):
    params = _params(Caller="+919876543210")
    forged = sign(URL, params, token="attacker-guess")
    with pytest.raises(FrappePermissionError):
        getattr(handler, endpoint)(_twilio_url=URL, _twilio_signature=forged, **params)


@pytest.mark.parametrize(
    "path",
    [
        "crm.integrations.twilio.api.voice",
        "crm.integrations.twilio.api.twilio_incoming_call_handler",
        "crm.integrations.twilio.api.update_recording_info",
        "crm.integrations.twilio.api.update_call_status_info",
    ],
)
def test_the_webhooks_are_guest_accessible(path):
    from frappe_core.whitelist import get_method

    assert getattr(get_method(path), "__frappe_allow_guest__", False) is True


# ---------------------------------------------------------------------------
# Call logs
# ---------------------------------------------------------------------------


def test_an_inbound_call_is_logged(twilio_on):
    from crm_app.models import CRMCallLog

    params = _params(Caller="+919876543210", CallStatus="completed")
    handler.twilio_incoming_call_handler(
        _twilio_url=URL, _twilio_signature=sign(URL, params), **params
    )

    log = CRMCallLog.objects.get(pk="CA-twilio-1")
    assert log.telephony_medium == "Twilio"
    assert log.type == "Incoming"
    assert log.status == "Completed"


def test_the_call_log_shape_matches_exotels(twilio_on):
    """§4: *"Call logs land in `crm_call_log` identically for both providers."*

    Both providers go through `call_log.record_call`, so this is really asserting that
    neither adapter has grown its own write path.
    """
    from crm_app.integrations import call_log as path
    from crm_app.models import CRMCallLog

    params = _params(Caller="+919876543210", CallStatus="completed")
    handler.twilio_incoming_call_handler(
        _twilio_url=URL, _twilio_signature=sign(URL, params), **params
    )
    path.record_call(
        call_id="EX-1", medium=path.MEDIUM_EXOTEL, call_type="Incoming", status="Completed"
    )

    twilio_log = CRMCallLog.objects.get(pk="CA-twilio-1")
    exotel_log = CRMCallLog.objects.get(pk="EX-1")
    assert set(vars(twilio_log)) == set(vars(exotel_log))
    assert twilio_log.type == exotel_log.type == "Incoming"
    assert twilio_log.status == exotel_log.status == "Completed"


def test_a_redelivered_webhook_does_not_duplicate(twilio_on):
    from crm_app.models import CRMCallLog

    params = _params(Caller="+919876543210")
    for _ in range(2):
        handler.twilio_incoming_call_handler(
            _twilio_url=URL, _twilio_signature=sign(URL, params), **params
        )
    assert CRMCallLog.objects.filter(pk="CA-twilio-1").count() == 1


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("no-answer", "No Answer"),
        ("in-progress", "In Progress"),
        ("completed", "Completed"),
        ("busy", "Busy"),
        (None, ""),
    ],
)
def test_status_mapping(raw, expected):
    """`twilio_handler.py:238-242` — split on `-`, title-case. Note `busy` stays `Busy`
    here, unlike Exotel, because the mapping is mechanical rather than a lookup table."""
    assert handler.call_status(raw) == expected


# ---------------------------------------------------------------------------
# TwiML
# ---------------------------------------------------------------------------


def test_the_dial_response_is_well_formed_xml(twilio_on):
    from xml.etree import ElementTree

    xml = client.dial_number_response(
        caller_id="+911111111111",
        to_number="+919876543210",
        record=True,
        recording_callback="https://crm.example.com/rec",
        status_callback="https://crm.example.com/status",
    )
    root = ElementTree.fromstring(xml)
    assert root.tag == "Response"
    dial = root.find("Dial")
    assert dial.get("callerId") == "+911111111111"
    assert dial.find("Number").text == "+919876543210"


def test_twiml_escapes_attacker_controlled_values(twilio_on):
    """`caller_id` and `to_number` come from a webhook payload. An unescaped quote would
    let a caller inject TwiML verbs and redirect the call somewhere of their choosing."""
    from xml.etree import ElementTree

    hostile = '+91" evil="1'
    xml = client.dial_number_response(
        caller_id=hostile,
        to_number="<Hangup/>",
        record=False,
        recording_callback="https://crm.example.com/rec",
        status_callback="https://crm.example.com/status",
    )
    root = ElementTree.fromstring(xml)  # would raise if the injection broke the document
    dial = root.find("Dial")
    assert dial.get("evil") is None
    assert dial.get("callerId") == hostile
    assert dial.find("Number").text == "<Hangup/>"
    assert root.find(".//Hangup") is None


def test_recording_is_off_when_the_setting_is_off(twilio_on):
    xml = client.dial_number_response(
        caller_id="+91", to_number="+92", record=False,
        recording_callback="c", status_callback="s",
    )
    assert 'record="do-not-record"' in xml


def test_an_unavailable_agent_gets_the_upstream_message(twilio_on):
    params = _params(Caller="+919876543210", To="+910000000000")
    xml = handler.twilio_incoming_call_handler(
        _twilio_url=URL, _twilio_signature=sign(URL, params), **params
    )
    assert "Agent is unavailable to take the call" in xml


def test_a_phone_agent_is_dialled_by_number(twilio_on, alice, administrator):
    from crm_app.models import CRMTelephonyAgent

    with session_user(administrator.name):
        CRMTelephonyAgent.objects.create(
            user=alice,
            twilio_number="+919876543210",
            mobile_no="+911234567890",
            call_receiving_device="Phone",
        )

    params = _params(Caller="+911111111111", To="+919876543210")
    xml = handler.twilio_incoming_call_handler(
        _twilio_url=URL, _twilio_signature=sign(URL, params), **params
    )
    assert "<Number" in xml and "+911234567890" in xml


def test_a_computer_agent_is_dialled_as_a_client(twilio_on, alice, administrator):
    from crm_app.models import CRMTelephonyAgent

    with session_user(administrator.name):
        CRMTelephonyAgent.objects.create(
            user=alice, twilio_number="+919876543210", call_receiving_device="Computer"
        )

    params = _params(Caller="+911111111111", To="+919876543210")
    xml = handler.twilio_incoming_call_handler(
        _twilio_url=URL, _twilio_signature=sign(URL, params), **params
    )
    assert "<Client" in xml
    assert "alice(at)example.com" in xml, "the @ must be substituted (Twilio error 31105)"


# ---------------------------------------------------------------------------
# Identity and access token
# ---------------------------------------------------------------------------


def test_the_identity_round_trips():
    assert client.safe_identity("alice@example.com") == "alice(at)example.com"
    assert client.emailid_from_identity("alice(at)example.com") == "alice@example.com"


def test_the_access_token_is_a_jwt_twilio_will_accept(twilio_on, alice):
    import jwt

    with session_user(alice.name):
        token = client.generate_voice_access_token(alice.name)

    header = jwt.get_unverified_header(token)
    assert header["cty"] == "twilio-fpa;v=1"

    claims = jwt.decode(token, "api-secret-0123456789abcdef0123456789ab", algorithms=["HS256"])
    assert claims["iss"] == "SK-key-789"
    assert claims["sub"] == ACCOUNT_SID
    assert claims["grants"]["identity"] == "alice(at)example.com"
    assert claims["grants"]["voice"]["outgoing"]["application_sid"] == TWIML_SID


def test_the_token_is_signed_with_the_api_secret_not_the_auth_token(twilio_on, alice):
    """Twilio uses the API-key secret for access tokens and the account auth token for
    webhook signatures. Mixing them produces a token Twilio rejects with a generic error."""
    import jwt

    with session_user(alice.name):
        token = client.generate_voice_access_token(alice.name)

    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, AUTH_TOKEN, algorithms=["HS256"])


def test_an_agent_without_a_twilio_number_gets_upstreams_error_shape(twilio_on, alice):
    with session_user(alice.name):
        result = handler.generate_access_token()
    assert result["error"] == "caller_phone_identity_missing"


def test_a_disabled_integration_returns_an_empty_token(settings, twilio_on, alice):
    settings.ENABLE_TWILIO = False
    with session_user(alice.name):
        assert handler.generate_access_token() == {}


# ---------------------------------------------------------------------------
# Routing preference
# ---------------------------------------------------------------------------


def test_the_deal_owner_is_preferred_when_several_agents_share_a_number(
    twilio_on, alice, bob, administrator
):
    """`twilio_handler.py:199-206`. Upstream also narrows to whoever is logged in, which
    this port cannot do — see `get_the_call_attender`'s docstring."""
    from crm_app.models import CRMDeal, CRMDealStatus, CRMTelephonyAgent

    with session_user(administrator.name):
        for user in (alice, bob):
            CRMTelephonyAgent.objects.create(
                user=user,
                twilio_number="+919876543210",
                mobile_no=f"+9100000000{1 if user is alice else 2}",
                call_receiving_device="Phone",
            )
        status, _ = CRMDealStatus.objects.get_or_create(
            deal_status="Qualification", defaults={"type": "Open"}
        )
        CRMDeal.objects.create(deal_owner=bob, status=status, mobile_no="+911111111111")

    owners = handler.get_twilio_number_owners("+919876543210")
    attender = handler.get_the_call_attender(owners, "+911111111111")
    assert attender["name"] == bob.name


def test_no_owners_means_no_attender():
    assert handler.get_the_call_attender({}, "+911111111111") is None
