"""Country (specs/CONFIGURATION.md 4.2).

Ported (REBUILD_PLAN S14):

- `test_the_countries_come_from_the_frameworks_list` from
  ``backend/tests/test_seed_defaults.py``; there `seed_defaults` writes the rows, here the
  data migration does.
- `test_the_country_picker_searches_countries` from ``backend/tests/test_address.py:229-236``.
  Changed expectation: the old test seeds India alone and expects exactly ``["India"]``;
  here the migration has written all 250 countries, and "ind" also matches Indonesia and
  others, so the check is that India is among the results.
- `test_countries_are_read_only_below_system_manager` from ``test_address.py:264-270``.

The rest is new.
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


def test_the_country_picker_searches_countries(auth_api):
    response = auth_api.get(f"{COUNTRIES}search/", {"txt": "ind"})
    assert response.status_code == 200, response.content[:300]
    assert "India" in [row["value"] for row in response.json()["message"]]


def test_countries_are_read_only_below_system_manager(auth_api):
    assert auth_api.get(f"{COUNTRIES}India/").status_code == 200
    assert auth_api.patch(f"{COUNTRIES}India/", {"code": "xx"}, format="json").status_code == 403
    created = auth_api.post(COUNTRIES, {"country_name": "Atlantis", "code": "at"}, format="json")
    assert created.status_code == 403
    assert not Country.objects.filter(pk="Atlantis").exists()


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
    assert Country.objects.get(pk=bare).date_format == "dd-mm-yyyy"


def test_the_rows_keep_the_files_order(auth_api):
    """`backend/` saved them one at a time, so the picker's first page (newest first) is
    the file's last rows (A-31 finding 3)."""
    data = reference_rows.json.loads(
        (reference_rows.DATA / "country_info.json").read_text(encoding="utf-8")
    )
    newest_first = list(Country.objects.order_by("-modified").values_list("pk", flat=True))
    assert newest_first == list(reversed(list(data)))
    response = auth_api.get(f"{COUNTRIES}search/", {"txt": ""})
    assert [row["value"] for row in response.json()["message"]] == newest_first[:10]


def test_an_admin_changes_it(api_as, administrator):
    allowed = api_as(administrator).patch(f"{COUNTRIES}India/", {"code": "IN"}, format="json")
    assert allowed.status_code == 200, allowed.content[:300]
