"""The three new auth endpoints — forgot password, set password, accept invitation.

All three are `allow_guest`: the only endpoints in this port that an unauthenticated
stranger can reach *and* that write something. They are tested the way phase 7's webhooks
were, from the outside, over real HTTP where the status code is part of the contract.

The enumeration tests are the ones to keep. Upstream names the weakness it is closing in a
comment — CWE-204 — and the property is not "the message is right" but "**every** path
produces the same answer", which only holds if you check the paths that are easy to forget:
a disabled account, Administrator, and a mail server that is down.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core import mail as django_mail

from crm_app.api import auth_pages
from frappe_core import password_reset
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    """The endpoints are rate-limited per IP, and every test here shares one.

    Without this, a test that runs after the two rate-limit tests gets a 429 and the failure
    points at whatever it was actually testing.

    The counters live in **Django's cache** (`frappe_core/security.py:42`), not in a module
    dict — a first version of this fixture guarded on `hasattr(security, "_RATE_BUCKETS")`
    and therefore did nothing at all, which the suite could not tell me because it happened
    to pass in file order.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def _post(api, path, payload=None):
    return api.post(f"/api/method/{path}", payload or {}, format="json")


RESET = "frappe.core.doctype.user.user.reset_password"
UPDATE = "frappe.core.doctype.user.user.update_password"
ACCEPT = "crm.api.accept_invitation"


# ---------------------------------------------------------------------------
# reset_password — the response never varies
# ---------------------------------------------------------------------------


def test_a_known_address_gets_the_generic_response_and_an_email(api, alice):
    django_mail.outbox.clear()
    response = _post(api, RESET, {"user": alice.pk})

    assert response.status_code == 200
    assert response.json()["message"]["message"] == auth_pages.GENERIC_RESET_RESPONSE
    assert len(django_mail.outbox) == 1
    assert django_mail.outbox[0].to == [alice.email or alice.pk]


def test_an_unknown_address_gets_the_same_response_and_no_email(api, db):
    django_mail.outbox.clear()
    response = _post(api, RESET, {"user": "nobody@example.com"})

    assert response.status_code == 200
    assert response.json()["message"]["message"] == auth_pages.GENERIC_RESET_RESPONSE
    assert django_mail.outbox == []


def test_a_disabled_account_gets_the_same_response(api, alice):
    """Easy to forget, and the one that would leak *which* accounts are switched off."""
    from frappe_platform.models import User

    User.objects.filter(pk=alice.pk).update(enabled=False)
    django_mail.outbox.clear()

    response = _post(api, RESET, {"user": alice.pk})

    assert response.status_code == 200
    assert response.json()["message"]["message"] == auth_pages.GENERIC_RESET_RESPONSE
    assert django_mail.outbox == [], "a disabled account must not be sent a way back in"


def test_administrator_gets_the_same_response(api, administrator):
    """`user.py:1049` excludes it. A reset link to the superuser account by return of post
    is not a feature."""
    django_mail.outbox.clear()
    response = _post(api, RESET, {"user": "Administrator"})

    assert response.status_code == 200
    assert response.json()["message"]["message"] == auth_pages.GENERIC_RESET_RESPONSE
    assert django_mail.outbox == []


def test_a_mail_failure_gets_the_same_response(api, alice):
    """`user.py:1057-1062`. A mail server that is down must not become an oracle."""
    with patch("crm_app.mail.send_password_reset", side_effect=OSError("smtp down")):
        response = _post(api, RESET, {"user": alice.pk})

    assert response.status_code == 200
    assert response.json()["message"]["message"] == auth_pages.GENERIC_RESET_RESPONSE


def test_an_empty_address_gets_the_same_response(api, db):
    response = _post(api, RESET, {"user": ""})
    assert response.status_code == 200
    assert response.json()["message"]["message"] == auth_pages.GENERIC_RESET_RESPONSE


