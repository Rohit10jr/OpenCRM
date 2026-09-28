"""The user menu is built from FCRM Settings' dropdown items: docs/FINDINGS.md 42.

``UserDropdown.vue`` shows nothing without them. Upstream seeds the six standard items
at install (``crm/install.py:530``) from ``crm/hooks.py:314``; the port seeds them when
the settings row is first loaded, and migration 0010 did it for rows that already existed.
"""

import importlib

import pytest
from django.apps import apps

from crm_app.models import FCRMSettings
from crm_app.models.metadata import (
    STANDARD_DROPDOWN_ITEMS,
    CRMDropdownItem,
    add_standard_dropdown_items,
)
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

STANDARD_NAMES = ["app_selector", "settings", "login_to_fc", "about", "separator", "logout"]


def _migration():
    return importlib.import_module("crm_app.migrations.0010_standard_dropdown_items")


def _names(settings):
    return list(settings.dropdown_items.order_by("idx").values_list("name1", flat=True))


def test_the_six_standard_items_match_upstreams_hook():
    assert [item["name1"] for item in STANDARD_DROPDOWN_ITEMS] == STANDARD_NAMES
    by_name = {item["name1"]: item for item in STANDARD_DROPDOWN_ITEMS}
    assert by_name["logout"] == {
        "name1": "logout",
        "label": "Log out",
        "type": "Route",
        "icon": "log-out",
        "route": "#",
        "is_standard": True,
    }
    assert by_name["settings"]["icon"] == "settings"
    assert by_name["separator"]["type"] == "Separator"
    assert all(item["is_standard"] for item in STANDARD_DROPDOWN_ITEMS)


def test_loading_the_settings_for_the_first_time_seeds_them(administrator):
    with session_user(administrator.name):
        settings = FCRMSettings.load()
    assert _names(settings) == STANDARD_NAMES
    rows = list(settings.dropdown_items.order_by("idx"))
    assert [row.idx for row in rows] == [1, 2, 3, 4, 5, 6]
    assert rows[1].label == "Settings"
    assert rows[5].label == "Log out"
    assert all(row.is_standard for row in rows)
    assert all(row.parenttype == "FCRM Settings" and row.parentfield == "dropdown_items" for row in rows)


def test_loading_it_again_adds_nothing(administrator):
    with session_user(administrator.name):
        FCRMSettings.load()
        settings = FCRMSettings.load()
    assert settings.dropdown_items.count() == 6


def test_a_row_that_has_items_of_its_own_is_left_alone(administrator):
    with session_user(administrator.name):
        settings = FCRMSettings.objects.create(brand_name="Acme")
        CRMDropdownItem(
            parent_settings=settings, name1="docs", label="Docs", type="Route", route="https://docs.example"
        ).save()
        assert add_standard_dropdown_items(settings) == 0
    assert _names(settings) == ["docs"]


def test_the_migration_seeds_a_row_created_without_them(administrator):
    with session_user(administrator.name):
        settings = FCRMSettings.objects.create(brand_name="Acme")
        assert settings.dropdown_items.count() == 0
        _migration().forwards(apps, None)
    assert _names(settings) == STANDARD_NAMES


def test_the_migration_is_a_no_op_without_the_row():
    _migration().forwards(apps, None)
    assert not FCRMSettings.objects.exists()


def test_the_frontend_receives_them_with_the_settings(api_as, alice, administrator):
    """``stores/settings.js`` fetches FCRM Settings through ``frappe.client.get``; the
    menu reads name1, label, type, icon, route, hidden and is_standard off each row and
    dispatches on name1 (``UserDropdown.vue``)."""
    with session_user(administrator.name):
        FCRMSettings.load()
    response = api_as(alice).post(
        "/api/method/frappe.client.get",
        {"doctype": "FCRM Settings", "name": "FCRM Settings"},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    items = response.json()["message"]["dropdown_items"]
    assert [item["name1"] for item in items] == STANDARD_NAMES
    for key in ("label", "type", "icon", "route", "hidden", "is_standard"):
        assert key in items[0], key
    assert items[5]["label"] == "Log out"
