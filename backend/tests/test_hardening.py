"""A9 and A10 - two hardening items carried over from the phase 0-2 concerns.

**A9** ``logout`` could not revoke anything: ``token_blacklist`` was not installed, so
``RefreshToken.blacklist()`` raised ``AttributeError``, the endpoint swallowed it, and a
captured refresh token stayed usable for its full 7-day lifetime.

**A10** The four underscore fields were writable through the generic endpoint. They are
projections of other tables (PHASE_0_FOUNDATION.md section 3), so a client could make a
document advertise assignees it did not have, until the next rebuild silently overwrote
the value.
"""

from urllib.parse import quote

import json

import pytest

pytestmark = pytest.mark.django_db

LOGIN = "/api/method/login"
LOGOUT = "/api/method/logout"
REFRESH = "/api/method/token/refresh"


# --- A9: logout actually revokes ------------------------------------------------


def _login(api, user, password="secret123"):
    """Log in and leave the client carrying the access token.

    ``logout`` is not ``allow_guest``, so it needs the header set - calling it from an
    unauthenticated client returns 401 and tests nothing.
    """
    response = api.post(LOGIN, {"usr": user.name, "pwd": password}, format="json")
    assert response.status_code == 200, response.json()
    tokens = response.json()["message"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return tokens


def test_refresh_token_works_before_logout(api, alice):
    tokens = _login(api, alice)
    response = api.post(REFRESH, {"refresh": tokens["refresh"]}, format="json")
    assert response.status_code == 200


def test_logout_revokes_the_refresh_token(api, alice):
    """The point of A9. Before ``token_blacklist`` was installed this still returned 200
    and the session could be renewed indefinitely after logging out."""
    tokens = _login(api, alice)

    assert api.post(LOGOUT, {"refresh": tokens["refresh"]}, format="json").status_code == 200

    response = api.post(REFRESH, {"refresh": tokens["refresh"]}, format="json")
    assert response.status_code != 200, "the refresh token still works after logout"


def test_logout_without_a_token_still_succeeds(api, alice):
    """The client may have already dropped it; logout must not error."""
    _login(api, alice)
    assert api.post(LOGOUT, {}, format="json").status_code == 200


def test_a_rotated_refresh_token_invalidates_its_predecessor(api, alice):
    """``ROTATE_REFRESH_TOKENS`` + ``BLACKLIST_AFTER_ROTATION``.

    Makes a refresh token single-use, so one captured in transit is only good until the
    legitimate client next refreshes.
    """
    tokens = _login(api, alice)
    first = tokens["refresh"]

    rotated = api.post(REFRESH, {"refresh": first}, format="json")
    assert rotated.status_code == 200
    assert rotated.json()["message"].get("refresh"), "rotation did not return a new token"

    assert api.post(REFRESH, {"refresh": first}, format="json").status_code != 200, (
        "the old refresh token is still usable after rotation"
    )


# --- A10: the underscore caches are not client-writable --------------------------

URL = "/api/resource/" + quote("Phase Zero Widget")


@pytest.mark.parametrize(
    "field, value",
    [
        ("_assign", ["someone@example.com"]),
        ("_liked_by", ["someone@example.com"]),
        ("_comments", [{"comment": "spoofed"}]),
        ("_user_tags", "spoofed"),
    ],
)
def test_underscore_fields_are_ignored_on_create(auth_api, field, value):
    response = auth_api.post(URL, {"label": "x", field: value}, format="json")

    assert response.status_code == 201
    stored = response.json()["data"].get(field)
    assert stored != value, f"{field} was accepted from the client"


def test_assign_cannot_be_spoofed_on_update(auth_api):
    """The one that matters: ``_assign`` is what the UI shows as the assignee list.

    Not an access-control hole - the permission layer queries ``ToDo``, never this - but
    a document should not be able to advertise an assignee that no ToDo backs.
    """
    created = auth_api.post(URL, {"label": "x"}, format="json").json()["data"]
    detail = f"{URL}/{quote(created['name'])}"

    auth_api.put(detail, {"label": "x", "_assign": ["victim@example.com"]}, format="json")

    # A JSON string on the wire (FINDINGS.md 40); decode before comparing.
    assert json.loads(auth_api.get(detail).json()["data"]["_assign"]) != ["victim@example.com"]


def test_audit_fields_are_still_read_only(auth_api):
    """The original four - guarding against a careless edit to READ_ONLY_FIELDS."""
    response = auth_api.post(
        URL, {"label": "x", "owner": "someone@example.com"}, format="json"
    )
    assert response.status_code == 201
    assert response.json()["data"]["owner"] != "someone@example.com"
