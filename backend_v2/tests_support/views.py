"""Document resources exposed only by the test URL configuration."""

from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.response import Response

from core.renderers import Envelope
from core.views import DocumentViewSet
from tests_support.serializers import (
    AutoIncrementDocumentSerializer,
    FieldDocumentSerializer,
    PromptDocumentSerializer,
    SecuredDocumentSerializer,
    WidgetSerializer,
)


class WidgetViewSet(DocumentViewSet):
    serializer_class = WidgetSerializer
    readable_fields = WidgetSerializer.Meta.fields
    filterable_fields = (
        "name",
        "widget_name",
        "status",
        "amount",
        "quantity",
        "widget_owner",
        "_assign",
    )
    sortable_fields = ("name", "widget_name", "status", "modified")
    searchable_fields = ("widget_name", "notes")
    reference_fields = ("status",)

    def list_rule(self, user):
        return Q(widget_owner=user) | Q(widget_owner__isnull=True)

    def has_object_rule(self, user, document, ptype):
        if ptype == "create":
            return document.status != "Forbidden"
        if ptype == "read":
            return document.status != "Private"
        if ptype == "write":
            return document.status != "Locked"
        return None


class FieldDocumentViewSet(DocumentViewSet):
    serializer_class = FieldDocumentSerializer
    readable_fields = FieldDocumentSerializer.Meta.fields
    filterable_fields = ("name", "title")
    sortable_fields = ("name", "title", "modified")
    searchable_fields = ("title",)

    @action(detail=False, methods=("get",), url_path="search")
    def search(self, request):
        return Response(Envelope([], "message"))

    @action(detail=True, methods=("post",), url_path="convert")
    def convert(self, request, pk=None):
        return Response(Envelope(self.get_object().pk, "message"))


class SecuredDocumentViewSet(DocumentViewSet):
    serializer_class = SecuredDocumentSerializer
    readable_fields = SecuredDocumentSerializer.Meta.fields
    filterable_fields = ("name", "manager_note", "audit_value", "manager_value")
    sortable_fields = ("name", "modified")
    searchable_fields = ()


class PromptDocumentViewSet(DocumentViewSet):
    serializer_class = PromptDocumentSerializer
    readable_fields = PromptDocumentSerializer.Meta.fields
    filterable_fields = ("name", "label")
    sortable_fields = ("name", "label", "modified")


class AutoIncrementDocumentViewSet(DocumentViewSet):
    serializer_class = AutoIncrementDocumentSerializer
    readable_fields = AutoIncrementDocumentSerializer.Meta.fields
    filterable_fields = ("name", "label")
    sortable_fields = ("name", "label", "modified")
