"""``frappe.onboarding.get_onboarding_status`` / ``update_user_onboarding_status``.

FINDINGS.md 39: frappe-ui's ``useOnboarding`` calls both from inside the package, on
every screen that shows the onboarding panel, and neither was served. The status is a
JSON object on the User row keyed ``<app>_onboarding_status`` (``frappe/onboarding.py``).
"""

import json

import pytest

pytestmark = pytest.mark.django_db

GET = "/api/method/frappe.onboarding.get_onboarding_status"
UPDATE = "/api/method/frappe.onboarding.update_user_onboarding_status"

STEPS = [
    {"name": "create_first_lead", "completed": True, "skipped": False},
    {"name": "invite_your_team", "completed": False, "skipped": True},
]


def test_a_user_with_no_status_gets_an_empty_object(auth_api):
    response = auth_api.post(GET, {}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"] == {}


def test_an_update_stores_the_steps_under_the_app_key(auth_api, alice):
    """``onboarding.js:121-126``: ``steps`` is stringified, ``appName`` is the app."""
    response = auth_api.post(
        UPDATE, {"steps": json.dumps(STEPS), "appName": "frappecrm"}, format="json"
    )
    assert response.status_code == 200, response.content[:300]

    assert auth_api.post(GET, {}, format="json").json()["message"] == {
        "frappecrm_onboarding_status": STEPS
    }
    alice.refresh_from_db()
    assert json.loads(alice.onboarding_status) == {"frappecrm_onboarding_status": STEPS}


def test_an_update_keeps_other_apps_keys(auth_api, alice):
    alice.onboarding_status = json.dumps({"helpdesk_onboarding_status": [{"name": "x"}]})
    alice.save()

    auth_api.post(UPDATE, {"steps": json.dumps(STEPS), "appName": "frappecrm"}, format="json")

    assert auth_api.post(GET, {}, format="json").json()["message"] == {
        "helpdesk_onboarding_status": [{"name": "x"}],
        "frappecrm_onboarding_status": STEPS,
    }


def test_the_first_update_works_for_a_user_with_no_status(auth_api):
    """Upstream 500s here (``UPSTREAM_BUGS_PHASE_3-6.md`` 40): ``frappe.parse_json`` of an
    unset column is ``None``, which it then subscripts."""
    response = auth_api.post(
        UPDATE, {"steps": json.dumps(STEPS), "appName": "frappecrm"}, format="json"
    )
    assert response.status_code == 200, response.content[:300]


def test_steps_that_are_not_json_are_refused(auth_api):
    response = auth_api.post(UPDATE, {"steps": "not json", "appName": "frappecrm"}, format="json")
    assert response.status_code == 417
    assert response.json()["exc_type"] == "ValidationError"


def test_a_guest_is_refused(api):
    assert api.post(GET, {}, format="json").status_code == 401
    assert api.post(UPDATE, {"steps": "[]", "appName": "x"}, format="json").status_code == 401
