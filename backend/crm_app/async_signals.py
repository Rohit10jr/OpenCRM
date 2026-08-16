"""Signals that enqueue background work — phase 5.

Upstream wires these through ``doc_events`` in ``crm/hooks.py:159-212``; here they are
Django signals, which is the mapping `PHASE_1_MODELS.md` §4 fixed for the whole port.

The interesting one is ``update_modified_background``. Upstream enqueues it from
``on_comment_insert`` (``crm/utils/__init__.py:238-249``) and from
``on_communication_update``, behind a three-part guard, and it exists so a lead rises to
the top of a list when someone comments on it.
"""

from __future__ import annotations

from django.db.models.signals import post_save

#: ``crm/utils/__init__.py:165`` — only these two ever bump.
TIMESTAMP_DOCTYPES = ("CRM Lead", "CRM Deal")


def timestamp_updates_enabled() -> bool:
    """``FCRM Settings.update_timestamp_on_new_communication``
    (``crm/utils/__init__.py:158-160``).

    Defaults to **True** in the model, matching the DocType JSON, so the behaviour is on
    unless somebody turns it off.
    """
    from crm_app.models import FCRMSettings

    value = FCRMSettings._default_manager.values_list(
        "update_timestamp_on_new_communication", flat=True
    ).first()
    # No settings row yet means nobody has opted out.
    return True if value is None else bool(value)


def should_update_modified(reference_doctype: str, reference_name: str) -> bool:
    """``crm/utils/__init__.py:158-171``, in order."""
    if not (reference_doctype and reference_name):
        return False
    if reference_doctype not in TIMESTAMP_DOCTYPES:
        return False
    return timestamp_updates_enabled()


def _enqueue_touch(reference_doctype: str, reference_name: str) -> None:
    from crm_app.tasks import update_modified_background

    if should_update_modified(reference_doctype, reference_name):
        update_modified_background.delay(reference_doctype, str(reference_name))


def on_comment_insert(sender, instance, created, **kwargs):
    """``crm/utils/__init__.py:238-249``. Only ``comment_type == "Comment"``."""
    if not created or instance.comment_type != "Comment":
        return
    _enqueue_touch(instance.reference_doctype, instance.reference_name)


def on_communication_write(sender, instance, created, **kwargs):
    """``crm/utils/__init__.py:264-...``.

    Upstream bumps on communication **update**, not insert — a reply landing on an
    existing thread is what should reorder the list.
    """
    _enqueue_touch(instance.reference_doctype, instance.reference_name)


def on_invitation_insert(sender, instance, created, **kwargs):
    """``crm_invitation.py:34-35`` — ``after_insert`` sends the invite.

    Queued rather than sent inline so a slow or dead SMTP server cannot fail the request
    that created the invitation.
    """
    if not created:
        return
    from crm_app.tasks import send_invitation_email

    send_invitation_email.delay(str(instance.pk))


def connect_signals() -> None:
    from crm_app.models import CRMInvitation
    from frappe_platform.models import Comment, Communication

    post_save.connect(on_comment_insert, sender=Comment, dispatch_uid="crm.async.comment")
    post_save.connect(
        on_communication_write, sender=Communication, dispatch_uid="crm.async.communication"
    )
    post_save.connect(
        on_invitation_insert, sender=CRMInvitation, dispatch_uid="crm.async.invitation"
    )