def test_every_path_produces_a_byte_identical_response(api, alice, administrator):
    """The property, stated as one assertion.

    Not "each message is right" — that would pass with four different-but-correct-looking
    answers. Identical bytes, same status, for a real account, an unknown one, a disabled
    one and the superuser.
    """
    from frappe_platform.models import User

    User.objects.create_user(name="off@example.com", password="x", enabled=False)

    seen = set()
    for address in (alice.pk, "nobody@example.com", "off@example.com", "Administrator"):
        response = _post(api, RESET, {"user": address})
        seen.add((response.status_code, response.content))

    assert len(seen) == 1, "the response varies by address — that is CWE-204"


def test_the_reset_endpoint_is_rate_limited(api, alice):
    """Unlimited, it is a mail cannon aimed at whatever address the caller names."""
    for _ in range(10):
        _post(api, RESET, {"user": alice.pk})

    response = _post(api, RESET, {"user": alice.pk})
    assert response.status_code == 429, response.content[:200]


def test_the_email_carries_a_working_link(api, alice):
    django_mail.outbox.clear()
    _post(api, RESET, {"user": alice.pk})

    body = django_mail.outbox[0].body
    assert "/crm/update-password?key=" in body
    raw_key = body.split("key=")[1].split()[0]
    assert password_reset.resolve_key(raw_key).ok


def test_the_email_is_rendered_from_a_template(api, alice):
    """`PHASE_8_AUTH_AND_DESK.md`: the wording lives in `crm_app/templates/emails/`, so
    whoever deploys can change it without touching Python."""
    django_mail.outbox.clear()
    _post(api, RESET, {"user": alice.pk})

    body = django_mail.outbox[0].body
    assert "expires in 60 minutes" in body
    assert "can only be used once" in body


# ---------------------------------------------------------------------------
# update_password — 200 / 401 / 410
# ---------------------------------------------------------------------------


def test_a_valid_key_sets_the_password_and_returns_tokens(api, alice):
    response = _post(api, UPDATE, {"key": password_reset.issue_key(alice), "new_password": "Str0ng!Passw0rd"})

    assert response.status_code == 200
    body = response.json()["message"]
    assert body["access"] and body["refresh"]
    assert body["user"] == alice.pk

    alice.refresh_from_db()
    assert alice.check_password("Str0ng!Passw0rd")


def test_the_new_password_actually_logs_in(api, alice):
    """The point of the whole screen, asserted end to end rather than by inspection."""
    _post(api, UPDATE, {"key": password_reset.issue_key(alice), "new_password": "Str0ng!Passw0rd"})

    login = _post(api, "login", {"usr": alice.pk, "pwd": "Str0ng!Passw0rd"})
    assert login.status_code == 200
    assert login.json()["message"]["user"] == alice.pk


def test_an_expired_key_answers_410(api, alice, settings):
    from datetime import timedelta

    from django.utils import timezone

    from frappe_platform.models import User

    raw = password_reset.issue_key(alice)
    User.objects.filter(pk=alice.pk).update(
        last_reset_password_key_generated_on=timezone.now() - timedelta(hours=2)
    )

    response = _post(api, UPDATE, {"key": raw, "new_password": "Str0ng!Passw0rd"})
    assert response.status_code == 410
    assert password_reset.EXPIRED_MESSAGE in response.json()["message"]


def test_an_invalid_key_answers_410(api, db):
    response = _post(api, UPDATE, {"key": "never-issued", "new_password": "Str0ng!Passw0rd"})
    assert response.status_code == 410
    assert password_reset.INVALID_MESSAGE in response.json()["message"]


def test_a_key_cannot_be_used_twice(api, alice):
    """Single use, over the wire."""
    raw = password_reset.issue_key(alice)
    first = _post(api, UPDATE, {"key": raw, "new_password": "Str0ng!Passw0rd"})
    second = _post(api, UPDATE, {"key": raw, "new_password": "An0ther!Passw0rd"})

    assert first.status_code == 200
    assert second.status_code == 410

    alice.refresh_from_db()
    assert alice.check_password("Str0ng!Passw0rd"), "the second attempt must not have won"


