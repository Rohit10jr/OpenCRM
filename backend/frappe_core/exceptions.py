"""Frappe-shaped exceptions and the error envelope the frontend already parses.

PHASE_0_FOUNDATION.md section 6c left the exact envelope open. It is settled here from
the consumers in the shipped frontend rather than guessed:

* ``src/data/document.js:40,43,61`` - ``err.exc_type`` compared against
  ``'DoesNotExistError'``, ``'PermissionError'``, ``'MandatoryError'``
* ``src/stores/users.js:34`` - ``'AuthenticationError'``
* ``src/data/document.js:41,46,62`` and ~20 other call sites - ``err.messages[0]``,
  and ``err.messages.map(...)`` so it must be a *list of plain strings*
* ``src/components/Settings/SettingsPage.vue:92`` - ``err.message`` as a separate scalar
* ``src/components/FilesUploader/FilesUploader.vue:215`` -
  ``JSON.parse(JSON.parse(error._server_messages)[0]).message``, which pins
  ``_server_messages`` as a JSON string containing JSON strings

``frappe-ui``'s request layer derives ``error.messages`` from ``_server_messages``, so
that field is the load-bearing one; ``exc_type`` drives the branching. Both are emitted.

``frappe.throw`` message text is preserved verbatim - it is user-facing copy
(CLAUDE.md hard rule 4).
"""

from __future__ import annotations

import json

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class FrappeError(Exception):
    """Base for every ported ``frappe.throw`` / ``frappe.exceptions.*``.

    ``exc_type`` is the bare class name, exactly as Frappe reports it.
    """

    http_status_code = 417  # Frappe's ValidationError default
    title = "Message"

    def __init__(self, message: str = "", title: str | None = None):
        self.message = message
        if title is not None:
            self.title = title
        super().__init__(message)

    @property
    def exc_type(self) -> str:
        return type(self).__name__


class ValidationError(FrappeError):
    http_status_code = 417


class PermissionError(FrappeError):  # noqa: A001 - shadows the builtin deliberately
    http_status_code = 403
    title = "Not Permitted"


class DoesNotExistError(FrappeError):
    http_status_code = 404
    title = "Not Found"


class MandatoryError(FrappeError):
    http_status_code = 417


class AuthenticationError(FrappeError):
    http_status_code = 401


class DuplicateEntryError(FrappeError):
    http_status_code = 409


def throw(message: str, exc: type[FrappeError] = ValidationError, title: str | None = None):
    """The port's ``frappe.throw``. Message text is preserved verbatim."""
    raise exc(message, title=title)


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


def build_server_messages(messages: list[str], title: str = "Message") -> str:
    """``_server_messages``: a JSON string whose items are themselves JSON strings."""
    return json.dumps([json.dumps({"message": m, "title": title}) for m in messages])


def build_error_body(
    exc_type: str, messages: list[str], title: str = "Message", exception: str | None = None
) -> dict:
    messages = [m for m in messages if m]
    if not messages:
        messages = ["Internal Server Error"]
    return {
        "exception": exception or f"frappe.exceptions.{exc_type}: {messages[0]}",
        "exc_type": exc_type,
        "_server_messages": build_server_messages(messages, title),
        # frappe-ui falls back to this when _server_messages is absent; emitting it
        # keeps err.message populated for SettingsPage.vue:92 and friends.
        "message": messages[0],
        "messages": messages,
    }


def _flatten_drf_detail(detail) -> list[str]:
    """DRF nests ValidationError details arbitrarily; the frontend wants flat strings."""
    if isinstance(detail, dict):
        out: list[str] = []
        for key, value in detail.items():
            for msg in _flatten_drf_detail(value):
                # Mirrors Frappe's MandatoryError text, which document.js:62 splits on
                # ': ' and takes the last segment as the field name.
                out.append(msg if key in ("non_field_errors", "detail") else f"{key}: {msg}")
        return out
    if isinstance(detail, (list, tuple)):
        return [m for item in detail for m in _flatten_drf_detail(item)]
    return [str(detail)]


def frappe_exception_handler(exc, context):
    """DRF ``EXCEPTION_HANDLER``. Renders every error in the Frappe envelope."""

    if isinstance(exc, FrappeError):
        body = build_error_body(exc.exc_type, [exc.message], exc.title)
        return Response(body, status=exc.http_status_code)

    if isinstance(exc, (Http404, ObjectDoesNotExist)):
        body = build_error_body("DoesNotExistError", [str(exc) or "Not found"], "Not Found")
        return Response(body, status=404)

    if isinstance(exc, DjangoValidationError):
        messages = list(exc.messages) if hasattr(exc, "messages") else [str(exc)]
        body = build_error_body("ValidationError", messages)
        return Response(body, status=417)

    if isinstance(exc, IntegrityError):
        body = build_error_body("DuplicateEntryError", [str(exc)], "Duplicate")
        return Response(body, status=409)

    if isinstance(exc, drf_exceptions.APIException):
        exc_type = {
            drf_exceptions.NotFound: "DoesNotExistError",
            drf_exceptions.PermissionDenied: "PermissionError",
            drf_exceptions.NotAuthenticated: "AuthenticationError",
            drf_exceptions.AuthenticationFailed: "AuthenticationError",
            drf_exceptions.ValidationError: "ValidationError",
        }.get(type(exc), type(exc).__name__)
        messages = _flatten_drf_detail(exc.detail)
        response = drf_exception_handler(exc, context)
        status_code = response.status_code if response is not None else exc.status_code
        body = build_error_body(exc_type, messages)
        result = Response(body, status=status_code)
        if response is not None and getattr(response, "_headers", None):
            for key, value in response.items():
                result[key] = value
        return result

    # Anything else is a genuine 500; let Django's handler log it.
    return None
