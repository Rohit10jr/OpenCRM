"""KNOWN_ISSUES §6, option 3 — revoking access tokens that have already been issued.

Access tokens were checked by signature alone, so `logout_all_sessions` and a password
change stopped new tokens being minted but left every issued one working until it expired.
The fix stamps the user with an integer `token_version`, copies it into each token as a
claim, and refuses a token whose claim no longer matches.

Integer, not a `password_changed_at` timestamp: `iat` has one-second resolution, so a token
issued in the same second as the change would compare as "not older" and slip through.

Upstream has no counterpart: it uses server-side sessions, which die when deleted.
"""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from rest_framework.test import APIClient

from frappe_core import password_reset
from frappe_platform.models import User

pytestmark = pytest.mark.django_db

LOGIN = "/api/method/login"
LOGOUT = "/api/method/logout"
REFRESH = "/api/method/token/refresh"
WHOAMI = "/api/method/frappe.auth.get_logged_user"
UPDATE = "/api/method/frappe.core.doctype.user.user.update_password"
NEW_PASSWORD = "Str0ng!Passw0rd"


def _login(user, password="secret123") -> dict:
    response = APIClient().post(LOGIN, {"usr": user.name, "pwd": password}, format="json")
    assert response.status_code == 200, response.json()
    return response.json()["message"]


def _whoami(access: str):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client.get(WHOAMI)


def _refresh(refresh: str):
    return APIClient().post(REFRESH, {"refresh": refresh}, format="json")


def _update_password(**payload):
    return APIClient().post(UPDATE, payload, format="json")


def _bump(user) -> None:
    from django.db.models import F

    User.objects.filter(pk=user.pk).update(token_version=F("token_version") + 1)


# ---------------------------------------------------------------------------
# The case the issue is about
# ---------------------------------------------------------------------------


def test_logout_all_sessions_revokes_an_access_token_issued_before_it(alice):
    """The test KNOWN_ISSUES §6 says to write first. Failed before the fix: 200."""
    before = _login(alice)
    assert _whoami(before["access"]).status_code == 200

    response = _update_password(
        key=password_reset.issue_key(alice), new_password=NEW_PASSWORD, logout_all_sessions=1
    )
    assert response.status_code == 200, response.json()

    assert _whoami(before["access"]).status_code == 401
    # The device that made the change stays signed in, as upstream's `keep_current` does.
    assert _whoami(response.json()["message"]["access"]).status_code == 200


def test_logout_all_sessions_reaches_a_refresh_token_that_has_been_rotated(alice):
    """The version check stops a rotated refresh token. Until 2 Nov 2026 it was the only
    thing that did: the refresh endpoint rotated without `outstand()`, so the rotated token
    was never in `OutstandingToken` for `_blacklist_outstanding_tokens` to find."""
    rotated = _refresh(_login(alice)["refresh"]).json()["message"]

    _update_password(
        key=password_reset.issue_key(alice), new_password=NEW_PASSWORD, logout_all_sessions=1
    )

    assert _refresh(rotated["refresh"]).status_code == 401
    assert _whoami(rotated["access"]).status_code == 401


def test_a_rotated_refresh_token_is_outstanding_and_gets_blacklisted(alice):
    """KNOWN_ISSUES §6, found while building it. The refresh endpoint now records the token
    it rotates to, as SimpleJWT's `TokenRefreshSerializer` does, so `logout_all_sessions`
    blacklists it as well as refusing it by version."""
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )
    from rest_framework_simplejwt.tokens import RefreshToken

    rotated = _refresh(_login(alice)["refresh"]).json()["message"]["refresh"]
    jti = RefreshToken(rotated)["jti"]
    assert OutstandingToken.objects.filter(jti=jti, user=alice).exists()

    _update_password(
        key=password_reset.issue_key(alice), new_password=NEW_PASSWORD, logout_all_sessions=1
    )

    assert BlacklistedToken.objects.filter(token__jti=jti).exists()


def test_a_password_set_without_the_box_ticked_keeps_other_sessions(alice):
    """As upstream: `update_password` clears sessions only when `logout_all_sessions` is set
    (`frappe/utils/password.py:150`)."""
    before = _login(alice)

    response = _update_password(key=password_reset.issue_key(alice), new_password=NEW_PASSWORD)
    assert response.status_code == 200, response.json()

    assert _whoami(before["access"]).status_code == 200
    assert _whoami(response.json()["message"]["access"]).status_code == 200


def test_a_password_change_with_the_box_ticked_revokes_the_old_access_token(alice):
    """The old-password path of `update_password`. Its response is a fresh token pair, and
    that pair must carry the new version or the user is signed out by their own change."""
    before = _login(alice)

    response = _update_password(
        usr=alice.name,
        old_password="secret123",
        new_password=NEW_PASSWORD,
        logout_all_sessions=1,
    )
    assert response.status_code == 200, response.json()

    assert _whoami(before["access"]).status_code == 401
    fresh = response.json()["message"]
    assert _whoami(fresh["access"]).status_code == 200
    assert _refresh(fresh["refresh"]).status_code == 200