def test_a_used_key_and_a_fabricated_one_answer_identically(api, alice):
    """No probing for whether a key was ever real."""
    raw = password_reset.issue_key(alice)
    _post(api, UPDATE, {"key": raw, "new_password": "Str0ng!Passw0rd"})

    used = _post(api, UPDATE, {"key": raw, "new_password": "Wh4tever!123"})
    fake = _post(api, UPDATE, {"key": "fabricated", "new_password": "Wh4tever!123"})

    assert (used.status_code, used.content) == (fake.status_code, fake.content)


def test_the_wrong_old_password_answers_401(api, alice):
    response = _post(
        api, UPDATE, {"usr": alice.pk, "old_password": "wrong", "new_password": "Str0ng!Passw0rd"}
    )
    assert response.status_code == 401


def test_the_right_old_password_works(api, alice, make_user):
    account = make_user("bob2@example.com", password="Original!Pass1")
    response = _post(
        api,
        UPDATE,
        {"usr": account.pk, "old_password": "Original!Pass1", "new_password": "Str0ng!Passw0rd"},
    )

    assert response.status_code == 200
    account.refresh_from_db()
    assert account.check_password("Str0ng!Passw0rd")


def test_a_weak_password_is_refused_server_side(api, alice):
    """`test_password_strength` is deliberately not ported — the browser validates, and the
    real minimum is enforced here through Django's validators, where a client that does not
    run our JavaScript cannot skip it."""
    response = _post(api, UPDATE, {"key": password_reset.issue_key(alice), "new_password": "abc"})

    assert response.status_code == 417
    alice.refresh_from_db()
    assert not alice.check_password("abc")


def test_an_absurdly_long_password_is_refused(api, alice):
    """`user.py:839-840`. Hashing a multi-megabyte string is a denial of service."""
    response = _post(
        api, UPDATE, {"key": password_reset.issue_key(alice), "new_password": "a" * 5000}
    )
    assert response.status_code == 417


def test_neither_key_nor_old_password_is_refused(api, db):
    response = _post(api, UPDATE, {"new_password": "Str0ng!Passw0rd"})
    assert response.status_code == 417


def test_logout_all_sessions_blacklists_outstanding_refresh_tokens(api, alice):
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
    from rest_framework_simplejwt.tokens import RefreshToken

    RefreshToken.for_user(alice)
    RefreshToken.for_user(alice)
    before = BlacklistedToken.objects.count()

    _post(
        api,
        UPDATE,
        {
            "key": password_reset.issue_key(alice),
            "new_password": "Str0ng!Passw0rd",
            "logout_all_sessions": 1,
        },
    )

    assert BlacklistedToken.objects.count() > before


def test_a_reset_does_not_re_enable_a_disabled_account(api, alice):
    """A disabled account must not have a way back in.

    Belt and braces: `reset_password` will not email one, but if a key were obtained some
    other way, redeeming it must not flip `enabled`.
    """
    from frappe_platform.models import User

    raw = password_reset.issue_key(alice)
    User.objects.filter(pk=alice.pk).update(enabled=False)

    _post(api, UPDATE, {"key": raw, "new_password": "Str0ng!Passw0rd"})

    alice.refresh_from_db()
    assert alice.enabled is False

    login = _post(api, "login", {"usr": alice.pk, "pwd": "Str0ng!Passw0rd"})
    assert login.status_code != 200, "a disabled account must not be able to log in"


# ---------------------------------------------------------------------------
# accept_invitation
# ---------------------------------------------------------------------------


@pytest.fixture
def invitation(administrator):
    from crm_app.models import CRMInvitation

    with session_user(administrator.name):
        return CRMInvitation.objects.create(
            email="newcomer@example.com", role="Sales User", status="Pending", key="invite-key-1"
        )


def test_accepting_creates_the_user_and_returns_a_set_password_link(api, invitation):
    from frappe_platform.models import User

    response = _post(api, ACCEPT, {"key": "invite-key-1"})

    assert response.status_code == 200
    body = response.json()["message"]
    assert body["status"] == "set_password"
    assert "/crm/update-password?key=" in body["redirect_to"]

    account = User.objects.get(pk="newcomer@example.com")
    assert account.enabled is True
    assert not account.has_usable_password(), "a new account must have no password yet"


