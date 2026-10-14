"""Outbound system mail — one place for "who carries it", one place for "what does it say".

`PHASE_8_AUTH_AND_DESK.md`: the wording lives in a Django template under
`crm_app/templates/emails/`, editable by whoever deploys. `APP_DIRS` is already `True`, so
Django finds it with no settings change and no new doctype.

Upstream's answer is a `password_reset` template *doctype* with a System Settings override,
so a non-technical admin can reword it in the product. That needs a settings screen to edit
it, and building one to change an email body is not what "let a second person log in"
means. If in-product editing is wanted later, the field belongs on `FCRM Settings`
(manager-writable already) plus a screen — a feature, sized as one.

**The invitation email moved here too**, out of the f-string it was built from in
`tasks.py`. Two emails, one mechanism, so the next person looking for "where does the
wording live" finds one answer rather than two.

**The carrier is the one a lead's mail uses** (FINDINGS.md 79). Upstream sends both through
`frappe.sendmail`, which with no sender takes whatever outgoing account the lookup finds
and that account's `default_sender` (`QueueBuilder.sender`, `email_queue.py:719-724`).
Until 13 Oct 2026 this module borrowed the default outgoing account's *address* and sent
through Django's `EMAIL_BACKEND`, while a lead's mail went through the account's own SMTP
— two transports, and the invitation printed in the worker's console. :func:`send` now
runs `crm_app.communication.find_outgoing_account()` and `open_backend` like everything
else: the default outgoing account carries system mail, and a deployment with none falls
through to the config account Django's mail settings describe.
"""

from __future__ import annotations

import logging
from email.utils import formataddr

from django.core.mail import EmailMessage
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

#: Upstream's own product name, used in subjects and bodies.
APP_NAME = "Open CRM"


def send(template: str, *, subject: str, to: str, context: dict) -> None:
    """Render `emails/<template>.txt` and send it through the outgoing account.

    The account is what `find_outgoing_account()` returns with no sender and no reference
    doctype — the default outgoing account, else the config account — which is what
    upstream's `frappe.sendmail` reaches with no sender. From is the account's
    `default_sender` (`email_account.py:468-469`), `formataddr((name, email_id))`: with
    the config account, `Frappe <notifications@...>`. Nothing to send through raises
    `OutgoingEmailError` with upstream's sentence (`find_outgoing(_raise_error=True)`,
    `email_account.py:528-532`).

    Deliberately does not swallow: the two callers want opposite things — the invitation
    task retries on `SMTPException`, and the password-reset endpoint must stay silent — and
    only they know which. `OutgoingEmailError` is on neither list: the task fails once with
    a logged traceback (`tasks.send_invitation_email` says why that is the trade), and the
    endpoint answers its one sentence as it does for every failure.
    """
    # Imported here: `crm_app.communication` reaches back into the models, and this module
    # is imported by the tasks and the auth endpoints alike.
    from crm_app import communication
    from frappe_core.exceptions import OutgoingEmailError

    account = communication.find_outgoing_account()
    if account is None:
        # Verbatim from email_account.py:530.
        raise OutgoingEmailError(
            "Please setup default outgoing Email Account from Tools > Email Account"
        )

    body = render_to_string(f"emails/{template}.txt", {"app_name": APP_NAME, **context})
    EmailMessage(
        subject=subject,
        body=body,
        from_email=formataddr((account.email_account_name, account.email_id)),
        to=[to],
        connection=communication.open_backend(account),
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