def test_a_single_logout_does_not_sign_out_another_session(alice):
    """`logout` blacklists its own refresh token and nothing else. Bumping the version there
    would sign the user out of every other device."""
    laptop = _login(alice)
    phone = _login(alice)

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {laptop['access']}")
    assert client.post(LOGOUT, {"refresh": laptop["refresh"]}, format="json").status_code == 200

    assert _whoami(phone["access"]).status_code == 200
    assert _refresh(phone["refresh"]).status_code == 200


# ---------------------------------------------------------------------------
# Tokens from before the change
# ---------------------------------------------------------------------------


def test_a_token_without_the_claim_works_while_the_version_is_zero(alice):
    """Tokens issued before this change carry no claim; deploying must not log everyone
    out. `RefreshToken.for_user` alone does not add it, which is what makes this one."""
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(alice)
    assert "token_version" not in refresh.access_token
    assert _whoami(str(refresh.access_token)).status_code == 200
    assert _refresh(str(refresh)).status_code == 200


def test_a_token_without_the_claim_counts_as_version_zero(alice):
    from rest_framework_simplejwt.tokens import RefreshToken

    access = str(RefreshToken.for_user(alice).access_token)
    _bump(alice)
    assert _whoami(access).status_code == 401


def test_issued_tokens_carry_the_users_version(alice):
    from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

    _bump(alice)
    _bump(alice)
    tokens = _login(alice)

    assert RefreshToken(tokens["refresh"])["token_version"] == 2
    assert AccessToken(tokens["access"])["token_version"] == 2
    assert _whoami(tokens["access"]).status_code == 200


# ---------------------------------------------------------------------------
# The refusal
# ---------------------------------------------------------------------------


def test_a_stale_token_is_refused_like_an_expired_one(alice):
    """`frontend/src/auth/jwtRequest.js:isAuthError` refreshes on a 401 or an
    `AuthenticationError`. A stale token must look the same as any other dead one."""
    stale = _login(alice)["access"]
    _bump(alice)

    revoked = _whoami(stale)
    garbage = _whoami("not-a-jwt")

    assert revoked.status_code == garbage.status_code == 401
    assert revoked.json()["exc_type"] == garbage.json()["exc_type"] == "AuthenticationError"
    assert revoked.json()["message"] == garbage.json()["message"]


def test_a_stale_refresh_token_is_refused_at_refresh(alice):
    """Belt and braces alongside the blacklist: this bump blacklists nothing."""
    tokens = _login(alice)
    _bump(alice)

    response = _refresh(tokens["refresh"])
    assert response.status_code == 401
    assert response.json()["exc_type"] == "AuthenticationError"


def test_the_check_costs_no_extra_query(alice, django_assert_num_queries):
    """The user row is already loaded to authenticate; the comparison must use it."""
    from frappe_core.authentication import VersionedJWTAuthentication

    access = _login(alice)["access"]
    request = RequestFactory().get("/", HTTP_AUTHORIZATION=f"Bearer {access}")

    with django_assert_num_queries(1):
        user, _ = VersionedJWTAuthentication().authenticate(request)
    assert user.pk == alice.pk


def test_the_file_route_refuses_a_stale_token(alice):
    """`frappe_core/file_views.py` authenticates on its own, by header or by cookie."""
    from frappe_core.file_views import ACCESS_COOKIE, authenticated_user

    access = _login(alice)["access"]
    by_header = RequestFactory().get("/", HTTP_AUTHORIZATION=f"Bearer {access}")
    by_cookie = RequestFactory().get("/")
    by_cookie.COOKIES[ACCESS_COOKIE] = access
    assert authenticated_user(by_header) == authenticated_user(by_cookie) == alice.pk

    _bump(alice)

    assert authenticated_user(by_header) is None
    assert authenticated_user(by_cookie) is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_a_websocket_connect_with_a_stale_token_is_refused(alice):
    from channels.db import database_sync_to_async
    from channels.routing import URLRouter
    from channels.testing import WebsocketCommunicator

    from config.routing import websocket_urlpatterns
    from frappe_core.api.auth import issue_tokens

    tokens = await database_sync_to_async(issue_tokens)(alice)
    await database_sync_to_async(_bump)(alice)

    communicator = WebsocketCommunicator(
        URLRouter(websocket_urlpatterns), f"/ws/realtime?token={tokens['access']}"
    )
    connected, _ = await communicator.connect()
    assert connected is False
    await communicator.disconnect()


# ---------------------------------------------------------------------------
# The field is not on the wire
# ---------------------------------------------------------------------------


def test_the_version_is_not_readable(alice, auth_api):
    body = auth_api.get(f"/api/resource/User/{alice.pk}").json()["data"]
    assert "token_version" not in body


def test_the_version_cannot_be_filtered_on(alice, auth_api):
    response = auth_api.get("/api/resource/User", {"filters": '[["token_version","=",0]]'})
    assert response.status_code == 400, response.content[:300]
    assert "data" not in response.json()


def test_the_version_cannot_be_written(alice, auth_api):
    """Writing it back to an old value would revive revoked tokens."""
    auth_api.put(f"/api/resource/User/{alice.pk}", {"token_version": 5}, format="json")
    alice.refresh_from_db()
    assert alice.token_version == 0
