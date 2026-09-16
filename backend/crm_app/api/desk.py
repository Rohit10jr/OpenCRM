"""Desk plumbing the pages call on load: ``frappe.apps.get_apps``,
``frappe.core.doctype.user.user.get_timezones``,
``frappe.integrations.frappe_providers.frappecloud_billing.current_site_info`` and
``frappe.utils.telemetry.pulse.client.boot_config``.

Four framework-level calls the CRM frontend makes that have nothing to do with the CRM's
own doctypes. Three exist in ``version-15``; ``boot_config`` does not exist there at all
and is answered here because the router calls it on every navigation (see its docstring).

None of these reads a row-restricted doctype, so none goes through ``base_queryset``;
what they do read is the caller's *roles*, through ``crm_app.api.user._roles_of`` - the
same helper ``crm.api.user``'s own ``only_for`` uses.
"""

from __future__ import annotations

import zoneinfo
from functools import lru_cache

from django.conf import settings

from frappe_core.whitelist import whitelist

#: ``crm/hooks.py:15-23`` - the CRM's ``add_to_apps_screen`` entry, verbatim, minus the
#: ``has_permission`` key, which is the gate rather than part of the answer.
CRM_APP = {
    "name": "crm",
    "logo": "/assets/crm/images/logo.svg",
    "title": "CRM",
    "route": "/crm",
}

#: ``crm/api/__init__.py:55-70`` resolves ``check_app_permission`` through module access:
#: Administrator passes outright, anyone else must have the ``FCRM`` module. This port
#: does not model Module Def / role-to-module mapping, so the roles that would hold FCRM
#: access on a CRM site stand in for it.
APP_ROLES = ("System Manager", "Sales Manager", "Sales User")


@whitelist("frappe.apps.get_apps")
def get_apps():
    """``frappe/apps.py:17-55`` - the app switcher in the user dropdown.

    Upstream walks every installed app, skips ``frappe`` itself, reads each app's
    ``add_to_apps_screen`` hook and calls that hook's ``has_permission`` before letting
    the app into the list. This deployment is **one app**, so the loop collapses to a
    single entry and the list has at most one item: the CRM's own hook entry
    (``crm/hooks.py:15-23``), returned when ``crm.api.check_app_permission``
    (``crm/api/__init__.py:55``) would have answered True.

    Divergences, both forced by what this port models:

    * ``check_app_permission`` asks whether the user can see the ``FCRM`` module. Module
      access is a framework concept (Module Def, "Blocked Modules" on User) that this
      port does not model, so the gate is the equivalent role test -
      :data:`APP_ROLES` - with Administrator passing outright, exactly as upstream's
      first line does. A user with none of those roles gets ``[]``.
    * Upstream's ``get_route`` picks ``/app`` when the user has no readable workspace;
      there are no Workspaces here, so the hook's own ``route`` is always used.
    * Upstream additionally hides apps whose setup wizard is incomplete, from anyone who
      is not a System Manager. There is no setup wizard in this port.

    The frontend (``frontend/src/components/UserDropdown.vue:70-76,176-194``) drops the
    ``crm`` entry from this answer and prepends a Desk entry of its own pointing at
    ``/desk`` - a route that does not exist in this deployment. Removing that dead entry
    is a frontend-stage item, not something this endpoint can fix: returning the CRM
    entry is what upstream returns, and the frontend filters it out by name.
    """
    from crm_app.api.user import _roles_of
    from frappe_core.session import get_current_user

    user = get_current_user()
    if user == "Administrator" or _roles_of(user).intersection(APP_ROLES):
        return [dict(CRM_APP)]
    return []


#: Prefixes ``pytz.common_timezones`` leaves out. ``Etc/*`` are the fixed-offset zones,
#: ``SystemV/*`` the legacy System V names, and ``posix/*`` / ``right/*`` are the two
#: parallel copies of the whole database that some tzdata builds ship.
_UNCOMMON_PREFIXES = ("Etc/", "SystemV/", "posix/", "right/")


