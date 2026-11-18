"""Ported from ``backend/tests/test_settings_access.py:126-175``, the FCRM Settings half
(REBUILD_PLAN S14); the Twilio and Exotel cases are INTEGRATIONS'.

`GET`/`PUT /api/resource/FCRM Settings/FCRM Settings` is `GET`/`PATCH
/api/v1/crm-settings/` (specs/CONFIGURATION.md 4.3). The old resource answered under
`data`; the singleton answers under `message`. Expected answers are otherwise unchanged,
except `test_the_key_cannot_be_probed_by_filtering`, which retires under PE-11 (a
settings record has no list route). The old fixture created the row; here the data
migration has written it, so the fixture updates it.

Also here: `test_an_open_singleton_is_still_readable` from
``backend/tests/test_phase7_review_fixes.py:114-125``, through `value/`.
"""

import pytest

from configuration.models import FCRMSettings

pytestmark = pytest.mark.django_db

SETTINGS = "/api/v1/crm-settings/"


@pytest.fixture
def manager(make_user):
    return make_user("mgr@example.com", roles=["Sales Manager"])


@pytest.fixture
def app_settings():
    FCRMSettings.objects.filter(pk="FCRM Settings").update(
        brand_name="Acme", access_key="fx-provider-key", currency="USD"
    )
    return FCRMSettings.objects.get(pk="FCRM Settings")


def test_everyone_can_read_the_app_settings(alice, app_settings, api_as):
    body = api_as(alice).get(SETTINGS).json()["message"]
    assert body["crm_timeline_timestamp_format"] == "Relative"


def test_an_ordinary_user_cannot_write_the_app_settings(alice, app_settings, api_as):
    response = api_as(alice).patch(SETTINGS, {"brand_name": "Pwned"}, format="json")
    assert response.status_code == 403

    app_settings.refresh_from_db()
    assert app_settings.brand_name == "Acme"


def test_a_manager_can_write_the_app_settings(manager, app_settings, api_as):
    response = api_as(manager).patch(SETTINGS, {"brand_name": "Acme Corp"}, format="json")
    assert response.status_code == 200, response.content[:300]


def test_the_exchange_rate_key_is_hidden_from_an_ordinary_user(alice, app_settings, api_as):
    body = api_as(alice).get(SETTINGS).json()["message"]
    assert "access_key" not in body


def test_a_manager_still_sees_the_exchange_rate_key(manager, app_settings, api_as):
    body = api_as(manager).get(SETTINGS).json()["message"]
    assert body["access_key"] == "fx-provider-key"


def test_an_open_singleton_is_still_readable(alice, api_as):
    response = api_as(alice).get(f"{SETTINGS}value/", {"field": "crm_timeline_timestamp_format"})
    assert response.status_code == 200, response.content[:300]


# --- new: no old test covers these (specs/CONFIGURATION.md section 4.3) -------------------


def test_the_key_is_refused_by_value_to_an_ordinary_user(alice, app_settings, api_as):
    response = api_as(alice).get(f"{SETTINGS}value/", {"field": "access_key"})
    assert response.status_code == 403


def test_a_manager_reads_the_key_by_value(manager, app_settings, api_as):
    response = api_as(manager).get(f"{SETTINGS}value/", {"field": "access_key"})
    assert response.json() == {"message": "fx-provider-key"}


def test_the_child_table_is_not_a_value(manager, app_settings, api_as):
    response = api_as(manager).get(f"{SETTINGS}value/", {"field": "dropdown_items"})
    assert response.status_code == 417


def test_a_system_manager_writes_it(make_user, app_settings, api_as):
    sysman = make_user("sysman@example.com", roles=["System Manager"])
    response = api_as(sysman).patch(SETTINGS, {"brand_name": "Sys"}, format="json")
    assert response.status_code == 200, response.content[:300]


def test_the_administrator_writes_it_without_its_groups(administrator, app_settings, api_as):
    administrator.groups.clear()
    administrator.clear_roles_cache()
    response = api_as(administrator).patch(SETTINGS, {"brand_name": "Admin"}, format="json")
    assert response.status_code == 200, response.content[:300]


def test_an_unknown_currency_is_refused(manager, app_settings, api_as):
    """`test_currency.py`'s `test_the_dashboard_currency_can_be_chosen`, the FCRM Settings
    case that waited for this milestone."""
    client = api_as(manager)
    assert client.patch(SETTINGS, {"currency": "EUR"}, format="json").status_code == 200
    assert client.patch(SETTINGS, {"currency": "XYZ"}, format="json").status_code == 417
    app_settings.refresh_from_db()
    assert app_settings.currency == "EUR"


def test_a_missing_row_answers_404(alice, api_as):
    FCRMSettings.objects.all().delete()
    assert api_as(alice).get(SETTINGS).status_code == 404


def test_there_is_no_list_route(alice, api_as):
    """PE-11: a settings record has no list route; the root is the record itself."""
    response = api_as(alice).get(SETTINGS, {"filters": '[["access_key", "like", "fx%"]]'})
    body = response.json()["message"]
    assert isinstance(body, dict) and "access_key" not in body
