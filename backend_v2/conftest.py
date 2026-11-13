import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from rest_framework.test import APIClient

from accounts.services import issue_tokens


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def builtin_users(request):
    marker = request.node.get_closest_marker("django_db")
    wants_db = marker is not None or any(
        name in request.fixturenames for name in ("db", "transactional_db")
    )
    if not wants_db:
        return
    transactional = bool(marker and marker.kwargs.get("transaction"))
    request.getfixturevalue("transactional_db" if transactional else "db")
    for name, first_name, user_type in (
        ("Administrator", "Administrator", "System User"),
        ("Guest", "Guest", "Website User"),
    ):
        get_user_model().objects.get_or_create(
            name=name,
            defaults={
                "email": f"{name.lower()}@example.com",
                "first_name": first_name,
                "full_name": first_name,
                "enabled": True,
                "user_type": user_type,
            },
        )


@pytest.fixture
def make_user(db):
    def _make(name, password="secret123", roles=(), **extra):
        user = get_user_model().objects.create_user(name=name, password=password, **extra)
        for role in roles:
            group, _ = Group.objects.get_or_create(name=role)
            user.groups.add(group)
        return user

    return _make


@pytest.fixture
def alice(make_user):
    return make_user("alice@example.com", first_name="Alice", roles=["Sales User"])


@pytest.fixture
def bob(make_user):
    return make_user("bob@example.com", first_name="Bob", roles=["Sales User"])


@pytest.fixture
def administrator(db):
    return get_user_model().objects.get(name="Administrator")


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def api_as():
    def _client(user):
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {issue_tokens(user)['access']}"
        )
        return client

    return _client


@pytest.fixture
def auth_api(alice, api_as):
    return api_as(alice)
