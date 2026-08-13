"""The generic ``/api/resource/`` endpoint - PHASE_0_FOUNDATION.md section 6a.

One pair of views serves all 29 doctypes; a phase-1 agent adds a model, registers it,
and it is routable with no view code at all.

Child tables are deliberately not routable (PHASE_1_MODELS.md section 3) - they are
reached through their parent and serialised inline.
"""

from __future__ import annotations

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
    """Registry lookup that refuses child tables and unknown doctypes alike."""
    if not registry.has_doctype(doctype):
        raise DoesNotExistError(f"DocType {doctype} not found")
    entry = registry.get_entry(doctype)
    if entry.is_child_table:
        # Same error a client sees for a doctype that does not exist: a child table has
        # no standalone identity on the wire.
        raise DoesNotExistError(f"DocType {doctype} not found")
    return entry


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
        # An empty instance is enough: every registered rule decides `create` before it
        # looks at any field.
        if not permissions.check_object_permission(entry.model(), "create", get_current_user()):
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
        with transaction.atomic():
            instance = serializer.save()
        return self.envelope(serializer_class(instance).data)

    def delete(self, request, doctype: str, name: str):
        _entry, instance = self._get_object(doctype, name, "delete")
        with transaction.atomic():
            instance.delete()
        return self.envelope(None)
