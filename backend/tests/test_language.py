"""The ``Language`` doctype: docs/FINDINGS.md 58.

Settings -> Preferences has a Language picker, a Link to ``Language``. The port had no
such doctype, so its search answered 404 and the dropdown was empty. Shapes follow
``frappe/core/doctype/language`` and ``frappe/desk/search.py`` for a doctype with
``show_title_field_in_link``.
"""

import csv

import pytest

from crm_app import setup
from frappe_core.session import session_user
from frappe_platform.models import Language, User

pytestmark = pytest.mark.django_db

SEARCH = "/api/method/frappe.desk.search.search_link"


@pytest.fixture
def languages(administrator):
    with session_user(administrator.name):
        return setup.add_languages()


def source_rows() -> list[dict]:
    with setup.LANGUAGES.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def search(client, **params):
    response = client.post(SEARCH, {"doctype": "Language", "txt": "", **params}, format="json")
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]


def test_the_seed_writes_the_frameworks_list_once(languages, administrator):
    rows = source_rows()
    assert languages == len(rows) == Language.objects.count()
    english = Language.objects.get(pk="en")
    assert english.language_name == "English" and english.enabled is True
    assert Language.objects.filter(enabled=True).count() == sum(r["enabled"] == "1" for r in rows)
    with session_user(administrator.name):
        assert setup.add_languages() == 0


def test_the_picker_offers_enabled_languages_by_name(auth_api, languages):
    """Value is the code, label the name, description the code: ``build_for_autosuggest``
    for ``show_title_field_in_link``. A disabled language is not offered."""
    results = search(auth_api, txt="Engl")
    assert {"value": "en", "label": "English", "description": "en"} in results
    assert "en-GB" not in [row["value"] for row in results]

    offered = {row["value"] for row in search(auth_api, page_length=200)}
    assert offered == set(Language.objects.filter(enabled=True).values_list("pk", flat=True))


def test_a_disabled_language_shows_only_when_asked_for(auth_api, languages):
    included = search(auth_api, txt="United Kingdom", filters={"include_disabled": 1})
    assert [row["value"] for row in included] == ["en-GB"]


def test_the_choice_is_saved_on_the_user(auth_api, alice, languages):
    response = auth_api.post(
        "/api/method/frappe.client.set_value",
        {"doctype": "User", "name": alice.name, "fieldname": {"language": "fr"}},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    assert User.objects.get(pk=alice.name).language == "fr"


def test_everyone_reads_the_list_and_only_an_admin_changes_it(auth_api, api_as, administrator, languages):
    assert auth_api.get("/api/resource/Language/en").status_code == 200
    refused = auth_api.put("/api/resource/Language/en", {"enabled": 0}, format="json")
    assert refused.status_code == 403
    allowed = api_as(administrator).put("/api/resource/Language/fr", {"enabled": 0}, format="json")
    assert allowed.status_code == 200, allowed.content[:300]
    assert Language.objects.get(pk="fr").enabled is False
