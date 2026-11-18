"""Outbound mail: who carries it, what it says, and how a mail server is checked.

The carrier is the old `crm_app.communication.find_outgoing_account()`
(`backend/crm_app/communication.py:400-440`): a saved Email Account first, found through
the module `MAIL_ACCOUNT_PROVIDER` names (CONFIGURATION's `configuration.mail`, so `core`
never imports it), then the settings-configured account, `ConfigAccount`
(`:372-398`, upstream `email_account.py:563-592`), which is `None` unless `EMAIL_HOST` is
set. `open_backend` sends a saved account through its own SMTP settings. The server
checks (`smtp_settings`, `check_smtp`, `check_imap`, `validate_email_account`) are the old
`backend/frappe_core/mail.py`. The wording lives in `templates/emails/*.txt`, as
`backend/crm_app/mail.py` keeps it.
"""

from __future__ import annotations

import imaplib
import smtplib
import socket
from dataclasses import dataclass
from email.utils import formataddr
from importlib import import_module

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.template.loader import render_to_string

from core.exceptions import OutgoingEmailError, ValidationError
from core.secrets import decrypt

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


def account_provider():
    """The module named by `MAIL_ACCOUNT_PROVIDER` (spec CONFIGURATION section 4.4,
    decision 7), or `None` when the setting is empty. It exposes
    `saved_outgoing_account(sender=None, reference_doctype=None)` and
    `default_signature()`, so `core` never imports the app that owns Email Account. A path
    that does not resolve fails the `core.E003` system check rather than falling back."""
    path = getattr(settings, "MAIL_ACCOUNT_PROVIDER", "") or ""
    return import_module(path) if path else None


def find_outgoing_account(sender=None, reference_doctype=None):
    """The account a message goes through (old `crm_app/communication.py:400-440`): a
    saved Email Account first (steps 1-3, through the provider), else the config account.
    Called with no arguments, as system mail calls it: the default outgoing account, else
    the config account."""
    provider = account_provider()
    if provider is not None:
        account = provider.saved_outgoing_account(
            sender=sender, reference_doctype=reference_doctype
        )
        if account is not None:
            return account
    return config_account()


def default_signature():
    """The default outgoing account's signature, `None` without a provider (old
    `crm_app/api/misc.py:62-67`)."""
    provider = account_provider()
    return provider.default_signature() if provider is not None else None


def open_backend(account):
    """The connection `account` sends through (old `communication.py:610-631`). The
    config account uses Django's own (`EMAIL_BACKEND` and the `EMAIL_*` settings); a saved
    account gets an SMTP backend built from `smtp_settings`, the same flags its save-time
    check used, so what was checked is what sends. Both with the explicit timeout."""
    if getattr(account, "from_site_config", False):
        return get_connection(fail_silently=False, timeout=_timeout())

    from django.core.mail.backends.smtp import EmailBackend

    return EmailBackend(**smtp_settings(account), timeout=_timeout(), fail_silently=False)


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


# --- Mail-server checks (old `backend/frappe_core/mail.py`; spec section 4.4) -----------
#
# Upstream checks an Email Account by opening a live connection before saving it
# (`email_account.py:156-168`). The old backend passes an explicit timeout
# (`MAIL_CONNECT_TIMEOUT`, ten seconds; upstream bug #15) so an unreachable server is an
# error while somebody is still looking at the form, not a hung request.


#: Seconds to wait for a mail server before calling it unreachable.
DEFAULT_MAIL_CONNECT_TIMEOUT = 10


def _timeout() -> int:
    return int(getattr(settings, "MAIL_CONNECT_TIMEOUT", DEFAULT_MAIL_CONNECT_TIMEOUT))


def smtp_settings(account, password: str | None = None) -> dict:
    """The SMTP connection an account describes, as Django backend arguments, in one
    place so the save-time check and the send cannot disagree.

    The login is `login_id` when `login_id_is_different`, else `email_id`;
    `use_ssl_for_outgoing` is implicit TLS on 465 and excludes STARTTLS; otherwise
    `use_tls` on 587; `no_smtp_authentication` sends no credentials. `password` is the
    plaintext when the caller has it; otherwise the stored value is decrypted here.
    """
    use_ssl = bool(getattr(account, "use_ssl_for_outgoing", False))
    authenticate = not getattr(account, "no_smtp_authentication", False)
    username = ""
    secret = ""
    if authenticate:
        login_id = getattr(account, "login_id", "") or ""
        different = bool(getattr(account, "login_id_is_different", False))
        username = login_id if different and login_id else account.email_id
        secret = password if password is not None else decrypt(getattr(account, "password", ""))
    return {
        "host": account.smtp_server,
        "port": account.smtp_port or (465 if use_ssl else 587),
        "username": username,
        "password": secret or "",
        "use_tls": bool(account.use_tls) and not use_ssl,
        "use_ssl": use_ssl,
    }


