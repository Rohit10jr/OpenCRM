"""Desk plumbing the pages call on load (specs/CONFIGURATION.md section 4.1).

Ported from `backend/crm_app/api/desk.py`, `api/demo.py` and `api/misc.py:31-39`. None
reads a row-restricted model; what they read is the caller's roles.
"""

from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.roles import (
    ADMINISTRATOR,
    ROLE_SALES_MANAGER,
    ROLE_SALES_USER,
    ROLE_SYSTEM_MANAGER,
)
from core.exceptions import PermissionError
from core.views import BaseAPIView

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
