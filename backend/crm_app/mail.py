"""Outbound mail — one place for "who is it from", one place for "what does it say".

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
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

#: Upstream's own product name, used in subjects and bodies.
APP_NAME = "Frappe CRM"


def default_sender() -> str:
    """The configured default-outgoing `Email Account`, falling back to settings.

    `PHASE_5_ASYNC.md` §3: outbound identity comes from the Email Account, not from
    `DEFAULT_FROM_EMAIL`. The fallback exists so a deployment that has not configured mail
    still sends something rather than raising.
    """
    from frappe_platform.models import EmailAccount

    configured = (
        EmailAccount._default_manager.filter(default_outgoing=True)
        .values_list("email_id", flat=True)
        .first()
    )
    return configured or settings.DEFAULT_FROM_EMAIL


def send(template: str, *, subject: str, to: str, context: dict) -> None:
    """Render `emails/<template>.txt` and send it. Raises on transport failure.

    Deliberately does not swallow: the two callers want opposite things — the invitation
    task retries on `SMTPException`, and the password-reset endpoint must stay silent — and
    only they know which.
    """
    body = render_to_string(f"emails/{template}.txt", {"app_name": APP_NAME, **context})
    EmailMessage(subject=subject, body=body, from_email=default_sender(), to=[to]).send(
        fail_silently=False
    )


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
