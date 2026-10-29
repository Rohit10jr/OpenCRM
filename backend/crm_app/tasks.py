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
from django.utils import timezone

#: `PHASE_5_ASYNC.md` §1 — invitations expire after 3 days
#: (``crm_invitation.py:105-116``).
INVITATION_EXPIRY_DAYS = 3

#: ``clear_old_versions(days=14)`` (``crm_view_settings.py:311-319``).
VERSION_RETENTION_DAYS = 14

#: The **only** doctype whose versions are pruned, named as a constant so the narrowness
#: is visible at the call site rather than buried in a filter. Upstream prunes saved-view
#: churn and nothing else; Lead and Deal history is the timeline and is kept forever.
VERSION_CHURN_DOCTYPE = "CRM View Settings"


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
    """``crm_view_settings.py:311-319`` — prunes **saved-view churn**, nothing else.

    **Read the next paragraph before changing this.** The name invites a general
    "delete old audit rows" implementation, and that would silently erase the timeline.

    Upstream deletes exactly one doctype's versions::

        frappe.db.delete("Version", {
            "ref_doctype": "CRM View Settings",      # <- only this
            "creation": ("<", add_days(now_datetime(), -days)),
        })

    Saved views are edited constantly - every column drag and filter tweak is a save, and
    each save writes a version row holding two copies of the column JSON. Nobody reads
    the history of a list view. **Lead and Deal versions are never pruned, by upstream or
    by us**: those are the audit trail `get_activities` renders, and upstream keeps them
    forever.

    ### Why this currently deletes nothing

    Not because `Version` is unmodelled - it has been since the phase-4 review. Because
    **this port does not track `CRM View Settings`**, so the rows it targets are never
    created (specs/VERSION_HISTORY.md). Upstream tracks six doctypes and displays two;
    the other four are visible only through Frappe's Desk, which this port has no
    equivalent of, so recording them would be write-only data.

    Implemented rather than left as ``return 0`` so the body matches the name, and so
    that turning view tracking on later needs no second change. The guard that matters is
    `test_lead_and_deal_history_is_never_pruned`.
    """
    from frappe_core.versions import Version

    cutoff = timezone.now() - datetime.timedelta(days=days)
    deleted, _ = Version.objects.filter(
        ref_doctype=VERSION_CHURN_DOCTYPE, creation__lt=cutoff
    ).delete()
    return deleted


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


