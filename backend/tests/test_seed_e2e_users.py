"""``manage.py seed_e2e_users``: the two accounts the Playwright suite signs in with
(``frontend/tests/e2e/users.js``), on a fresh database, for the e2e CI workflow."""

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError

from frappe_platform.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def passwords(monkeypatch):
    monkeypatch.setenv("ADMIN_PWD", "admin-e2e-pass")
    monkeypatch.setenv("SALES_PWD", "sales-e2e-pass")


def test_it_sets_the_admin_password_and_creates_ada_as_a_sales_user(passwords):
    call_command("seed_e2e_users")

    assert User.objects.get(name="Administrator").check_password("admin-e2e-pass")
    ada = User.objects.get(name="ada@example.com")
    assert ada.check_password("sales-e2e-pass")
    assert ada.enabled
    assert set(ada.groups.values_list("name", flat=True)) == {"Sales User"}


def test_running_it_again_resets_ada_to_sales_user_only(passwords):
    call_command("seed_e2e_users")
    ada = User.objects.get(name="ada@example.com")
    ada.groups.add(Group.objects.get_or_create(name="Sales Manager")[0])
    ada.enabled = False
    ada.save()

    call_command("seed_e2e_users")

    ada.refresh_from_db()
    assert set(ada.groups.values_list("name", flat=True)) == {"Sales User"}
    assert ada.enabled
    assert User.objects.filter(name="ada@example.com").count() == 1


def test_it_refuses_without_the_passwords(monkeypatch):
    monkeypatch.delenv("ADMIN_PWD", raising=False)
    monkeypatch.setenv("SALES_PWD", "sales-e2e-pass")

    with pytest.raises(CommandError, match="ADMIN_PWD"):
        call_command("seed_e2e_users")
    assert not User.objects.filter(name="ada@example.com").exists()
