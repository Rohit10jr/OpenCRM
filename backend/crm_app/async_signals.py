"""Signals that enqueue background work — phase 5.

Upstream wires these through ``doc_events`` in ``crm/hooks.py:159-212``; here they are
Django signals, which is the mapping `PHASE_1_MODELS.md` §4 fixed for the whole port.

The interesting one is ``update_modified_background``. Upstream enqueues it from
``on_comment_insert`` (``crm/utils/__init__.py:238-249``), behind a three-part guard,
and it exists so a lead rises to the top of a list when someone comments on it. A
communication bumps ``modified`` too, inline rather than queued, in the same write that
sets the lead's or deal's communication status (``apply_communication_update``).
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save, pre_save

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


def communication_status_for(instance) -> str | None:
    """``_get_communication_status`` (``crm/utils/__init__.py:174-193``): the status a
    lead's or deal's ``communication_status`` takes from this communication, if any.

    ``Open`` for a received one when ``auto_reopen_on_new_communication`` is on,
    ``Replied`` for a sent one when ``auto_mark_replied_on_response`` is on; the two
    General settings in Settings (FINDINGS.md 60). Both are off by default.
    """
    if not (instance.reference_doctype and instance.reference_name):
        return None
    if instance.sent_or_received not in ("Sent", "Received"):
        return None

    from crm_app.models import FCRMSettings

    switches = FCRMSettings._default_manager.values_list(
        "auto_reopen_on_new_communication", "auto_mark_replied_on_response"
    ).first() or (False, False)
    auto_reopen, auto_replied = switches

    if instance.sent_or_received == "Received" and auto_reopen:
        return "Open"
    if instance.sent_or_received == "Sent" and auto_replied:
        return "Replied"
    return None


def apply_communication_update(instance) -> None:
    """``on_communication_update`` (``crm/utils/__init__.py:261-290``), on every save of
    a communication, the first included, as Frappe's ``on_update`` runs on insert too.

    One column write on the lead or deal, no save (``frappe.db.set_value`` with
    ``update_modified=False``), so no validation or SLA step runs and ``modified_by``
    is left alone:

    * ``modified`` set to now when ``update_timestamp_on_new_communication`` is on;
    * ``communication_status`` set to the status above, only when this communication is
      the latest on the document (``frappe.get_last_doc``, ``creation desc``), so an old
      thread edited later does not reopen a lead that has moved on.

    Upstream did the ``modified`` part in a background job until 29 Mar 2026
    (``3eb42143f``), which is what the port copied; now both are inline, as here.

    A status named here that the ``CRM Communication Status`` table lacks is skipped:
    upstream's ``set_value`` would store the dangling name, and the port's column is a
    foreign key that cannot. ``seed_defaults`` writes both rows.
    """
    doctype, name = instance.reference_doctype, instance.reference_name
    if not (doctype and name) or doctype not in TIMESTAMP_DOCTYPES:
        return

    from django.utils import timezone

    from crm_app.models import CRMCommunicationStatus
    from frappe_core import registry
    from frappe_platform.models import Communication

    values: dict = {}
    if timestamp_updates_enabled():
        values["modified"] = timezone.now()

    status = communication_status_for(instance)
    if status:
        latest = (
            Communication._default_manager.filter(reference_doctype=doctype, reference_name=name)
            .order_by("-creation")
            .values_list("pk", flat=True)
            .first()
        )
        if latest == instance.pk:
            if CRMCommunicationStatus._default_manager.filter(pk=status).exists():
                values["communication_status_id"] = status
            else:
                logger.warning("communication status %r is not a CRM Communication Status", status)

    if values and registry.has_doctype(doctype):
        registry.get_model(doctype)._default_manager.filter(pk=name).update(**values)


def on_communication_write(sender, instance, created, **kwargs):
    """``crm/hooks.py:168-171``: ``on_update`` -> ``on_communication_update``."""
    apply_communication_update(instance)
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


# --- ToDo: crm/api/todo.py -----------------------------------------------------------------
#
# Registered upstream in hooks.py:doc_events for ToDo. ``after_insert`` makes the
# assignee the lead's or deal's owner and notifies them; ``on_update`` notifies when the
# assignment is cancelled and clears the owner. The bell menu is how a rep learns a
# lead was handed to them (FINDINGS.md 18). ``get_notification_text`` is HTML the
# frontend renders as such, so its shape is kept byte for byte.

_ASSIGNABLE = ("CRM Lead", "CRM Deal", "CRM Task")


def _remember_todo_status(sender, instance, **kwargs):
    """``has_value_changed("status")`` needs the stored value; one read before the write."""
    instance._previous_status = None
    if instance._state.adding or instance.pk is None:
        return
    instance._previous_status = (
        sender._default_manager.filter(pk=instance.pk).values_list("status", flat=True).first()
    )


def _owner_field(reference_type: str) -> str:
    return "lead_owner" if reference_type == "CRM Lead" else "deal_owner"


def _set_owner(reference_type: str, reference_name: str, user) -> None:
    """``frappe.db.set_value(..., update_modified=False)``: a bare update, no save."""
    from frappe_core import registry

    registry.get_model(reference_type)._default_manager.filter(pk=reference_name).update(
        **{f"{_owner_field(reference_type)}_id": user}
    )


def _full_name(user: str | None) -> str:
    from frappe_platform.models import User

    if not user:
        return ""
    return (
        User._default_manager.filter(pk=user).values_list("full_name", flat=True).first()
        or user
    )


def get_notification_text(owner: str, todo, reference_doc, is_cancelled: bool = False) -> str:
    """``crm/api/todo.py:get_notification_text``, verbatim."""
    name = todo.reference_name
    doctype = todo.reference_type
    if doctype.startswith("CRM "):
        doctype = doctype[4:].lower()
    if doctype in ("lead", "deal"):
        name = (
            getattr(reference_doc, "lead_name", None) or name
            if doctype == "lead"
            else getattr(reference_doc, "organization_id", None)
            or getattr(reference_doc, "lead_name", None)
            or name
        )
        bold_name = f'<span class="font-medium text-ink-gray-9">{name}</span>'
        bold_owner = f'<span class="font-medium text-ink-gray-9">{owner}</span>'
        if is_cancelled:
            return f"""
                <div class="mb-2 leading-5 text-ink-gray-5">
                    <span>Your assignment on {doctype} {bold_name} has been removed by {bold_owner}</span>
                </div>
            """
        return f"""
            <div class="mb-2 leading-5 text-ink-gray-5">
                <span class="font-medium text-ink-gray-9">{owner}</span>
                <span>assigned a {doctype} {bold_name} to you</span>
            </div>
        """
    if doctype == "task":
        bold_title = f'<span class="font-medium text-ink-gray-9">{reference_doc.title}</span>'
        bold_owner = f'<span class="font-medium text-ink-gray-9">{owner}</span>'
        if is_cancelled:
            return f"""
                <div class="mb-2 leading-5 text-ink-gray-5">
                    <span>Your assignment on task {bold_title} has been removed by {bold_owner}</span>
                </div>
            """
        return f"""
            <div class="mb-2 leading-5 text-ink-gray-5">
                <span class="font-medium text-ink-gray-9">{owner}</span>
                <span>assigned a new task {bold_title} to you</span>
            </div>
        """
    return ""


def get_redirect_to_doc(todo, reference_doc) -> tuple[str, str]:
    """A task notification lands on the task's own lead or deal."""
    if todo.reference_type == "CRM Task":
        return reference_doc.reference_doctype, reference_doc.reference_docname
    return todo.reference_type, todo.reference_name


