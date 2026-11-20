"""Ported from the `user_settings` cases of ``backend/tests/test_form_load.py`` (`:333`,
`:341`, `:354`, `:409`, `:422`, `:431`; REBUILD_PLAN S14).

`frappe.model.utils.user_settings.save` and `.get` are `POST` and `GET
/api/v1/user-settings/` (specs/CONFIGURATION.md 4.5). Expected answers are unchanged.
The cases that read settings back through `getdoctype` (`:366`, `:378`, `:384`, `:394`)
come with it (CF5c).
"""

import json

import pytest

from configuration.models import UserSettings

pytestmark = pytest.mark.django_db

SETTINGS = "/api/v1/user-settings/"


def save_settings(client, doctype: str, settings: dict):
    return client.post(
        SETTINGS, {"doctype": doctype, "user_settings": json.dumps(settings)}, format="json"
    )


def stored(client, doctype: str):
    return json.loads(client.get(SETTINGS, {"doctype": doctype}).json()["message"])


def test_save_returns_what_was_sent(auth_api):
    response = save_settings(auth_api, "CRM Deal", {"GridView": {"CRM Contacts": ["email"]}})

    assert response.status_code == 200
    assert response.json()["message"] == {"GridView": {"CRM Contacts": ["email"]}}


def test_save_merges_at_the_top_level(auth_api):
    save_settings(auth_api, "CRM Deal", {"GridView": {"CRM Contacts": ["email"]}})
    save_settings(auth_api, "CRM Deal", {"List": {"page_length": 40}})

    assert stored(auth_api, "CRM Deal") == {
        "GridView": {"CRM Contacts": ["email"]},
        "List": {"page_length": 40},
    }


def test_a_second_save_of_the_same_key_replaces_it_wholesale(auth_api):
    save_settings(auth_api, "CRM Deal", {"GridView": {"CRM Contacts": ["email"]}})
    save_settings(auth_api, "CRM Deal", {"GridView": {"CRM Products": ["item"]}})

    assert stored(auth_api, "CRM Deal") == {"GridView": {"CRM Products": ["item"]}}


def test_save_accepts_a_dict_as_well_as_a_json_string(auth_api):
    response = auth_api.post(
        SETTINGS,
        {"doctype": "CRM Deal", "user_settings": {"List": {"page_length": 7}}},
        format="json",
    )

    assert response.status_code == 200
    assert stored(auth_api, "CRM Deal") == {"List": {"page_length": 7}}


def test_empty_settings_are_stored_as_an_empty_object(auth_api):
    response = auth_api.post(SETTINGS, {"doctype": "CRM Deal", "user_settings": ""}, format="json")

    assert response.status_code == 200
    assert response.json()["message"] == {}
    assert auth_api.get(SETTINGS, {"doctype": "CRM Deal"}).json()["message"] == "{}"


def test_saving_settings_needs_a_session(api):
    response = api.post(SETTINGS, {"doctype": "CRM Deal", "user_settings": "{}"}, format="json")

    assert response.status_code == 401


# --- new: no old test covers these (specs/CONFIGURATION.md section 4.5) -------------------


def test_get_answers_the_stored_string(auth_api):
    save_settings(auth_api, "CRM Deal", {"List": {"page_length": 40}})
    answer = auth_api.get(SETTINGS, {"doctype": "CRM Deal"}).json()["message"]
    assert isinstance(answer, str) and json.loads(answer) == {"List": {"page_length": 40}}


def test_get_with_nothing_saved_is_an_empty_object_string(auth_api):
    assert auth_api.get(SETTINGS, {"doctype": "CRM Lead"}).json() == {"message": "{}"}


def test_json_that_is_not_an_object_becomes_empty(auth_api):
    response = auth_api.post(SETTINGS, {"doctype": "CRM Deal", "user_settings": "[1, 2]"}, format="json")
    assert response.json() == {"message": {}}


def test_each_user_has_only_their_own_row(auth_api, api_as, bob, alice):
    save_settings(auth_api, "CRM Deal", {"List": {"page_length": 40}})
    save_settings(api_as(bob), "CRM Deal", {"List": {"page_length": 5}})
    assert stored(auth_api, "CRM Deal") == {"List": {"page_length": 40}}
    assert stored(api_as(bob), "CRM Deal") == {"List": {"page_length": 5}}
    assert UserSettings.objects.filter(doctype="CRM Deal").count() == 2


def test_the_doctype_is_not_validated(auth_api):
    """As backend/: any name is a key."""
    assert save_settings(auth_api, "Not A Doctype", {"x": 1}).status_code == 200
    assert stored(auth_api, "Not A Doctype") == {"x": 1}


def test_pe12b_a_string_that_is_not_json_is_refused(auth_api):
    response = auth_api.post(SETTINGS, {"doctype": "CRM Deal", "user_settings": "{oops"}, format="json")
    assert response.status_code == 417
    assert response.json()["message"] == "User settings must be valid JSON"


def test_pe12b_an_over_long_doctype_is_refused(auth_api):
    response = save_settings(auth_api, "X" * 141, {"x": 1})
    assert response.status_code == 417
    assert response.json()["message"] == "DocType name is too long"


def test_an_over_long_doctype_is_read_as_nothing_saved(auth_api):
    """A-36 finding 3: the length check is on the write only; a read answers "{}"."""
    assert auth_api.get(SETTINGS, {"doctype": "X" * 141}).json() == {"message": "{}"}


@pytest.mark.parametrize("method", ["get", "post"])
def test_pe12b_a_missing_doctype_is_refused(auth_api, method):
    """A-36 finding 5: no row is stored under an empty key."""
    if method == "get":
        response = auth_api.get(SETTINGS)
    else:
        response = auth_api.post(SETTINGS, {"user_settings": "{}"}, format="json")
    assert response.status_code == 417
    assert response.json()["message"] == "DocType is required"
    assert not UserSettings.objects.exists()


def test_the_rows_go_with_their_user(make_user, api_as):
    gone = make_user("gone@example.com", roles=["Sales User"])
    save_settings(api_as(gone), "CRM Deal", {"x": 1})
    gone.delete()
    assert not UserSettings.objects.exists()
