"""``crm.www.crm.get_context_for_dev`` - the boot values the page needs before it draws.

FINDINGS.md 26: ``main.js`` mounts the app only after this call answers, so an unserved
path was a blank page. The frontend reads exactly these keys off ``window``
(``utils/index.js:82``, ``utils/numberFormat.js``, ``App.vue:43-45``,
``AppSidebar.vue:250-251``, ``demoData.js:5``, ``Field.vue:470``), so the shape is
asserted key for key rather than "contains what upstream sends".
"""

import pytest

from tests.test_phase3_endpoints import frontend_called_paths

pytestmark = pytest.mark.django_db

BOOT = "crm.www.crm.get_context_for_dev"

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

#: The keys the formatters read: ``numberFormat.js:111,173,204,241``, ``index.js:82,86``,
#: ``stores/meta.js:58`` and ``FieldLayout/Field.vue:358`` (``currency``).
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
    response = client.post(f"/api/method/{BOOT}", {}, format="json")
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]


def test_a_guest_gets_the_boot_values(api, settings):
    """The first visit has no token yet; upstream is ``allow_guest=True`` for the same
    reason, and the port drops its developer-mode gate because production calls it too."""
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
    """``window.sysdefaults.date_format.replace(...)`` has no guard (``utils/index.js:82``):
    a missing key is a TypeError on every date cell, not a fallback. Strings, as Frappe
    stores defaults - the frontend ``cint``s the numeric ones itself."""
    values = boot(api)["sysdefaults"]
    assert set(values) == set(FORMAT_KEYS)
    for key in FORMAT_KEYS:
        assert isinstance(values[key], str), key
    assert values["date_format"]


def test_the_defaults_are_frappes_own_fallbacks(api, settings):
    """``frappe/utils/data.py``: ``get_user_date_format`` falls back to ``yyyy-mm-dd``,
    ``get_user_time_format`` to ``HH:mm:ss``, ``fmt_money`` to ``#,###.##``; System
    Settings defaults ``rounding_method`` to Banker's Rounding (legacy) and leaves
    ``currency`` empty until the setup wizard picks one (the frontend shows USD)."""
    assert settings.FRAPPE_SYSDEFAULTS["date_format"] == "yyyy-mm-dd"
    assert settings.FRAPPE_SYSDEFAULTS["time_format"] == "HH:mm:ss"
    assert settings.FRAPPE_SYSDEFAULTS["number_format"] == "#,###.##"
    assert settings.FRAPPE_SYSDEFAULTS["float_precision"] == "3"
    assert settings.FRAPPE_SYSDEFAULTS["currency"] == ""
    assert settings.FRAPPE_SYSDEFAULTS["rounding_method"] == "Banker's Rounding (legacy)"
    assert boot(api)["sysdefaults"]["date_format"] == "yyyy-mm-dd"


def test_a_users_own_time_zone_wins(api_as, make_user, settings):
    """``get_boot``: ``frappe.db.get_value("User", user, "time_zone") or
    get_system_timezone()`` - the user's column first."""
    user = make_user("tz@example.com", roles=["Sales User"], time_zone="Asia/Kolkata")
    values = boot(api_as(user))
    assert values["timezone"] == {"system": settings.TIME_ZONE, "user": "Asia/Kolkata"}


def test_a_user_without_a_time_zone_gets_the_system_zone(auth_api, settings):
    assert boot(auth_api)["timezone"]["user"] == settings.TIME_ZONE


def test_the_boot_call_is_post_only(api):
    """Upstream declares ``methods=["POST"]``; the port answers a wrong method with a
    ``PermissionError`` naming the method (``method_views.py:45-49``), not a 405."""
    response = api.get(f"/api/method/{BOOT}")
    assert response.status_code == 403
    body = response.json()
    assert body["exc_type"] == "PermissionError"
    assert body["message"] == f"Method {BOOT} does not accept GET"


def test_the_guard_sees_the_prefixed_call():
    """``main.js`` writes this path as ``url: '/api/method/...'``. Until 23 Sep 2026 the
    guard regex matched bare dotted paths only, which is how the one call made before
    the app mounts stayed unserved through eight phases."""
    assert BOOT in frontend_called_paths()