#: The task name's frequency slug -> the label stored on `Lead Sync Source`.
#: `lead_sync_source.json`'s Select options are the labels; `hooks.py`'s scheduler keys are
#: the slugs. Nothing upstream maps between them because upstream runs one job per
#: frequency that filters on the label directly; this keeps the two vocabularies in one
#: place so a typo is a KeyError here rather than a source that silently never syncs.
FREQUENCY_LABELS = {
    "5_minutes": "Every 5 Minutes",
    "10_minutes": "Every 10 Minutes",
    "15_minutes": "Every 15 Minutes",
    "hourly": "Hourly",
    "daily": "Daily",
    "monthly": "Monthly",
}


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

    # Phase 7 filled this in. The task names, queues and cron entries are unchanged from
    # phase 5 — only the body moved from `raise NotImplementedError` to real work.
    from crm_app.integrations.facebook.sync import sync_due_sources

    return sync_due_sources(FREQUENCY_LABELS[frequency])


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

    The carrier is what ``crm_app.mail.send`` finds with the outgoing-account lookup: the
    default outgoing ``Email Account``, else the config account Django's mail settings
    describe (FINDINGS.md 79) - never ``DEFAULT_FROM_EMAIL`` on its own
    (`PHASE_5_ASYNC.md` §3). The From is that account's name and address, upstream's
    ``default_sender``.

    **A deployment with neither fails this task once.** ``mail.send`` raises
    ``OutgoingEmailError``, which is not in ``autoretry_for`` - retrying would not make
    an account appear - so the task fails with a logged traceback and ``email_sent_at``
    stays null. Upstream fails the invitation in front of the inviter instead: it sends
    inside ``after_insert`` (``crm_invitation.py:34-51``, ``frappe.sendmail(now=True)``),
    so the insert itself is refused. Here the insert has already answered by the time the
    worker runs, which is the phase-5 trade-off of sending from a task rather than inside
    the request (`PHASE_5_ASYNC.md` §3).

    Idempotent: it skips an invitation that already has ``email_sent_at``, so neither a
    redelivery nor a retry after a partial failure sends a second invite.
    """
    from crm_app import mail
    from crm_app.models import CRMInvitation

    invitation = CRMInvitation._default_manager.filter(pk=invitation_name).first()
    if invitation is None or invitation.email_sent_at:
        return False

    # **A page, not the API.** Upstream links to `/api/method/crm.api.accept_invitation`
    # because that endpoint answers a GET with an HTTP *redirect* into the Desk. Ours
    # answers with JSON, so a person clicking that link would land on raw JSON — which is
    # exactly what this link did until the phase-8 review caught it.
    #
    # The SPA page calls the endpoint and acts on what it returns. Same destination for the
    # invitee, and the URL in the email is now something a human can be shown.
    invite_link = (
        f"{settings.FRONTEND_ORIGIN.rstrip('/')}/crm/accept-invitation?key={invitation.key}"
    )

    # Phase 8 moved the wording into `crm_app/templates/emails/invitation.txt`. It was an
    # f-string here; there are two emails now, and one answer to "where does the wording
    # live" is worth more than the indirection costs.
    mail.send_invitation(
        to=invitation.email, invite_link=invite_link, expiry_days=INVITATION_EXPIRY_DAYS
    )

    # update(), not save(): stamping the send time must not bump `modified`.
    CRMInvitation._default_manager.filter(pk=invitation_name).update(
        email_sent_at=timezone.now()
    )
    return True


@shared_task(
    name="crm.send_communication_email",
    # Same narrow retry list as `send_invitation_email`, for the same reason: these two
    # exceptions are the transport failing, and `autoretry_for=(Exception,)` would turn a
    # bug in the message builder into four tracebacks and a delayed failure.
    autoretry_for=(smtplib.SMTPException, OSError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def send_communication_email(communication_name: str, copy_to: str | None = None) -> bool:
    """The queued half of ``frappe.core.doctype.communication.email.make``.

    **Celery is this port's Email Queue** (decided in phase 5), so this is what upstream's
    ``frappe.sendmail(now=False, ...)`` reaches — the ``Email Queue`` row and its retry.
    ``make(now=1)`` bypasses it and sends inside the request instead, which is upstream's
    ``now`` argument.

    Idempotent: :func:`crm_app.communication.send_communication` claims the row under a
    lock (``communication_date``) before sending and returns without sending when it is
    already claimed, so two deliveries cannot both send; a failed send clears the claim
    and the retry does the work.

    ``copy_to`` is the resolved "send me a copy" address, worked out at request time
    because a worker has no session user to resolve it from.

    It takes the Communication's *name*, not a built message: a queued message is an
    argument list that may be replayed much later, and re-reading the row means the worker
    sends what is stored rather than a snapshot that may since have been deleted.
    """
    from crm_app import communication

    return communication.send_communication(communication_name, copy_to=copy_to or None)


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


def _reconcile_products() -> dict:
    """The ERPNext Item <-> CRM Product sync itself.

    A named seam rather than an inline ``raise``, so the surrounding control flow (skip,
    reconcile, publish, return) could be tested against upstream's before a provider
    existed. **Phase 7 filled it in** — `crm_app/integrations/erpnext/reconcile.py`.

    Keeping the seam rather than inlining the call: it is the one place the phase-5 tests
    stub, and it keeps `tasks.py` free of an ERPNext import.
    """
    from crm_app.integrations.erpnext.reconcile import reconcile

    return reconcile()


@shared_task(name="crm.run_product_reconciliation")
def run_product_reconciliation(user: str | None = None) -> dict:
    """``crm/fcrm/doctype/crm_product/reconcile_job.py:21-37``.

    The reconciliation itself is an **ERPNext integration** — it reads
    ``ERPNext CRM Settings`` and syncs Item <-> CRM Product, both phase-7 deferred. What
    is *not* deferred is the completion event, which `PHASE_6_REALTIME.md` §2 lists as one
    of the two events phase 6 consumes.

    **The skip path returns before publishing**, exactly as ``reconcile_job.py:24-25``
    does. Phase 5 published unconditionally, so that phase 6 would have an emitter to wire
    up; that was backwards — it announced a sync that had not happened. Here the flag gate
    is upstream's ``_get_skip_reason`` and it short-circuits the same way.

    ``user`` is resolved rather than defaulted to ``None``: upstream publishes to
    ``frappe.session.user``, and in this port a ``None`` user means *broadcast*. Telling
    every connected browser that somebody else's ERPNext sync finished is not a smaller
    version of the right behaviour, it is a different one.
    """
    from crm_app.realtime import publish
    from frappe_core.session import get_current_user

    if not getattr(settings, "ENABLE_ERPNEXT", False):
        return {"skipped": "ENABLE_ERPNEXT is off"}

    summary = _reconcile_products()
    publish("crm_product_sync_complete", user=user or get_current_user())
    return summary
