"""Celery tasks — phase 5.

Ported from the ``frappe.enqueue`` call sites and the ``scheduler_events`` dict in
``crm/hooks.py``. Task names are the ``crm.*`` strings the Beat schedule references;
they are declared, not derived, for the same reason the endpoint paths are.

**Idempotence is a requirement here, not a nicety** (`PHASE_5_ASYNC.md` §5): Celery
redelivers on worker loss, so every task below either filters to work that is still
outstanding or writes a value that does not accumulate.
"""

from __future__ import annotations

import datetime
import smtplib

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

#: `PHASE_5_ASYNC.md` §1 — invitations expire after 3 days
#: (``crm_invitation.py:105-116``).
INVITATION_EXPIRY_DAYS = 3

#: ``clear_old_versions(days=14)`` (``crm_view_settings.py:311-319``).
VERSION_RETENTION_DAYS = 14


# ---------------------------------------------------------------------------
# Scheduled — daily
# ---------------------------------------------------------------------------


@shared_task(name="crm.expire_invitations")
def expire_invitations() -> int:
    """``crm_invitation.py:105-116``. Returns how many were expired.

    Idempotent by construction: it only selects ``status="Pending"``, and it sets them
    to ``Expired``, so a redelivery finds nothing left to do.
    """
    from crm_app.models import CRMInvitation

    cutoff = timezone.now() - datetime.timedelta(days=INVITATION_EXPIRY_DAYS)
    stale = CRMInvitation._default_manager.filter(status="Pending", creation__lt=cutoff)
    # update(), not save(): this is a status sweep, not a document edit, and there is no
    # per-row logic to run.
    return stale.update(status="Expired")


@shared_task(name="crm.clear_old_versions")
def clear_old_versions(days: int = VERSION_RETENTION_DAYS) -> int:
    """``crm_view_settings.py:311-319`` — deletes old ``Version`` rows.

    **A no-op here, and it will stay one until `Version` is modelled.** Upstream deletes
    from the framework's document-version audit table, which this port does not have
    (see `PROGRESS_PHASE_3.md` — it is also why `get_activities` has no field-change
    entries). Registered anyway so the Beat entry matches `hooks.py`, and so the day
    `Version` lands there is already a job pruning it.

    Returns 0 rather than raising: a scheduled job that errors every night trains people
    to ignore the log.
    """
    return 0


@shared_task(name="crm.flush_expired_tokens")
def flush_expired_tokens() -> int:
    """`PHASE_5_ASYNC.md` §2a — not upstream; it exists because we chose JWT.

    ``token_blacklist`` records every rotated refresh token and nothing removes them.
    With rotation on and a 5-minute access token that is roughly 12 rows per active user
    per hour, growing forever.

    SimpleJWT ships the cleanup as a management command; it only deletes tokens already
    past expiry, so it cannot log anyone out. Returns the number deleted so a silently
    dead job is visible as a flatlining number rather than an absence of errors.
    """
    from django.core.management import call_command

    try:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    except ImportError:  # pragma: no cover - blacklist app not installed
        return 0

    before = OutstandingToken.objects.filter(expires_at__lt=timezone.now()).count()
    call_command("flushexpiredtokens")
    return before


# ---------------------------------------------------------------------------
# Scheduled — lead sync, deferred to phase 7
# ---------------------------------------------------------------------------


def lead_sync_enabled() -> bool:
    return bool(getattr(settings, "ENABLE_FACEBOOK_LEAD_SYNC", False))


def _sync_leads(frequency: str) -> dict:
    """`PHASE_5_ASYNC.md` §1: *"register the beat entries now, leave the tasks as no-ops
    behind a feature flag."*

    The Facebook lead-sync doctypes (``Lead Sync Source``, ``Facebook Lead Form`` …) are
    phase-7 deferred and not modelled, so there is nothing to sync against. Returning a
    ``skipped`` marker rather than silently succeeding keeps the distinction visible in
    the result backend.
    """
    if not lead_sync_enabled():
        return {"skipped": "ENABLE_FACEBOOK_LEAD_SYNC is off", "frequency": frequency}
    raise NotImplementedError(
        "Lead sync is phase 7; the flag is on but no provider is implemented"
    )


@shared_task(name="crm.sync_leads_daily")
def sync_leads_daily() -> dict:
    return _sync_leads("daily")


@shared_task(name="crm.sync_leads_hourly")
def sync_leads_hourly() -> dict:
    return _sync_leads("hourly")


@shared_task(name="crm.sync_leads_monthly")
def sync_leads_monthly() -> dict:
    return _sync_leads("monthly")


@shared_task(name="crm.sync_leads_5_minutes")
def sync_leads_5_minutes() -> dict:
    return _sync_leads("5_minutes")


@shared_task(name="crm.sync_leads_10_minutes")
def sync_leads_10_minutes() -> dict:
    return _sync_leads("10_minutes")


@shared_task(name="crm.sync_leads_15_minutes")
def sync_leads_15_minutes() -> dict:
    return _sync_leads("15_minutes")


# ---------------------------------------------------------------------------
# Enqueued
# ---------------------------------------------------------------------------


