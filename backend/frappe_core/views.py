"""The generic ``/api/resource/`` endpoint - PHASE_0_FOUNDATION.md section 6a.

One pair of views serves all 29 doctypes; a phase-1 agent adds a model, registers it,
and it is routable with no view code at all.

Child tables are deliberately not routable (PHASE_1_MODELS.md section 3) - they are
reached through their parent and serialised inline.
"""

from __future__ import annotations

import copy

from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from frappe_core import permissions, registry
from frappe_core.exceptions import DoesNotExistError, PermissionError as FrappePermissionError
from frappe_core.query import (
    coerce_offset,
    coerce_page_length,
    fetch_rows,
    parse_json_param,
    resolve_group_by,
)
from frappe_core.renderers import Envelope, FrappeEnvelopeRenderer
from frappe_core.session import (
    clear_request_cache,
    get_current_user,
    reset_current_user,
    set_current_user,
)


class FrappeAPIView(APIView):
    """Binds the authenticated user into the ambient session for the request.

    DRF authenticates inside ``initial()``, after middleware has run, so the contextvar
    has to be (re)bound here for ``@me`` resolution and ``owner`` stamping to see the
    JWT-authenticated user.
    """

    renderer_classes = [FrappeEnvelopeRenderer]
    envelope_key = "data"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        user = getattr(request, "user", None)
        name = user.pk if (user is not None and getattr(user, "is_authenticated", False)) else None
        self._session_token = set_current_user(name)
        # A fresh memo per request - a cached subtree must never outlive the request
        # that computed it, or a hierarchy change would not take effect until restart.
        clear_request_cache()

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        token = getattr(self, "_session_token", None)
        if token is not None:
            reset_current_user(token)
            self._session_token = None
        return response

    def envelope(self, payload, status_code=status.HTTP_200_OK) -> Response:
        return Response(Envelope(payload, self.envelope_key), status=status_code)


def _resolve_routable_entry(doctype: str):
    """Registry lookup that refuses child tables, unrouted doctypes and unknown ones."""
    if not registry.has_doctype(doctype):
        raise DoesNotExistError(f"DocType {doctype} not found")
    entry = registry.get_entry(doctype)
    if entry.is_child_table or not entry.routable:
        # Same error a client sees for a doctype that does not exist. A child table has
        # no standalone identity on the wire; an unrouted doctype has one but is
        # deliberately unpublished (specs/UNROUTED_DOCTYPES.md). Both are "no such route"
        # from outside, and saying so tells an unauthenticated prober nothing about
        # which doctypes exist.
        raise DoesNotExistError(f"DocType {doctype} not found")
    return entry


def _candidate_instance(entry, data):
    """An unsaved instance carrying the payload's own fields, for the ``create`` check.

    Relations are skipped deliberately: the payload holds raw keys (``"CRM-DEAL-0001"``),
    and assigning one to a FK descriptor raises. The fields that decide a create rule -
    ``reference_doctype``, ``attached_to_name`` and their kin - are plain columns, so
    excluding relations costs nothing and avoids a class of error entirely.

    Falls back to an empty instance if the payload will not construct one. A malformed
    body is the serializer's business to reject with a 400; failing here would answer a
    validation problem with a permission error.
    """
    model = entry.model
    plain = {
        field.name
        for field in model._meta.get_fields()
        if getattr(field, "concrete", False) and not field.is_relation
    }
    try:
        return model(**{k: v for k, v in (data or {}).items() if k in plain})
    except Exception:
        return model()


