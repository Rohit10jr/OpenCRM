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
import re

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError, RestrictedError
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

    def __init__(
        self, message: str = "", title: str | None = None, *, messages: list[str] | None = None
    ):
        # ``messages``: every sentence upstream would have ``msgprint``-ed before the
        # throw, when there is more than one - a document missing three mandatory
        # fields reports all three. ``message`` stays the first of them.
        self.messages = [m for m in (messages or []) if m] or [message]
        self.message = message or self.messages[0]
        if title is not None:
            self.title = title
        super().__init__(self.message)

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


class LinkValidationError(ValidationError):
    """``frappe.LinkValidationError``: a Link names a document that does not exist.
    ``document.py:_validate_links`` throws it as "Could not find <Label>: <name>", and
    for a child row "Could not find Row #<idx>: <Label>: <name>"."""


class AuthenticationError(FrappeError):
    http_status_code = 401


class DuplicateEntryError(FrappeError):
    http_status_code = 409


class NameError(FrappeError):  # noqa: A001 - shadows the builtin deliberately, as frappe.exceptions does
    """``frappe.NameError``: the document's name itself is unacceptable.

    Upstream declares it with 409 rather than ValidationError's 417
    (``frappe/exceptions.py:50``); ``validate_name`` throws it for a name containing
    ``<`` or ``>``, a name equal to the doctype, or the ``New <DocType>`` marker.
    """

    http_status_code = 409


class LinkExistsError(ValidationError):
    """``frappe.LinkExistsError``: the document is linked from another and cannot go.

    Upstream checks every Link field before deleting (``delete_doc.py:
    check_if_doc_is_linked``); the port's ``on_delete=PROTECT`` columns refuse at the
    database, and ``frappe_exception_handler`` renders that refusal as this.
    """


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


# Matched with ``isinstance``, most specific first. An exact-type map let SimpleJWT's
# ``InvalidToken``, a subclass of ``AuthenticationFailed``, fall through to its own class
# name, which ``frontend/src/stores/users.js`` does not branch on (FINDINGS.md 6). The
# serializer's ``ValidationError`` is Frappe's ``ValidationError`` and answers 417 like
# the port's own, not DRF's 400: upstream has one status for a validation failure, and
# the frontend should not see two for the same ``exc_type`` (FINDINGS.md 4).
_DRF_EXC_TYPES: tuple[tuple[type, str, int | None], ...] = (
    (drf_exceptions.NotFound, "DoesNotExistError", None),
    (drf_exceptions.PermissionDenied, "PermissionError", None),
    (drf_exceptions.NotAuthenticated, "AuthenticationError", None),
    (drf_exceptions.AuthenticationFailed, "AuthenticationError", None),
    (drf_exceptions.ValidationError, "ValidationError", 417),
)


def _drf_exc_type(exc) -> tuple[str, int | None]:
    """Frappe's label for a DRF exception, and the status to use instead of DRF's."""
    for klass, label, status in _DRF_EXC_TYPES:
        if isinstance(exc, klass):
            return label, status
    return type(exc).__name__, None


def _drf_messages(exc) -> list[str]:
    detail = exc.detail
    if isinstance(exc, (drf_exceptions.AuthenticationFailed, drf_exceptions.NotAuthenticated)):
        # SimpleJWT nests a per-token-class breakdown under ``messages``; the one
        # sentence under ``detail`` is what a person should see.
        if isinstance(detail, dict) and "detail" in detail:
            return [str(detail["detail"])]
    return _flatten_drf_detail(detail)


def _doctype_of(model) -> str:
    get_doctype = getattr(model, "get_doctype", None)
    return get_doctype() if callable(get_doctype) else model.__name__


def _is_child_table(model) -> bool:
    """The registry's flag, not the model's: ``register_doctype(..., is_child_table=True)``
    records it on the entry only, so ``model.is_child_table()`` answers False for a
    child table declared that way (every CRM child table is)."""
    # Lazy: registry is imported by models, which import this module.
    from frappe_core import registry

    try:
        return bool(registry.get_entry(_doctype_of(model)).is_child_table)
    except Exception:
        is_child = getattr(model, "is_child_table", None)
        return bool(is_child()) if callable(is_child) else False


