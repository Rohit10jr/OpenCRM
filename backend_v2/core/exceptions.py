"""Frappe-shaped exceptions and the error body consumed by the frontend."""

from __future__ import annotations

import json
import re

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError, RestrictedError
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response

from core.doctypes import doctype_of, is_child_table


class FrappeError(Exception):
    http_status_code = 417
    title = "Message"

    def __init__(
        self,
        message: str = "",
        title: str | None = None,
        *,
        messages: list[str] | None = None,
    ):
        self.messages = [item for item in (messages or []) if item] or [message]
        self.message = message or self.messages[0]
        if title is not None:
            self.title = title
        super().__init__(self.message)

    @property
    def exc_type(self) -> str:
        return type(self).__name__


class ValidationError(FrappeError):
    http_status_code = 417


class PermissionError(FrappeError):
    http_status_code = 403
    title = "Not Permitted"


class DoesNotExistError(FrappeError):
    http_status_code = 404
    title = "Not Found"


class MandatoryError(FrappeError):
    http_status_code = 417


class InvalidEmailAddressError(ValidationError):
    pass


class OutgoingEmailError(ValidationError):
    pass


class LinkValidationError(ValidationError):
    pass


class AuthenticationError(FrappeError):
    http_status_code = 401


class DuplicateEntryError(FrappeError):
    http_status_code = 409


class NameError(FrappeError):
    http_status_code = 409


class LinkExistsError(ValidationError):
    pass


class RateLimitExceededError(FrappeError):
    http_status_code = 429


class SecurityException(FrappeError):
    http_status_code = 403


class FilterError(ValueError):
    """A malformed or forbidden list filter, rendered as Invalid Filter."""


def throw(
    message: str,
    exc: type[FrappeError] = ValidationError,
    title: str | None = None,
):
    raise exc(message, title=title)


def build_server_messages(messages: list[str], title: str = "Message") -> str:
    return json.dumps(
        [json.dumps({"message": message, "title": title}) for message in messages]
    )


def build_error_body(
    exc_type: str,
    messages: list[str],
    title: str = "Message",
    exception: str | None = None,
) -> dict:
    messages = [message for message in messages if message]
    if not messages:
        messages = ["Internal Server Error"]
    return {
        "exception": exception
        or f"frappe.exceptions.{exc_type}: {messages[0]}",
        "exc_type": exc_type,
        "_server_messages": build_server_messages(messages, title),
        "message": messages[0],
        "messages": messages,
    }


def _flatten_drf_detail(detail) -> list[str]:
    if isinstance(detail, dict):
        messages: list[str] = []
        for key, value in detail.items():
            for message in _flatten_drf_detail(value):
                messages.append(
                    message
                    if key in ("non_field_errors", "detail")
                    else f"{key}: {message}"
                )
        return messages
    if isinstance(detail, (list, tuple)):
        return [
            message
            for item in detail
            for message in _flatten_drf_detail(item)
        ]
    return [str(detail)]


_DRF_EXC_TYPES: tuple[tuple[type, str, int | None], ...] = (
    (drf_exceptions.NotFound, "DoesNotExistError", None),
    (drf_exceptions.PermissionDenied, "PermissionError", None),
    (drf_exceptions.NotAuthenticated, "AuthenticationError", None),
    (drf_exceptions.AuthenticationFailed, "AuthenticationError", None),
    (drf_exceptions.ValidationError, "ValidationError", 417),
)


def _drf_exc_type(exc) -> tuple[str, int | None]:
    for exception_class, label, status in _DRF_EXC_TYPES:
        if isinstance(exc, exception_class):
            return label, status
    return type(exc).__name__, None


def _drf_messages(exc) -> list[str]:
    detail = exc.detail
    if isinstance(
        exc,
        (drf_exceptions.AuthenticationFailed, drf_exceptions.NotAuthenticated),
    ) and isinstance(detail, dict) and "detail" in detail:
        return [str(detail["detail"])]
    return _flatten_drf_detail(detail)


