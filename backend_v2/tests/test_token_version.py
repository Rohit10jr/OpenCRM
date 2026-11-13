import pytest
from django.test import RequestFactory
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from accounts.authentication import VersionedJWTAuthentication, bump_token_version

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login/"
LOGOUT = "/api/v1/auth/logout/"
REFRESH = "/api/v1/auth/token/refresh/"
ME = "/api/v1/auth/me/"


def _login(user):
    response = APIClient().post(LOGIN, {"usr": user.name, "pwd": "secret123"}, format="json")
    assert response.status_code == 200, response.json()
    return response.json()["message"]


def _whoami(access):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client.get(ME)


def _refresh(token):
    return APIClient().post(REFRESH, {"refresh": token}, format="json")


def test_a_single_logout_does_not_sign_out_another_session(alice):
    laptop = _login(alice)
    phone = _login(alice)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {laptop['access']}")
    assert client.post(LOGOUT, {"refresh": laptop["refresh"]}, format="json").status_code == 200
    assert _whoami(phone["access"]).status_code == 200
    assert _refresh(phone["refresh"]).status_code == 200


def test_a_token_without_the_claim_works_while_the_version_is_zero(alice):
    refresh = RefreshToken.for_user(alice)
    assert "token_version" not in refresh.access_token
    assert _whoami(str(refresh.access_token)).status_code == 200
    assert _refresh(str(refresh)).status_code == 200


def test_a_token_without_the_claim_counts_as_version_zero(alice):
    access = str(RefreshToken.for_user(alice).access_token)
    bump_token_version(alice)
    assert _whoami(access).status_code == 401


def test_issued_tokens_carry_the_users_version(alice):
    bump_token_version(alice)
    bump_token_version(alice)
    tokens = _login(alice)
    assert RefreshToken(tokens["refresh"])["token_version"] == 2
    assert AccessToken(tokens["access"])["token_version"] == 2
    assert _whoami(tokens["access"]).status_code == 200


def test_a_stale_token_is_refused_like_an_expired_one(alice):
    stale = _login(alice)["access"]
    bump_token_version(alice)
    revoked = _whoami(stale)
    garbage = _whoami("not-a-jwt")
    assert revoked.status_code == garbage.status_code == 401
    assert revoked.json()["exc_type"] == garbage.json()["exc_type"] == "AuthenticationError"
    assert revoked.json()["message"] == garbage.json()["message"]


def test_a_stale_refresh_token_is_refused_at_refresh(alice):
    tokens = _login(alice)
    bump_token_version(alice)
    response = _refresh(tokens["refresh"])
    assert response.status_code == 401
    assert response.json()["exc_type"] == "AuthenticationError"


def test_the_check_costs_no_extra_query(alice, django_assert_num_queries):
    access = _login(alice)["access"]
    request = RequestFactory().get("/", HTTP_AUTHORIZATION=f"Bearer {access}")
    with django_assert_num_queries(1):
        user, _ = VersionedJWTAuthentication().authenticate(request)
    assert user.pk == alice.pk


def test_bump_token_version_refreshes_the_user_instance(alice):
    bump_token_version(alice)
    assert alice.token_version == 1


def test_a_rotated_refresh_token_is_outstanding(alice):
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

    rotated = _refresh(_login(alice)["refresh"]).json()["message"]["refresh"]
    jti = RefreshToken(rotated)["jti"]
    assert OutstandingToken.objects.filter(jti=jti, user=alice).exists()
