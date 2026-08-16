"""Signals that enqueue background work — phase 5.

Upstream wires these through ``doc_events`` in ``crm/hooks.py:159-212``; here they are
Django signals, which is the mapping `PHASE_1_MODELS.md` §4 fixed for the whole port.

The interesting one is ``update_modified_background``. Upstream enqueues it from
``on_comment_insert`` (``crm/utils/__init__.py:238-249``) and from
``on_communication_update``, behind a three-part guard, and it exists so a lead rises to
the top of a list when someone comments on it.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save

logger = logging.getLogger(__name__)

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


#: ``comment.py``'s ``comment_type`` -> docinfo key map. Only ``comments`` is consumed by
#: this frontend (``Activities.vue:591`` returns early on anything else), but the mapping
#: is the source's and the extra keys cost nothing.
DOCINFO_KEYS = {
    "Comment": "comments",
    "Like": "like_logs",
    "Assignment": "assignments",
    "Attachment": "attachments",
}


def _notify_watchers(doc, key: str, action: str = "add") -> None:
    """Tell whoever has the document open that its activity feed changed.

    Phase 6. This is what makes `PHASE_6_REALTIME.md` §3's per-document groups do
    something — without it ``doc_subscribe`` joins a group nothing ever sends to. The
    event name and payload are Frappe's own, so ``Activities.vue`` needs no new handler:
    it destructures ``{doc, key}`` and matches ``doc.reference_doctype`` /
    ``doc.reference_name`` against the document it is showing (``Activities.vue:590-596``).

    ``doc`` is sent as a small dict rather than the full serialised document. The handler
    reads three fields, and a signal that serialises an entire Comment on every write —
    including its attachment queries — would be paying for a payload nobody opens.

    The whole body is exception-safe. A signal that raised here would fail the *write*,
    which is precisely the dependency §4's last criterion forbids.
    """
    reference_doctype = getattr(doc, "reference_doctype", None)
    reference_name = getattr(doc, "reference_name", None)
    if not (reference_doctype and reference_name and key):
        return

    try:
        from crm_app import realtime

        realtime.publish_to_doc(
            reference_doctype,
            str(reference_name),
            "docinfo_update",
            message={
                "doc": {
                    "name": str(doc.pk),
                    "reference_doctype": reference_doctype,
                    "reference_name": str(reference_name),
                },
                "key": key,
                "action": action,
            },
        )
    except Exception:  # pragma: no cover - publish_to_doc already swallows its own
        logger.warning("realtime: docinfo_update could not be prepared", exc_info=True)


def on_comment_insert(sender, instance, created, **kwargs):
    """``crm/utils/__init__.py:238-249``. Only ``comment_type == "Comment"``."""
    if created and instance.comment_type == "Comment":
        _enqueue_touch(instance.reference_doctype, instance.reference_name)

    # The realtime notice is *not* limited to comments, and not to inserts: a like or an
    # attachment changes the same activity feed, and an edited comment changes what is
    # shown. `comment.py`'s own notify_change fires on both write and delete.
    key = DOCINFO_KEYS.get(instance.comment_type)
    if key:
        _notify_watchers(instance, key, "add" if created else "update")


def on_communication_write(sender, instance, created, **kwargs):
    """``crm/utils/__init__.py:264-...``.

    Upstream bumps on communication **update**, not insert — a reply landing on an
    existing thread is what should reorder the list.
    """
    _enqueue_touch(instance.reference_doctype, instance.reference_name)
    _notify_watchers(instance, "communications", "add" if created else "update")


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
