"""Country (specs/CONFIGURATION.md 4.2).

`test_the_countries_come_from_the_frameworks_list` is ported from
``backend/tests/test_seed_defaults.py`` (REBUILD_PLAN S14); there `seed_defaults`
writes the rows, here the data migration does. The rest is new: no old test covers the
Country resource or its search.
"""

import importlib

import pytest
from django.apps import apps

from configuration.models import Country

pytestmark = pytest.mark.django_db

COUNTRIES = "/api/v1/countries/"

reference_rows = importlib.import_module("configuration.migrations.0004_reference_rows")


def test_the_countries_come_from_the_frameworks_list():
    assert Country.objects.count() == 250
    india = Country.objects.get(pk="India")
    assert india.code == "in"
    assert "Asia/Kolkata" in india.time_zones
    assert india.date_format and india.time_format


# --- new ------------------------------------------------------------------------------------


def test_a_second_run_writes_nothing():
    assert reference_rows.add_countries(apps) == 0


def test_the_owner_is_administrator():
    india = Country.objects.get(pk="India")
    assert (india.owner_id, india.modified_by_id) == ("Administrator", "Administrator")


def test_a_country_without_formats_gets_the_frameworks_fallbacks():
    """`country.py:53-75`: `dd-mm-yyyy` and `HH:mm:ss` when the file gives none."""
    data = reference_rows.json.loads(
        (reference_rows.DATA / "country_info.json").read_text(encoding="utf-8")
    )
    bare = next(name for name, info in data.items() if not info.get("date_format"))
    row = Country.objects.get(pk=bare)
    assert row.date_format == "dd-mm-yyyy"


def test_the_address_picker_searches_countries(auth_api):
    response = auth_api.get(f"{COUNTRIES}search/", {"txt": "Indi"})
    assert response.status_code == 200, response.content[:300]
    assert "India" in [row["value"] for row in response.json()["message"]]


def test_everyone_reads_it_and_only_an_admin_changes_it(auth_api, api_as, administrator):
    assert auth_api.get(f"{COUNTRIES}India/").status_code == 200
    assert auth_api.patch(f"{COUNTRIES}India/", {"code": "xx"}, format="json").status_code == 403
    allowed = api_as(administrator).patch(f"{COUNTRIES}India/", {"code": "IN"}, format="json")
    assert allowed.status_code == 200, allowed.content[:300]