def notify_user(notification: dict) -> None:
    """``crm_notification.py:notify_user``: never notify yourself, never twice."""
    from crm_app.models import CRMNotification

    if notification["owner"] == notification["assigned_to"]:
        return
    values = {
        "from_user_id": notification["owner"],
        "to_user_id": notification["assigned_to"],
        "type": notification["notification_type"],
        "message": notification["message"],
        "notification_text": notification["notification_text"],
        "notification_type_doctype": notification["reference_doctype"],
        "notification_type_doc": notification["reference_docname"],
        "reference_doctype": notification["redirect_to_doctype"],
        "reference_name": notification["redirect_to_docname"],
    }
    if CRMNotification._default_manager.filter(**values).exists():
        return
    CRMNotification._default_manager.create(**values)


def notify_assigned_user(todo, is_cancelled: bool = False) -> None:
    """``crm/api/todo.py:notify_assigned_user``, verbatim in its two sentences."""
    from frappe_core import registry
    from frappe_core.session import get_current_user

    if not registry.has_doctype(todo.reference_type):
        return
    reference = (
        registry.get_model(todo.reference_type)
        ._default_manager.filter(pk=todo.reference_name)
        .first()
    )
    if reference is None:
        return
    acting_user = get_current_user() or todo.assigned_by_id
    owner = _full_name(acting_user)
    if is_cancelled:
        message = (
            f"Your assignment on {todo.reference_type} {todo.reference_name} "
            f"has been removed by {owner}"
        )
    else:
        message = f"{owner} assigned a {todo.reference_type} {todo.reference_name} to you"
    redirect_to_doctype, redirect_to_docname = get_redirect_to_doc(todo, reference)
    notify_user(
        {
            "owner": acting_user,
            "assigned_to": todo.allocated_to_id,
            "notification_type": "Assignment",
            "message": message,
            "notification_text": get_notification_text(owner, todo, reference, is_cancelled),
            "reference_doctype": todo.reference_type,
            "reference_docname": todo.reference_name,
            "redirect_to_doctype": redirect_to_doctype,
            "redirect_to_docname": redirect_to_docname,
        }
    )


