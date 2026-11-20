"""Ported from ``backend/tests/test_user_emails.py`` (REBUILD_PLAN S14).

A user's outgoing email accounts: `user_emails`, rows of User Email
(specs/CONFIGURATION.md 4.4). `frappe.client.get` and `frappe.client.set_value` on User
are ACCOUNTS' `GET`/`PATCH /api/v1/users/<name>/`. The old fixtures created accounts with
`objects.create`, whose save hook linked them; here `save(user=...)` links them, as
the old receiver did. Expected answers are unchanged.
"""

import pytest

from configuration.models import EmailAccount, UserEmail

pytestmark = pytest.mark.django_db

USERS = "/api/v1/users/"


def make_account(user, **fields):
    account = EmailAccount(**fields)
    account.save(user=user)
    return account


@pytest.fixture
def gmail(administrator):
    return make_account(
        administrator,
        email_account_name="ZZ Gmail",
        email_id="zz.sales@example.com",
        service="GMail",
        enable_outgoing=True,
    )


def rows_of(client, user):
    response = client.get(f"{USERS}{user}/")
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]["user_emails"]


def set_rows(client, user, rows, **more):
    return client.patch(f"{USERS}{user}/", {"user_emails": rows, **more}, format="json")


def test_a_manager_adds_an_account_from_the_profile_and_it_stays(api_as, administrator, gmail):
    client = api_as(administrator)
    response = set_rows(client, administrator.name, [{"email_account": gmail.pk}])
    assert response.status_code == 200, response.content[:300]
    rows = rows_of(client, administrator.name)
    assert [(r["email_account"], r["email_id"], r["enable_outgoing"]) for r in rows] == [
        (gmail.pk, "zz.sales@example.com", True)
    ]

    response = set_rows(client, administrator.name, [])
    assert response.status_code == 200, response.content[:300]
    assert rows_of(client, administrator.name) == []


def test_a_sales_users_pick_is_dropped_as_upstream_resets_it(auth_api, alice, gmail):
    response = set_rows(auth_api, alice.name, [{"email_account": gmail.pk}], first_name="Alicia")
    assert response.status_code == 200, response.content[:300]
    assert rows_of(auth_api, alice.name) == []
    alice.refresh_from_db()
    assert alice.first_name == "Alicia"


def test_a_sales_managers_pick_is_dropped_too(api_as, make_user, gmail):
    """New (A-34 finding 2): System Manager only, not the manager pair, writes
    `user_emails` (`User.PRIVILEGED_WRITE_ROLES`); the rest of the save applies."""
    manager = make_user("mgr@example.com", roles=["Sales Manager", "Sales User"])
    client = api_as(manager)
    response = set_rows(client, manager.name, [{"email_account": gmail.pk}], first_name="Mgr")
    assert response.status_code == 200, response.content[:300]
    assert rows_of(client, manager.name) == []
    manager.refresh_from_db()
    assert manager.first_name == "Mgr"


def test_an_account_with_a_users_address_links_itself_to_that_user(administrator, alice):
    account = make_account(
        administrator, email_account_name="ZZ Alice", email_id=alice.name, enable_outgoing=True
    )
    account.save(user=administrator)  # a second save adds nothing

    rows = list(UserEmail.objects.filter(parent_user=alice))
    assert [(r.email_account_id, r.email_id, r.enable_outgoing) for r in rows] == [
        (account.pk, alice.name, True)
    ]

    account.enable_outgoing = False
    account.save(user=administrator)
    assert UserEmail.objects.get(parent_user=alice).enable_outgoing is False

    account.delete()
    assert not UserEmail.objects.filter(parent_user=alice).exists()


def test_the_rows_come_back_with_the_user_for_the_composer(auth_api, alice, administrator):
    account = make_account(
        administrator, email_account_name="ZZ Mine", email_id=alice.name, enable_outgoing=True
    )
    rows = rows_of(auth_api, alice.name)
    assert [(r["email_account"], r["email_id"]) for r in rows] == [(account.pk, alice.name)]