def check_smtp(
    host: str,
    port: int | None,
    username: str = "",
    password: str = "",
    use_tls: bool = True,
    *,
    use_ssl: bool = False,
    authenticate: bool = True,
) -> None:
    """Open an SMTP session, then close it; `ValidationError` on failure
    (`validate_smtp_conn`, `email_account.py:183-188`). Django's backend, so the check
    and the send share one stack."""
    from django.core.mail.backends.smtp import EmailBackend

    if not host:
        raise ValidationError("SMTP Server is required")

    backend = EmailBackend(
        host=host,
        port=port or (465 if use_ssl else 587),
        username=username if authenticate else "",
        password=password if authenticate else "",
        use_tls=bool(use_tls) and not use_ssl,
        use_ssl=bool(use_ssl),
        timeout=_timeout(),
        fail_silently=False,
    )
    try:
        backend.open()
    except smtplib.SMTPAuthenticationError:
        raise ValidationError("Failed to create email account: invalid credentials") from None
    except (smtplib.SMTPException, socket.timeout, socket.gaierror, OSError) as exc:
        raise ValidationError(f"Could not connect to the mail server: {exc}") from None
    finally:
        try:
            backend.close()
        except Exception:  # noqa: BLE001 - closing a failed connection
            pass


def check_imap(
    host: str,
    port: int | None,
    username: str = "",
    password: str = "",
    use_ssl: bool = True,
) -> None:
    """Open an IMAP connection and log in (`get_incoming_server()`), with the same
    explicit timeout."""
    if not host:
        raise ValidationError("Email Server is required")

    connect = imaplib.IMAP4_SSL if use_ssl else imaplib.IMAP4
    default_port = 993 if use_ssl else 143
    connection = None
    try:
        connection = connect(host, port or default_port, timeout=_timeout())
        if username:
            connection.login(username, password)
    except imaplib.IMAP4.error:
        raise ValidationError("Failed to create email account: invalid credentials") from None
    except (socket.timeout, socket.gaierror, OSError) as exc:
        raise ValidationError(f"Could not connect to the mail server: {exc}") from None
    finally:
        if connection is not None:
            try:
                connection.logout()
            except Exception:  # noqa: BLE001 - closing a failed connection
                pass


def validate_email_account(account) -> None:
    """Check whichever directions the account has enabled (`email_account.py:156-168`),
    with its three escape hatches: `awaiting_password` returns at once; a local
    `smtp_server` needs no password; `no_smtp_authentication` skips the login but still
    opens the socket. A Frappe Mail account with either direction on is always refused
    (its service config has no password and no server): intended, as the old backend.
    """
    if getattr(account, "awaiting_password", False):
        return

    # `decrypt` passes an unencrypted value through, so this is right both for an unsaved
    # account (plaintext) and a stored one (ciphertext).
    password = decrypt(getattr(account, "password", ""))
    has_credentials = bool(password) or account.smtp_server in ("127.0.0.1", "localhost")
    if not has_credentials:
        if account.enable_incoming or (
            account.enable_outgoing and not account.no_smtp_authentication
        ):
            raise ValidationError("Password is required or select Awaiting Password")
        return

    if account.enable_outgoing:
        smtp = smtp_settings(account, password)
        check_smtp(
            smtp["host"],
            smtp["port"],
            username=smtp["username"],
            password=smtp["password"],
            use_tls=smtp["use_tls"],
            use_ssl=smtp["use_ssl"],
            authenticate=not account.no_smtp_authentication,
        )

    if account.enable_incoming and account.use_imap:
        check_imap(
            getattr(account, "email_server", "") or account.smtp_server,
            getattr(account, "incoming_port", None),
            username=account.email_id,
            password=password,
        )
