"""A4 - email account credentials are checked before saving.

Upstream opens a live connection inside ``validate()``
(``email_account.py:156-168``). Phase 3 skipped it, believing the port had no mail layer;
Django ships one, so the gap was avoidable.

It mattered because the failure was silent: a mistyped password saved cleanly and the
first anyone knew was that invitations never arrived.

**No test here touches a real mail server.** The connection functions are patched, which
is what lets the *decision logic* - which directions to check, when to skip, what to
raise - be tested at all. Upstream skips this whole path in its own suite
(``if in_patch or in_test: return``), so there is no upstream test to mirror.
"""

import socket
import smtplib

import pytest

from frappe_core import mail
from frappe_core.exceptions import ValidationError
from frappe_platform.models import EmailAccount

# Deliberately **no** module-level ``django_db`` mark. Almost everything here is decision
# logic over an unsaved model instance, which needs no database - and a test that can run
# without one does. Only the two endpoint tests at the bottom touch the database, and
# they say so individually.


def _account(**overrides) -> EmailAccount:
    fields = {
        "email_account_name": "Support",
        "email_id": "support@example.com",
        "password": "hunter2",
        "smtp_server": "smtp.example.com",
        "smtp_port": 587,
        "enable_outgoing": True,
        "enable_incoming": False,
        "use_tls": True,
        "use_imap": True,
    }
    fields.update(overrides)
    return EmailAccount(**fields)


# --- which directions get checked ------------------------------------------------------


def test_outgoing_only_checks_smtp(monkeypatch):
    called = []
    monkeypatch.setattr(mail, "check_smtp", lambda *a, **k: called.append("smtp"))
    monkeypatch.setattr(mail, "check_imap", lambda *a, **k: called.append("imap"))

    mail.validate_email_account(_account(enable_outgoing=True, enable_incoming=False))

    assert called == ["smtp"]


def test_incoming_only_checks_imap(monkeypatch):
    called = []
    monkeypatch.setattr(mail, "check_smtp", lambda *a, **k: called.append("smtp"))
    monkeypatch.setattr(mail, "check_imap", lambda *a, **k: called.append("imap"))

    mail.validate_email_account(_account(enable_outgoing=False, enable_incoming=True))

    assert called == ["imap"]


def test_both_directions_check_both(monkeypatch):
    called = []
    monkeypatch.setattr(mail, "check_smtp", lambda *a, **k: called.append("smtp"))
    monkeypatch.setattr(mail, "check_imap", lambda *a, **k: called.append("imap"))

    mail.validate_email_account(_account(enable_outgoing=True, enable_incoming=True))

    assert called == ["smtp", "imap"]


# --- upstream's escape hatches ---------------------------------------------------------


def test_awaiting_password_skips_the_check(monkeypatch):
    """Upstream's own "save now, credentials later" path (``email_account.py:157``).

    Worth pinning: it means we are not inventing a way around the check - the way was
    already there.
    """
    monkeypatch.setattr(mail, "check_smtp", lambda *a, **k: pytest.fail("should not connect"))

    mail.validate_email_account(_account(awaiting_password=True, password=""))


def test_a_local_server_needs_no_password(monkeypatch):
    """``smtp_server in ("127.0.0.1", "localhost")`` - upstream treats a local relay as
    usable without credentials (``email_account.py:158``)."""
    called = []
    monkeypatch.setattr(mail, "check_smtp", lambda *a, **k: called.append("smtp"))

    mail.validate_email_account(_account(password="", smtp_server="localhost"))

    assert called == ["smtp"]


def test_no_password_and_a_remote_server_is_rejected():
    with pytest.raises(ValidationError, match="Password is required or select Awaiting Password"):
        mail.validate_email_account(_account(password=""))


def test_no_smtp_authentication_still_opens_the_socket(monkeypatch):
    """The login step is skipped, the connection is not - an unreachable relay is still
    worth catching."""
    seen = {}
    monkeypatch.setattr(
        mail, "check_smtp", lambda *a, **k: seen.update(authenticate=k.get("authenticate"))
    )

    mail.validate_email_account(_account(no_smtp_authentication=True))

    assert seen["authenticate"] is False


# --- what the failures say --------------------------------------------------------------


def test_bad_credentials_raise_the_message_the_ui_expects(monkeypatch):
    """``EmailAdd.vue:149`` holds this exact string, and it was unreachable until now."""

    def boom(*a, **k):
        raise smtplib.SMTPAuthenticationError(535, b"bad password")

    monkeypatch.setattr("django.core.mail.backends.smtp.EmailBackend.open", boom)

    with pytest.raises(ValidationError, match="invalid credentials"):
        mail.check_smtp("smtp.example.com", 587, "u", "p")


def test_an_unreachable_host_reports_the_connection_failure(monkeypatch):
    def boom(*a, **k):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr("django.core.mail.backends.smtp.EmailBackend.open", boom)

    with pytest.raises(ValidationError, match="Could not connect to the mail server"):
        mail.check_smtp("nope.invalid", 587, "u", "p")


def test_a_missing_smtp_server_is_rejected_before_connecting():
    with pytest.raises(ValidationError, match="SMTP Server is required"):
        mail.check_smtp("", 587)


# --- the timeout ------------------------------------------------------------------------


def test_the_connect_timeout_is_passed_to_the_backend(monkeypatch, settings):
    """**The divergence from upstream.** Upstream passes no timeout, so an unreachable
    host blocks the save until the OS gives up - 20 to 130 seconds, during which the user
    sees a spinner rather than the error written for them.

    Recorded in UPSTREAM_BUGS_PHASE_3-6.md. If a slow but working relay is ever reported
    as broken, raise ``MAIL_CONNECT_TIMEOUT`` - do not remove it.
    """
    settings.MAIL_CONNECT_TIMEOUT = 7
    captured = {}

    class _Backend:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def open(self):
            return True

        def close(self):
            return None

    monkeypatch.setattr("django.core.mail.backends.smtp.EmailBackend", _Backend)

    mail.check_smtp("smtp.example.com", 587, "u", "p")

    assert captured["timeout"] == 7


def test_the_timeout_has_a_default_when_unset(settings):
    del settings.MAIL_CONNECT_TIMEOUT
    assert mail._timeout() == mail.DEFAULT_MAIL_CONNECT_TIMEOUT


# --- the endpoint -------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_rejected_account_is_not_saved(monkeypatch, administrator):
    """Validation runs *before* the row is created, so a failure leaves nothing behind."""
    from crm_app.api.settings import create_email_account
    from frappe_core.session import session_user

    def boom(_account):
        raise ValidationError("Failed to create email account: invalid credentials")

    monkeypatch.setattr("crm_app.api.settings.validate_email_account", boom)

    before = EmailAccount.objects.count()
    with session_user(administrator.name), pytest.raises(ValidationError):
        create_email_account(
            {
                "service": "GMail",
                "email_id": "x@example.com",
                "email_account_name": "Broken",
                "password": "wrong",
                "enable_outgoing": True,
            }
        )

    assert EmailAccount.objects.count() == before


@pytest.mark.django_db
def test_a_valid_account_saves(monkeypatch, administrator):
    from crm_app.api.settings import create_email_account
    from frappe_core.session import session_user

    monkeypatch.setattr("crm_app.api.settings.validate_email_account", lambda _a: None)

    with session_user(administrator.name):
        name = create_email_account(
            {
                "service": "GMail",
                "email_id": "ok@example.com",
                "email_account_name": "Working",
                "password": "right",
                "enable_outgoing": True,
            }
        )

    assert EmailAccount.objects.filter(pk=name).exists()
