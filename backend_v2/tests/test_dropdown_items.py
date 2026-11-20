"""Ported from ``backend/tests/test_dropdown_items.py`` (REBUILD_PLAN S14).

The sidebar's user menu is built from FCRM Settings' dropdown items
(specs/CONFIGURATION.md 4.3). `frappe.client.get` on FCRM Settings is
`GET /api/v1/crm-settings/`. Changed for this backend: the data migration writes the row
with its six items, so `test_loading_the_settings_for_the_first_time_seeds_them` deletes
the row first, and the two cases about `backend/`'s data-fix migration 0010
(`:79-89`) become "the migration writes the row with six items and leaves an existing
row alone". Expected answers are otherwise unchanged.
"""

import importlib

import pytest
from django.apps import apps

from configuration.models import (
    STANDARD_DROPDOWN_ITEMS,
    CRMDropdownItem,
    FCRMSettings,
    add_standard_dropdown_items,
)

pytestmark = pytest.mark.django_db

STANDARD_NAMES = ["app_selector", "settings", "login_to_fc", "about", "separator", "logout"]


def _migration():
    return importlib.import_module("configuration.migrations.0006_fcrm_settings_row")


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
    FCRMSettings.objects.all().delete()
    settings = FCRMSettings.load_or_create(user=administrator)
    assert _names(settings) == STANDARD_NAMES
    rows = list(settings.dropdown_items.order_by("idx"))
    assert [row.idx for row in rows] == [1, 2, 3, 4, 5, 6]
    assert rows[1].label == "Settings"
    assert rows[5].label == "Log out"
    assert all(row.is_standard for row in rows)
    assert all(
        row.parenttype == "FCRM Settings" and row.parentfield == "dropdown_items"
        for row in rows
    )


def test_loading_it_again_adds_nothing(administrator):
    FCRMSettings.load_or_create(user=administrator)
    settings = FCRMSettings.load_or_create(user=administrator)
    assert settings.dropdown_items.count() == 6


def test_a_row_that_has_items_of_its_own_is_left_alone(administrator):
    settings = FCRMSettings.objects.get(pk="FCRM Settings")
    settings.dropdown_items.all().delete()
    CRMDropdownItem(
        parent_settings=settings,
        name1="docs",
        label="Docs",
        type="Route",
        route="https://docs.example",
    ).save(user=administrator)
    assert add_standard_dropdown_items(settings, user=administrator) == 0
    assert _names(settings) == ["docs"]


def test_the_migration_writes_the_row_with_six_items():
    settings = FCRMSettings.objects.get(pk="FCRM Settings")
    assert _names(settings) == STANDARD_NAMES
    rows = list(settings.dropdown_items.order_by("idx"))
    assert [row.idx for row in rows] == [1, 2, 3, 4, 5, 6]
    assert all(row.owner_id == "Administrator" and row.is_standard for row in rows)
    assert len({row.name for row in rows}) == 6


def test_the_migration_leaves_an_existing_row_alone(administrator):
    settings = FCRMSettings.objects.get(pk="FCRM Settings")
    settings.dropdown_items.all().delete()
    _migration().write_row(apps, None)
    assert settings.dropdown_items.count() == 0


def test_the_frontend_receives_them_with_the_settings(api_as, alice):
    response = api_as(alice).get("/api/v1/crm-settings/")
    assert response.status_code == 200, response.content[:300]
    items = response.json()["message"]["dropdown_items"]
    assert [item["name1"] for item in items] == STANDARD_NAMES
    for key in ("label", "type", "icon", "route", "hidden", "is_standard"):
        assert key in items[0], key
    assert items[5]["label"] == "Log out"


# --- new: no old test covers these (specs/CONFIGURATION.md section 4.3) -------------------


def test_an_existing_row_is_never_refilled(administrator):
    """A manager may empty the table; load_or_create adds items only when it creates the
    row (A-30 question 2)."""
    FCRMSettings.objects.get(pk="FCRM Settings").dropdown_items.all().delete()
    settings = FCRMSettings.load_or_create(user=administrator)
    assert settings.dropdown_items.count() == 0


def test_force_restores_a_standard_row_and_keeps_a_custom_one(administrator):
    """The force branch, ported whole; its operator command is milestone 6's."""
    settings = FCRMSettings.objects.get(pk="FCRM Settings")
    settings.dropdown_items.filter(name1="settings").update(type="Separator", label="")
    settings.dropdown_items.filter(name1="about").delete()
    CRMDropdownItem(
        parent_settings=settings, idx=7, name1="docs", label="Docs", type="Route"
    ).save(user=administrator)

    assert add_standard_dropdown_items(settings, user=administrator, force=True) == 2
    restored = settings.dropdown_items.get(name1="settings")
    assert (restored.type, restored.label) == ("Route", "Settings")
    assert settings.dropdown_items.filter(name1="about").exists()
    assert settings.dropdown_items.filter(name1="docs").exists()


def test_a_manager_empties_the_menu_and_it_stays_empty(api_as, make_user, administrator):
    """No save hook refills it (spec section 4.3): neither the read nor either loader
    puts the standard items back on a row that exists."""
    manager = make_user("mgr@example.com", roles=["Sales Manager"])
    client = api_as(manager)
    response = client.patch("/api/v1/crm-settings/", {"dropdown_items": []}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert client.get("/api/v1/crm-settings/").json()["message"]["dropdown_items"] == []
    assert FCRMSettings.load(user=administrator).dropdown_items.count() == 0
    assert FCRMSettings.load_or_create(user=administrator).dropdown_items.count() == 0


def test_load_on_a_missing_row_writes_the_standard_items(administrator):
    """A-32 finding 4: `load`, the old loader's name, behaves as `load_or_create`."""
    FCRMSettings.objects.all().delete()
    settings = FCRMSettings.load(user=administrator)
    assert _names(settings) == STANDARD_NAMES
