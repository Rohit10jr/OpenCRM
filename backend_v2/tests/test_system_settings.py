"""Ported from ``backend/tests/test_system_settings.py`` (REBUILD_PLAN S14).

`frappe.client.get` on System Settings is `GET /api/v1/system-settings/`;
`frappe.client.set_value` is `PATCH` on the same route (specs/CONFIGURATION.md 4.2).
Expected answers are unchanged, except:

- `test_nobody_deletes_it`: the singleton route has no DELETE, so it answers 405 (PE-1;
  403 from `frappe.client.delete` in backend/).
- Waiting for later work: `test_the_defaults_page_loads_the_row_and_its_options`
  (`getdoctype`, milestone 5); the currency half of
  `test_a_required_format_cannot_be_blanked_and_a_currency_must_exist` (Currency, CF2c).
"""

import pytest

from configuration.models import SYSDEFAULT_FIELDS, SystemSettings

pytestmark = pytest.mark.django_db

BOOT = "/api/v1/boot/"
SETTINGS = "/api/v1/system-settings/"


def sysdefaults(client) -> dict:
    response = client.post(BOOT, {}, format="json")
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]["sysdefaults"]


def set_values(client, **values):
    return client.patch(SETTINGS, values, format="json")


@pytest.fixture
def grace(make_user):
    return make_user(
        "grace@example.com", first_name="Grace", roles=["Sales Manager", "Sales User"]
    )


def test_the_row_starts_from_the_environments_formats(api, settings):
    row = SystemSettings.load_or_create()
    expected = {field: str(settings.FRAPPE_SYSDEFAULTS[field]) for field in SYSDEFAULT_FIELDS}
    assert row.sysdefaults() == expected
    assert sysdefaults(api) == expected


def test_a_system_manager_reads_the_row(api_as, administrator):
    """The read half of `test_the_defaults_page_loads_the_row_and_its_options`."""
    response = api_as(administrator).get(SETTINGS)
    assert response.status_code == 200, response.content[:300]
    doc = response.json()["message"]
    assert doc["name"] == "System Settings"
    assert doc["date_format"] == SystemSettings.load_or_create().date_format


def test_a_saved_format_reaches_every_users_boot(api_as, administrator, auth_api):
    response = set_values(api_as(administrator), date_format="dd.mm.yyyy")
    assert response.status_code == 200, response.content[:300]
    assert sysdefaults(auth_api)["date_format"] == "dd.mm.yyyy"


def test_a_required_format_cannot_be_blanked(api_as, administrator):
    client = api_as(administrator)
    before = SystemSettings.load_or_create().date_format
    assert set_values(client, date_format="").status_code == 417
    assert SystemSettings.load_or_create().date_format == before


@pytest.mark.parametrize("who", ["alice", "grace"])
def test_only_a_system_manager_reads_or_writes_it(api_as, request, who):
    client = api_as(request.getfixturevalue(who))
    assert client.get(SETTINGS).status_code == 403
    assert set_values(client, date_format="dd-mm-yyyy").status_code == 403
    assert client.get(f"{SETTINGS}value/", {"field": "date_format"}).status_code == 403
    assert SystemSettings.load_or_create().date_format != "dd-mm-yyyy"
    assert sysdefaults(client)["date_format"]


def test_a_missing_row_is_written_again_on_the_next_boot(api):
    SystemSettings.objects.all().delete()
    assert sysdefaults(api)["date_format"]
    assert SystemSettings.objects.count() == 1


def test_nobody_deletes_it(api_as, administrator):
    """405 under PE-1: the singleton route has no DELETE."""
    response = api_as(administrator).delete(SETTINGS)
    assert response.status_code == 405, response.content[:300]
    assert SystemSettings.objects.filter(pk="System Settings").exists()


# --- new: no old test covers these (specs/CONFIGURATION.md section 4.2) -------------------


def test_the_rewritten_row_is_written_by_administrator(api):
    SystemSettings.objects.all().delete()
    sysdefaults(api)
    row = SystemSettings.objects.get()
    assert (row.owner_id, row.modified_by_id) == ("Administrator", "Administrator")


def test_the_migration_wrote_the_row():
    """The data migration, not a first request, writes it (decision 13)."""
    assert SystemSettings.objects.filter(pk="System Settings").exists()


def test_an_unknown_choice_is_refused(api_as, administrator):
    assert set_values(api_as(administrator), time_format="hh").status_code == 417


def test_the_administrator_passes_without_its_groups(api_as, administrator):
    administrator.groups.clear()
    administrator.clear_roles_cache()
    assert api_as(administrator).get(SETTINGS).status_code == 200