@shared_task(name="crm.update_modified_background")
def update_modified_background(doctype: str, docname: str) -> bool:
    """``crm/utils/__init__.py:252-253``.

    ``frappe.db.set_value(..., "modified", now(), update_modified=False)`` — a bare
    column write that bumps ``modified`` **without** touching ``modified_by``.

    `PHASE_5_ASYNC.md` §2 is right that this looks trivial and is not: it is why a lead
    jumps to the top of a list when someone comments on it, and the default list sort is
    ``modified desc``. Using ``save()`` here would re-stamp ``modified_by`` to whoever
    the worker happens to be running as, quietly rewriting authorship.
    """
    from frappe_core import registry

    if not registry.has_doctype(doctype):
        return False
    model = registry.get_model(doctype)
    updated = model._default_manager.filter(pk=docname).update(modified=timezone.now())
    return bool(updated)


@shared_task(
    name="crm.send_invitation_email",
    # `PHASE_5_ASYNC.md` §3: *"Use Django's email backend plus a Celery task with
    # retry."* Frappe's Email Queue retries a failed send; dropping the invite on the
    # first refused connection would leave a user unable to sign in with no trace.
    #
    # The retry list is narrow on purpose. `autoretry_for=(Exception,)` would also retry
    # a bug in this function three times before giving up, turning one traceback into
    # four and delaying the failure. These two are the transport failing.
    autoretry_for=(smtplib.SMTPException, OSError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def send_invitation_email(invitation_name: str) -> bool:
    """``crm_invitation.py:37-51``.

    Outbound identity comes from the configured default-outgoing ``Email Account``, not
    ``DEFAULT_FROM_EMAIL`` (`PHASE_5_ASYNC.md` §3).

    Idempotent: it skips an invitation that already has ``email_sent_at``, so neither a
    redelivery nor a retry after a partial failure sends a second invite.
    """
    from django.core.mail import EmailMessage

    from crm_app.models import CRMInvitation
    from frappe_platform.models import EmailAccount

    invitation = CRMInvitation._default_manager.filter(pk=invitation_name).first()
    if invitation is None or invitation.email_sent_at:
        return False

    sender = (
        EmailAccount._default_manager.filter(default_outgoing=True)
        .values_list("email_id", flat=True)
        .first()
    ) or settings.DEFAULT_FROM_EMAIL

    title = "Frappe CRM"
    # `frappe.utils.get_url()` upstream; the path is an API route, so it is the backend's
    # own origin, not the frontend's (see SITE_URL in settings/base.py).
    invite_link = (
        f"{settings.SITE_URL}/api/method/crm.api.accept_invitation?key={invitation.key}"
    )

    EmailMessage(
        subject=f"You have been invited to join {title}",
        body=(
            f"You have been invited to join {title}.\n\n"
            f"Accept the invitation: {invite_link}\n"
        ),
        from_email=sender,
        to=[invitation.email],
    ).send(fail_silently=False)

    # update(), not save(): stamping the send time must not bump `modified`.
    CRMInvitation._default_manager.filter(pk=invitation_name).update(
        email_sent_at=timezone.now()
    )
    return True


@shared_task(name="crm.delete_bulk_docs")
def delete_bulk_docs_task(doctype: str, items: list, delete_linked: bool = False, user: str | None = None):
    """``crm/api/doc.py:833-836`` — the enqueued half of ``delete_bulk_docs``.

    **The permission check runs inside the task, against ``user``**, not just at request
    time (`PHASE_5_ASYNC.md` §5). That matters twice over. The task runs later, in a
    worker with no request context, so without an explicit user the ambient session is
    ``Guest``. And a queued message is an argument list like any other: re-authorizing
    here means a task that is replayed, hand-crafted or delayed past a permission change
    still cannot delete more than ``user`` may delete right now.

    It calls the two halves directly rather than re-entering ``delete_bulk_docs``, which
    would enqueue the batch again and never terminate.

    Idempotent: ``authorize_bulk_delete`` drops names that no longer exist.
    """
    from crm_app.api.doc import authorize_bulk_delete, perform_bulk_delete
    from frappe_core.session import get_current_user, session_user

    with session_user(user):
        # `session_user(None)` binds Guest; read it back rather than passing None down,
        # so a task enqueued without a user is denied rather than unfiltered.
        targets = authorize_bulk_delete(doctype, [str(i) for i in items], get_current_user())
        perform_bulk_delete(doctype, targets, delete_linked)
    return "success"


@shared_task(name="crm.run_product_reconciliation")
def run_product_reconciliation(user: str | None = None) -> dict:
    """``crm/fcrm/doctype/crm_product/reconcile_job.py:21-37``.

    The reconciliation itself is an **ERPNext integration** — it reads
    ``ERPNext CRM Settings`` and syncs Item <-> CRM Product, both phase-7 deferred. So
    the body is a flag-gated no-op.

    What is *not* deferred is the completion event: upstream ends with
    ``frappe.publish_realtime("crm_product_sync_complete", user=...)`` and
    `PHASE_6_REALTIME.md` §2 lists it as one of the events phase 6 consumes. The publish
    call is made unconditionally so phase 6 has a real emitter to wire up.
    """
    from crm_app.realtime import publish

    if not getattr(settings, "ENABLE_ERPNEXT", False):
        summary = {"skipped": "ENABLE_ERPNEXT is off"}
    else:  # pragma: no cover - phase 7
        raise NotImplementedError(
            "Product reconciliation is phase 7; the flag is on but no provider exists"
        )

    publish("crm_product_sync_complete", user=user)
    return summary
