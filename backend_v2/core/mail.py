"""Outbound system mail: who carries it, and what it says.

The carrier is the old `crm_app.communication.find_outgoing_account()` reduced to its
last step, the settings-configured account (`backend/crm_app/communication.py:372-398`,
upstream `email_account.py:563-592`): `None` unless `EMAIL_HOST` is set. The saved Email
Account steps, tried before it, and the unsaved `EmailAccount` this object stands in for
arrive with CONFIGURATION (specs/ACCOUNTS.md section 4.8). The wording lives in
`templates/emails/*.txt`, as `backend/crm_app/mail.py` keeps it.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.utils import formataddr

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.template.loader import render_to_string

from core.exceptions import OutgoingEmailError

#: Upstream's product name, in subjects and bodies.
APP_NAME = "Open CRM"
NO_ACCOUNT = "Please setup default outgoing Email Account from Tools > Email Account"


@dataclass(frozen=True)
class ConfigAccount:
    """The settings as an outgoing account, with the old field names."""

    email_account_name: str
    email_id: str
    smtp_server: str
    smtp_port: int
    use_tls: bool
    use_ssl_for_outgoing: bool
    login_id: str
    login_id_is_different: bool
    no_smtp_authentication: bool
    always_use_account_email_id_as_sender: bool
    enable_outgoing: bool = True
    from_site_config: bool = True


def config_account() -> ConfigAccount | None:
    host = settings.EMAIL_HOST
    if not host:
        return None
    login = settings.EMAIL_HOST_USER or ""
    address = settings.DEFAULT_FROM_EMAIL
    return ConfigAccount(
        email_account_name=settings.EMAIL_SENDER_NAME,
        email_id=address,
        smtp_server=host,
        smtp_port=settings.EMAIL_PORT,
        use_tls=bool(settings.EMAIL_USE_TLS),
        use_ssl_for_outgoing=bool(settings.EMAIL_USE_SSL),
        login_id=login,
        login_id_is_different=bool(login) and login != address,
        no_smtp_authentication=not login,
        always_use_account_email_id_as_sender=bool(
            settings.EMAIL_ALWAYS_USE_ACCOUNT_EMAIL_ID_AS_SENDER
        ),
    )


def find_outgoing_account():
    """The account system mail goes through. Only the config account for now."""
    return config_account()


def open_backend(account):
    """The config account sends through Django's own connection (`EMAIL_BACKEND` and the
    `EMAIL_*` settings), with the explicit connect timeout the old backend passes."""
    return get_connection(fail_silently=False, timeout=settings.MAIL_CONNECT_TIMEOUT)


def send(template: str, *, subject: str, to: str, context: dict) -> None:
    """Render `emails/<template>.txt` and send it, From the account's name and address.
    Raises `OutgoingEmailError` with upstream's sentence when nothing can carry it; the
    callers decide whether to swallow (old `crm_app/mail.py:send`)."""
    account = find_outgoing_account()
    if account is None:
        raise OutgoingEmailError(NO_ACCOUNT)
    body = render_to_string(f"emails/{template}.txt", {"app_name": APP_NAME, **context})
    EmailMessage(
        subject=subject,
        body=body,
        from_email=formataddr((account.email_account_name, account.email_id)),
        to=[to],
        connection=open_backend(account),
    ).send(fail_silently=False)


def send_invitation(*, to: str, invite_link: str, expiry_days: int) -> None:
    send(
        "invitation",
        subject=f"You have been invited to join {APP_NAME}",
        to=to,
        context={"invite_link": invite_link, "expiry_days": expiry_days},
    )


def send_password_reset(*, to: str, reset_link: str, expiry_minutes: int) -> None:
    send(
        "password_reset",
        subject=f"Reset your {APP_NAME} password",
        to=to,
        context={"reset_link": reset_link, "expiry_minutes": expiry_minutes},
    )
