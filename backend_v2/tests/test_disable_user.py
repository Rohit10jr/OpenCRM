import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login/"
ME = "/api/v1/auth/me/"


def _login(user):
    return APIClient().post(LOGIN, {"usr": user.name, "pwd": "secret123"}, format="json").json()["message"]


def _whoami(access):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client.get(ME)


def test_saving_an_enabled_user_keeps_their_tokens(alice):
    before = _login(alice)
    alice.first_name = "Changed"
    alice.save()
    assert _whoami(before["access"]).status_code == 200


def test_a_user_can_be_created_disabled():
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user("off@example.com", "x", enabled=False)
    assert get_user_model().objects.get(pk=user.pk).enabled is False
