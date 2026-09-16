"""The five framework-level calls the CRM frontend makes that are not CRM endpoints.

``frappe.apps.get_apps``, ``frappe.core.doctype.user.user.get_timezones``,
``frappe.integrations.frappe_providers.frappecloud_billing.current_site_info``,
``frappe.utils.telemetry.pulse.client.boot_config`` and ``crm.demo.api.clear_demo_data``.

Four of them answer the same thing on every call, so what is actually worth asserting is
the *shape* the frontend destructures and the *gate* in front of it:

* ``get_apps`` gates on roles, and a caller with none must get ``[]`` rather than the
  app entry - the app switcher is the one place this endpoint's answer is visible.
* ``current_site_info`` and ``clear_demo_data`` both reproduce ``frappe.only_for``, and
  they reproduce its *two different* forms: the silent one and the one that names the
  roles. Both sentences are user-facing copy and are asserted verbatim.
* ``get_timezones`` is asserted on membership and ordering rather than on an exact list,
  because the list comes from the tzdata build on the host and grows between releases.
"""

import json

import pytest

pytestmark = pytest.mark.django_db

GET_APPS = "frappe.apps.get_apps"
GET_TIMEZONES = "frappe.core.doctype.user.user.get_timezones"
SITE_INFO = "frappe.integrations.frappe_providers.frappecloud_billing.current_site_info"
BOOT_CONFIG = "frappe.utils.telemetry.pulse.client.boot_config"
CLEAR_DEMO = "crm.demo.api.clear_demo_data"

CRM_ENTRY = {
    "name": "crm",
    "logo": "/assets/crm/images/logo.svg",
    "title": "CRM",
    "route": "/crm",
}

#: ``frappe/__init__.py:947-970`` with ``message=True``, ``frappe.bold`` included.
DEMO_REFUSAL = (
    "This action is only allowed for <strong>Sales Manager</strong>, "
    "<strong>System Manager</strong>"
)


def call(client, path, payload=None):
    return client.post(f"/api/method/{path}", payload or {}, format="json")


@pytest.fixture
def system_manager(make_user):
    return make_user("sysmgr@example.com", roles=["System Manager"])


@pytest.fixture
def sales_manager(make_user):
    return make_user("salesmgr@example.com", roles=["Sales Manager"])


@pytest.fixture
def roleless(make_user):
    """A real, enabled user holding no CRM role at all - a Website User in effect."""
    return make_user("nobody@example.com", roles=[])


# ---------------------------------------------------------------------------
# frappe.apps.get_apps
# ---------------------------------------------------------------------------


def test_get_apps_gives_the_administrator_the_crm_entry(api_as, administrator):
    """``crm/hooks.py:15-23``, verbatim, and nothing else: this deployment is one app."""
    response = call(api_as(administrator), GET_APPS)
    assert response.status_code == 200
    assert response.json()["message"] == [CRM_ENTRY]


def test_get_apps_gives_a_sales_user_the_crm_entry(auth_api):
    """A Sales User holds FCRM module access upstream, so ``check_app_permission`` passes."""
    response = call(auth_api, GET_APPS)
    assert response.status_code == 200
    assert response.json()["message"] == [CRM_ENTRY]


def test_get_apps_hides_the_app_from_a_user_with_no_crm_role(api_as, roleless):
    """``crm/api/__init__.py:55`` returns False without FCRM, and the app is dropped.

    ``[]``, not a 403: upstream's loop ``continue``s past an app whose ``has_permission``
    says no, so the switcher is simply empty for that user.
    """
    response = call(api_as(roleless), GET_APPS)
    assert response.status_code == 200
    assert response.json()["message"] == []


def test_get_apps_gives_the_other_two_crm_roles_the_entry_too(api_as, system_manager, sales_manager):
    """The three roles that hold FCRM module access on a CRM site all pass the gate."""
    for user in (system_manager, sales_manager):
        response = call(api_as(user), GET_APPS)
        assert response.status_code == 200
        assert response.json()["message"] == [CRM_ENTRY]


# ---------------------------------------------------------------------------
# frappe.core.doctype.user.user.get_timezones
# ---------------------------------------------------------------------------


def test_get_timezones_is_a_sorted_list_of_common_zones(auth_api):
    """``{"timezones": [...]}`` - the key PreferencesSettings.vue:130-138 destructures."""
    response = call(auth_api, GET_TIMEZONES)
    assert response.status_code == 200
    zones = response.json()["message"]["timezones"]

    assert isinstance(zones, list)
    assert "Asia/Kolkata" in zones
    assert "Europe/Berlin" in zones
    assert "UTC" in zones
    # The fixed-offset family is what ``pytz.common_timezones`` leaves out, and it is the
    # part a naive ``available_timezones()`` would wrongly include - 40-odd ``Etc/GMT+7``
    # entries whose sign is inverted from what anyone picking one would expect.
    assert not [zone for zone in zones if zone.startswith("Etc/")]
    assert zones == sorted(zones)


