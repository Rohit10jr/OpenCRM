"""Desk plumbing the pages call on load (specs/CONFIGURATION.md section 4.1).

Ported from `backend/crm_app/api/desk.py`, `api/demo.py` and `api/misc.py:31-39`. None
reads a row-restricted model; what they read is the caller's roles.
"""

import json

from django.conf import settings
from django.db.models import Q
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.roles import (
    ADMINISTRATOR,
    ROLE_SALES_MANAGER,
    ROLE_SALES_USER,
    ROLE_SYSTEM_MANAGER,
)
from configuration import exchange_rate
from configuration.models import SystemSettings
from configuration.serializers import (
    DOCUMENT_FIELDS,
    FCRM_SETTINGS_FIELDS,
    CountrySerializer,
    CurrencySerializer,
    EmailAccountSerializer,
    FCRMSettingsSerializer,
    LanguageSerializer,
    SystemSettingsSerializer,
)
from core.access import Access
from core.exceptions import PermissionError, ValidationError
from core.mixins import LinkSearchMixin
from core.mixins.rename import RenameMixin
from core.query import parse_json_param
from core.views import BaseAPIView, DocumentViewSet, SingletonViewSet

#: The CRM's `add_to_apps_screen` entry (`crm/hooks.py:15-23`), verbatim.
CRM_APP = {
    "name": "crm",
    "logo": "/assets/crm/images/logo.svg",
    "title": "CRM",
    "route": "/crm",
}
#: Stand-ins for FCRM module access, which neither backend models.
APP_ROLES = {ROLE_SYSTEM_MANAGER, ROLE_SALES_MANAGER, ROLE_SALES_USER}
#: `frappe.only_for` roles of `clear_demo_data`, in upstream's order.
DEMO_ROLES = (ROLE_SALES_MANAGER, ROLE_SYSTEM_MANAGER)


class AppsView(BaseAPIView):
    """`frappe.apps.get_apps`: the CRM entry for a CRM role, `[]` (not 403) otherwise."""

    def get(self, request):
        user = request.user
        if user.name == ADMINISTRATOR or user.get_roles() & APP_ROLES:
            return Response([dict(CRM_APP)])
        return Response([])


class SiteInfoView(BaseAPIView):
    """`frappecloud_billing.current_site_info`: never a Frappe Cloud site, so `{}`, behind
    upstream's `only_for("System Manager")` with no sentence of its own."""

    def get(self, request):
        user = request.user
        if user.name != ADMINISTRATOR and not user.has_role(ROLE_SYSTEM_MANAGER):
            raise PermissionError("Not permitted")
        return Response({})


class TelemetryConfigView(BaseAPIView):
    """`telemetry.pulse.client.boot_config`: on only when a PostHog project and host are
    both configured; the router reads `enabled` alone."""

    def get(self, request):
        enabled = bool(settings.POSTHOG_PROJECT_ID and settings.POSTHOG_HOST)
        return Response({"enabled": enabled})


class ClearDemoDataView(BaseAPIView):
    """`crm.demo.api.clear_demo_data`: the role check, then an early return — no demo
    data is ever recorded, so there is nothing to clear. POST only."""

    def post(self, request):
        user = request.user
        if user.name != ADMINISTRATOR and user.get_roles().isdisjoint(DEMO_ROLES):
            roles = ", ".join(f"<strong>{role}</strong>" for role in DEMO_ROLES)
            raise PermissionError(
                f"This action is only allowed for {roles}", title="Not Permitted"
            )
        return Response(None)


class TranslationsView(BaseAPIView):
    """`crm.api.get_translations`: guest, `{}` — no catalogues, so the source strings."""

    permission_classes = (AllowAny,)

    def get(self, request):
        return Response({})


