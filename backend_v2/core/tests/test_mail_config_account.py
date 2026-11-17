"""The settings-configured outgoing account (specs/ACCOUNTS.md section 4.8).

Ported from ``backend/tests/test_mail_config_account.py`` :140, :147, :179, :188, :221
(REBUILD_PLAN S14). ``crm_app.communication`` becomes ``core.mail``; :147 drops its
``isinstance(account, EmailAccount)`` check, since Email Account arrives with
CONFIGURATION. The invitation and reset cases (:314, :331, :341, :367, :378) are ported
with their endpoints; the lead, Communication and saved-account cases are carried.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.test import override_settings

from core import mail as mail_service

HOST = "smtp.example.test"
FROM = "notifications@example.test"
BACKEND = Path(__file__).resolve().parents[2]

SMTP_PROBE = (
    "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test'); "
    "from django.core.mail.backends.smtp import EmailBackend; "
    "b = EmailBackend(); print(f'FLAGS:{int(b.use_tls)},{int(b.use_ssl)},{b.port}')"
)


@pytest.fixture
def config_account():
    with override_settings(
        EMAIL_HOST=HOST,
        DEFAULT_FROM_EMAIL=FROM,
        EMAIL_SENDER_NAME="Frappe",
        EMAIL_ALWAYS_USE_ACCOUNT_EMAIL_ID_AS_SENDER=False,
    ):
        yield


@pytest.fixture
def no_config_account():
    with override_settings(EMAIL_HOST=""):
        yield


def test_the_config_account_exists_only_while_email_host_is_set(no_config_account):
    assert mail_service.config_account() is None
    assert mail_service.find_outgoing_account() is None


def test_the_config_account_is_the_settings_as_an_unsaved_email_account():
    with override_settings(
        EMAIL_HOST=HOST,
        EMAIL_PORT=2525,
        EMAIL_HOST_USER="relay-login",
        EMAIL_USE_TLS=True,
        EMAIL_USE_SSL=False,
        DEFAULT_FROM_EMAIL=FROM,
        EMAIL_SENDER_NAME="Acme Notifications",
        EMAIL_ALWAYS_USE_ACCOUNT_EMAIL_ID_AS_SENDER=True,
    ):
        account = mail_service.config_account()

    assert account.from_site_config is True
    assert account.email_account_name == "Acme Notifications"
    assert account.email_id == FROM
    assert account.enable_outgoing is True
    assert account.smtp_server == HOST
    assert account.smtp_port == 2525
    assert account.use_tls is True
    assert account.use_ssl_for_outgoing is False
    assert account.login_id == "relay-login"
    assert account.login_id_is_different is True
    assert account.no_smtp_authentication is False
    assert account.always_use_account_email_id_as_sender is True


def test_no_login_means_no_smtp_authentication():
    with override_settings(EMAIL_HOST=HOST, EMAIL_HOST_USER="", DEFAULT_FROM_EMAIL=FROM):
        account = mail_service.config_account()

    assert account.no_smtp_authentication is True
    assert account.login_id_is_different is False


@pytest.mark.parametrize("explicit_tls", [None, "True"], ids=["tls-unset", "tls-true"])
def test_ssl_turns_tls_off_so_the_config_account_can_connect(explicit_tls):
    """The defaults are computed when ``base.py`` is imported, so a fresh interpreter
    evaluates them. Building the backend is the assertion."""
    env = {k: v for k, v in os.environ.items() if k not in ("EMAIL_USE_TLS", "EMAIL_PORT")}
    env.update(EMAIL_HOST=HOST, EMAIL_HOST_USER="relay-login", EMAIL_USE_SSL="True")
    if explicit_tls is not None:
        env["EMAIL_USE_TLS"] = explicit_tls

    result = subprocess.run(
        [sys.executable, "-c", SMTP_PROBE],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stderr[-2000:]
    line = [s for s in result.stdout.splitlines() if s.startswith("FLAGS:")]
    assert line, f"probe did not report; stdout={result.stdout[-500:]}"
    assert line[0] == "FLAGS:0,1,465", "use_tls, use_ssl, port: implicit TLS on 465, STARTTLS off"


def test_the_config_account_sends_through_the_configured_backend(config_account):
    from django.core.mail.backends.locmem import EmailBackend

    account = mail_service.config_account()
    assert isinstance(mail_service.open_backend(account), EmailBackend)


# --- new: the carrier itself (no old test sends through it directly) ---------------------


def test_nothing_to_send_through_raises_upstreams_sentence(no_config_account):
    from core.exceptions import OutgoingEmailError

    with pytest.raises(OutgoingEmailError) as raised:
        mail_service.send_password_reset(to="a@example.test", reset_link="x", expiry_minutes=60)
    assert raised.value.message == mail_service.NO_ACCOUNT


def test_the_reset_mail_is_from_the_config_account(config_account):
    from django.core import mail

    mail.outbox.clear()
    mail_service.send_password_reset(
        to="a@example.test", reset_link="http://f/crm/update-password?key=k", expiry_minutes=60
    )

    message = mail.outbox[0]
    assert message.from_email == f"Frappe <{FROM}>"
    assert message.subject == "Reset your Open CRM password"
    assert "http://f/crm/update-password?key=k" in message.body
    assert "expires in 60 minutes" in message.body
