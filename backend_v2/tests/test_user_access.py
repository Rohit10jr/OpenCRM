"""Ported from ``backend/tests/test_user_access.py`` (REBUILD_PLAN S14).

`/api/resource/User/<name>` with PUT becomes `/api/v1/users/<name>/` with PATCH (S25);
the old ``data`` key is the envelope's ``message``. Expected answers are unchanged.
Three holes, three mechanisms: ``User.SENSITIVE_FIELDS`` (grant yourself a role), the
self-only write rule (edit a colleague), ``User.READONLY_FIELDS`` (switch yourself off).
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

pytestmark = pytest.mark.django_db

User = get_user_model()
USERS = "/api/v1/users/"


def test_a_user_cannot_grant_themselves_a_role(alice, api_as):
    manager, _ = Group.objects.get_or_create(name="Sales Manager")
    system, _ = Group.objects.get_or_create(name="System Manager")

    response = api_as(alice).patch(
        f"{USERS}{alice.name}/", {"groups": [manager.pk, system.pk]}, format="json"
    )

    alice.refresh_from_db()
    assert alice.get_roles() == {"Sales User"}, response.json()


def test_a_user_cannot_make_themselves_a_django_superuser(alice, api_as):
    api_as(alice).patch(
        f"{USERS}{alice.name}/", {"is_staff": True, "is_superuser": True}, format="json"
    )

    alice.refresh_from_db()
    assert alice.is_staff is False
    assert alice.is_superuser is False


@pytest.mark.parametrize("field", ["groups", "user_permissions", "is_superuser", "is_staff"])
def test_the_privileged_fields_are_not_readable_either(auth_api, alice, field):
    body = auth_api.get(f"{USERS}{alice.name}/").json()["message"]
    assert field not in body


def test_a_user_cannot_edit_a_colleague(alice, bob, api_as):
    assert api_as(alice).patch(
        f"{USERS}{bob.name}/", {"first_name": "PWNED"}, format="json"
    ).status_code == 403
    bob.refresh_from_db()
    assert bob.first_name == "Bob"


def test_a_colleague_is_readable_on_purpose(alice, bob, api_as):
    assert api_as(alice).get(f"{USERS}{bob.name}/").status_code == 200


def test_the_list_shows_colleagues_but_not_the_built_ins(alice, bob, api_as):
    names = {row["name"] for row in api_as(alice).get(USERS).json()["message"]}
    assert {alice.name, bob.name} <= names
    assert not names & {"Administrator", "Guest"}


def test_administrator_is_invisible_to_a_normal_user(alice, api_as):
    assert api_as(alice).get(f"{USERS}Administrator/").status_code == 403


def test_a_user_cannot_create_or_delete_accounts(alice, bob, api_as):
    client = api_as(alice)
    assert client.post(USERS, {"name": "mallory@example.com"}, format="json").status_code == 403
    assert client.delete(f"{USERS}{bob.name}/").status_code == 403
    assert User.objects.filter(pk=bob.name).exists()


def test_a_system_manager_still_sees_everyone(make_user, alice, bob, api_as):
    boss = make_user("boss@example.com", roles=["System Manager"])
    names = {row["name"] for row in api_as(boss).get(USERS).json()["message"]}

    assert {alice.name, bob.name} <= names
    assert "Administrator" not in names, "the built-ins stay hidden even from a manager"


def test_a_user_cannot_switch_their_own_account_off(alice, api_as):
    response = api_as(alice).patch(
        f"{USERS}{alice.name}/", {"enabled": False}, format="json"
    )
    assert response.status_code == 200, "the write is accepted; the field is ignored"

    alice.refresh_from_db()
    assert alice.enabled is True


def test_a_disabled_account_is_rejected_at_the_door(alice, api_as):
    client = api_as(alice)
    User.objects.filter(pk=alice.name).update(enabled=False)

    assert client.get(f"{USERS}{alice.name}/").status_code == 401


def test_enabled_is_still_readable(auth_api, alice):
    assert auth_api.get(f"{USERS}{alice.name}/").json()["message"]["enabled"] is True


def test_user_type_is_readable_but_not_writable(alice, api_as):
    client = api_as(alice)
    assert client.get(f"{USERS}{alice.name}/").json()["message"]["user_type"]

    client.patch(f"{USERS}{alice.name}/", {"user_type": "Website User"}, format="json")

    alice.refresh_from_db()
    assert alice.user_type == "System User"


@pytest.mark.parametrize(
    "field,value",
    [
        ("first_name", "Alicia"),
        ("last_name", "Smith"),
        ("user_image", "/files/a.png"),
        ("language", "fr"),
        ("time_zone", "Europe/Paris"),
        ("email_signature", "-- Alicia"),
    ],
)
def test_the_profile_fields_are_still_editable(alice, api_as, field, value):
    response = api_as(alice).patch(
        f"{USERS}{alice.name}/", {field: value}, format="json"
    )
    assert response.status_code == 200, response.json()

    alice.refresh_from_db()
    assert getattr(alice, field) == value


# --- ACCOUNTS additions (specs/ACCOUNTS.md section 4.1), no old test covers these -------


def test_a_sales_user_patching_another_users_row_is_refused_by_the_object_rule(
    alice, bob, api_as
):
    """The object rule is applied to User at all (A-13): without it every write passed."""
    response = api_as(alice).patch(
        f"{USERS}{bob.name}/", {"last_name": "Changed"}, format="json"
    )
    assert response.status_code == 403
    bob.refresh_from_db()
    assert bob.last_name == ""


def test_a_name_sent_on_update_is_ignored(alice, api_as):
    """PE-7 (proposed): the record keeps its name and no second row appears."""
    response = api_as(alice).patch(
        f"{USERS}{alice.name}/",
        {"name": "someone.else@example.com", "first_name": "Al"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["message"]["name"] == alice.name
    assert not User.objects.filter(pk="someone.else@example.com").exists()
    alice.refresh_from_db()
    assert alice.first_name == "Al"


def test_user_emails_is_an_empty_list_until_configuration(auth_api, alice):
    body = auth_api.get(f"{USERS}{alice.name}/").json()["message"]
    assert body["user_emails"] == []
    assert body["doctype"] == "User"
    assert "password" not in body and "last_login" not in body


def test_a_system_manager_creates_and_deletes_a_user(make_user, api_as):
    boss = make_user("boss@example.com", roles=["System Manager"])
    client = api_as(boss)

    created = client.post(
        USERS, {"name": "new@example.com", "email": "new@example.com"}, format="json"
    )
    assert created.status_code == 200, created.json()
    assert client.delete(f"{USERS}new@example.com/").status_code == 200
    assert not User.objects.filter(pk="new@example.com").exists()


def test_a_sales_manager_cannot_write_another_user(make_user, alice, api_as):
    manager = make_user("grace@example.com", roles=["Sales Manager"])
    response = api_as(manager).patch(
        f"{USERS}{alice.name}/", {"first_name": "X"}, format="json"
    )
    assert response.status_code == 403


# --- ported from backend/tests/test_platform_models.py:111-122 --------------------------


def test_star_over_http_does_not_leak_the_hash(auth_api, alice):
    import json

    response = auth_api.get(USERS, {"fields": json.dumps(["*"])})
    assert response.status_code == 200
    body = json.dumps(response.json())
    assert "password" not in body
    assert alice.password not in body


def test_reading_a_user_document_does_not_leak_the_hash(auth_api, alice):
    response = auth_api.get(f"{USERS}{alice.name}/")
    assert response.status_code == 200
    assert "password" not in response.json()["message"]
