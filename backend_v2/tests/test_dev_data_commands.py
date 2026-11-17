"""Ports of the old seed command tests for FOUNDATION's development data."""

import io

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from accounts.models import User
from accounts.roles import SEEDED_ROLES

pytestmark = pytest.mark.django_db

PASSWORDS = {
    "ADMIN_PWD": "admin-dev-pass",
    "SALES_PWD": "sales-dev-pass",
    "MANAGER_PWD": "manager-dev-pass",
    "SALES2_PWD": "sales-two-dev-pass",
}

EXPECTED_USERS = {
    "Administrator": ("admin-dev-pass", {"Administrator", "System Manager"}),
    "ada@example.com": ("sales-dev-pass", {"Sales User"}),
    "grace@example.com": ("manager-dev-pass", {"Sales Manager"}),
    "alan@example.com": ("sales-two-dev-pass", {"Sales User"}),
}


def _suite_user_rows():
    rows = []
    for account in User.objects.filter(name__in=EXPECTED_USERS).order_by("name"):
        fields = {
            field.name: getattr(account, field.name)
            for field in account._meta.concrete_fields
        }
        roles = tuple(account.groups.order_by("name").values_list("name", flat=True))
        rows.append((fields, roles))
    return rows


@pytest.fixture
def passwords(monkeypatch):
    for variable, value in PASSWORDS.items():
        monkeypatch.setenv(variable, value)


@pytest.mark.parametrize("command", ("seed_dev_data", "clear_dev_data"))
@override_settings(DEV_DATA_ALLOWED=False)
def test_dev_data_commands_refuse_without_opt_in_and_change_nothing(
    command, make_user, passwords
):
    for name in ("ada@example.com", "grace@example.com", "alan@example.com"):
        make_user(name, first_name="Must remain", roles=["Sales User"])
    administrator = User.objects.get(name="Administrator")
    administrator.set_password("must-remain")
    administrator.enabled = False
    administrator.save()
    before_count = User.objects.count()
    before_rows = _suite_user_rows()

    with pytest.raises(
        CommandError,
        match=rf"{command} refuses to run: DEV_DATA_ALLOWED is not set",
    ):
        call_command(command)

    assert User.objects.count() == before_count
    assert _suite_user_rows() == before_rows


def test_seed_creates_the_four_users_with_passwords_and_roles(passwords):
    output = io.StringIO()

    call_command("seed_dev_data", stdout=output)

    for name, (password, roles) in EXPECTED_USERS.items():
        account = User.objects.get(name=name)
        assert account.check_password(password)
        assert set(account.groups.values_list("name", flat=True)) == roles
    assert "users: 3 created, 4 reset" in output.getvalue()
    assert "3 row(s) created" in output.getvalue()


def test_seed_refuses_before_writing_when_a_password_is_missing(
    passwords, monkeypatch
):
    monkeypatch.delenv("MANAGER_PWD")

    with pytest.raises(CommandError, match="MANAGER_PWD") as error:
        call_command("seed_dev_data")

    assert PASSWORDS["MANAGER_PWD"] not in str(error.value)
    assert not User.objects.filter(name="ada@example.com").exists()
    assert not User.objects.get(name="Administrator").has_usable_password()


def test_running_seed_twice_creates_nothing_and_restores_all_users(passwords):
    call_command("seed_dev_data", stdout=io.StringIO())
    unexpected_role = Group.objects.get(name="Sales Manager")
    for name in EXPECTED_USERS:
        account = User.objects.get(name=name)
        account.set_password("changed-by-http-suite")
        account.enabled = False
        account.save(update_fields=("password", "enabled", "modified"))
        account.groups.set([unexpected_role])
    output = io.StringIO()

    call_command("seed_dev_data", stdout=output)

    for name, (password, roles) in EXPECTED_USERS.items():
        account = User.objects.get(name=name)
        assert account.enabled is True
        assert account.check_password(password)
        assert set(account.groups.values_list("name", flat=True)) == roles
    assert "users: 0 created, 4 reset" in output.getvalue()
    assert "0 row(s) created" in output.getvalue()


def test_seed_runs_each_step_as_administrator(passwords, monkeypatch):
    actors = []
    from core.dev_data import DevDataStep
    from core.management.commands import seed_dev_data

    def tracked_seed(user, force):
        actors.append(user)
        return 0

    monkeypatch.setattr(
        seed_dev_data,
        "STEPS",
        (DevDataStep("tracked", tracked_seed, lambda user, force: 0),),
    )

    call_command("seed_dev_data", stdout=io.StringIO())

    assert len(actors) == 1
    assert actors[0].name == "Administrator"


def test_clear_removes_only_the_three_non_builtin_seed_users(passwords, make_user):
    call_command("seed_dev_data", stdout=io.StringIO())
    handmade = make_user("handmade@example.com", roles=["Sales User"])
    role_names = set(Group.objects.values_list("name", flat=True))
    output = io.StringIO()

    call_command("clear_dev_data", stdout=output)

    assert not User.objects.filter(
        name__in=("ada@example.com", "grace@example.com", "alan@example.com")
    ).exists()
    assert User.objects.filter(name="Administrator").exists()
    assert User.objects.filter(name="Guest").exists()
    assert User.objects.filter(name=handmade.name).exists()
    assert User.objects.get(name="Administrator").check_password("admin-dev-pass")
    assert set(Group.objects.values_list("name", flat=True)) == role_names
    assert set(SEEDED_ROLES) <= role_names
    assert "users: 3" in output.getvalue()
    assert "3 row(s) removed" in output.getvalue()


def test_demo_is_accepted_and_reports_that_it_adds_nothing_yet(passwords):
    output = io.StringIO()

    call_command("seed_dev_data", demo=True, stdout=output)

    assert "Demo records are not available yet." in output.getvalue()
