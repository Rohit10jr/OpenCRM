"""The response and error envelopes - PHASE_0_FOUNDATION.md section 6c.

Section 6c left the error shape open ("check ``frontend/src/`` error handling and match
it exactly"). It is pinned here against the real consumers in the shipped frontend, each
cited on the assertion it justifies.
"""

import json
from urllib.parse import quote

import pytest

from frappe_core.exceptions import (
    DoesNotExistError,
    MandatoryError,
    PermissionError as FrappePermissionError,
    ValidationError,
    build_error_body,
    throw,
)

pytestmark = pytest.mark.django_db

WIDGETS = "/api/resource/" + quote("Phase Zero Widget")


# --- success envelopes --------------------------------------------------------


def test_resource_list_is_wrapped_in_data(auth_api):
    assert set(auth_api.get(WIDGETS).json()) == {"data"}


def test_method_call_is_wrapped_in_message(auth_api):
    body = auth_api.get("/api/method/frappe.auth.get_logged_user").json()
    assert set(body) == {"message"}


# --- error envelope shape -----------------------------------------------------


def test_error_body_carries_exc_type(auth_api):
    """``src/data/document.js:40`` branches on ``err.exc_type``."""
    body = auth_api.get(f"{WIDGETS}/does-not-exist").json()
    assert body["exc_type"] == "DoesNotExistError"


def test_error_body_carries_a_messages_list_of_plain_strings(auth_api):
    """``document.js:41`` reads ``err.messages[0]``; ``:62`` calls ``.map()`` on it."""
    body = auth_api.get(f"{WIDGETS}/does-not-exist").json()
    assert isinstance(body["messages"], list)
    assert all(isinstance(m, str) for m in body["messages"])
    assert body["messages"][0]


def test_error_body_carries_a_scalar_message(auth_api):
    """``SettingsPage.vue:92`` prints ``err.message + ': ' + err.messages[0]``."""
    body = auth_api.get(f"{WIDGETS}/does-not-exist").json()
    assert isinstance(body["message"], str)


def test_server_messages_is_double_encoded(auth_api):
    """``FilesUploader.vue:216`` does ``JSON.parse(JSON.parse(_server_messages)[0]).message``.

    frappe-ui derives ``error.messages`` from this field, so its exact double-encoding
    is load-bearing rather than decorative.
    """
    body = auth_api.get(f"{WIDGETS}/does-not-exist").json()
    outer = json.loads(body["_server_messages"])
    assert isinstance(outer, list)
    inner = json.loads(outer[0])
    assert set(inner) >= {"message", "title"}
    assert inner["message"] == body["messages"][0]


def test_error_body_is_not_wrapped_in_an_envelope(auth_api):
    """The frontend reads exc_type off the top level, not out of ``data``/``message``."""
    body = auth_api.get(f"{WIDGETS}/does-not-exist").json()
    assert "data" not in body
    assert "exception" in body


def test_exception_string_matches_frappes_format(auth_api):
    body = auth_api.get(f"{WIDGETS}/does-not-exist").json()
    assert body["exception"].startswith("frappe.exceptions.DoesNotExistError: ")


# --- status codes -------------------------------------------------------------


@pytest.mark.parametrize(
    "exc,expected_status,expected_type",
    [
        (ValidationError, 417, "ValidationError"),
        (FrappePermissionError, 403, "PermissionError"),
        (DoesNotExistError, 404, "DoesNotExistError"),
        (MandatoryError, 417, "MandatoryError"),
    ],
)
def test_status_codes_match_frappe(exc, expected_status, expected_type):
    assert exc.http_status_code == expected_status
    assert exc("x").exc_type == expected_type


def test_unauthenticated_is_401_with_authentication_error(api):
    """``src/stores/users.js:34`` branches on ``'AuthenticationError'``."""
    response = api.get(WIDGETS)
    assert response.status_code == 401
    assert response.json()["exc_type"] == "AuthenticationError"


# --- message preservation -----------------------------------------------------


def test_throw_preserves_the_message_verbatim():
    """CLAUDE.md hard rule 4 - the text is user-facing copy."""
    message = "Organization is required to convert a Lead to a Deal"
    with pytest.raises(ValidationError) as caught:
        throw(message)
    assert caught.value.message == message
    assert build_error_body("ValidationError", [message])["messages"] == [message]


def test_thrown_message_survives_the_round_trip(auth_api):
    body = auth_api.get(f"{WIDGETS}/PZW-0000-00000").json()
    assert "PZW-0000-00000" in body["messages"][0]


def test_validation_errors_from_the_serializer_are_flattened(auth_api):
    """DRF nests field errors; the frontend wants ``['field: message', ...]``."""
    response = auth_api.post(
        "/api/resource/" + quote("Phase Zero Field"), {}, format="json"
    )
    assert response.status_code == 400
    body = response.json()
    assert body["exc_type"] == "ValidationError"
    assert any("organization_name" in m for m in body["messages"])


def test_empty_message_list_never_reaches_the_client():
    """frappe-ui shows ``messages[0]``; an empty list would render a blank toast."""
    body = build_error_body("ValidationError", [])
    assert body["messages"] == ["Internal Server Error"]
