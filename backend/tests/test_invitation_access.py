"""An invitation is a bearer token for a role.

`CRM Invitation` holds the **role being granted** and a **`key` that redeems it**.
Upstream's `accept_invitation` (`crm/api/__init__.py:83`) looks the invitation up by key
alone -- unauthenticated, with no binding to the caller -- and then logs in as, or sends a
password-reset link for, `invitation.email`.

Upstream also grants **Sales User `read: 1`** on the doctype, with `key` a plain `Data`
field carrying no permlevel. So whoever can read the row can redeem it: a Sales User who
reads a pending System Manager invitation becomes that System Manager. Recorded as
upstream bug #21.

**Nothing here is exploitable in this port today**, because `accept_invitation` was never
implemented -- a forged or stolen key has nothing to redeem it with. These tests exist for
the day it is. The endpoint is phase 8's, and the rule has to already be in place when it
lands, not be remembered alongside it.
"""

import pytest

from crm_app.models import CRMInvitation
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _config_account():
    """Creating an invitation sends it (eagerly, here), and the send needs a carrier
    (FINDINGS.md 79): with no ``Email Account`` and no ``EMAIL_HOST`` the task raises out of
    ``CRMInvitation.objects.create``. None of this file is about mail; the config account
    carries the invitation so the fixture below can exist."""
    from django.test import override_settings

    with override_settings(EMAIL_HOST="smtp.example.test"):
        yield


@pytest.fixture
def pending_admin_invite(administrator):
    """The dangerous one: an open invitation carrying the highest role."""
    with session_user(administrator.name):
        return CRMInvitation.objects.create(
            email="newadmin@example.com",
            role="System Manager",
            key="secret-redeem-key",
            status="Pending",
        )


@pytest.fixture
def manager(make_user):
    return make_user("mgr@example.com", roles=["Sales Manager"])


# --- the row is not readable ---------------------------------------------------------------


def test_an_ordinary_user_cannot_read_an_invitation(alice, pending_admin_invite, api_as):
    """Stricter than upstream, and this is the divergence that matters: upstream's
    `read: 1` for Sales User is precisely what makes the key reachable."""
    assert api_as(alice).get(
        f"/api/resource/CRM Invitation/{pending_admin_invite.name}"
    ).status_code == 403


def test_the_list_route_hides_them_too(alice, pending_admin_invite, api_as):
    assert api_as(alice).get("/api/resource/CRM Invitation").json()["data"] == []


def test_an_ordinary_user_cannot_mint_an_invitation(alice, api_as):
    """Forging one grants whatever role it names, once something can redeem it."""
    response = api_as(alice).post(
        "/api/resource/CRM Invitation",
        {"email": "alice-alt@example.com", "role": "System Manager", "status": "Pending"},
        format="json",
    )
    assert response.status_code == 403
    assert not CRMInvitation.objects.filter(email="alice-alt@example.com").exists()


def test_an_ordinary_user_cannot_change_the_role_on_one(alice, pending_admin_invite, api_as):
    assert api_as(alice).put(
        f"/api/resource/CRM Invitation/{pending_admin_invite.name}",
        {"role": "Sales User"},
        format="json",
    ).status_code == 403


# --- the key never reaches the wire, even for a manager ------------------------------------


def test_the_key_is_not_served_to_a_manager(manager, pending_admin_invite, api_as):
    """The second layer. A manager may legitimately see who has been invited and to what
    role; nobody needs the token over HTTP. `tasks.py` reads the attribute directly when
    it builds the email, which is the only thing that ever needs it."""
    body = api_as(manager).get(
        f"/api/resource/CRM Invitation/{pending_admin_invite.name}"
    ).json()["data"]

    assert "key" not in body
    assert body["email"] == "newadmin@example.com"
    assert body["role"] == "System Manager"


def test_the_key_cannot_be_probed_by_filtering(manager, pending_admin_invite, api_as):
    """Hiding it from output is not enough on its own - a filter turns the row count into
    an oracle and `like` narrows it a character at a time. That is how a real SMTP password
    was recovered before the field-security guard existed."""
    response = api_as(manager).get(
        '/api/resource/CRM Invitation?filters=[["key","like","secret%"]]'
    )
    assert response.status_code == 400


def test_the_key_cannot_be_selected_explicitly(manager, pending_admin_invite, api_as):
    response = api_as(manager).get('/api/resource/CRM Invitation?fields=["key"]')
    assert response.status_code == 417


# --- managers keep the feature -------------------------------------------------------------


def test_a_manager_sees_the_pending_list(manager, pending_admin_invite, api_as):
    """`InviteUserPage.vue` is the only consumer: manager-gated, and it asks for `name`,
    `email` and `role`. Exactly that still works."""
    rows = api_as(manager).get(
        '/api/resource/CRM Invitation?fields=["name","email","role"]'
        '&filters=[["status","=","Pending"]]'
    ).json()["data"]

    assert [r["email"] for r in rows] == ["newadmin@example.com"]


def test_the_email_task_can_still_read_the_key(pending_admin_invite):
    """Internal ORM access is untouched - field security covers the wire only, and the
    invitation email is the one thing that legitimately needs the token."""
    fresh = CRMInvitation.objects.get(pk=pending_admin_invite.name)
    assert fresh.key == "secret-redeem-key"
