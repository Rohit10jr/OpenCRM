"""The invitation email and the two accounts jobs (old `backend/crm_app/tasks.py`)."""

import datetime
import smtplib

from celery import shared_task
from celery.schedules import crontab
from django.conf import settings
from django.utils import timezone

#: Invitations expire after three days, enforced only by the daily sweep on `creation`.
INVITATION_EXPIRY_DAYS = 3


@shared_task(
    name="accounts.send_invitation_email",
    # Only the transport failing is retried; a missing account (OutgoingEmailError) or a
    # bug fails once with its traceback.
    autoretry_for=(smtplib.SMTPException, OSError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def send_invitation_email(invitation_name: str) -> bool:
    """Send one invitation (old `send_invitation_email`). Idempotent: an invitation that
    already has `email_sent_at` is skipped. The link opens the frontend page, not the
    API, whose JSON answer a person clicking it could not use."""
    from accounts.models import CRMInvitation
    from core import mail

    invitation = CRMInvitation._default_manager.filter(pk=invitation_name).first()
    if invitation is None or invitation.email_sent_at:
        return False
    invite_link = (
        f"{settings.FRONTEND_ORIGIN.rstrip('/')}/crm/accept-invitation?key={invitation.key}"
    )
    mail.send_invitation(
        to=invitation.email, invite_link=invite_link, expiry_days=INVITATION_EXPIRY_DAYS
    )
    # update(), not save(): stamping the send time must not bump `modified`.
    CRMInvitation._default_manager.filter(pk=invitation_name).update(
        email_sent_at=timezone.now()
    )
    return True


@shared_task(name="accounts.expire_invitations")
def expire_invitations() -> int:
    """Pending invitations older than three days become Expired (upstream
    `crm_invitation.py:105-116`). Returns how many."""
    from accounts.models import CRMInvitation

    cutoff = timezone.now() - datetime.timedelta(days=INVITATION_EXPIRY_DAYS)
    return CRMInvitation._default_manager.filter(
        status="Pending", creation__lt=cutoff
    ).update(status="Expired")


@shared_task(name="accounts.flush_expired_tokens")
def flush_expired_tokens() -> int:
    """Not upstream's: SimpleJWT's blacklist records every rotated refresh token and
    nothing else removes them. Deletes only tokens already past expiry, so it logs nobody
    out; returns how many, so a dead job shows as a flat line."""
    from django.core.management import call_command
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

    before = OutstandingToken.objects.filter(expires_at__lt=timezone.now()).count()
    call_command("flushexpiredtokens")
    return before


BEAT_SCHEDULE = {
    "expire-invitations": {
        "task": "accounts.expire_invitations",
        "schedule": crontab(hour=0, minute=0),
    },
    "flush-expired-tokens": {
        "task": "accounts.flush_expired_tokens",
        "schedule": crontab(hour=1, minute=0),
    },
}
