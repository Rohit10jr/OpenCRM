"""A2 - `/api/resource/User` was open to every authenticated caller.

Three separate holes, closed by three separate mechanisms. Each test below names which,
because the obvious single fix - "a rule saying you may only touch your own row" - closes
exactly one of them and reads as though it closed all three.

===========================  ==========================================================
Hole                         Closed by
===========================  ==========================================================
Grant yourself a role        `User.SENSITIVE_FIELDS` - the field leaves the API entirely
Rename or disable a          `platform_docs.user_has_permission` - self-only **writes**
colleague
Re-enable your own           `User.READONLY_FIELDS` - readable, never writable
disabled account
===========================  ==========================================================

Reads stay open to colleagues on purpose - `test_a_colleague_is_readable_on_purpose`
records why, and narrowing them breaks kanban.

All three were observed against the real route with a genuine JWT before the fix; the
tests are written as the attack so they fail loudly if a mechanism is removed.
"""

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from frappe_platform.models import User

pytestmark = pytest.mark.django_db


def _client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


# --- escalation: the fields are gone ----------------------------------------------------


def test_a_user_cannot_grant_themselves_a_role(alice):
    """Observed at 200 before the fix: ['Sales User'] -> ['Sales Manager', 'System Manager'].

    Note this is a write to alice's **own** document, which the self-only rule permits -
    which is why `groups` has to leave the serializer rather than be guarded by a rule.
    """
    manager, _ = Group.objects.get_or_create(name="Sales Manager")
    system, _ = Group.objects.get_or_create(name="System Manager")

    response = _client(alice).put(
        f"/api/resource/User/{alice.name}",
        {"groups": [manager.pk, system.pk]},
        format="json",
    )

    alice.refresh_from_db()
    assert alice.get_roles() == {"Sales User"}, response.json()


def test_a_user_cannot_make_themselves_a_django_superuser(alice):
    """`/admin/` is routed (`config/urls.py:5`), so is_staff + is_superuser is a key to
    the Django admin - every model, every row, around the permission layer entirely."""
    _client(alice).put(
        f"/api/resource/User/{alice.name}",
        {"is_staff": True, "is_superuser": True},
        format="json",
    )

    alice.refresh_from_db()
    assert alice.is_staff is False
    assert alice.is_superuser is False


@pytest.mark.parametrize("field", ["groups", "user_permissions", "is_superuser", "is_staff"])
def test_the_privileged_fields_are_not_readable_either(auth_api, alice, field):
    body = auth_api.get(f"/api/resource/User/{alice.name}").json()["data"]
    assert field not in body


# --- the self-only rule -----------------------------------------------------------------


def test_a_user_cannot_edit_a_colleague(alice, bob):
    assert _client(alice).put(
        f"/api/resource/User/{bob.name}", {"first_name": "PWNED"}, format="json"
    ).status_code == 403
    bob.refresh_from_db()
    assert bob.first_name == "Bob"


def test_a_colleague_is_readable_on_purpose(alice, bob):
    """**Reads are deliberately not narrowed to self**, and this test exists to stop the
    obvious "tighten it" change being made without reading why.

    A first version of this rule restricted reads to your own row - closer to upstream's
    doctype permission - and broke kanban: a board grouped by a Link-to-User builds one
    column per user, and upstream builds that list with `frappe.get_all`
    (`crm_view_settings.py:187`), which ignores permissions by design. The board
    collapsed to a single column.

    `crm.api.session.get_users` already serves the same people to any caller, so this
    withholds nothing that was otherwise secret. See
    `test_kanban_resolves_columns_from_a_link_target` in test_get_data.py.
    """
    assert _client(alice).get(f"/api/resource/User/{bob.name}").status_code == 200


def test_the_list_shows_colleagues_but_not_the_built_ins(alice, bob):
    names = {r["name"] for r in _client(alice).get("/api/resource/User").json()["data"]}
    assert {alice.name, bob.name} <= names
    assert not names & {"Administrator", "Guest"}


def test_administrator_is_invisible_to_a_normal_user(alice):
    """Upstream's own rule (`user.py:1173`), ported: the built-ins are hidden from
    everyone but Administrator, so a normal user cannot even see the account worth
    attacking."""
    assert _client(alice).get("/api/resource/User/Administrator").status_code == 403


def test_a_user_cannot_create_or_delete_accounts(alice, bob):
    assert _client(alice).post(
        "/api/resource/User", {"name": "mallory@example.com"}, format="json"
    ).status_code == 403
    assert _client(alice).delete(f"/api/resource/User/{bob.name}").status_code == 403
    assert User.objects.filter(pk=bob.name).exists()


def test_a_system_manager_still_sees_everyone(make_user, alice, bob):
    boss = make_user("boss@example.com", roles=["System Manager"])
    rows = _client(boss).get("/api/resource/User").json()["data"]
    names = {r["name"] for r in rows}

    assert {alice.name, bob.name} <= names
    assert "Administrator" not in names, "the built-ins stay hidden even from a manager"


# --- readable, never writable -----------------------------------------------------------


def test_a_user_cannot_switch_their_own_account_off(alice):
    """What `READONLY_FIELDS` actually enforces on `enabled`.

    The first version of this test asserted that a *disabled* user could not re-enable
    themselves - and passed with the mechanism removed, because a disabled account is
    rejected at authentication and never reaches a serializer at all (the test below).
    It was green for a reason unrelated to what it claimed to test.

    This is the real behaviour: an account's own subject may not flip its access flag in
    either direction.
    """
    response = _client(alice).put(
        f"/api/resource/User/{alice.name}", {"enabled": False}, format="json"
    )
    assert response.status_code == 200, "the write is accepted; the field is ignored"

    alice.refresh_from_db()
    assert alice.enabled is True


def test_a_disabled_account_is_rejected_at_the_door(alice):
    """The *first* layer, and the one that matters most - recorded here because the
    read-only flag above is easy to mistake for it.

    A token issued before the account was disabled is refused at authentication:
    SimpleJWT checks `is_active`, which this model maps to `enabled`.
    """
    client = _client(alice)
    User.objects.filter(pk=alice.name).update(enabled=False)

    assert client.get(f"/api/resource/User/{alice.name}").status_code == 401


def test_enabled_is_still_readable(auth_api, alice):
    """It has to be: `User.default_list_data()` puts it in the Users settings screen."""
    assert auth_api.get(f"/api/resource/User/{alice.name}").json()["data"]["enabled"] is True


def test_user_type_is_readable_but_not_writable(alice):
    client = _client(alice)
    assert client.get(f"/api/resource/User/{alice.name}").json()["data"]["user_type"]

    client.put(f"/api/resource/User/{alice.name}", {"user_type": "Website User"}, format="json")

    alice.refresh_from_db()
    assert alice.user_type == "System User"


# --- the profile screens still work -----------------------------------------------------


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
def test_the_profile_fields_are_still_editable(alice, field, value):
    """Every field the three Vue settings components write. If one of these fails, a
    settings screen is broken - `ProfileSettings.vue`, `PreferencesSettings.vue` and
    `UserEmailSettings.vue` all edit the session user through this route."""
    response = _client(alice).put(
        f"/api/resource/User/{alice.name}", {field: value}, format="json"
    )
    assert response.status_code == 200, response.json()

    alice.refresh_from_db()
    assert getattr(alice, field) == value
