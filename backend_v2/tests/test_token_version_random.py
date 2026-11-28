"""PE-32 (ACCOUNTS §10.5): every account starts at a random token version, and the data
migration gave every existing account a fresh one. New: the old backend starts at 0.
"""

import io

import pytest
from django.core import mail
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import override_settings

from accounts.models import CRMInvitation, User

pytestmark = pytest.mark.django_db


def test_create_user_never_starts_at_zero(make_user):
    versions = {make_user(f"u{i}@example.com").token_version for i in range(5)}
    assert 0 not in versions
    assert len(versions) == 5


def test_post_users_never_starts_at_zero(administrator, api_as):
    response = api_as(administrator).post(
        "/api/v1/users/", {"name": "posted@example.com", "email": "posted@example.com"}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
    assert User.objects.get(pk="posted@example.com").token_version > 0


@override_settings(EMAIL_HOST="smtp.example.test")
def test_invitation_accept_never_starts_at_zero(administrator, api_as):
    mail.outbox.clear()
    CRMInvitation(email="joiner@example.com", role="Sales User", status="Pending", key="k-join").save(
        user=administrator
    )
    response = api_as(administrator).post(
        "/api/v1/auth/accept-invitation/", {"key": "k-join"}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
    assert User.objects.get(pk="joiner@example.com").token_version > 0


#: The seed reads the suite users' passwords from the environment; CI has no `.env`, so
#: the test supplies its own (as `test_dev_data_commands.py` does).
SEED_PASSWORDS = {
    "ADMIN_PWD": "admin-test-pass",
    "SALES_PWD": "sales-test-pass",
    "MANAGER_PWD": "manager-test-pass",
    "SALES2_PWD": "sales-two-test-pass",
}


@override_settings(DEV_DATA_ALLOWED=True)
def test_the_seed_never_starts_at_zero(monkeypatch):
    for variable, value in SEED_PASSWORDS.items():
        monkeypatch.setenv(variable, value)
    call_command("seed_dev_data", stdout=io.StringIO())
    seeded = User.objects.exclude(pk__in=User.BUILTIN_NAMES)
    assert seeded.exists()
    assert not seeded.filter(token_version=0).exists()


def test_the_data_migration_gives_every_row_a_fresh_version(make_user):
    """accounts/0006 on its own historical apps: every row changes, none ends at 0."""
    import importlib

    alice = make_user("alice2@example.com")
    User.objects.update(token_version=7)
    apps = MigrationLoader(connection).project_state(
        ("accounts", "0006_fresh_token_versions")
    ).apps
    module = importlib.import_module("accounts.migrations.0006_fresh_token_versions")

    module.fresh_token_versions(apps, None)

    versions = list(User.objects.values_list("token_version", flat=True))
    assert len(versions) >= 3  # Administrator, Guest, alice2
    assert 7 not in versions and 0 not in versions
    assert User.objects.get(pk=alice.pk).token_version != 7