def _child_parent_name(row) -> str:
    """The parent document's name for a child-table row, whatever the column is called:
    ``parent`` as a string in Frappe's shape, or a ``parent_<x>`` foreign key."""
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
    """Frappe's sentence for a delete refused by a Link, built from Django's refusal.

    ``delete_doc.py:raise_link_exists_exception`` names the document, the first document
    that references it and, when the reference sits in a child table, that row's parent
    and position. Django hands over the referencing rows; the deleted document is read
    back through the foreign key that protected it, which the exception's own message
    names by model class.
    """
    rows = (
        getattr(exc, "protected_objects", None)
        or getattr(exc, "restricted_objects", None)
        or ()
    )
    # Django hands the rows over as a set; pick by name so the sentence is the same on
    # every run, as upstream's is (the query's first row, ordered by the database).
    row = min(rows, key=lambda r: str(r.pk), default=None)
    if row is None:
        return LinkExistsError(str(exc))

    # Django's message names the deleted model ("model 'CRMIndustry'") and every
    # protecting field ("'CRMOrganization.industry'"). A row can hold two links to the
    # same doctype - ``owner`` and ``modified_by`` on every document - so the field is
    # taken from the message, not from the first foreign key pointing at the model.
    message = str(exc)
    match = re.search(r"model '([^']+)'", message)
    deleted_model_name = match.group(1) if match else ""
    named_fields = {
        fieldname
        for model_name, fieldname in re.findall(r"'(\w+)\.(\w+)'", message)
        if model_name == type(row).__name__
    }
    candidates = [
        field
        for field in type(row)._meta.fields
        if field.is_relation
        and field.related_model is not None
        and (not deleted_model_name or field.related_model.__name__ == deleted_model_name)
    ]
    field = next((f for f in candidates if f.name in named_fields), None)
    if field is None and candidates:
        field = candidates[0]
    doctype = name = ""
    if field is not None:
        doctype = _doctype_of(field.related_model)
        name = str(getattr(row, field.attname, "") or "")

    # A Link in a child table is reported as the parent document (delete_doc.py:
    # 318-341), with no row position: only the dynamic-link check adds "at Row", and
    # the port's foreign keys are all static Links.
    reference_doctype = _doctype_of(type(row))
    reference_name = str(row.pk)
    if _is_child_table(type(row)):
        reference_doctype = str(getattr(row, "parenttype", "") or reference_doctype)
        reference_name = _child_parent_name(row) or reference_name

    parts = (
        "Cannot delete or cancel because",
        doctype,
        name,
        "is linked with",
        reference_doctype,
        reference_name,
    )
    return LinkExistsError(" ".join(part for part in parts if part))


def frappe_exception_handler(exc, context):
    """DRF ``EXCEPTION_HANDLER``. Renders every error in the Frappe envelope."""

    if isinstance(exc, FrappeError):
        body = build_error_body(exc.exc_type, list(exc.messages), exc.title)
        return Response(body, status=exc.http_status_code)

    if isinstance(exc, (Http404, ObjectDoesNotExist)):
        body = build_error_body("DoesNotExistError", [str(exc) or "Not found"], "Not Found")
        return Response(body, status=404)

    if isinstance(exc, DjangoValidationError):
        messages = list(exc.messages) if hasattr(exc, "messages") else [str(exc)]
        body = build_error_body("ValidationError", messages)
        return Response(body, status=417)

    # Before IntegrityError: ProtectedError and RestrictedError subclass it, and a
    # refused delete is not a duplicate (FINDINGS.md 3).
    if isinstance(exc, (ProtectedError, RestrictedError)):
        error = link_exists_error(exc)
        body = build_error_body(error.exc_type, [error.message], error.title)
        return Response(body, status=error.http_status_code)

    if isinstance(exc, IntegrityError):
        body = build_error_body("DuplicateEntryError", [str(exc)], "Duplicate")
        return Response(body, status=409)

    # `FilterError` has promised a 400 in its own docstring since phase 0 and nothing
    # delivered one, so every malformed filter has been answering 500 - including, once
    # the field-security guard landed, a deliberate refusal to filter on a secret. A
    # security decision that presents as a crash reads as a bug to whoever is on call,
    # and tells the caller nothing about what to send instead.
    #
    # Imported here rather than at module scope: `filters` imports `field_security`,
    # which is imported by `serializers`, which imports this module.
    from frappe_core.filters import FilterError

    if isinstance(exc, FilterError):
        body = build_error_body("ValidationError", [str(exc)], "Invalid Filter")
        return Response(body, status=400)

    if isinstance(exc, drf_exceptions.APIException):
        exc_type, status_override = _drf_exc_type(exc)
        messages = _drf_messages(exc)
        response = drf_exception_handler(exc, context)
        status_code = status_override or (
            response.status_code if response is not None else exc.status_code
        )
        body = build_error_body(exc_type, messages)
        result = Response(body, status=status_code)
        # Retry-After on a 429, WWW-Authenticate on a 401: DRF's handler sets them on
        # its response, and they must ride along. (An earlier guard on a ``_headers``
        # attribute, gone from HttpResponse since Django 3.2, silently dropped them.)
        if response is not None:
            for key, value in response.items():
                result[key] = value
        return result

    # Anything else is a genuine 500; let Django's handler log it.
    return None
