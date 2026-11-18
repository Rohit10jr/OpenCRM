"""Ported from ``backend/tests/test_onboarding_status.py`` (REBUILD_PLAN S14).

`frappe.onboarding.get_onboarding_status` is `GET /api/v1/onboarding/status/` and
`update_user_onboarding_status` is `POST` on the same route (specs/CONFIGURATION.md 4.2).
Expected answers are unchanged.
"""

import json

import pytest

pytestmark = pytest.mark.django_db

STATUS = "/api/v1/onboarding/status/"

STEPS = [
    {"name": "create_first_lead", "completed": True, "skipped": False},
    {"name": "invite_your_team", "completed": False, "skipped": True},
]


def test_a_user_with_no_status_gets_an_empty_object(auth_api):
    response = auth_api.get(STATUS)
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"] == {}


def test_an_update_stores_the_steps_under_the_app_key(auth_api, alice):
    response = auth_api.post(
        STATUS, {"steps": json.dumps(STEPS), "appName": "frappecrm"}, format="json"
    )
    assert response.status_code == 200, response.content[:300]

    assert auth_api.get(STATUS).json()["message"] == {"frappecrm_onboarding_status": STEPS}
    alice.refresh_from_db()
    assert json.loads(alice.onboarding_status) == {"frappecrm_onboarding_status": STEPS}


def test_an_update_keeps_other_apps_keys(auth_api, alice):
    alice.onboarding_status = json.dumps({"helpdesk_onboarding_status": [{"name": "x"}]})
    alice.save()

    auth_api.post(STATUS, {"steps": json.dumps(STEPS), "appName": "frappecrm"}, format="json")

    assert auth_api.get(STATUS).json()["message"] == {
        "helpdesk_onboarding_status": [{"name": "x"}],
        "frappecrm_onboarding_status": STEPS,
    }


def test_the_first_update_works_for_a_user_with_no_status(auth_api):
    """Upstream 500s here (UPSTREAM_BUGS.md 40)."""
    response = auth_api.post(
        STATUS, {"steps": json.dumps(STEPS), "appName": "frappecrm"}, format="json"
    )
    assert response.status_code == 200, response.content[:300]


def test_steps_that_are_not_json_are_refused(auth_api):
    response = auth_api.post(STATUS, {"steps": "not json", "appName": "frappecrm"}, format="json")
    assert response.status_code == 417
    assert response.json()["exc_type"] == "ValidationError"


def test_a_guest_is_refused(api):
    assert api.get(STATUS).status_code == 401
    assert api.post(STATUS, {"steps": "[]", "appName": "x"}, format="json").status_code == 401


# --- new: no old test covers these (specs/CONFIGURATION.md section 4.2) -------------------


def test_app_name_is_required(auth_api):
    response = auth_api.post(STATUS, {"steps": "[]"}, format="json")
    assert response.status_code == 417
    assert response.json()["message"] == "appName is required"


def test_steps_may_be_a_list_and_the_update_answers_null(auth_api):
    response = auth_api.post(STATUS, {"steps": STEPS, "appName": "frappecrm"}, format="json")
    assert response.json() == {"message": None}


def test_the_update_leaves_the_row_timestamps_alone(auth_api, alice):
    before = alice.modified
    auth_api.post(STATUS, {"steps": "[]", "appName": "frappecrm"}, format="json")
    alice.refresh_from_db()
    assert alice.modified == before