def test_the_link_it_returns_actually_sets_a_password(api, invitation):
    """The two halves joined: accept, then redeem what accept handed back."""
    from frappe_platform.models import User

    body = _post(api, ACCEPT, {"key": "invite-key-1"}).json()["message"]
    raw_key = body["redirect_to"].split("key=")[1]

    response = _post(api, UPDATE, {"key": raw_key, "new_password": "Str0ng!Passw0rd"})
    assert response.status_code == 200

    account = User.objects.get(pk="newcomer@example.com")
    assert account.check_password("Str0ng!Passw0rd")


def test_accepting_grants_the_role_and_the_ones_it_implies(api, administrator):
    """`crm_invitation.py:66-72`. A System Manager who did not also get Sales User would be
    unable to see a lead."""
    from crm_app.models import CRMInvitation
    from frappe_platform.models import User

    with session_user(administrator.name):
        CRMInvitation.objects.create(
            email="boss@example.com", role="System Manager", status="Pending", key="k-boss"
        )

    _post(api, ACCEPT, {"key": "k-boss"})

    account = User.objects.get(pk="boss@example.com")
    assert account.get_roles() >= {"System Manager", "Sales Manager", "Sales User"}


def test_accepting_marks_the_invitation_and_clears_its_key(api, invitation):
    from crm_app.models import CRMInvitation

    _post(api, ACCEPT, {"key": "invite-key-1"})

    row = CRMInvitation.objects.get(pk=invitation.pk)
    assert row.status == "Accepted"
    assert row.accepted_at is not None
    assert row.key == "", "the key must not survive redemption"


def test_an_invitation_cannot_be_accepted_twice(api, invitation):
    first = _post(api, ACCEPT, {"key": "invite-key-1"})
    second = _post(api, ACCEPT, {"key": "invite-key-1"})

    assert first.status_code == 200
    assert second.status_code == 417
    assert "Invalid or expired key" in second.json()["message"]


def test_an_unknown_key_is_refused(api, db):
    response = _post(api, ACCEPT, {"key": "never-issued"})
    assert response.status_code == 417
    assert "Invalid or expired key" in response.json()["message"]


def test_an_absent_key_is_refused(api, db):
    response = _post(api, ACCEPT, {})
    assert response.status_code == 417


def test_an_expired_invitation_is_refused(api, administrator):
    from crm_app.models import CRMInvitation

    with session_user(administrator.name):
        CRMInvitation.objects.create(
            email="late@example.com", role="Sales User", status="Expired", key="k-late"
        )

    response = _post(api, ACCEPT, {"key": "k-late"})
    assert response.status_code == 417


def test_an_existing_user_is_logged_in_rather_than_asked_for_a_password(api, alice, administrator):
    from crm_app.models import CRMInvitation

    with session_user(administrator.name):
        CRMInvitation.objects.create(
            email=alice.pk, role="Sales Manager", status="Pending", key="k-existing"
        )

    body = _post(api, ACCEPT, {"key": "k-existing"}).json()["message"]

    assert body["status"] == "logged_in"
    assert body["access"] and body["refresh"]
    alice.refresh_from_db()
    assert "Sales Manager" in alice.get_roles()


def test_the_invitation_key_still_never_reaches_the_wire(api, auth_api, invitation, alice):
    """Bug #21, and `KNOWN_ISSUES.md` §2: *"do not remove it to make redemption easier."*

    This is the test that would fail if a future change made the endpoint more convenient
    by exposing the key.
    """
    from frappe_core.field_security import sensitive_fields

    from crm_app.models import CRMInvitation

    assert "key" in sensitive_fields(CRMInvitation)

    response = auth_api.get("/api/resource/CRM Invitation")
    # A Sales User cannot even list them; if that ever loosens, the key must still be gone.
    if response.status_code == 200:
        for row in response.json()["data"]:
            assert "key" not in row


def test_accept_is_rate_limited(api, administrator):
    """The key is a bearer token, so an unlimited endpoint is a guessing machine."""
    for _ in range(10):
        _post(api, ACCEPT, {"key": "wrong"})

    response = _post(api, ACCEPT, {"key": "wrong"})
    assert response.status_code == 429