def _child_parent_name(row) -> str:
    parent = getattr(row, "parent", None)
    if isinstance(parent, str) and parent:
        return parent
    for field in type(row)._meta.fields:
        if field.name.startswith("parent") and field.is_relation:
            value = getattr(row, field.attname, None)
            if value:
                return str(value)
    return ""


def link_exists_error(exc: ProtectedError | RestrictedError) -> LinkExistsError:
    rows = (
        getattr(exc, "protected_objects", None)
        or getattr(exc, "restricted_objects", None)
        or ()
    )
    row = min(rows, key=lambda item: str(item.pk), default=None)
    if row is None:
        return LinkExistsError(str(exc))

    message = str(exc)
    match = re.search(r"model '([^']+)'", message)
    deleted_model_name = match.group(1) if match else ""
    named_fields = {
        field_name
        for model_name, field_name in re.findall(r"'(\w+)\.(\w+)'", message)
        if model_name == type(row).__name__
    }
    candidates = [
        field
        for field in type(row)._meta.fields
        if field.is_relation
        and field.related_model is not None
        and (
            not deleted_model_name
            or field.related_model.__name__ == deleted_model_name
        )
    ]
    field = next(
        (candidate for candidate in candidates if candidate.name in named_fields),
        None,
    )
    if field is None and candidates:
        field = candidates[0]

    doctype = name = ""
    if field is not None:
        doctype = doctype_of(field.related_model)
        name = str(getattr(row, field.attname, "") or "")

    reference_doctype = doctype_of(type(row))
    reference_name = str(row.pk)
    if is_child_table(type(row)):
        reference_doctype = str(
            getattr(row, "parenttype", "") or reference_doctype
        )
        reference_name = _child_parent_name(row) or reference_name

    return LinkExistsError(
        link_exists_message(
            doctype,
            name,
            reference_doctype,
            reference_name,
        )
    )


def link_exists_message(
    doctype: str,
    name: str,
    reference_doctype: str,
    reference_name: str,
    row: str = "",
) -> str:
    parts = (
        "Cannot delete or cancel because",
        doctype,
        name,
        "is linked with",
        reference_doctype,
        reference_name,
        row,
    )
    return " ".join(str(part) for part in parts if part)


def frappe_exception_handler(exc, context):
    if isinstance(exc, FrappeError):
        body = build_error_body(exc.exc_type, list(exc.messages), exc.title)
        return Response(body, status=exc.http_status_code)

    if isinstance(exc, (Http404, ObjectDoesNotExist)):
        body = build_error_body(
            "DoesNotExistError",
            [str(exc) or "Not found"],
            "Not Found",
        )
        return Response(body, status=404)

    if isinstance(exc, DjangoValidationError):
        messages = list(exc.messages) if hasattr(exc, "messages") else [str(exc)]
        return Response(
            build_error_body("ValidationError", messages),
            status=417,
        )

    if isinstance(exc, (ProtectedError, RestrictedError)):
        error = link_exists_error(exc)
        return Response(
            build_error_body(error.exc_type, [error.message], error.title),
            status=error.http_status_code,
        )

    if isinstance(exc, IntegrityError):
        return Response(
            build_error_body("DuplicateEntryError", [str(exc)], "Duplicate"),
            status=409,
        )

    if isinstance(exc, FilterError):
        return Response(
            build_error_body("ValidationError", [str(exc)], "Invalid Filter"),
            status=400,
        )

    if isinstance(exc, drf_exceptions.APIException):
        # Lazy to avoid settings loading the default permission while this module is
        # still defining the AuthenticationError that permission imports.
        from rest_framework.views import exception_handler as drf_exception_handler

        exc_type, status_override = _drf_exc_type(exc)
        response = drf_exception_handler(exc, context)
        status_code = status_override or (
            response.status_code if response is not None else exc.status_code
        )
        result = Response(
            build_error_body(exc_type, _drf_messages(exc)),
            status=status_code,
        )
        if response is not None:
            for key, value in response.items():
                result[key] = value
        return result

    return None
