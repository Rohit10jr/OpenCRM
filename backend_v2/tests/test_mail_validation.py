"""Ported from ``backend/tests/test_mail_validation.py:1-187`` (REBUILD_PLAN S14); the two
endpoint cases (`:192-236`) move with `create_email_account` (CF4c).

Email Account credentials are checked before saving (specs/CONFIGURATION.md 4.4); the
checks live in `core.mail`. Changed fixture: the old tests built an unsaved
`EmailAccount`; here the checks take any account-shaped object, so the fixture is a
`SimpleNamespace` with the same fields. Expected answers are unchanged.

**No test here touches a real mail server.** The connection functions are patched.
"""

import imaplib
import smtplib
import socket
import sys
from types import ModuleType, SimpleNamespace

import pytest
from django.core.checks import run_checks

from core import mail
from core.exceptions import ValidationError


def _account(**overrides):
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
        "no_smtp_authentication": False,
        "awaiting_password": False,
        "login_id": "",
        "login_id_is_different": False,
        "use_ssl_for_outgoing": False,
        "email_server": "",
        "incoming_port": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


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
    monkeypatch.setattr(mail, "check_smtp", lambda *a, **k: pytest.fail("should not connect"))

    mail.validate_email_account(_account(awaiting_password=True, password=""))


def test_a_local_server_needs_no_password(monkeypatch):
    called = []
    monkeypatch.setattr(mail, "check_smtp", lambda *a, **k: called.append("smtp"))

    mail.validate_email_account(_account(password="", smtp_server="localhost"))

    assert called == ["smtp"]


def test_no_password_and_a_remote_server_is_rejected():
    with pytest.raises(ValidationError, match="Password is required or select Awaiting Password"):
        mail.validate_email_account(_account(password=""))


def test_no_smtp_authentication_still_opens_the_socket(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        mail, "check_smtp", lambda *a, **k: seen.update(authenticate=k.get("authenticate"))
    )

    mail.validate_email_account(_account(no_smtp_authentication=True))

    assert seen["authenticate"] is False


# --- what the failures say --------------------------------------------------------------


def test_bad_credentials_raise_the_message_the_ui_expects(monkeypatch):
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


# --- new: no old test covers these (specs/CONFIGURATION.md section 4.4) -------------------


class _FakeIMAP:
    login_error = None

    def __init__(self, host, port, timeout=None):
        self.args = (host, port, timeout)

    def login(self, username, password):
        if self.login_error:
            raise self.login_error

    def logout(self):
        return None


def test_imap_is_ssl_on_993_with_the_email_id_and_the_email_server(monkeypatch):
    seen = {}

    class _IMAP(_FakeIMAP):
        def __init__(self, host, port, timeout=None):
            seen["connect"] = (host, port, timeout)

        def login(self, username, password):
            seen["login"] = (username, password)

    monkeypatch.setattr(imaplib, "IMAP4_SSL", _IMAP)
    mail.validate_email_account(
        _account(enable_outgoing=False, enable_incoming=True, email_server="imap.example.com")
    )
    assert seen["connect"] == ("imap.example.com", 993, 10)
    assert seen["login"] == ("support@example.com", "hunter2")


def test_imap_falls_back_to_the_smtp_server(monkeypatch):
    seen = {}

    class _IMAP(_FakeIMAP):
        def __init__(self, host, port, timeout=None):
            seen["host"] = host

    monkeypatch.setattr(imaplib, "IMAP4_SSL", _IMAP)
    mail.validate_email_account(_account(enable_outgoing=False, enable_incoming=True))
    assert seen["host"] == "smtp.example.com"


def test_an_imap_login_error_is_invalid_credentials(monkeypatch):
    class _IMAP(_FakeIMAP):
        login_error = imaplib.IMAP4.error("auth failed")

    monkeypatch.setattr(imaplib, "IMAP4_SSL", _IMAP)
    with pytest.raises(ValidationError, match="invalid credentials"):
        mail.check_imap("imap.example.com", None, "u", "p")


def test_an_unreachable_imap_server_reports_the_connection_failure(monkeypatch):
    def boom(*a, **k):
        raise socket.timeout("timed out")

    monkeypatch.setattr(imaplib, "IMAP4_SSL", boom)
    with pytest.raises(ValidationError, match="Could not connect to the mail server: timed out"):
        mail.check_imap("imap.example.com", None, "u", "p")


