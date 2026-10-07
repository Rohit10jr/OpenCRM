"""Mail-server connection checks.

A4 - upstream validates an ``Email Account``'s credentials by opening a live connection
before saving it (``frappe/email/doctype/email_account/email_account.py:156-168``)::

    if self.enable_incoming:
        self.get_incoming_server()      # opens IMAP
    if self.enable_outgoing:
        self.validate_smtp_conn()       # opens an SMTP session

Phase 3 saved accounts unvalidated, on the grounds that this port has no mail layer.
That was wrong: Django ships one. ``django.core.mail.backends.smtp.EmailBackend`` wraps
``smtplib``, and ``imaplib`` is standard library - so the check is a few lines, not a
subsystem.

It matters because the failure is silent. A password typed wrong saves cleanly, and the
first anyone knows is that invitations never arrived - days later, with nothing pointing
at the cause. The frontend is already written for the loud version: ``EmailAdd.vue:149``
holds an unreachable "Failed to create email account: invalid credentials" waiting for
this to exist.

### The timeout, and why it is not upstream's number

**Upstream passes no timeout.** ``smtplib`` and ``imaplib`` then fall back to the
system default, which on an unreachable host means the save blocks until the OS gives up
- typically 20 to 130 seconds depending on platform and whether the host resolves. A
misconfigured server therefore hangs the request rather than reporting an error, and the
user sees a spinner, not the message written for them.

We pass an explicit timeout (:data:`MAIL_CONNECT_TIMEOUT`, default 10s) so the failure
arrives as an error while somebody is still looking at the form.

That is a **deliberate divergence** and it has a cost worth stating: a genuinely slow but
working mail server - a loaded corporate relay, or one reached over a poor link - could
exceed 10 seconds and be reported as broken when it is merely slow. If that happens, the
fix is to raise ``MAIL_CONNECT_TIMEOUT``, not to remove it. Recorded in
``UPSTREAM_BUGS.md``.
"""

from __future__ import annotations

import imaplib
import smtplib
import socket

from django.conf import settings

from frappe_core.exceptions import ValidationError
from frappe_core.secrets import decrypt

#: Seconds to wait for a mail server before calling it unreachable. Upstream passes no
#: timeout at all - see the module docstring for why we do.
DEFAULT_MAIL_CONNECT_TIMEOUT = 10


def _timeout() -> int:
    return int(getattr(settings, "MAIL_CONNECT_TIMEOUT", DEFAULT_MAIL_CONNECT_TIMEOUT))


def smtp_settings(account, password: str | None = None) -> dict:
    """The SMTP connection an ``Email Account`` describes, as Django backend arguments.

    ``EmailAccount.get_smtp_server``'s rules (``email_account.py``), in one place so the
    save-time check and the send cannot disagree - a check that passed with one set of
    flags while the send used another was Codex finding 3 on the email.make stage:

    * the login is ``login_id`` when ``login_id_is_different``, else ``email_id``;
    * ``use_ssl_for_outgoing`` is implicit TLS on 465 and excludes STARTTLS (Django
      refuses both flags at once); otherwise ``use_tls`` on 587;
    * ``no_smtp_authentication`` sends no credentials at all.

    ``password`` is the decrypted credential when the caller already has it (validation
    runs on an unsaved account whose password is still plaintext); otherwise the stored
    value is decrypted here.
    """
    use_ssl = bool(getattr(account, "use_ssl_for_outgoing", False))
    authenticate = not getattr(account, "no_smtp_authentication", False)
    username = ""
    secret = ""
    if authenticate:
        login_id = getattr(account, "login_id", "") or ""
        different = bool(getattr(account, "login_id_is_different", False))
        username = login_id if different and login_id else account.email_id
        secret = password if password is not None else decrypt(account.password)
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
    """Open an SMTP session, then close it. Raises :class:`ValidationError` on failure.

    Port of ``validate_smtp_conn`` (``email_account.py:183-188``), which does the same
    thing through ``get_smtp_server().session``.

    Uses Django's backend rather than raw ``smtplib`` so TLS handling, EHLO ordering and
    error wrapping match how this application will actually send mail. Checking with one
    stack and sending with another would let a check pass where sending fails.
    """
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
        # Upstream's wording, which EmailAdd.vue:149 already displays.
        raise ValidationError("Failed to create email account: invalid credentials") from None
    except (smtplib.SMTPException, socket.timeout, socket.gaierror, OSError) as exc:
        raise ValidationError(f"Could not connect to the mail server: {exc}") from None
    finally:
        try:
            backend.close()
        except Exception:  # pragma: no cover - closing a failed connection
            pass


def check_imap(
    host: str,
    port: int | None,
    username: str = "",
    password: str = "",
    use_ssl: bool = True,
) -> None:
    """Open an IMAP connection and log in. Port of ``get_incoming_server()``.

    ``imaplib`` is standard library, so this needs no backend - but it does need the same
    explicit timeout, for the same reason.
    """
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
            except Exception:  # pragma: no cover - closing a failed connection
                pass


def validate_email_account(account) -> None:
    """Check whichever directions the account has enabled.

    Mirrors ``email_account.py:156-168``, including its three escape hatches:

    * ``awaiting_password`` - upstream's own "save it now, credentials later" path, so
      this is not us inventing a way to skip the check;
    * a local ``smtp_server`` is treated as usable without a password;
    * ``no_smtp_authentication`` skips the login step but still opens the socket, which
      is the point - an unreachable relay is still worth catching.
    """
    if getattr(account, "awaiting_password", False):
        return

    # `decrypt` passes an unprefixed value straight through, which is what makes this
    # correct on both paths: validation normally runs on an *unsaved* instance whose
    # password is still plaintext, but re-validating a stored account hands us
    # ciphertext. See frappe_core/secrets.py.
    password = decrypt(account.password)
    has_credentials = bool(password) or account.smtp_server in ("127.0.0.1", "localhost")
    if not has_credentials:
        if account.enable_incoming or (
            account.enable_outgoing and not account.no_smtp_authentication
        ):
            # Upstream's message, verbatim (email_account.py:168).
            raise ValidationError("Password is required or select Awaiting Password")
        return

    if account.enable_outgoing:
        # The very settings the send will use (crm_app.communication.open_backend).
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