@lru_cache(maxsize=1)
def _get_timezones() -> list[str]:
    """``frappe/core/doctype/user/user.py:788-792`` - the cached, sorted list.

    Upstream is ``sorted(pytz.common_timezones)``. ``pytz`` is not a dependency of this
    port and is not being added for a dropdown, so the list is built from the standard
    library's :func:`zoneinfo.available_timezones` instead.

    **This is an approximation, and deliberately so.** ``pytz.common_timezones`` is
    derived from tzdata's ``zone.tab`` - the zones that name a country - plus ``UTC``
    and ``GMT``; ``zoneinfo`` exposes no equivalent of ``zone.tab``, so the filter here
    is structural: keep the ``Area/Location`` names, drop the fixed-offset and legacy
    families, add ``UTC`` and ``GMT`` back. That yields ~520 names where
    ``pytz.common_timezones`` has ~439; the extras are the backward-compatibility
    aliases (``US/Pacific``, ``Asia/Calcutta``) that ``pytz`` files under
    ``all_timezones`` only. Every one of them is a real, resolvable zone, so a user who
    picks one gets the right offset - the list is simply longer than upstream's.
    """
    names = {
        name
        for name in zoneinfo.available_timezones()
        if "/" in name and not name.startswith(_UNCOMMON_PREFIXES)
    }
    names.update({"UTC", "GMT"})
    return sorted(names)


@whitelist("frappe.core.doctype.user.user.get_timezones")
def get_timezones():
    """``frappe/core/doctype/user/user.py:783-785`` - ``{"timezones": [...]}``.

    Read by ``frontend/src/components/Settings/PreferencesSettings.vue:130-138``, which
    maps ``data.timezones`` straight into the time-zone dropdown, so the shape is a flat
    list of strings under that one key. The list itself is cached process-wide with
    :func:`functools.lru_cache`, as upstream caches it - it cannot change without a
    restart.

    The User model already carries ``time_zone`` (``frappe_platform/models.py:123``);
    this endpoint only supplies the options.
    """
    return {"timezones": _get_timezones()}


@whitelist("frappe.integrations.frappe_providers.frappecloud_billing.current_site_info")
def current_site_info():
    """``frappe/integrations/frappe_providers/frappecloud_billing.py:43-71``.

    Upstream is the Frappe Cloud billing bridge: ``frappe.only_for("System Manager")``,
    then a ``POST`` to ``press.saas.api.site.info`` signed with the site's
    ``fc_communication_secret`` (``get_headers``, lines 27-41), merged with the site name
    and base URL and cached for ten minutes.

    **This port can never be a Frappe Cloud site**, so there is nothing to call and no
    secret to call it with. On a self-hosted site upstream does not answer either: with
    no ``fc_communication_secret``, ``get_headers`` throws "Communication secret not
    set" and the caller gets a 417. Answering ``{}`` instead is a settled user decision
    (16 Sep 2026) rather than an oversight, and it is safe: the only caller is
    ``frontend/src/composables/frappecloud.js``, whose dialog is reachable only when
    ``window.is_fc_site`` is set - which this port never sets - so ``base_url`` and
    ``site_name`` are never actually read. Should billing of any kind be added later, it
    reports through this same call.

    The role gate is kept exactly as upstream has it, because it is the one part of the
    endpoint that is not about Frappe Cloud: ``frappe.only_for`` with ``message=False``
    (``frappe/__init__.py:947-970``) - Administrator passes, a System Manager passes,
    and anybody else gets a bare ``PermissionError``. ``is_fc_site`` and the rest of the
    module's endpoints are not ported; nothing in the frontend reaches them without
    ``window.is_fc_site``.
    """
    from crm_app.api.user import only_for

    # ``only_for(roles)`` here is the port's ``frappe.only_for(roles)`` with
    # ``message=False``: it raises ``PermissionError("Not permitted")``.
    only_for(["System Manager"])
    return {}


@whitelist("frappe.utils.telemetry.pulse.client.boot_config")
def boot_config():
    """``frappe.utils.telemetry.pulse.client.boot_config`` - **not in version-15**.

    There is no such module on the pinned framework branch; the shipped CRM frontend
    calls it anyway and tolerates the 404. ``frontend/src/router.js:10-22`` reads exactly
    one key off the answer - ``enabled`` - and uses it to decide whether to show the
    persona wizard at ``/onboarding``: the wizard exists only to feed telemetry, so with
    telemetry off it is skipped.

    Answering it properly instead of 404ing costs nothing and removes a console error on
    every navigation. ``enabled`` is true only when a PostHog project **and** host are
    configured (``POSTHOG_PROJECT_ID`` / ``POSTHOG_HOST``, ``config/settings/base.py``),
    which is the same condition upstream's telemetry uses: a key with no host, or a host
    with no key, cannot send anything, so it reports off.

    Divergence: the *sending* side is not wired up. Upstream's boot config also hands the
    browser the PostHog key so frappe-ui's ``useTelemetry`` can post events; doing that
    is a frontend-stage item. Until a key is configured this endpoint answers off, which
    is the correct answer for a deployment that captures nothing.
    """
    enabled = bool(
        getattr(settings, "POSTHOG_PROJECT_ID", "") and getattr(settings, "POSTHOG_HOST", "")
    )
    return {"enabled": enabled}