def test_a_missing_imap_server_is_rejected_before_connecting():
    with pytest.raises(ValidationError, match="Email Server is required"):
        mail.check_imap("", None)


def test_smtp_settings_use_the_login_id_and_implicit_ssl():
    smtp = mail.smtp_settings(
        _account(login_id="relay-user", login_id_is_different=True, use_ssl_for_outgoing=True,
                 smtp_port=None)
    )
    assert smtp == {
        "host": "smtp.example.com",
        "port": 465,
        "username": "relay-user",
        "password": "hunter2",
        "use_tls": False,
        "use_ssl": True,
    }


def test_smtp_settings_send_no_credentials_without_authentication():
    smtp = mail.smtp_settings(_account(no_smtp_authentication=True))
    assert (smtp["username"], smtp["password"]) == ("", "")


# --- the saved-account provider (decision 7) ----------------------------------------------


@pytest.fixture
def provider(monkeypatch, settings):
    module = ModuleType("fake_mail_provider")
    module.saved = None
    module.signature = None
    module.calls = []

    def saved_outgoing_account(sender=None, reference_doctype=None):
        module.calls.append((sender, reference_doctype))
        return module.saved

    module.saved_outgoing_account = saved_outgoing_account
    module.default_signature = lambda: module.signature
    monkeypatch.setitem(sys.modules, "fake_mail_provider", module)
    settings.MAIL_ACCOUNT_PROVIDER = "fake_mail_provider"
    return module


def test_without_a_provider_only_the_config_account_is_used(settings):
    settings.MAIL_ACCOUNT_PROVIDER = ""
    settings.EMAIL_HOST = "smtp.config.test"
    account = mail.find_outgoing_account()
    assert account.from_site_config and account.smtp_server == "smtp.config.test"
    assert mail.default_signature() is None


def test_a_saved_account_is_tried_before_the_config_account(provider, settings):
    settings.EMAIL_HOST = "smtp.config.test"
    provider.saved = _account()
    assert mail.find_outgoing_account(sender="a@example.com", reference_doctype="CRM Lead") is provider.saved
    assert provider.calls == [("a@example.com", "CRM Lead")]


def test_no_saved_account_falls_back_to_the_config_account(provider, settings):
    settings.EMAIL_HOST = "smtp.config.test"
    assert mail.find_outgoing_account().from_site_config


def test_the_signature_comes_from_the_provider(provider):
    provider.signature = "Regards"
    assert mail.default_signature() == "Regards"


def test_a_saved_account_does_not_use_the_settings_connection(monkeypatch):
    """`open_backend`'s saved-account branch (A-33 point 6): what was checked sends."""
    captured = {}

    class _Backend:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("django.core.mail.backends.smtp.EmailBackend", _Backend)
    monkeypatch.setattr(mail, "get_connection", lambda **k: pytest.fail("settings connection"))
    backend = mail.open_backend(_account(smtp_server="smtp.saved.test"))
    assert isinstance(backend, _Backend)
    assert (captured["host"], captured["username"], captured["password"]) == (
        "smtp.saved.test",
        "support@example.com",
        "hunter2",
    )
    assert captured["timeout"] == 10


def test_the_config_account_uses_the_settings_connection(monkeypatch, settings):
    settings.EMAIL_HOST = "smtp.config.test"
    seen = {}
    monkeypatch.setattr(mail, "get_connection", lambda **k: seen.update(k) or "conn")
    assert mail.open_backend(mail.config_account()) == "conn"
    assert seen["timeout"] == 10


def test_a_provider_path_that_does_not_resolve_fails_the_system_check(settings):
    settings.MAIL_ACCOUNT_PROVIDER = "no_such_module_for_mail"
    errors = [error for error in run_checks() if error.id == "core.E003"]
    assert len(errors) == 1 and "does not resolve" in errors[0].msg


def test_a_provider_without_the_two_calls_fails_the_system_check(monkeypatch, settings):
    monkeypatch.setitem(sys.modules, "empty_mail_provider", ModuleType("empty_mail_provider"))
    settings.MAIL_ACCOUNT_PROVIDER = "empty_mail_provider"
    errors = [error for error in run_checks() if error.id == "core.E003"]
    assert len(errors) == 1 and "saved_outgoing_account" in errors[0].msg


def test_a_resolving_provider_passes_the_system_check(provider):
    assert not [error for error in run_checks() if error.id == "core.E003"]
