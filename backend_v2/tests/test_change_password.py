"""`crm.api.user.change_password` → `POST /api/v1/auth/change-password/`.

Ported (REBUILD_PLAN S14) from ``backend/tests/test_phase3_endpoints.py:494, :506, :515``
and ``backend/tests/test_security.py:182, :190, :205``; expected answers unchanged.
"""

import pytest

pytestmark = pytest.mark.django_db
CHANGE_PW = "/api/v1/auth/change-password/"
LOGIN = "/api/v1/auth/login/"


def _auth(api, user):
    tokens = api.post(LOGIN, {"usr": user.name, "pwd": "secret123"}, format="json").json()["message"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return api


# --- test_phase3_endpoints.py ------------------------------------------------------------


def test_change_password_rejects_reuse_with_the_upstream_message(auth_api):
    response = auth_api.post(
        CHANGE_PW, {"old_password": "secret123", "new_password": "secret123"}, format="json"
    )
    assert response.json()["messages"] == [
        "New password cannot be the same as current password. "
        "Please choose a different password."
    ]


def test_change_password_rejects_a_wrong_current_password(auth_api):
    response = auth_api.post(
        CHANGE_PW, {"old_password": "wrong", "new_password": "Str0ng!Passphrase42"}, format="json"
    )
    assert response.json()["messages"] == ["Incorrect current password. Please try again."]


def test_change_password_succeeds_and_actually_changes_it(auth_api, alice):
    response = auth_api.post(
        CHANGE_PW,
        {"old_password": "secret123", "new_password": "Str0ng!Passphrase42"},
        format="json",
    )
    assert response.status_code == 200
    alice.refresh_from_db()
    assert alice.check_password("Str0ng!Passphrase42")


# --- test_security.py ----------------------------------------------------------------------


def test_change_password_works(api, alice):
    client = _auth(api, alice)
    response = client.post(
        CHANGE_PW, {"old_password": "secret123", "new_password": "N3wPassw0rd!x"}, format="json"
    )
    assert response.status_code == 200


def test_wrong_current_password_eventually_locks(api, alice, settings):
    settings.LOGIN_MAX_CONSECUTIVE_ATTEMPTS = 2
    client = _auth(api, alice)

    for _ in range(3):
        client.post(
            CHANGE_PW, {"old_password": "wrong", "new_password": "N3wPassw0rd!x"}, format="json"
        )

    response = client.post(
        CHANGE_PW, {"old_password": "secret123", "new_password": "N3wPassw0rd!x"}, format="json"
    )
    assert "Too many failed attempts" in str(response.json())


def test_the_endpoint_is_capped_at_five_calls(api, alice):
    client = _auth(api, alice)

    codes = [
        client.post(
            CHANGE_PW,
            {"old_password": "secret123", "new_password": "same-as-before"},
            format="json",
        ).status_code
        for _ in range(7)
    ]

    assert 429 in codes, f"never rate limited: {codes}"


# --- new: no old test covers these (specs/ACCOUNTS.md section 4.4) -----------------------


def test_a_weak_password_is_refused_with_the_validator_messages(auth_api):
    response = auth_api.post(
        CHANGE_PW, {"old_password": "secret123", "new_password": "123"}, format="json"
    )
    assert response.status_code == 417
    assert response.json()["message"].startswith("Password is too weak. ")


def test_success_answers_the_upstream_sentence(auth_api):
    response = auth_api.post(
        CHANGE_PW,
        {"old_password": "secret123", "new_password": "Str0ng!Passphrase42"},
        format="json",
    )
    assert response.json() == {"message": "Password Updated Successfully"}


def test_an_anonymous_caller_is_refused_before_the_view(api):
    assert api.post(CHANGE_PW, {}, format="json").status_code in (401, 403)
