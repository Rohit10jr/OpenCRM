"""Disabling a user revokes their tokens, and Django admin is where it is done.

Upstream logs a disabled user out (`frappe/core/doctype/user/user.py:272-274`). A disabled
user's tokens were already refused here, but re-enabling the account brought back every
token that had not expired (KNOWN_ISSUES §6).
"""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse
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


def _change_url(user) -> str:
    return reverse("admin:accounts_user_change", args=[user.pk])


@pytest.fixture
def admin_client():
    client = Client()
    client.force_login(User.objects.create_superuser("root@example.com", "x"))
    return client


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


def test_admin_disables_a_user_and_revokes_their_tokens(admin_client, alice):
    before = _login(alice)

    response = admin_client.post(_change_url(alice), {})

    assert response.status_code == 302, response.content[:300]
    alice.refresh_from_db()
    assert alice.enabled is False
    assert alice.token_version == 1
    assert _whoami(before["access"]).status_code == 401


def test_admin_enables_a_user(admin_client, alice):
    User.objects.filter(pk=alice.pk).update(enabled=False)

    response = admin_client.post(_change_url(alice), {"enabled": "on"})

    assert response.status_code == 302, response.content[:300]
    alice.refresh_from_db()
    assert alice.enabled is True


def test_admin_changes_nothing_but_enabled(admin_client, alice):
    groups = set(alice.groups.values_list("name", flat=True))

    admin_client.post(
        _change_url(alice),
        {"enabled": "on", "is_staff": "on", "is_superuser": "on", "email": "new@example.com"},
    )

    alice.refresh_from_db()
    assert alice.is_staff is False
    assert alice.is_superuser is False
    assert alice.email != "new@example.com"
    assert set(alice.groups.values_list("name", flat=True)) == groups


def test_administrator_cannot_be_disabled_in_admin(admin_client, administrator):
    response = admin_client.get(_change_url(administrator))
    assert response.status_code == 200
    assert b'name="enabled"' not in response.content

    admin_client.post(_change_url(administrator), {})

    administrator.refresh_from_db()
    assert administrator.enabled is True


def test_admin_cannot_add_or_delete_users(admin_client, alice):
    assert admin_client.get(reverse("admin:accounts_user_add")).status_code == 403
    assert admin_client.get(reverse("admin:accounts_user_delete", args=[alice.pk])).status_code == 403
    assert User.objects.filter(pk=alice.pk).exists()


def test_a_non_staff_user_cannot_reach_the_page(alice):
    client = Client()
    client.force_login(alice)

    response = client.post(_change_url(alice), {})

    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]
    alice.refresh_from_db()
    assert alice.enabled is True
