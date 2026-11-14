import json

import pytest

from core.exceptions import (
    DoesNotExistError,
    MandatoryError,
    PermissionError,
    ValidationError,
    build_error_body,
    throw,
)


pytestmark = pytest.mark.django_db
WIDGETS = "/api/v1/test-widgets/"


def test_resource_list_uses_client_message_envelope(auth_api):
    assert set(auth_api.get(WIDGETS).json()) == {"message"}


def test_resource_error_shape_is_top_level_and_double_encoded(auth_api):
    body = auth_api.get(WIDGETS + "does-not-exist/").json()
    assert body["exc_type"] == "DoesNotExistError"
    assert isinstance(body["message"], str)
    assert isinstance(body["messages"], list)
    assert "data" not in body
    assert body["exception"].startswith("frappe.exceptions.DoesNotExistError: ")
    inner = json.loads(json.loads(body["_server_messages"])[0])
    assert inner["message"] == body["messages"][0]


@pytest.mark.parametrize(
    ("exception", "status_code"),
    [(ValidationError, 417), (PermissionError, 403), (DoesNotExistError, 404), (MandatoryError, 417)],
)
def test_status_codes_match_reference(exception, status_code):
    assert exception.http_status_code == status_code


def test_unauthenticated_is_authentication_error(api):
    response = api.get(WIDGETS)
    assert response.status_code == 401
    assert response.json()["exc_type"] == "AuthenticationError"


def test_validation_errors_are_flattened(auth_api):
    response = auth_api.post("/api/v1/test-fields/", {}, format="json")
    assert response.status_code == 417
    assert response.json()["exc_type"] == "ValidationError"
    assert any("title" in message for message in response.json()["messages"])


def test_throw_and_empty_messages_keep_load_bearing_shapes():
    message = "Organization is required to convert a Lead to a Deal"
    with pytest.raises(ValidationError, match=message):
        throw(message)
    assert build_error_body("ValidationError", [])["messages"] == ["Internal Server Error"]
