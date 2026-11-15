"""Base API views for endpoints and document resources."""

import copy

from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import mixins, viewsets
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from core.delete import check_dynamic_links
from core.doctypes import doctype_of
from core.exceptions import (
    DoesNotExistError,
    PermissionError,
    build_error_body,
)
from core.field_access import is_hidden
from core.inputs import build_payload
from core.query import by_name, fetch_rows, parse_json_param
from core.renderers import Envelope, WithResponseKeys
from core.translate import _


@csrf_exempt
def not_found(request, *args, **kwargs):
    """Return the settled Frappe body for a URL with no route."""

    return JsonResponse(
        build_error_body(
            "DoesNotExistError",
            ["Not found."],
            "Not Found",
        ),
        status=404,
    )


class BaseAPIView(APIView):
    """Use Frappe inputs and the method-path ``message`` success envelope."""

    envelope_key = "message"

    def get_inputs(self, request) -> dict:
        return build_payload(request)

    def envelope(self, payload, status_code=status.HTTP_200_OK) -> Response:
        extra = None
        if isinstance(payload, WithResponseKeys):
            extra = payload.keys
            payload = payload.message
        return Response(
            Envelope(payload, self.envelope_key, extra=extra),
            status=status_code,
        )

    def finalize_response(self, request, response, *args, **kwargs):
        if (
            isinstance(response, Response)
            and response.status_code < 400
            and not isinstance(response.data, Envelope)
        ):
            payload = response.data
            extra = None
            if isinstance(payload, WithResponseKeys):
                extra = payload.keys
                payload = payload.message
            response.data = Envelope(payload, self.envelope_key, extra=extra)
        return super().finalize_response(request, response, *args, **kwargs)


class DocumentViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """CRUD base with one field policy and one row policy for every door."""

    http_method_names = ("get", "post", "patch", "delete", "head", "options")
    lookup_value_regex = ".+?"
    readable_fields = ()
    filterable_fields = ()
    sortable_fields = ()
    searchable_fields = ()
    reference_fields = ()

    @staticmethod
    def list_rule(user) -> Q | None:
        return None

    @staticmethod
    def has_object_rule(user, document, ptype: str) -> bool | None:
        return None

    @property
    def document_model(self):
        return self.get_serializer_class().Meta.model

    @property
    def document_type(self):
        return doctype_of(self.document_model)

    def get_queryset(self):
        queryset = self.document_model.objects.all()
        rule = self.list_rule(self.request.user)
        return queryset.filter(rule) if rule is not None else queryset

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "user": self.request.user}

    def _candidate_instance(self, data):
        plain = {
            field.name
            for field in self.document_model._meta.get_fields()
            if getattr(field, "concrete", False) and not field.is_relation
        }
        try:
            return self.document_model(
                **{key: value for key, value in (data or {}).items() if key in plain}
            )
        except Exception:
            return self.document_model()

    def _object_by_name(self, ptype: str):
        name = self.kwargs[self.lookup_url_kwarg or self.lookup_field]
        document = by_name(self.document_model, name).first()
        if document is None:
            raise DoesNotExistError(
                _("{0} {1} not found").format(self.document_type, name)
            )
        if self.has_object_rule(self.request.user, document, ptype) is False:
            raise PermissionError(
                _("No permission for {0} {1}").format(self.document_type, name),
                title=_("Not Permitted"),
            )
        return document

    def get_object(self):
        return self._object_by_name("read")

    def _check_destination(self, user, document, validated_data):
        watched = set(self.reference_fields)
        if not watched.intersection(validated_data):
            return
        changed = {
            name: value
            for name, value in validated_data.items()
            if name in watched and getattr(document, name, None) != value
        }
        if not changed:
            return
        candidate = copy.copy(document)
        for name, value in changed.items():
            setattr(candidate, name, value)
        if self.has_object_rule(user, candidate, "write") is False:
            raise PermissionError(
                _("Not permitted to move {0} there").format(self.document_type),
                title=_("Not Permitted"),
            )

    def list(self, request, *args, **kwargs):
        params = request.query_params
        rows = fetch_rows(
            self.get_queryset(),
            user=request.user,
            fields=params.get("fields"),
            filters=params.get("filters"),
            or_filters=params.get("or_filters"),
            order_by=params.get("order_by"),
            group_by=params.get("group_by"),
            limit_start=params.get("limit_start"),
            limit_page_length=params.get("limit_page_length"),
            selectable=self.readable_fields,
            filterable=self.filterable_fields,
            sortable=self.sortable_fields,
        )
        return Response(Envelope(rows, "message"))

    @action(detail=False, methods=("get",), url_path="value")
    def value(self, request):
        fields = parse_json_param(request.query_params.get("fieldname"), None)
        if fields is None or isinstance(fields, str):
            fields = [fields or "name"]
        elif isinstance(fields, dict):
            fields = list(fields)
        fields = [str(field) for field in fields]

        filters = parse_json_param(request.query_params.get("filters"), None)
        if isinstance(filters, str):
            filters = {"name": filters}
        if not filters:
            filters = None

        rows = fetch_rows(
            self.get_queryset(),
            user=request.user,
            fields=fields,
            filters=filters,
            limit_page_length=1,
            selectable=self.readable_fields,
            filterable=self.filterable_fields,
            sortable=self.sortable_fields,
        )
        as_dict = request.query_params.get("as_dict", True)
        if str(as_dict).strip().lower() not in ("", "0", "false", "none", "null"):
            payload = rows[0] if rows else {}
        elif not rows:
            payload = None
        elif len(fields) > 1:
            payload = [rows[0].get(field) for field in fields]
        else:
            payload = rows[0].get(fields[0])
        return Response(Envelope(payload, "message"))

    @action(detail=True, methods=("get",), url_path="permissions")
    def permissions(self, request, *args, **kwargs):
        name = self.kwargs[self.lookup_url_kwarg or self.lookup_field]
        document = by_name(self.document_model, name).first()
        if document is None:
            payload = {"permissions": {}}
        else:
            payload = {
                "permissions": {
                    ptype: self.has_object_rule(request.user, document, ptype) is not False
                    for ptype in (
                        "read",
                        "write",
                        "delete",
                        "create",
                        "share",
                        "print",
                        "email",
                    )
                }
            }
        return Response(Envelope(payload, "message"))

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self._object_by_name("read"))
        return Response(Envelope(serializer.data, "message"))

    def create(self, request, *args, **kwargs):
        candidate = self._candidate_instance(request.data)
        if self.has_object_rule(request.user, candidate, "create") is False:
            raise PermissionError(
                _("Not permitted to create {0}").format(self.document_type),
                title=_("Not Permitted"),
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            document = serializer.save(user=request.user)
        output = self.get_serializer(document)
        return Response(Envelope(output.data, "message"), status=status.HTTP_200_OK)

    def partial_update(self, request, *args, **kwargs):
        document = self._object_by_name("write")
        serializer = self.get_serializer(document, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self._check_destination(request.user, document, serializer.validated_data)
        with transaction.atomic():
            document = serializer.save(user=request.user)
        return Response(Envelope(self.get_serializer(document).data, "message"))

    def update(self, request, *args, **kwargs):
        # Kept unreachable: PUT is intentionally absent from ``http_method_names``.
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        document = self._object_by_name("delete")
        with transaction.atomic():
            check_dynamic_links(document)
            document.delete()
        return Response(Envelope(None, "message"))


class SingletonViewSet(DocumentViewSet):
    """GET and PATCH one settings document at a URL without its name."""

    http_method_names = ("get", "patch", "head", "options")

    def _singleton(self, ptype: str):
        document = self.document_model._default_manager.filter(
            pk=self.document_model.singleton_name()
        ).first()
        if document is None:
            raise DoesNotExistError(
                _("{0} {1} not found").format(
                    self.document_type, self.document_model.singleton_name()
                )
            )
        if self.has_object_rule(self.request.user, document, ptype) is False:
            raise PermissionError(
                _("No permission for {0} {1}").format(
                    self.document_type, self.document_model.singleton_name()
                ),
                title=_("Not Permitted"),
            )
        return document

    def retrieve(self, request, *args, **kwargs):
        return Response(
            Envelope(self.get_serializer(self._singleton("read")).data, "message")
        )

    def partial_update(self, request, *args, **kwargs):
        document = self._singleton("write")
        serializer = self.get_serializer(document, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            document = serializer.save(user=request.user)
        return Response(Envelope(self.get_serializer(document).data, "message"))

    @action(detail=False, methods=("get",), url_path="value")
    def value(self, request):
        field = request.query_params.get("field")
        document = self.document_model._default_manager.filter(
            pk=self.document_model.singleton_name()
        ).first()
        if document is None:
            return Response(Envelope(None, "message"))
        if self.has_object_rule(request.user, document, "read") is False:
            raise PermissionError(
                _("Not permitted to read {0}").format(self.document_type)
            )
        if is_hidden(self.document_model, field, request.user):
            raise PermissionError(_("Field {0!r} is not readable").format(field))
        return Response(Envelope(getattr(document, field, None), "message"))
