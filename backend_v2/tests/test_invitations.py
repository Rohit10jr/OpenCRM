"""Invitations: the email, the two jobs and `invite_by_email` (specs/ACCOUNTS.md 4.6, 4.9).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_phase5_async.py:138-191`` (both jobs)
and ``:368-436`` (the invitation email; :377, which needs a saved Email Account, is
CONFIGURATION's), and ``backend/tests/test_mail_config_account.py:314, :331, :341``.
``crm_app.tasks`` is ``accounts.tasks``; ``session_user`` + ``objects.create`` is
``create_for_user``. The email is queued after commit; ``_send_on_commit_now`` runs it at
once as the old post_save did, and the deferral itself has its own test below. The
``invite_by_email`` cases are new: no old test calls it.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from django.core import mail
from django.test import override_settings
from django.utils import timezone

from accounts.models import CRMInvitation
from accounts.tasks import (
    BEAT_SCHEDULE,
    expire_invitations,
    flush_expired_tokens,
    send_invitation_email,
)

pytestmark = pytest.mark.django_db
FROM = "notifications@example.test"
INVITE = "/api/v1/invitations/invite-by-email/"


@pytest.fixture(autouse=True)
def _config_account():
    with override_settings(
        EMAIL_HOST="smtp.example.test", DEFAULT_FROM_EMAIL=FROM, EMAIL_SENDER_NAME="Frappe"
    ):
        yield


@pytest.fixture
def _send_on_commit_now(monkeypatch):
    monkeypatch.setattr(
        "accounts.models.transaction",
        SimpleNamespace(on_commit=lambda func, *args, **kwargs: func()),
    )


def _invitation(email, *, age_days=0, status="Pending", administrator=None):
    invitation = CRMInvitation.objects.create_for_user(
        user=administrator or "Administrator",
        email=email,
        role="Sales User",
        status=status,
        key=f"k-{email}",
    )
    if age_days:
        CRMInvitation.objects.filter(pk=invitation.pk).update(
            creation=timezone.now() - datetime.timedelta(days=age_days)
        )
    return invitation


# --- expire_invitations (test_phase5_async.py:138-171) -------------------------------------


def test_expire_invitations_expires_only_stale_pending_ones(administrator):
    fresh = _invitation("fresh@example.com", age_days=1, administrator=administrator)
    stale = _invitation("stale@example.com", age_days=5, administrator=administrator)

    assert expire_invitations() == 1
    assert CRMInvitation.objects.get(pk=fresh.pk).status == "Pending"
    assert CRMInvitation.objects.get(pk=stale.pk).status == "Expired"


def test_expire_invitations_leaves_accepted_ones_alone(administrator):
    accepted = _invitation(
        "done@example.com", age_days=10, status="Accepted", administrator=administrator
    )
    expire_invitations()
    assert CRMInvitation.objects.get(pk=accepted.pk).status == "Accepted"


def test_expire_invitations_is_idempotent(administrator):
    _invitation("stale@example.com", age_days=5, administrator=administrator)
    assert expire_invitations() == 1
    assert expire_invitations() == 0


# --- flush_expired_tokens (test_phase5_async.py:177-201) -----------------------------------


def test_flush_expired_tokens_removes_only_expired_ones(alice):
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    from rest_framework_simplejwt.tokens import RefreshToken

    RefreshToken.for_user(alice)
    live = OutstandingToken.objects.count()
    assert live >= 1

    assert flush_expired_tokens() == 0
    assert OutstandingToken.objects.count() == live


def test_flush_expired_tokens_deletes_an_expired_one(alice):
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    from rest_framework_simplejwt.tokens import RefreshToken

    RefreshToken.for_user(alice)
    OutstandingToken.objects.update(expires_at=timezone.now() - datetime.timedelta(days=1))

    assert flush_expired_tokens() >= 1
    assert OutstandingToken.objects.count() == 0


def test_both_jobs_are_scheduled_daily_at_the_old_times():
    """Old `config/celery.py:40-56`: 00:00 and 01:00."""
    expire = BEAT_SCHEDULE["expire-invitations"]
    flush = BEAT_SCHEDULE["flush-expired-tokens"]
    assert expire["task"] == "accounts.expire_invitations"
    assert (expire["schedule"].hour, expire["schedule"].minute) == ({0}, {0})
    assert flush["task"] == "accounts.flush_expired_tokens"
    assert (flush["schedule"].hour, flush["schedule"].minute) == ({1}, {0})


# --- the invitation email (test_phase5_async.py:368-436) -----------------------------------


def test_creating_an_invitation_sends_one_email(administrator, _send_on_commit_now):
    mail.outbox.clear()
    invitation = _invitation("invitee@example.com", administrator=administrator)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["invitee@example.com"]
    assert invitation.key in mail.outbox[0].body


def test_sending_records_the_timestamp(administrator, _send_on_commit_now):
    invitation = _invitation("stamped@example.com", administrator=administrator)
    assert CRMInvitation.objects.get(pk=invitation.pk).email_sent_at is not None


def test_the_invitation_email_retries_a_transport_failure():
    import smtplib

    assert smtplib.SMTPException in send_invitation_email.autoretry_for
    assert OSError in send_invitation_email.autoretry_for
    assert Exception not in send_invitation_email.autoretry_for
    assert send_invitation_email.max_retries == 3


def test_the_invitation_email_is_idempotent(administrator, _send_on_commit_now):
    invitation = _invitation("once@example.com", administrator=administrator)
    mail.outbox.clear()

    assert send_invitation_email(str(invitation.pk)) is False
    assert mail.outbox == []


# --- the carrier (test_mail_config_account.py:314, :331, :341) -----------------------------


def test_an_invitation_is_sent_from_the_config_account(administrator, _send_on_commit_now):
    mail.outbox.clear()
    invitation = _invitation("invitee@example.test", administrator=administrator)

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.from_email == f"Frappe <{FROM}>"
    assert message.to == ["invitee@example.test"]
    assert invitation.key in message.body


def test_the_sender_name_setting_names_the_config_account(administrator, _send_on_commit_now):
    mail.outbox.clear()
    with override_settings(EMAIL_SENDER_NAME="Acme CRM"):
        _invitation("invitee2@example.test", administrator=administrator)

    assert mail.outbox[0].from_email == f"Acme CRM <{FROM}>"


def test_an_invitation_with_nothing_to_send_through_fails_its_task_once(administrator):
    from core.exceptions import OutgoingEmailError
    from core.mail import NO_ACCOUNT

    invitation = _invitation("nobody-carries@example.test", administrator=administrator)
    mail.outbox.clear()

    assert not issubclass(OutgoingEmailError, send_invitation_email.autoretry_for)
    with override_settings(EMAIL_HOST=""), pytest.raises(OutgoingEmailError) as raised:
        send_invitation_email(invitation.pk)
    assert raised.value.message == NO_ACCOUNT
    assert mail.outbox == []
    assert CRMInvitation.objects.get(pk=invitation.pk).email_sent_at is None


# --- new: queued after commit, from every creation (A-22) ---------------------------------


def test_the_email_is_queued_only_once_the_row_is_committed(
    administrator, django_capture_on_commit_callbacks
):
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        _invitation("later@example.com", administrator=administrator)
    assert mail.outbox == [], "nothing is sent before the commit"

    for callback in callbacks:
        callback()
    assert [message.to for message in mail.outbox] == [["later@example.com"]]


def test_a_managers_direct_resource_create_sends_too(make_user, api_as, _send_on_commit_now):
    manager = make_user("mgr@example.com", roles=["Sales Manager"])
    mail.outbox.clear()

    response = api_as(manager).post(
        "/api/v1/invitations/",
        {"email": "direct@example.com", "role": "Sales User", "status": "Pending"},
        format="json",
    )

    assert response.status_code == 200, response.json()
    assert [message.to for message in mail.outbox] == [["direct@example.com"]]
    assert CRMInvitation.objects.get(email="direct@example.com").key == "", (
        "the model never mints a key; only invite_by_email does"
    )


# --- invite_by_email (new; specs/ACCOUNTS.md 4.6) ------------------------------------------


@pytest.fixture
def manager(make_user):
    return make_user("mgr@example.com", roles=["Sales Manager"])


def test_a_sales_user_is_not_permitted(auth_api):
    response = auth_api.post(INVITE, {"emails": "x@example.com", "role": "Sales User"}, format="json")
    assert response.status_code == 403
    assert response.json()["messages"] == ["Not permitted"]


@pytest.mark.parametrize(
    "role,message",
    [
        ("System Manager", "You are not allowed to invite System Managers"),
        ("Sales Manager", "You are not allowed to invite Sales Managers"),
        ("Guest", "Cannot invite for this role"),
    ],
)
def test_a_sales_manager_cannot_invite_above_sales_user(manager, api_as, role, message):
    response = api_as(manager).post(
        INVITE, {"emails": "x@example.com", "role": role}, format="json"
    )
    assert response.status_code == 403
    assert response.json()["messages"] == [message]


@pytest.mark.parametrize("emails", ["", "not-an-address, also bad"])
def test_an_empty_or_invalid_list_answers_null(manager, api_as, emails):
    response = api_as(manager).post(INVITE, {"emails": emails, "role": "Sales User"}, format="json")
    assert response.json() == {"message": None}
    assert not CRMInvitation.objects.exists()


def test_members_and_existing_invitations_of_any_status_are_skipped(
    manager, alice, administrator, api_as, _send_on_commit_now
):
    _invitation("old@example.com", status="Expired", administrator=administrator)
    mail.outbox.clear()

    response = api_as(manager).post(
        INVITE,
        {"emails": f"{alice.email}, old@example.com\nnew@example.com", "role": "Sales User"},
        format="json",
    )

    body = response.json()["message"]
    assert body == {
        "existing_members": [alice.email],
        "existing_invites": ["old@example.com"],
        "to_invite": ["new@example.com"],
    }
    created = CRMInvitation.objects.get(email="new@example.com")
    assert (created.status, created.role, len(created.key)) == ("Pending", "Sales User", 40)
    assert [message.to for message in mail.outbox] == [["new@example.com"]]
