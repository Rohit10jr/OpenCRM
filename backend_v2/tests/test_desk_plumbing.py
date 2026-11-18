"""Ported from ``backend/tests/test_desk_plumbing.py`` (REBUILD_PLAN S14), except the two
timezone cases (old :108, :125), which ACCOUNTS ported.

`/api/method/<dotted path>` becomes the routes in specs/CONFIGURATION.md section 1. Expected
answers are unchanged, except the post-only case: a wrong method is 405 under PE-1, where
the old dispatch answered 403 with a sentence naming the method.
"""

import json

import pytest

pytestmark = pytest.mark.django_db

GET_APPS = "/api/v1/desk/apps/"
SITE_INFO = "/api/v1/desk/site-info/"
BOOT_CONFIG = "/api/v1/desk/telemetry-config/"
CLEAR_DEMO = "/api/v1/demo/clear/"
TRANSLATIONS = "/api/v1/translations/"

CRM_ENTRY = {
    "name": "crm",
    "logo": "/assets/crm/images/logo.svg",
    "title": "CRM",
    "route": "/crm",
}
DEMO_REFUSAL = (
    "This action is only allowed for <strong>Sales Manager</strong>, "
    "<strong>System Manager</strong>"
)


@pytest.fixture
def system_manager(make_user):
    return make_user("sysmgr@example.com", roles=["System Manager"])


@pytest.fixture
def sales_manager(make_user):
    return make_user("salesmgr@example.com", roles=["Sales Manager"])


@pytest.fixture
def roleless(make_user):
    """A real, enabled user holding no CRM role at all."""
    return make_user("nobody@example.com", roles=[])


# --- get_apps ---------------------------------------------------------------------------


def test_get_apps_gives_the_administrator_the_crm_entry(api_as, administrator):
    response = api_as(administrator).get(GET_APPS)
    assert response.status_code == 200
    assert response.json()["message"] == [CRM_ENTRY]


def test_get_apps_gives_a_sales_user_the_crm_entry(auth_api):
    response = auth_api.get(GET_APPS)
    assert response.status_code == 200
    assert response.json()["message"] == [CRM_ENTRY]


def test_get_apps_hides_the_app_from_a_user_with_no_crm_role(api_as, roleless):
    """``[]``, not a 403: upstream skips an app whose permission check says no."""
    response = api_as(roleless).get(GET_APPS)
    assert response.status_code == 200
    assert response.json()["message"] == []


def test_get_apps_gives_the_other_two_crm_roles_the_entry_too(api_as, system_manager, sales_manager):
    for user in (system_manager, sales_manager):
        response = api_as(user).get(GET_APPS)
        assert response.status_code == 200
        assert response.json()["message"] == [CRM_ENTRY]


# --- current_site_info ------------------------------------------------------------------


def test_current_site_info_is_empty_for_the_administrator(api_as, administrator):
    response = api_as(administrator).get(SITE_INFO)
    assert response.status_code == 200
    assert response.json()["message"] == {}


def test_current_site_info_is_empty_for_a_system_manager(api_as, system_manager):
    response = api_as(system_manager).get(SITE_INFO)
    assert response.status_code == 200
    assert response.json()["message"] == {}


def test_current_site_info_refuses_a_sales_user(auth_api):
    response = auth_api.get(SITE_INFO)
    assert response.status_code == 403
    body = response.json()
    assert body["exc_type"] == "PermissionError"
    assert body["message"] == "Not permitted"


# --- boot_config ------------------------------------------------------------------------


def test_boot_config_is_off_when_nothing_is_configured(auth_api, settings):
    settings.POSTHOG_PROJECT_ID = ""
    settings.POSTHOG_HOST = ""
    response = auth_api.get(BOOT_CONFIG)
    assert response.status_code == 200
    assert response.json()["message"] == {"enabled": False}


def test_boot_config_is_on_when_both_settings_are_set(auth_api, settings):
    settings.POSTHOG_PROJECT_ID = "phc_test_project"
    settings.POSTHOG_HOST = "https://eu.posthog.com"
    assert auth_api.get(BOOT_CONFIG).json()["message"] == {"enabled": True}


@pytest.mark.parametrize(
    ("project_id", "host"),
    [("phc_test_project", ""), ("", "https://eu.posthog.com")],
)
def test_boot_config_needs_both_halves(auth_api, settings, project_id, host):
    settings.POSTHOG_PROJECT_ID = project_id
    settings.POSTHOG_HOST = host
    assert auth_api.get(BOOT_CONFIG).json()["message"] == {"enabled": False}


# --- clear_demo_data --------------------------------------------------------------------


def test_clear_demo_data_is_a_no_op_for_the_administrator(api_as, administrator):
    response = api_as(administrator).post(CLEAR_DEMO, {}, format="json")
    assert response.status_code == 200
    assert response.json()["message"] is None


def test_clear_demo_data_allows_a_sales_manager(api_as, sales_manager):
    response = api_as(sales_manager).post(CLEAR_DEMO, {}, format="json")
    assert response.status_code == 200
    assert response.json()["message"] is None


def test_clear_demo_data_allows_a_system_manager(api_as, system_manager):
    response = api_as(system_manager).post(CLEAR_DEMO, {}, format="json")
    assert response.status_code == 200
    assert response.json()["message"] is None


def test_clear_demo_data_refuses_a_sales_user_by_name(auth_api):
    response = auth_api.post(CLEAR_DEMO, {}, format="json")
    assert response.status_code == 403
    body = response.json()
    assert body["exc_type"] == "PermissionError"
    assert body["message"] == DEMO_REFUSAL
    server_message = json.loads(json.loads(body["_server_messages"])[0])
    assert server_message["title"] == "Not Permitted"


def test_clear_demo_data_is_post_only(api_as, administrator):
    """PE-1: a wrong method is 405 with an Allow header (the old dispatch: 403)."""
    response = api_as(administrator).get(CLEAR_DEMO)
    assert response.status_code == 405
    assert "POST" in response["Allow"]


# --- new: get_translations (no old test covers it) ----------------------------------------


def test_translations_are_empty_for_a_guest(api):
    response = api.get(TRANSLATIONS)
    assert response.status_code == 200
    assert response.json() == {"message": {}}


def test_a_roleless_user_is_refused_clear_demo_data_too(api_as, roleless):
    assert api_as(roleless).post(CLEAR_DEMO, {}, format="json").status_code == 403
