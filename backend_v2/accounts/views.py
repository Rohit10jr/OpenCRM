"""The authentication endpoints and the accounts resources."""

from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts import directory, front_door, invitations, services, user_roles
from accounts.roles import ADMINISTRATOR, GUEST, ROLE_SYSTEM_MANAGER
from accounts.serializers import (
    CRMInvitationSerializer,
    CRMSalesHierarchySerializer,
    UserSerializer,
)
from core.access import Access
from core.inputs import build_payload
from core.mixins import LinkSearchMixin
from core.renderers import Envelope
from core.security import rate_limit, resolve_ip
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

    @action(detail=False, methods=("get",), url_path="timezones")
    def timezones(self, request):
        """`frappe.core.doctype.user.user.get_timezones`."""
        return Response(Envelope({"timezones": services.timezones()}, "message"))

    @action(detail=False, methods=("get",), url_path="signature")
    def signature(self, request):
        """`crm.api.get_user_signature`: the caller's own."""
        return Response(Envelope(services.user_signature(request.user), "message"))

    @action(detail=False, methods=("post",), url_path="add-existing")
    def add_existing(self, request):
        """`crm.api.user.add_existing_users`."""
        inputs = build_payload(request)
        user_roles.add_existing_users(
            # The default applies only when `role` is absent (old user.py:111); an empty
            # one reaches update_user_role and is refused there.
            request.user, inputs.get("users"), inputs.get("role", "Sales User")
        )
        return Response(Envelope(None, "message"))

    # The two per-user actions take the user from the URL but never load it through
    # get_object(): the old code applies no object rule to the target (spec 4.2).
    @action(detail=True, methods=("post",), url_path="update-role")
    def update_role(self, request, **kwargs):
        """`crm.api.user.update_user_role`."""
        inputs = build_payload(request)
        user_roles.update_user_role(
            request.user, self._url_name(), inputs.get("new_role")
        )
        return Response(Envelope(None, "message"))

    @action(detail=True, methods=("post",), url_path="remove-crm-roles")
    def remove_crm_roles(self, request, **kwargs):
        """`crm.api.user.remove_crm_roles_from_user`."""
        message = user_roles.remove_crm_roles_from_user(request.user, self._url_name())
        return Response(Envelope(message, "message"))

    def _url_name(self):
        return self.kwargs[self.lookup_url_kwarg or self.lookup_field]

    def search_filters(self, filters, flags, user):
        """Frappe's `user_query` (old `crm_app/api/client.py:45-60`, FINDINGS 46):
        enabled accounts only, and no Website Users unless a System User asked with
        `ignore_user_type`."""
        hide_website = not (
            flags["ignore_user_type"] and user.user_type == "System User"
        )
        if isinstance(filters, list):
            # The old code turned a list into a 500 (dict() of a list); the same rules
            # apply in list form instead (supervisor, 18 Nov 2026).
            def fieldname(condition):
                if isinstance(condition, (list, tuple)) and len(condition) >= 3:
                    return condition[-3]
                return None

            result = list(filters)
            if "enabled" not in {fieldname(condition) for condition in result}:
                result.append(["enabled", "=", 1])
            if hide_website:
                result.append(["user_type", "!=", "Website User"])
            return result
        if not isinstance(filters, (dict, type(None))):
            return filters
        result = dict(filters or {})
        result.setdefault("enabled", 1)
        if hide_website:
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


class ChangePasswordView(BaseAPIView):
    """`crm.api.user.change_password`: five calls per five minutes per address, counting
    successes too (`crm/api/user.py:9`), beside the account lockout."""

    @rate_limit(limit=5, seconds=300)
    def post(self, request):
        inputs = self.get_inputs(request)
        return Response(
            services.change_password(
                request.user,
                inputs.get("old_password") or "",
                inputs.get("new_password") or "",
            )
        )


class OAuthProvidersView(BaseAPIView):
    """`crm.api.auth.oauth_providers`: always `[]`, guest. There is no Social Login Key
    model, as in the old backend (`crm_app/api/auth.py`); no frontend file calls it."""

    permission_classes = (AllowAny,)

    def get(self, request):
        return Response([])


class ResetPasswordView(BaseAPIView):
    """`frappe.core.doctype.user.user.reset_password`: 10 per hour per (IP, address)."""

    permission_classes = (AllowAny,)

    @rate_limit(
        limit=10,
        seconds=60 * 60,
        key="user",
        normalise=lambda value: str(value or "").strip().lower(),
    )
    def post(self, request):
        inputs = self.get_inputs(request)
        return Response(
            front_door.reset_password(inputs.get("user") or inputs.get("email") or "")
        )


class UpdatePasswordView(BaseAPIView):
    """`frappe.core.doctype.user.user.update_password`: 20 per hour, on the IP alone with a
    key and on (IP, account) on the old-password path."""

    permission_classes = (AllowAny,)

    @rate_limit(
        limit=20, seconds=60 * 60, key=front_door.throttle_identity, pass_user=True
    )
    def post(self, request):
        user = request.user if getattr(request.user, "is_authenticated", False) else None
        return Response(
            front_door.update_password(
                self.get_inputs(request), user, resolve_ip(request)
            )
        )


INVITATION_MANAGER_ROLES = {"System Manager", "Sales Manager"}


def _is_invitation_manager(user) -> bool:
    return user.name == ADMINISTRATOR or bool(user.get_roles() & INVITATION_MANAGER_ROLES)


class CRMInvitationViewSet(DocumentViewSet):
    """System Manager and Sales Manager for every operation; everyone else a deny-all list
    (old `platform_docs.py:394-407`). Stricter than upstream, whose Sales User read is what
    made a pending key redeemable by the wrong person (upstream bug #21)."""

    access = Access.ruled()
    serializer_class = CRMInvitationSerializer
    readable_fields = CRMInvitationSerializer.Meta.fields
    filterable_fields = CRMInvitationSerializer.Meta.fields
    sortable_fields = CRMInvitationSerializer.Meta.fields
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        return None if _is_invitation_manager(user) else Q(pk__in=[])

    @staticmethod
    def has_object_rule(user, document, ptype):
        return _is_invitation_manager(user)

    @action(detail=False, methods=("post",), url_path="invite-by-email")
    def invite_by_email(self, request):
        """`crm.api.invite_by_email`."""
        inputs = build_payload(request)
        result = invitations.invite_by_email(
            request.user, inputs.get("emails") or "", inputs.get("role")
        )
        return Response(Envelope(result, "message"))


class AcceptInvitationView(BaseAPIView):
    """`crm.api.accept_invitation`: guest, 10 per hour per IP."""

    permission_classes = (AllowAny,)

    @rate_limit(limit=10, seconds=60 * 60)
    def post(self, request):
        inputs = self.get_inputs(request)
        return Response(invitations.accept_invitation(inputs.get("key") or ""))
