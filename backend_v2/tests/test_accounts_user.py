import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from accounts.roles import (
    ADMINISTRATOR,
    GUEST,
    ROLE_ADMINISTRATOR,
    ROLE_SYSTEM_MANAGER,
    SEEDED_ROLES,
)


pytestmark = pytest.mark.django_db

User = get_user_model()


def test_user_name_and_email_are_lowercased_and_stripped():
    user = User.objects.create_user("  Alice@Example.COM  ")

    assert user.name == "alice@example.com"
    assert user.email == "alice@example.com"


@pytest.mark.parametrize("name", [ADMINISTRATOR, GUEST])
def test_builtin_names_keep_their_capitals(name):
    user = User.objects.get(name=name)

    user.save()

    assert user.name == name


def test_lowercase_administrator_is_different_from_builtin_administrator():
    ordinary = User.objects.create_user("administrator")

    assert ordinary.name == "administrator"
    assert User.objects.filter(name=ADMINISTRATOR).exists()
    assert User.objects.filter(name="administrator").exists()


def test_full_name_defaults_from_first_and_last_name():
    user = User.objects.create_user(
        "person@example.com", first_name="Ada", last_name="Lovelace"
    )

    assert user.full_name == "Ada Lovelace"


def test_is_active_follows_enabled():
    user = User(name="person@example.com", enabled=False)
    assert user.is_active is False

    user.enabled = True
    assert user.is_active is True


def test_get_roles_adds_administrator_only_for_literal_administrator():
    administrator = User.objects.get(name=ADMINISTRATOR)
    ordinary = User.objects.create_user("administrator")

    administrator.groups.clear()
    assert ROLE_ADMINISTRATOR in administrator.get_roles()
    assert ROLE_ADMINISTRATOR not in ordinary.get_roles()


def test_create_superuser_grants_system_manager_not_administrator():
    user = User.objects.create_superuser(
        "Founder@Example.com", password="Str0ng!Passw0rd"
    )

    assert user.name == "founder@example.com"
    assert user.is_staff is True
    assert user.is_superuser is True
    assert ROLE_SYSTEM_MANAGER in user.get_roles()
    assert ROLE_ADMINISTRATOR not in user.get_roles()


def test_seed_migration_creates_roles_and_builtin_users():
    assert set(Group.objects.filter(name__in=SEEDED_ROLES).values_list("name", flat=True)) == set(
        SEEDED_ROLES
    )

    administrator = User.objects.get(name=ADMINISTRATOR)
    guest = User.objects.get(name=GUEST)
    assert administrator.has_usable_password() is False
    assert guest.has_usable_password() is False
    assert administrator.get_roles() == {ROLE_ADMINISTRATOR, ROLE_SYSTEM_MANAGER}
    assert guest.get_roles() == set()
