import pytest

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login/"
LOGOUT = "/api/v1/auth/logout/"
REFRESH = "/api/v1/auth/token/refresh/"


def _login(api, user):
    response = api.post(LOGIN, {"usr": user.name, "pwd": "secret123"}, format="json")
    assert response.status_code == 200, response.json()
    tokens = response.json()["message"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return tokens


def test_refresh_token_works_before_logout(api, alice):
    tokens = _login(api, alice)
    assert api.post(REFRESH, {"refresh": tokens["refresh"]}, format="json").status_code == 200


def test_logout_revokes_the_refresh_token(api, alice):
    tokens = _login(api, alice)
    assert api.post(LOGOUT, {"refresh": tokens["refresh"]}, format="json").status_code == 200
    assert api.post(REFRESH, {"refresh": tokens["refresh"]}, format="json").status_code != 200


def test_logout_without_a_token_still_succeeds(api, alice):
    _login(api, alice)
    assert api.post(LOGOUT, {}, format="json").status_code == 200


def test_a_rotated_refresh_token_invalidates_its_predecessor(api, alice):
    first = _login(api, alice)["refresh"]
    rotated = api.post(REFRESH, {"refresh": first}, format="json")
    assert rotated.status_code == 200
    assert rotated.json()["message"].get("refresh")
    assert api.post(REFRESH, {"refresh": first}, format="json").status_code != 200