def _onboarding_status(user) -> dict:
    """The caller's `User.onboarding_status` as a dict; `{}` when unset or unreadable."""
    raw = user.onboarding_status
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class OnboardingStatusView(BaseAPIView):
    """`frappe.onboarding.get_onboarding_status` (GET) and
    `update_user_onboarding_status` (POST), which frappe-ui's onboarding panel calls
    (old `crm_app/api/onboarding.py:43-85`). The status is a JSON object on the caller's
    own User row keyed `<appName>_onboarding_status`."""

    def get(self, request):
        return Response(_onboarding_status(request.user))

    def post(self, request):
        inputs = self.get_inputs(request)
        app_name = inputs.get("appName") or ""
        steps = inputs.get("steps", "")
        if not app_name:
            raise ValidationError("appName is required")
        parsed = parse_json_param(steps, None) if isinstance(steps, str) else steps
        # A string that is not JSON comes back unchanged; only an array or object is.
        if not isinstance(parsed, (list, dict)):
            raise ValidationError("steps must be JSON")
        status = _onboarding_status(request.user)
        status[f"{app_name}_onboarding_status"] = parsed
        # An update, not a save: the row's timestamps stay untouched, as upstream's
        # update_modified=False. Upstream 500s on a user with no status (bug 40); here
        # an unset status is {}, as in backend/.
        type(request.user)._default_manager.filter(pk=request.user.pk).update(
            onboarding_status=json.dumps(status)
        )
        return Response(None)


class SystemSettingsViewSet(SingletonViewSet):
    """System Manager or Administrator for everything, reading included; nobody deletes
    it, and the singleton route has no delete (old `platform_docs.py:532-551`). The boot
    call reads the row server-side for every caller."""

    access = Access.ruled()
    serializer_class = SystemSettingsSerializer
    readable_fields = SystemSettingsSerializer.Meta.fields
    filterable_fields = SystemSettingsSerializer.Meta.fields
    sortable_fields = SystemSettingsSerializer.Meta.fields
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        return None if _is_system_admin(user) else Q(pk__in=[])

    @staticmethod
    def has_object_rule(user, document, ptype):
        if ptype == "delete":
            return False
        return _is_system_admin(user)


def _is_system_admin(user) -> bool:
    return user.name == ADMINISTRATOR or user.has_role(ROLE_SYSTEM_MANAGER)


class BootView(BaseAPIView):
    """`crm.www.crm.get_context_for_dev`: the values the page needs before it draws
    (old `crm_app/api/boot.py:41-73`). Guest, POST only, exactly eight keys. System
    Settings is read server-side, so no permission on it is needed; a missing row is
    written again (spec section 4.2)."""

    permission_classes = (AllowAny,)

    def post(self, request):
        system_zone = settings.TIME_ZONE
        # A guest's request.user is None here (UNAUTHENTICATED_USER).
        own_zone = getattr(request.user, "time_zone", "") or ""
        return Response(
            {
                "sysdefaults": SystemSettings.load_or_create().sysdefaults(),
                "timezone": {"system": system_zone, "user": own_zone or system_zone},
                "translated_messages": {},
                "translated_doctypes": [],
                "state_options": {},
                "is_demo_site": False,
                "demo_data_created": False,
                "is_fc_site": False,
            }
        )


#: Version-15 `currency.json`'s readers besides System Manager (old
#: `platform_docs.py:504-510`); Sales Manager is listed rather than looked up through
#: Sales User.
CURRENCY_READERS = frozenset(
    {"Sales User", "Sales Manager", "Accounts Manager", "Accounts User", "Purchase User"}
)


def _read_all_write_admin(user, ptype) -> bool:
    """Everyone reads; System Manager or Administrator writes, creates and deletes."""
    if ptype == "read":
        return True
    return _is_system_admin(user)


class CountryViewSet(LinkSearchMixin, DocumentViewSet):
    """Old `platform_docs.py:458-466`. Every column readable, filterable and sortable."""

    access = Access.ruled()
    serializer_class = CountrySerializer
    readable_fields = CountrySerializer.Meta.fields
    filterable_fields = CountrySerializer.Meta.fields
    sortable_fields = CountrySerializer.Meta.fields
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        return None

    @staticmethod
    def has_object_rule(user, document, ptype):
        return _read_all_write_admin(user, ptype)


