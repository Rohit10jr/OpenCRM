"""Ported from ``backend/tests/test_boot.py`` (REBUILD_PLAN S14).

`crm.www.crm.get_context_for_dev` is `POST /api/v1/boot/` (specs/CONFIGURATION.md 4.2).
Expected answers are unchanged, except a wrong method, which answers 405 (PE-1). Not
ported: `test_the_guard_sees_the_prefixed_call`, which checks the old backend's frontend
path guard; here the route map guard covers the route.
"""

import pytest

pytestmark = pytest.mark.django_db

BOOT = "/api/v1/boot/"

EXPECTED_KEYS = {
    "sysdefaults",
    "timezone",
    "translated_messages",
    "translated_doctypes",
    "state_options",
    "is_demo_site",
    "demo_data_created",
    "is_fc_site",
}

FORMAT_KEYS = (
    "date_format",
    "time_format",
    "number_format",
    "float_precision",
    "currency_precision",
    "currency",
    "rounding_method",
)


def boot(client):
    response = client.post(BOOT, {}, format="json")
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]


def test_a_guest_gets_the_boot_values(api, settings):
    values = boot(api)
    assert set(values) == EXPECTED_KEYS
    assert values["sysdefaults"] == settings.FRAPPE_SYSDEFAULTS
    assert values["timezone"] == {"system": settings.TIME_ZONE, "user": settings.TIME_ZONE}
    assert values["translated_messages"] == {}
    assert values["translated_doctypes"] == []
    assert values["state_options"] == {}
    assert values["is_demo_site"] is False
    assert values["demo_data_created"] is False
    assert values["is_fc_site"] is False


def test_sysdefaults_always_carry_the_keys_the_formatters_read(api):
    values = boot(api)["sysdefaults"]
    assert set(values) == set(FORMAT_KEYS)
    for key in FORMAT_KEYS:
        assert isinstance(values[key], str), key
    assert values["date_format"]


def test_the_defaults_are_frappes_own_fallbacks(api, settings):
    assert settings.FRAPPE_SYSDEFAULTS["date_format"] == "yyyy-mm-dd"
    assert settings.FRAPPE_SYSDEFAULTS["time_format"] == "HH:mm:ss"
    assert settings.FRAPPE_SYSDEFAULTS["number_format"] == "#,###.##"
    assert settings.FRAPPE_SYSDEFAULTS["float_precision"] == "3"
    assert settings.FRAPPE_SYSDEFAULTS["currency"] == ""
    assert settings.FRAPPE_SYSDEFAULTS["rounding_method"] == "Banker's Rounding (legacy)"
    assert boot(api)["sysdefaults"]["date_format"] == "yyyy-mm-dd"


def test_a_users_own_time_zone_wins(api_as, make_user, settings):
    user = make_user("tz@example.com", roles=["Sales User"], time_zone="Asia/Kolkata")
    values = boot(api_as(user))
    assert values["timezone"] == {"system": settings.TIME_ZONE, "user": "Asia/Kolkata"}


def test_a_user_without_a_time_zone_gets_the_system_zone(auth_api, settings):
    assert boot(auth_api)["timezone"]["user"] == settings.TIME_ZONE


def test_the_boot_call_is_post_only(api):
    """405 under PE-1 (403 "Method ... does not accept GET" in backend/)."""
    assert api.get(BOOT).status_code == 405
