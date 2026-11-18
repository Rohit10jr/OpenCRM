"""Document resources exposed only by the test URL configuration."""

from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.response import Response

from core.access import Access
from core.mixins import (
    BulkDeleteMixin,
    BulkUpdateMixin,
    LinkedDocumentsMixin,
    LinkSearchMixin,
    ListExportMixin,
    RenameMixin,
)
from core.renderers import Envelope
from core.views import DocumentViewSet, SingletonViewSet
from tests_support.export import placeholder_export_field_info
from tests_support.list_views import WidgetListView
from tests_support.serializers import (
    AutoIncrementDocumentSerializer,
    DynamicReferenceSerializer,
    FieldDocumentSerializer,
    PointingDocumentSerializer,
    PromptDocumentSerializer,
    SearchableDocumentSerializer,
    SecuredDocumentSerializer,
    SingletonDocumentSerializer,
    WidgetSerializer,
)


class WidgetViewSet(
    BulkDeleteMixin,
    BulkUpdateMixin,
    LinkedDocumentsMixin,
    LinkSearchMixin,
    ListExportMixin,
    RenameMixin,
    DocumentViewSet,
):
    export_field_info = staticmethod(placeholder_export_field_info)
    list_view_class = WidgetListView
    access = Access.ruled()
    serializer_class = WidgetSerializer
    readable_fields = WidgetSerializer.Meta.fields
    filterable_fields = (
        "name",
        "widget_name",
        "status",
        "amount",
        "quantity",
        "notes",
        "widget_owner",
        "_assign",
    )
    sortable_fields = ("name", "widget_name", "status", "modified")
    searchable_fields = ("widget_name", "notes")
    reference_fields = ("status",)

    @staticmethod
    def list_rule(user):
        return Q(widget_owner=user) | Q(widget_owner__isnull=True)

    @staticmethod
    def has_object_rule(user, document, ptype):
        if ptype == "create":
            return document.status != "Forbidden"
        if ptype == "read":
            return document.status != "Private"
        if ptype == "write":
            return document.status != "Locked"
        return None


class SearchableDocumentViewSet(LinkSearchMixin, DocumentViewSet):
    access = Access.open(
        reason="A disabled-row search fixture with no confidential or protected data."
    )
    serializer_class = SearchableDocumentSerializer
    readable_fields = SearchableDocumentSerializer.Meta.fields
    filterable_fields = ("name", "title", "disabled")
    sortable_fields = ("name", "title", "modified")
    searchable_fields = ("title",)


class PointingDocumentViewSet(DocumentViewSet):
    access = Access.ruled()
    serializer_class = PointingDocumentSerializer
    readable_fields = PointingDocumentSerializer.Meta.fields
    filterable_fields = ("name", "widget", "widget_status")
    sortable_fields = ("name", "modified")

    @staticmethod
    def list_rule(user):
        return Q(owner=user)

    @staticmethod
    def has_object_rule(user, document, ptype):
        return document.owner_id == user.pk


class DynamicReferenceViewSet(DocumentViewSet):
    access = Access.ruled()
    serializer_class = DynamicReferenceSerializer
    readable_fields = DynamicReferenceSerializer.Meta.fields
    filterable_fields = ("name", "reference_doctype", "reference_name")
    sortable_fields = ("name", "modified")

    @staticmethod
    def list_rule(user):
        return Q(owner=user)

    @staticmethod
    def has_object_rule(user, document, ptype):
        return document.owner_id == user.pk


class FieldDocumentViewSet(DocumentViewSet):
    access = Access.open(
        reason="A field-naming fixture with no confidential rows or protected fields."
    )
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


class SecuredDocumentViewSet(ListExportMixin, DocumentViewSet):
    export_field_info = staticmethod(placeholder_export_field_info)
    access = Access.ruled()
    serializer_class = SecuredDocumentSerializer
    readable_fields = SecuredDocumentSerializer.Meta.fields
    filterable_fields = ("name", "manager_note", "audit_value", "manager_value")
    sortable_fields = ("name", "modified")
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        return None

    @staticmethod
    def has_object_rule(user, document, ptype):
        return None


class PromptDocumentViewSet(DocumentViewSet):
    access = Access.open(
        reason="A prompt-naming fixture with no confidential rows or protected fields."
    )
    serializer_class = PromptDocumentSerializer
    readable_fields = PromptDocumentSerializer.Meta.fields
    filterable_fields = ("name", "label")
    sortable_fields = ("name", "label", "modified")


class AutoIncrementDocumentViewSet(DocumentViewSet):
    access = Access.open(
        reason="An integer-naming fixture with no confidential rows or protected fields."
    )
    serializer_class = AutoIncrementDocumentSerializer
    readable_fields = AutoIncrementDocumentSerializer.Meta.fields
    filterable_fields = ("name", "label")
    sortable_fields = ("name", "label", "modified")


class SingletonDocumentViewSet(SingletonViewSet):
    access = Access.ruled()
    serializer_class = SingletonDocumentSerializer
    readable_fields = SingletonDocumentSerializer.Meta.fields
    filterable_fields = ("name", "value", "manager_note")
    sortable_fields = ("name", "modified")

    @staticmethod
    def list_rule(user):
        return None

    @staticmethod
    def has_object_rule(user, document, ptype):
        if ptype == "read" and document.value == "Private":
            return False
        return None
