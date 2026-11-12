import json
from urllib.parse import urlencode

import pytest
from django.db import models
from django.db.models.deletion import ProtectedError
from django.test import override_settings
from django.urls import path
from rest_framework import exceptions as drf_exceptions
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIClient

from config import urls as config_urls
from core.doctypes import doctype_of, is_child_table
from core.exceptions import (
    AuthenticationError,
    DoesNotExistError,
    DuplicateEntryError,
    FrappeError,
    InvalidEmailAddressError,
    LinkExistsError,
    LinkValidationError,
    MandatoryError,
    OutgoingEmailError,
    RateLimitExceededError,
    SecurityException,
    ValidationError,
    build_error_body,
    frappe_exception_handler,
    throw,
)
from core.exceptions import NameError as FrappeNameError
from core.exceptions import PermissionError as FrappePermissionError
from core.inputs import bind_arguments
from core.renderers import WithResponseKeys
from core.views import FrappeAPIView

handler404 = config_urls.handler404


class OpenEchoView(FrappeAPIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        return Response(self.get_inputs(request))


class OpenPostOnlyView(FrappeAPIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        return Response("ok")


class ProtectedView(FrappeAPIView):
    def get(self, request):
        return Response("secret")


class ThrowingView(FrappeAPIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        throw("Organization is required to convert a Lead to a Deal")


class SiblingsView(FrappeAPIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response(
            WithResponseKeys(
                None,
                docs=[{"name": "CRM Lead"}],
                user_settings={"compact": True},
            )
        )


urlpatterns = [
    path("echo/", OpenEchoView.as_view()),
    path("post-only/", OpenPostOnlyView.as_view()),
    path("protected/", ProtectedView.as_view()),
    path("throw/", ThrowingView.as_view()),
    path("siblings/", SiblingsView.as_view()),
]


class ProtectedTarget(models.Model):
    DOCTYPE = "Protected Target"
    name = models.CharField(primary_key=True, max_length=100)

    class Meta:
        app_label = "core"


class ProtectingDocument(models.Model):
    DOCTYPE = "Protecting Document"
    name = models.CharField(primary_key=True, max_length=100)
    target = models.ForeignKey(ProtectedTarget, on_delete=models.PROTECT)

    class Meta:
        app_label = "core"


@pytest.fixture
def api():
    return APIClient()


@override_settings(ROOT_URLCONF=__name__)
def test_input_parsing_merges_query_and_json_body_with_body_winning(api):
    query = urlencode(
        {
            "shared": '"from query"',
            "decoded": '["Open", "Lost"]',
            "order_by": "modified desc",
            "cmd": "legacy.method",
        }
    )
    response = api.post(
        f"/echo/?{query}",
        {"shared": "from body", "native": [1, 2]},
        format="json",
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": {
            "shared": "from body",
            "decoded": ["Open", "Lost"],
            "order_by": "modified desc",
            "native": [1, 2],
        }
    }


@override_settings(ROOT_URLCONF=__name__)
def test_form_body_reads_one_value_per_key(api):
    response = api.post(
        "/echo/",
        {"one": "value", "repeated": ["first", "second"]},
        format="multipart",
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": {"one": "value", "repeated": "second"}
    }


def test_surplus_inputs_are_dropped_unless_kwargs_are_accepted():
    def fixed(known):
        return known

    def open_ended(known, **kwargs):
        return known, kwargs

    payload = {"known": 1, "surplus": 2}
    assert bind_arguments(fixed, payload) == {"known": 1}
    assert bind_arguments(open_ended, payload) == payload


@override_settings(ROOT_URLCONF=__name__)
def test_with_response_keys_are_siblings_beside_message(api):
    response = api.get("/siblings/")

    assert response.status_code == 200
    assert response.json() == {
        "message": None,
        "docs": [{"name": "CRM Lead"}],
        "user_settings": {"compact": True},
    }


@override_settings(ROOT_URLCONF=__name__)
def test_non_guest_view_without_a_user_is_not_permitted(api):
    response = api.get("/protected/")

    assert response.status_code == 401
    assert response.json()["exc_type"] == "AuthenticationError"
    assert response.json()["message"] == "Not permitted"


@override_settings(ROOT_URLCONF=__name__)
def test_disallowed_method_is_405_with_allow_header(api):
    response = api.get("/post-only/")

    assert response.status_code == 405
    assert response["Allow"] == "POST, OPTIONS"
    assert response.json()["exc_type"] == "MethodNotAllowed"
    assert response.json()["message"] == 'Method "GET" not allowed.'


@pytest.mark.parametrize("debug", [True, False])
@pytest.mark.parametrize("url", ["/api/v1/no-such-route/", "/no-such-route/"])
def test_unknown_url_is_frappe_404_everywhere(api, settings, debug, url):
    settings.DEBUG = debug
    response = api.get(url)

    assert response.status_code == 404
    assert response.json() == build_error_body(
        "DoesNotExistError", ["Not found."], "Not Found"
    )


@pytest.mark.parametrize("debug", [True, False])
def test_unknown_admin_url_keeps_djangos_response(api, settings, debug):
    settings.DEBUG = debug
    response = api.get("/admin/no-such-route/")

    assert response.headers["Content-Type"].split(";", 1)[0] != "application/json"
    assert response.content != json.dumps(
        build_error_body("DoesNotExistError", ["Not found."], "Not Found")
    ).encode()


def test_error_body_carries_exc_type_messages_and_scalar_message():
    body = build_error_body("DoesNotExistError", ["CRM Lead missing not found"])

    assert body["exc_type"] == "DoesNotExistError"
    assert body["messages"] == ["CRM Lead missing not found"]
    assert all(isinstance(message, str) for message in body["messages"])
    assert body["message"] == "CRM Lead missing not found"


def test_server_messages_is_double_encoded():
    body = build_error_body("ValidationError", ["first", "second"])
    outer = json.loads(body["_server_messages"])

    assert isinstance(outer, list)
    assert json.loads(outer[0]) == {"message": "first", "title": "Message"}


def test_exception_string_matches_frappes_format():
    body = build_error_body("DoesNotExistError", ["not found"])
    assert body["exception"] == "frappe.exceptions.DoesNotExistError: not found"


def test_error_body_is_not_wrapped_by_the_renderer(api):
    response = frappe_exception_handler(DoesNotExistError("missing"), {})
    response.accepted_renderer = __import__(
        "core.renderers", fromlist=["FrappeEnvelopeRenderer"]
    ).FrappeEnvelopeRenderer()
    response.accepted_media_type = "application/json"
    response.renderer_context = {}

    assert json.loads(response.rendered_content) == response.data
    assert "message" in response.data
    assert "data" not in response.data


@pytest.mark.parametrize(
    "exception_class,status_code,exc_type,title",
    [
        (ValidationError, 417, "ValidationError", "Message"),
        (FrappePermissionError, 403, "PermissionError", "Not Permitted"),
        (DoesNotExistError, 404, "DoesNotExistError", "Not Found"),
        (MandatoryError, 417, "MandatoryError", "Message"),
        (InvalidEmailAddressError, 417, "InvalidEmailAddressError", "Message"),
        (OutgoingEmailError, 417, "OutgoingEmailError", "Message"),
        (LinkValidationError, 417, "LinkValidationError", "Message"),
        (AuthenticationError, 401, "AuthenticationError", "Message"),
        (DuplicateEntryError, 409, "DuplicateEntryError", "Message"),
        (FrappeNameError, 409, "NameError", "Message"),
        (LinkExistsError, 417, "LinkExistsError", "Message"),
        (RateLimitExceededError, 429, "RateLimitExceededError", "Message"),
        (SecurityException, 403, "SecurityException", "Message"),
    ],
)
def test_status_codes_match_frappe(
    exception_class, status_code, exc_type, title
):
    error = exception_class("x")
    assert error.http_status_code == status_code
    assert error.exc_type == exc_type
    assert error.title == title


def test_throw_preserves_the_message_verbatim():
    message = "Organization is required to convert a Lead to a Deal"
    with pytest.raises(ValidationError) as caught:
        throw(message)
    assert caught.value.message == message
    assert build_error_body("ValidationError", [message])["messages"] == [message]


@override_settings(ROOT_URLCONF=__name__)
def test_thrown_message_survives_the_round_trip(api):
    response = api.get("/throw/")

    assert response.status_code == 417
    assert response.json()["message"] == (
        "Organization is required to convert a Lead to a Deal"
    )


def test_validation_errors_from_a_serializer_are_flattened():
    error = drf_exceptions.ValidationError(
        {
            "organization_name": ["This field is required."],
            "non_field_errors": ["Combination is invalid."],
        }
    )
    response = frappe_exception_handler(error, {})

    assert response.status_code == 417
    assert response.data["exc_type"] == "ValidationError"
    assert response.data["messages"] == [
        "organization_name: This field is required.",
        "Combination is invalid.",
    ]


def test_empty_message_list_never_reaches_the_client():
    assert build_error_body("ValidationError", [])["messages"] == [
        "Internal Server Error"
    ]


def test_drf_response_headers_survive_the_envelope():
    response = frappe_exception_handler(drf_exceptions.Throttled(wait=7), {})

    assert response.status_code == 429
    assert response["Retry-After"] == "7"


def test_protected_error_is_mapped_before_integrity_error():
    target = ProtectedTarget(name="target-1")
    source = ProtectingDocument(name="source-1", target=target)
    refusal = ProtectedError(
        "Cannot delete some instances of model 'ProtectedTarget' because they are "
        "referenced through protected foreign keys: "
        "'ProtectingDocument.target'.",
        {source},
    )

    response = frappe_exception_handler(refusal, {})

    assert response.status_code == 417
    assert response.data["exc_type"] == "LinkExistsError"
    assert response.data["message"] == (
        "Cannot delete or cancel because Protected Target target-1 "
        "is linked with Protecting Document source-1"
    )


def test_doctype_metadata_uses_class_attributes_with_settled_defaults():
    class PlainModel:
        pass

    class ChildModel:
        DOCTYPE = "Child Row"
        IS_CHILD_TABLE = True

    assert doctype_of(PlainModel) == "PlainModel"
    assert not is_child_table(PlainModel)
    assert doctype_of(ChildModel) == "Child Row"
    assert is_child_table(ChildModel)


def test_frappe_error_keeps_multiple_messages_and_first_scalar():
    error = FrappeError("first", messages=["first", "second"])
    response = frappe_exception_handler(error, {})

    assert response.data["message"] == "first"
    assert response.data["messages"] == ["first", "second"]
