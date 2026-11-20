"""Ported from ``backend/tests/test_language.py`` (REBUILD_PLAN S14).

`frappe.desk.search.search_link` on Language is `GET /api/v1/languages/search/`; the
resource routes are `/api/v1/languages/`; the user's choice is saved through ACCOUNTS'
`PATCH /api/v1/users/<name>/` (specs/CONFIGURATION.md 4.2 and 8). Expected answers are
unchanged. In `backend/` the rows come from `seed_defaults`; here the data migration
writes them, so the old fixture's count is checked against the table.
"""

import csv
import importlib
import json

import pytest
from django.apps import apps

from accounts.models import User
from configuration.models import Language

pytestmark = pytest.mark.django_db

SEARCH = "/api/v1/languages/search/"
LANGUAGES = "/api/v1/languages/"

reference_rows = importlib.import_module("configuration.migrations.0004_reference_rows")


def source_rows() -> list[dict]:
    with (reference_rows.DATA / "languages.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def search(client, **params):
    response = client.get(SEARCH, {"txt": "", **params})
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]


def test_the_seed_writes_the_frameworks_list_once():
    rows = source_rows()
    assert len(rows) == Language.objects.count()
    english = Language.objects.get(pk="en")
    assert english.language_name == "English" and english.enabled is True
    assert Language.objects.filter(enabled=True).count() == sum(r["enabled"] == "1" for r in rows)
    assert reference_rows.add_languages(apps) == 0


def test_the_rows_keep_the_files_order():
    """New (A-31 finding 3): one increasing stamp per row, in file order, as `backend/`
    saved them one at a time."""
    codes = [row["language_code"] for row in source_rows()]
    newest_first = list(Language.objects.order_by("-modified").values_list("pk", flat=True))
    assert newest_first == list(reversed(codes))


def test_the_picker_offers_enabled_languages_by_name(auth_api):
    results = search(auth_api, txt="Engl")
    assert {"value": "en", "label": "English", "description": "en"} in results
    assert "en-GB" not in [row["value"] for row in results]

    offered = {row["value"] for row in search(auth_api, page_length=200)}
    assert offered == set(Language.objects.filter(enabled=True).values_list("pk", flat=True))


def test_a_disabled_language_shows_only_when_asked_for(auth_api):
    included = search(
        auth_api, txt="United Kingdom", filters=json.dumps({"include_disabled": 1})
    )
    assert [row["value"] for row in included] == ["en-GB"]


def test_the_choice_is_saved_on_the_user(auth_api, alice):
    response = auth_api.patch(f"/api/v1/users/{alice.name}/", {"language": "fr"}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert User.objects.get(pk=alice.name).language == "fr"


def test_everyone_reads_the_list_and_only_an_admin_changes_it(auth_api, api_as, administrator):
    assert auth_api.get(f"{LANGUAGES}en/").status_code == 200
    refused = auth_api.patch(f"{LANGUAGES}en/", {"enabled": 0}, format="json")
    assert refused.status_code == 403
    allowed = api_as(administrator).patch(f"{LANGUAGES}fr/", {"enabled": 0}, format="json")
    assert allowed.status_code == 200, allowed.content[:300]
    assert Language.objects.get(pk="fr").enabled is False