class LanguageViewSet(LinkSearchMixin, DocumentViewSet):
    """Old `platform_docs.py:484-496`. Every column readable, filterable and sortable."""

    access = Access.ruled()
    serializer_class = LanguageSerializer
    readable_fields = LanguageSerializer.Meta.fields
    filterable_fields = LanguageSerializer.Meta.fields
    sortable_fields = LanguageSerializer.Meta.fields
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        return None

    @staticmethod
    def has_object_rule(user, document, ptype):
        return _read_all_write_admin(user, ptype)


def _reads_currency(user) -> bool:
    return _is_system_admin(user) or bool(user.get_roles() & CURRENCY_READERS)


class CurrencyViewSet(LinkSearchMixin, DocumentViewSet):
    """Read by System Manager, Administrator and the CRM and accounting roles above; a
    caller with none gets an empty list and 403 by name (old `platform_docs.py:504-529`).
    Every column readable, filterable and sortable."""

    access = Access.ruled()
    serializer_class = CurrencySerializer
    readable_fields = CurrencySerializer.Meta.fields
    filterable_fields = CurrencySerializer.Meta.fields
    sortable_fields = CurrencySerializer.Meta.fields
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        return None if _reads_currency(user) else Q(pk__in=[])

    @staticmethod
    def has_object_rule(user, document, ptype):
        if ptype == "read":
            return _reads_currency(user)
        return _is_system_admin(user)


class FCRMSettingsViewSet(SingletonViewSet):
    """Everyone reads it (the timeline reads it on every screen); the manager pair or
    Administrator writes it (old `platform_docs.py:302-315`). `access_key` is restricted
    to the same callers. Every column readable, filterable and sortable."""

    access = Access.ruled()
    serializer_class = FCRMSettingsSerializer
    readable_fields = (*DOCUMENT_FIELDS, *FCRM_SETTINGS_FIELDS)
    filterable_fields = readable_fields
    sortable_fields = readable_fields
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        return None

    @staticmethod
    def has_object_rule(user, document, ptype):
        if user.name == ADMINISTRATOR or ptype == "read":
            return True
        return user.has_role(ROLE_SYSTEM_MANAGER) or user.has_role(ROLE_SALES_MANAGER)


class ExchangeRateView(BaseAPIView):
    """`crm.api.exchange_rate.get_exchange_rate`: signed-in callers; the rate between two
    currencies (configuration/exchange_rate.py; spec section 4.3)."""

    def get(self, request):
        inputs = self.get_inputs(request)
        return Response(
            exchange_rate.get_exchange_rate(
                inputs.get("from_currency"),
                inputs.get("to_currency"),
                inputs.get("date"),
                user=request.user,
            )
        )


class EmailAccountViewSet(RenameMixin, DocumentViewSet):
    """Everyone reads an Email Account (the Profile picker lists them); the manager pair
    or Administrator creates, writes, renames and deletes (old `platform_docs.py:158-186`).
    Saved through the resource without validation, service defaults or the name check,
    and a `password` or `api_secret` sent on update is ignored, as in `backend/`
    (decision 4). The sensitive and restricted fields are applied by the model's
    declarations on every route."""

    access = Access.ruled()
    serializer_class = EmailAccountSerializer
    readable_fields = EmailAccountSerializer.Meta.fields
    filterable_fields = EmailAccountSerializer.Meta.fields
    sortable_fields = EmailAccountSerializer.Meta.fields
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        return None

    @staticmethod
    def has_object_rule(user, document, ptype):
        if user.name == ADMINISTRATOR or ptype == "read":
            return True
        return user.has_role(ROLE_SYSTEM_MANAGER) or user.has_role(ROLE_SALES_MANAGER)
