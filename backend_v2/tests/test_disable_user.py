"""Disabling a user revokes their tokens, and Django admin is where it is done.

Upstream logs a disabled user out (`frappe/core/doctype/user/user.py:272-274`). A disabled
user's tokens were already refused here, but re-enabling the account brought back every
token that had not expired (KNOWN_ISSUES §6).
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import User

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login/"
REFRESH = "/api/v1/auth/token/refresh/"
WHOAMI = "/api/v1/auth/me/"


def _login(user, password="secret123") -> dict:
    response = APIClient().post(LOGIN, {"usr": user.name, "pwd": password}, format="json")
    assert response.status_code == 200, response.json()
    return response.json()["message"]


def _whoami(access: str):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client.get(WHOAMI)


def test_re_enabling_a_user_does_not_bring_back_their_old_tokens(alice):
    before = _login(alice)
    assert _whoami(before["access"]).status_code == 200

    alice.enabled = False
    alice.save()
    alice.enabled = True
    alice.save()

    assert _whoami(before["access"]).status_code == 401
    assert APIClient().post(REFRESH, {"refresh": before["refresh"]}, format="json").status_code == 401
    # They can sign in again; only the old tokens are gone.
    assert _whoami(_login(alice)["access"]).status_code == 200


def test_saving_an_enabled_user_keeps_their_tokens(alice):
    before = _login(alice)
    alice.first_name = "Changed"
    alice.save()
    assert _whoami(before["access"]).status_code == 200


def test_a_user_can_be_created_disabled():
    user = User.objects.create_user("off@example.com", "x", enabled=False)
    assert User.objects.get(pk=user.pk).enabled is False
