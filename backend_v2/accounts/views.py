"""The authentication endpoints and the accounts resources."""

from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts import directory, services
from accounts.roles import ADMINISTRATOR, GUEST, ROLE_SYSTEM_MANAGER
from accounts.serializers import CRMSalesHierarchySerializer, UserSerializer
from core.access import Access
from core.inputs import build_payload
from core.mixins import LinkSearchMixin
from core.renderers import Envelope
from core.security import resolve_ip
from core.views import BaseAPIView, DocumentViewSet

BUILTIN_USERS = (ADMINISTRATOR, GUEST)


def _is_user_admin(user) -> bool:
    # System Manager alone administers users (platform_docs.py:47 ADMIN_ROLES).
    return user.name == ADMINISTRATOR or user.has_role(ROLE_SYSTEM_MANAGER)


class UserViewSet(LinkSearchMixin, DocumentViewSet):
    """`User`, ruled as `backend/crm_app/permissions/platform_docs.py:90-136` rules it."""

    access = Access.ruled()
    serializer_class = UserSerializer
    readable_fields = UserSerializer.Meta.fields
    filterable_fields = UserSerializer.Meta.fields
    sortable_fields = UserSerializer.Meta.fields
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        # Everyone sees colleagues (kanban builds a column per user); only the literal
        # Administrator sees the built-ins.
        if user.name == ADMINISTRATOR:
            return None
        return ~Q(pk__in=BUILTIN_USERS)

    @staticmethod
    def has_object_rule(user, document, ptype):
        if user.name == ADMINISTRATOR:
            return True
        if ptype == "create":
            return _is_user_admin(user)
        name = getattr(document, "pk", None)
        if name is None:
            return _is_user_admin(user)
        if str(name) in BUILTIN_USERS:
            return False
        if _is_user_admin(user):
            return True
        if ptype == "read":
            return True
        # Your own row only, and never delete: it would orphan everything you own.
        return ptype == "write" and str(name) == str(user.name)

    @action(detail=False, methods=("get",), url_path="directory")
    def directory(self, request):
        """`crm.api.session.get_users`."""
        inputs = build_payload(request)
        result = directory.get_users(request.user, inputs.get("include_all", False))
        return Response(Envelope(list(result), "message"))

    @action(detail=False, methods=("get", "post"), url_path="info")
    def info(self, request):
        """`crm.api.session.get_user_info`."""
        inputs = build_payload(request)
        result = directory.get_user_info(request.user, inputs.get("users"))
        return Response(Envelope(result, "message"))

    def search_filters(self, filters, flags, user):
        """Frappe's `user_query` (old `crm_app/api/client.py:45-60`, FINDINGS 46):
        enabled accounts only, and no Website Users unless a System User asked with
        `ignore_user_type`."""
        if not isinstance(filters, (dict, type(None))):
            return filters
        result = dict(filters or {})
        result.setdefault("enabled", 1)
        if not (flags["ignore_user_type"] and user.user_type == "System User"):
            result["user_type"] = ["!=", "Website User"]
        return result


class LoginView(BaseAPIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        inputs = self.get_inputs(request)
        username = inputs.get("usr") or inputs.get("username") or inputs.get("email") or ""
        password = inputs.get("pwd") or inputs.get("password") or ""
        return Response(services.login(username, password, resolve_ip(request)))


class RefreshTokenView(BaseAPIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        inputs = self.get_inputs(request)
        token = inputs.get("refresh") or inputs.get("refresh_token") or ""
        return Response(services.refresh_token(token))


class LogoutView(BaseAPIView):
    def post(self, request):
        inputs = self.get_inputs(request)
        token = inputs.get("refresh") or inputs.get("refresh_token") or ""
        return Response(services.logout(token))


class LoggedUserView(BaseAPIView):
    def get(self, request):
        return Response(request.user.name)


class CRMSalesHierarchyViewSet(DocumentViewSet):
    """Everyone reads the chart; System Manager alone writes it — not the manager pair,
    since the chart decides what a manager can see (old `platform_docs.py:346-361`)."""

    access = Access.ruled()
    serializer_class = CRMSalesHierarchySerializer
    readable_fields = CRMSalesHierarchySerializer.Meta.fields
    filterable_fields = CRMSalesHierarchySerializer.Meta.fields
    sortable_fields = CRMSalesHierarchySerializer.Meta.fields
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        return None

    @staticmethod
    def has_object_rule(user, document, ptype):
        if user.name == ADMINISTRATOR or ptype == "read":
            return True
        return user.has_role(ROLE_SYSTEM_MANAGER)
