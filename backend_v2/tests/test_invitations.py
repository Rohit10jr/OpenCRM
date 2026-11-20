"""Invitations: the email, the two jobs and `invite_by_email` (specs/ACCOUNTS.md 4.6, 4.9).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_phase5_async.py:138-191`` (both jobs)
and ``:368-436`` (the invitation email; :377, which needs a saved Email Account, was
ported with CONFIGURATION's Email Account), and
``backend/tests/test_mail_config_account.py:314, :331, :341``.
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


def test_the_invitation_email_uses_the_default_outgoing_account(
    administrator, monkeypatch, _send_on_commit_now
):
    """Ported from `test_phase5_async.py:377` (CONFIGURATION milestone 4): identity comes
    from the saved default outgoing Email Account, which beats the config account (the
    module fixture). Its own SMTP backend is replaced with locmem, as the old test does."""
    from django.core.mail.backends.locmem import EmailBackend

    from configuration.models import EmailAccount
    from core import mail as core_mail

    monkeypatch.setattr(core_mail, "open_backend", lambda account: EmailBackend())
    EmailAccount(
        email_account_name="Outbound",
        email_id="sales@acme.com",
        enable_outgoing=True,
        default_outgoing=True,
    ).save(user=administrator)

    mail.outbox.clear()
    _invitation("invitee2@example.com", administrator=administrator)
    assert mail.outbox[0].from_email == "Outbound <sales@acme.com>"


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


def test_a_rolled_back_create_sends_nothing(administrator, django_capture_on_commit_callbacks):
    from django.db import transaction

    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        try:
            with transaction.atomic():
                _invitation("rolled.back@example.com", administrator=administrator)
                raise RuntimeError("roll back")
        except RuntimeError:
            pass

    assert callbacks == []
    assert mail.outbox == []
    assert not CRMInvitation.objects.filter(email="rolled.back@example.com").exists()


# --- PE-8 (owner, 20 Nov 2026): the resource is System Manager's; email and role set once ---


@pytest.mark.parametrize("roles", [["Sales Manager"], ["Sales User"]])
def test_only_a_system_manager_creates_one_through_the_resource(make_user, api_as, roles):
    caller = make_user("caller@example.com", roles=roles)
    mail.outbox.clear()

    response = api_as(caller).post(
        "/api/v1/invitations/",
        {"email": "direct@example.com", "role": "Sales User", "status": "Pending"},
        format="json",
    )

    assert response.status_code == 403
    assert not CRMInvitation.objects.filter(email="direct@example.com").exists()
    assert mail.outbox == []


@pytest.mark.parametrize("roles", [["System Manager"], None])
def test_a_system_manager_or_administrator_creates_one_the_server_fills_in(
    make_user, administrator, api_as, roles, _send_on_commit_now
):
    caller = make_user("caller@example.com", roles=roles) if roles else administrator
    mail.outbox.clear()

    response = api_as(caller).post(
        "/api/v1/invitations/",
        {
            "email": "direct@example.com",
            "role": "Sales Manager",
            "status": "Accepted",
            "invited_by": "Guest",
            "key": "chosen-by-caller",
        },
        format="json",
    )

    assert response.status_code == 200, response.content[:300]
    created = CRMInvitation.objects.get(email="direct@example.com")
    assert created.role == "Sales Manager"
    assert created.status == "Pending"
    assert created.invited_by_id == caller.name
    assert len(created.key) == 40 and created.key != "chosen-by-caller"
    assert "key" not in response.json()["message"]
    assert [message.to for message in mail.outbox] == [["direct@example.com"]]


@pytest.mark.parametrize(
    "change,label",
    [({"role": "System Manager"}, "Role"), ({"email": "someone.else@example.com"}, "Email")],
)
@pytest.mark.parametrize("roles", [["System Manager"], None])
def test_email_and_role_are_set_once(
    make_user, administrator, api_as, roles, change, label
):
    invitation = _invitation("held@example.com", status="Expired", administrator=administrator)
    caller = make_user("caller@example.com", roles=roles) if roles else administrator

    response = api_as(caller).patch(
        f"/api/v1/invitations/{invitation.pk}/", change, format="json"
    )

    assert response.status_code == 417
    assert response.json()["message"] == f"Value cannot be changed for {label}"
    invitation.refresh_from_db()
    assert (invitation.role, invitation.email) == ("Sales User", "held@example.com")


def test_the_same_email_and_role_sent_back_are_accepted(administrator, api_as):
    invitation = _invitation("held@example.com", status="Expired", administrator=administrator)
    response = api_as(administrator).patch(
        f"/api/v1/invitations/{invitation.pk}/",
        {"email": "held@example.com", "role": "Sales User"},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]


@pytest.mark.parametrize("change", [{"status": "Pending"}, {"accepted_at": "2026-11-20 10:00:00"}])
def test_the_server_set_fields_are_ignored_on_change(administrator, api_as, change):
    invitation = _invitation("held@example.com", status="Expired", administrator=administrator)
    response = api_as(administrator).patch(
        f"/api/v1/invitations/{invitation.pk}/", change, format="json"
    )
    assert response.status_code == 200
    invitation.refresh_from_db()
    assert (invitation.status, invitation.accepted_at) == ("Expired", None)


@pytest.mark.parametrize(
    "change",
    [{"role": "System Manager"}, {"email": "someone.else@example.com"}, {"status": "Pending"}],
)
def test_a_sales_manager_changes_nothing_through_the_resource(
    make_user, administrator, api_as, change
):
    invitation = _invitation("held@example.com", status="Expired", administrator=administrator)
    caller = make_user("caller@example.com", roles=["Sales Manager"])

    response = api_as(caller).patch(
        f"/api/v1/invitations/{invitation.pk}/", change, format="json"
    )

    assert response.status_code == 403
    invitation.refresh_from_db()
    assert (invitation.role, invitation.email, invitation.status) == (
        "Sales User",
        "held@example.com",
        "Expired",
    )


def test_a_manager_still_lists_reads_and_deletes(make_user, administrator, api_as):
    invitation = _invitation("listed@example.com", administrator=administrator)
    client = api_as(make_user("mgr2@example.com", roles=["Sales Manager"]))

    assert [row["name"] for row in client.get("/api/v1/invitations/").json()["message"]] == [
        invitation.pk
    ]
    assert client.get(f"/api/v1/invitations/{invitation.pk}/").status_code == 200
    assert client.delete(f"/api/v1/invitations/{invitation.pk}/").status_code == 200
    assert not CRMInvitation.objects.filter(pk=invitation.pk).exists()


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


def test_invite_by_email_records_who_invited(manager, api_as):
    """PE-8: as upstream's before_insert, on this path too (A-64 finding 4)."""
    api_as(manager).post(INVITE, {"emails": "new@example.com", "role": "Sales User"}, format="json")
    assert CRMInvitation.objects.get(email="new@example.com").invited_by_id == manager.name
