"""What happens when a `WhatsApp Message` is written.

Ports `crm/api/whatsapp.py`'s `validate` (`:36-45`), `on_update` (`:47-57`) and
`notify_agent` (`:59-88`), which upstream wires through `doc_events` in `hooks.py`.

Signals rather than hooks, which is the mapping `PHASE_1_MODELS.md` §4 fixed for the whole
port.

## The realtime event is a **broadcast**

`whatsapp.py:48-55` publishes with no `user` and no room, carrying only
`{reference_doctype, reference_name}`; the client filters (`Activities.vue:572-578`).
`AS_BUILT.md` records this specifically so phase 7 would not reach for `publish_to_doc` by
analogy with `docinfo_update` — it is the one realtime event in the port that is genuinely
a broadcast.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save

logger = logging.getLogger(__name__)


def resolve_reference(instance) -> bool:
    """`whatsapp.py:36-45` — work out which lead or deal a message belongs to.

    Returns True if a reference was written. The whole body is exception-safe, as upstream's
    is: a message that cannot be attributed is still a message, and losing it because a
    phone-number lookup failed would be worse than leaving it unattached.
    """
    if instance.reference_doctype and instance.reference_name:
        return False

    number = getattr(instance, "from") if instance.type == "Incoming" else instance.to
    if not number:
        return False

    try:
        from crm_app.integrations.phone import get_contact_lead_or_deal_from_number

        docname, doctype = get_contact_lead_or_deal_from_number(number)
    except Exception:
        logger.warning(
            "CRM WhatsApp: failed to resolve contact from number", exc_info=True
        )
        return False

    if not (docname and doctype):
        return False

    type(instance)._default_manager.filter(pk=instance.pk).update(
        reference_doctype=doctype, reference_name=str(docname)
    )
    instance.reference_doctype = doctype
    instance.reference_name = str(docname)
    return True


def publish_message(instance) -> None:
    """`whatsapp.py:47-57`. Broadcast — see the module docstring."""
    from crm_app import realtime

    realtime.publish(
        "whatsapp_message",
        {
            "reference_doctype": instance.reference_doctype,
            "reference_name": instance.reference_name,
        },
    )


def notify_agent(instance) -> int:
    """`whatsapp.py:59-88` — tell whoever is assigned that a message came in.

    **Incoming only.** An outgoing message is one the agent just sent; notifying them about
    their own message is noise, and upstream returns early for exactly that reason.

    Returns how many notifications were created, which is what makes this testable.
    """
    if instance.type != "Incoming":
        return 0
    if not (instance.reference_doctype and instance.reference_name):
        return 0

    from django.utils.html import escape

    from crm_app.models import CRMNotification
    from frappe_core.assignment import get_assigned_users

    doctype = instance.reference_doctype
    if doctype.startswith("CRM "):
        doctype = doctype[4:].lower()

    # `whatsapp.py:67` escapes the reference name before interpolating it. The name is
    # attacker-influenced in the sense that a lead's id derives from data, and this text is
    # rendered as HTML in the notification list.
    safe_name = escape(instance.reference_name)
    notification_text = (
        '<div class="mb-2 leading-5 text-ink-gray-5">'
        '<span class="font-medium text-ink-gray-9">You</span>'
        f"<span>received a whatsapp message in {escape(doctype)}</span>"
        f'<span class="font-medium text-ink-gray-9">{safe_name}</span>'
        "</div>"
    )

    created = 0
    for user in get_assigned_users(instance.reference_doctype, instance.reference_name):
        CRMNotification._default_manager.create(
            from_user_id=instance.owner_id,
            to_user_id=user,
            type="WhatsApp",
            message=instance.message or "",
            notification_text=notification_text,
            reference_doctype="WhatsApp Message",
            reference_name=str(instance.pk),
            notification_type_doctype=instance.reference_doctype,
            notification_type_doc=str(instance.reference_name),
        )
        created += 1
    return created


def on_message_saved(sender, instance, created, **kwargs):
    if not created:
        return
    resolve_reference(instance)
    publish_message(instance)
    notify_agent(instance)


def connect_signals() -> None:
    from crm_app.models import WhatsAppMessage

    post_save.connect(
        on_message_saved, sender=WhatsAppMessage, dispatch_uid="crm.whatsapp.message"
    )