def check_destination(entry, instance, validated) -> None:
    """Re-check write permission against the document **as the payload would leave it**.

    ``_get_object`` checks the instance as it stands, which is the right question for most
    edits and the wrong one for a row that names its own parent. A comment on a deal you
    own passes that check; repointing it at a deal you cannot see then plants a comment
    there - the same hole `create` was just closed against, entered through `update`.

    **Opt-in, via `entry.reference_fields`.** Only doctypes that name their parent are
    re-checked; everything else returns immediately. Running this for every doctype would
    make every write in the product pay a second `has_permission` call - a real cost on
    the org-hierarchy rules, which query - to close a hole that exists in three places.
    """
    watched = set(entry.reference_fields)
    if not watched or not (watched & set(validated or {})):
        return

    plain = {
        field.name
        for field in entry.model._meta.get_fields()
        if getattr(field, "concrete", False) and not field.is_relation
    }
    changed = {
        name: value
        for name, value in validated.items()
        if name in plain and getattr(instance, name, None) != value
    }
    if not changed:
        return

    candidate = copy.copy(instance)
    for name, value in changed.items():
        setattr(candidate, name, value)

    if not permissions.check_object_permission(candidate, "write", get_current_user()):
        raise FrappePermissionError(
            f"Not permitted to move {entry.doctype} there", title="Not Permitted"
        )


class ResourceListView(FrappeAPIView):
    """``GET`` list and ``POST`` create for one doctype."""

    def get(self, request, doctype: str):
        entry = _resolve_routable_entry(doctype)
        params = request.query_params

        rows = fetch_rows(
            doctype,
            fields=parse_json_param(params.get("fields")),
            filters=parse_json_param(params.get("filters")),
            or_filters=parse_json_param(params.get("or_filters")),
            order_by=parse_json_param(params.get("order_by")),
            limit_start=coerce_offset(params.get("limit_start")),
            limit_page_length=coerce_page_length(params.get("limit_page_length")),
            user=get_current_user(),
        )
        # Validated for injection safety even though phase 0 does not aggregate on it;
        # phase 4's group_by view branch consumes the parsed value.
        resolve_group_by(entry.model, params.get("group_by"))
        return self.envelope(rows)

    def post(self, request, doctype: str):
        entry = _resolve_routable_entry(doctype)

        # Create is a permission decision too, and not always a permissive one. The
        # org-hierarchy rule returns True for `create` (an unsaved document always
        # passes), but CRM Notification's own rule returns *False* - a user may not mint
        # notifications for other people. Without this check that endpoint was open.
        #
        # The candidate carries the payload's own fields, so a rule can see *what is
        # being created*. This used to pass a bare `entry.model()` on the grounds that
        # "every registered rule decides `create` before it looks at any field" - true
        # when written, and false once `Comment`, `Communication` and `File` began
        # deferring to the document they reference. An empty shell has no reference, so
        # those rules waved every create through and a comment could be forged onto a
        # record the author cannot see.
        if not permissions.check_object_permission(
            _candidate_instance(entry, request.data), "create", get_current_user()
        ):
            raise FrappePermissionError(
                f"Not permitted to create {doctype}", title="Not Permitted"
            )

        serializer_class = entry.get_serializer_class()
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            instance = serializer.save()
        return self.envelope(serializer_class(instance).data, status.HTTP_201_CREATED)


class ResourceDetailView(FrappeAPIView):
    """``GET`` / ``PUT`` / ``DELETE`` for a single document."""

    def _get_object(self, doctype: str, name: str, ptype: str):
        entry = _resolve_routable_entry(doctype)
        try:
            instance = entry.model._default_manager.get(pk=name)
        except entry.model.DoesNotExist:
            raise DoesNotExistError(f"{doctype} {name} not found") from None

        if not permissions.check_object_permission(instance, ptype, get_current_user()):
            # Frappe's own wording for a denied document read.
            raise FrappePermissionError(
                f"No permission for {doctype} {name}", title="Not Permitted"
            )
        return entry, instance

    def get(self, request, doctype: str, name: str):
        entry, instance = self._get_object(doctype, name, "read")
        return self.envelope(entry.get_serializer_class()(instance).data)

    def put(self, request, doctype: str, name: str):
        entry, instance = self._get_object(doctype, name, "write")
        serializer_class = entry.get_serializer_class()
        serializer = serializer_class(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        check_destination(entry, instance, serializer.validated_data)
        with transaction.atomic():
            instance = serializer.save()
        return self.envelope(serializer_class(instance).data)

    def delete(self, request, doctype: str, name: str):
        _entry, instance = self._get_object(doctype, name, "delete")
        with transaction.atomic():
            instance.delete()
        return self.envelope(None)