def test_get_timezones_answers_the_same_list_every_time(auth_api):
    """``lru_cache``, as upstream caches it (``user.py:788``)."""
    from crm_app.api.desk import _get_timezones

    first = call(auth_api, GET_TIMEZONES).json()["message"]["timezones"]
    second = call(auth_api, GET_TIMEZONES).json()["message"]["timezones"]
    assert first == second
    # Identity, not just equality: equality would also hold if the list were rebuilt on
    # every call, which is the thing the cache exists to avoid.
    assert _get_timezones() is _get_timezones()


# ---------------------------------------------------------------------------
# frappecloud_billing.current_site_info
# ---------------------------------------------------------------------------


def test_current_site_info_is_empty_for_the_administrator(api_as, administrator):
    """This port can never be a Frappe Cloud site; ``{}`` is the settled answer."""
    response = call(api_as(administrator), SITE_INFO)
    assert response.status_code == 200
    assert response.json()["message"] == {}


def test_current_site_info_is_empty_for_a_system_manager(api_as, system_manager):
    """``frappe.only_for("System Manager")`` - the role upstream lets through."""
    response = call(api_as(system_manager), SITE_INFO)
    assert response.status_code == 200
    assert response.json()["message"] == {}


def test_current_site_info_refuses_a_sales_user(auth_api):
    """``only_for(..., message=False)`` raises a bare ``PermissionError``.

    Upstream gives the user no sentence at all here; the port's bare ``PermissionError``
    carries "Not permitted", which is what every other ``message=False`` gate in this
    port says.
    """
    response = call(auth_api, SITE_INFO)
    assert response.status_code == 403
    body = response.json()
    assert body["exc_type"] == "PermissionError"
    assert body["message"] == "Not permitted"


# ---------------------------------------------------------------------------
# telemetry boot_config
# ---------------------------------------------------------------------------


def test_boot_config_is_off_when_nothing_is_configured(auth_api):
    """No PostHog key, no telemetry - and so no persona wizard (router.js:10-22)."""
    response = call(auth_api, BOOT_CONFIG)
    assert response.status_code == 200
    assert response.json()["message"] == {"enabled": False}


def test_boot_config_is_on_when_both_settings_are_set(auth_api, settings):
    settings.POSTHOG_PROJECT_ID = "phc_test_project"
    settings.POSTHOG_HOST = "https://eu.posthog.com"
    response = call(auth_api, BOOT_CONFIG)
    assert response.json()["message"] == {"enabled": True}


@pytest.mark.parametrize(
    ("project_id", "host"),
    [
        ("phc_test_project", ""),
        ("", "https://eu.posthog.com"),
    ],
)
def test_boot_config_needs_both_halves(auth_api, settings, project_id, host):
    """A key with no host, or a host with no key, cannot send an event - so it is off."""
    settings.POSTHOG_PROJECT_ID = project_id
    settings.POSTHOG_HOST = host
    response = call(auth_api, BOOT_CONFIG)
    assert response.json()["message"] == {"enabled": False}


# ---------------------------------------------------------------------------
# crm.demo.api.clear_demo_data
# ---------------------------------------------------------------------------


def test_clear_demo_data_is_a_no_op_for_the_administrator(api_as, administrator):
    """Upstream returns early without a recorded demo state, and there never is one here."""
    response = call(api_as(administrator), CLEAR_DEMO)
    assert response.status_code == 200
    assert response.json()["message"] is None


def test_clear_demo_data_allows_a_sales_manager(api_as, sales_manager):
    response = call(api_as(sales_manager), CLEAR_DEMO)
    assert response.status_code == 200
    assert response.json()["message"] is None


def test_clear_demo_data_allows_a_system_manager(api_as, system_manager):
    response = call(api_as(system_manager), CLEAR_DEMO)
    assert response.status_code == 200
    assert response.json()["message"] is None


def test_clear_demo_data_refuses_a_sales_user_by_name(auth_api):
    """``only_for(..., message=True)`` - the sentence names the two roles, in order."""
    response = call(auth_api, CLEAR_DEMO)
    assert response.status_code == 403
    body = response.json()
    assert body["exc_type"] == "PermissionError"
    assert body["message"] == DEMO_REFUSAL
    # ``frappe.throw(..., title=_("Not Permitted"))`` - the title travels in
    # _server_messages, a JSON list of JSON strings, as the frontend reads it.
    server_message = json.loads(json.loads(body["_server_messages"])[0])
    assert server_message["title"] == "Not Permitted"


def test_clear_demo_data_is_post_only(api_as, administrator):
    """A destructive action must not be reachable by a link or a prefetch.

    ``frappe_core/method_views.py:45-49`` answers a wrong method with a
    ``PermissionError`` naming the method, not a 405 - the port has one error envelope
    and this is the shape of it.
    """
    response = api_as(administrator).get(f"/api/method/{CLEAR_DEMO}")
    assert response.status_code == 403
    body = response.json()
    assert body["exc_type"] == "PermissionError"
    assert body["message"] == f"Method {CLEAR_DEMO} does not accept GET"