def on_todo_write(sender, instance, created, **kwargs):
    """``crm/api/todo.py:after_insert`` and ``on_update``."""
    reference_type = instance.reference_type
    reference_name = instance.reference_name
    assignee = instance.allocated_to_id
    if not (reference_name and assignee):
        return
    if created:
        # Upstream's after_insert does not look at status, because nothing upstream
        # inserts a ToDo already cancelled; the port's permission tests do, and an
        # assignment that never was should neither hand over the record nor notify.
        if instance.status == "Cancelled":
            return
        if reference_type in ("CRM Lead", "CRM Deal"):
            # Mirror assign_to: the latest assignment owns the record.
            _set_owner(reference_type, reference_name, assignee)
        if reference_type in _ASSIGNABLE:
            notify_assigned_user(instance)
        return
    previous = getattr(instance, "_previous_status", None)
    if previous != instance.status and instance.status == "Cancelled" and reference_type in _ASSIGNABLE:
        notify_assigned_user(instance, is_cancelled=True)
        if reference_type in ("CRM Lead", "CRM Deal"):
            # Cancelling an assignment clears the owner; upstream accepts the wrinkle
            # that removing one of several co-assignees clears it too.
            _set_owner(reference_type, reference_name, None)


def connect_signals() -> None:
    from crm_app.models import CRMInvitation
    from frappe_platform.models import Comment, Communication, ToDo

    pre_save.connect(_remember_todo_status, sender=ToDo, dispatch_uid="crm.async.todo.pre")
    post_save.connect(on_todo_write, sender=ToDo, dispatch_uid="crm.async.todo")
    post_save.connect(on_comment_insert, sender=Comment, dispatch_uid="crm.async.comment")
    post_save.connect(
        on_communication_write, sender=Communication, dispatch_uid="crm.async.communication"
    )
    post_save.connect(
        on_invitation_insert, sender=CRMInvitation, dispatch_uid="crm.async.invitation"
    )
