"""``frappe.core.doctype.communication.email.make`` - sending an email from a lead or
deal (``CommunicationArea.vue:206-229``).

The endpoint only. The model work - building the row, copying attachments, choosing the
account, building and sending the message - lives in :mod:`crm_app.communication`, which
is where the docstring explaining each of those steps is. Two reasons for the split: an
api module may not reach a model manager directly
(``tests/test_phase3_endpoints.py::test_no_endpoint_bypasses_the_permission_layer``), and
the Celery task needs the same code with no request around it.

### Permission

Upstream checks ``ptype="email"`` on the reference document::

    if doctype and name:
        frappe.has_permission(doctype, doc=name, ptype="email", throw=True)

This port has no ``email`` permission type - it models row rules, not the DocType
permission matrix - so the check is **read** on the reference document, through the same
object check every other endpoint uses. That is the honest translation rather than a
loosening: in ``crm/fcrm/doctype/crm_lead/crm_lead.json`` and ``crm_deal.json`` every role
granted ``read`` is granted ``email`` in the same permission row, so the two answer alike
for CRM Lead and CRM Deal, which are the only doctypes this endpoint is reached with.

It is deliberately *not* the ``write`` that ``/api/resource/`` requires to create a
Communication (``crm_app/permissions/attachments.py``). That rule is about forging history
onto a record; this is upstream's "may this person mail this record", and upstream grants
it with read. Someone who can open a lead can email from it.

A reference document that does not exist is 404, and ``doctype``/``name`` may both be
absent - upstream allows a Communication that references nothing, and section 5.6 of
``docs/http/08_activities_comments_notifications.http`` already relies on it.

### Deliberately not ported

Named here because their absence is a behaviour, not an oversight:

* **read receipts and the tracking pixel** - ``read_receipt`` and
  ``mark_email_as_seen``/``get_imaginary_pixel_response``; the accepted-and-ignored
  argument would otherwise promise a feature that never fires;
* **``print_format`` / ``print_html`` / ``print_letterhead`` / ``print_language``** -
  attaching a rendered print format needs the print stack, which this port has not built;
* **``send_after``** - Celery is the queue here and nothing in the CRM schedules a send;
* **unsubscribe lists** - so ``emails_not_sent_to`` is always ``""``. Upstream computes it
  as "the addresses on the row that no message went to", which is driven by
  ``Email Unsubscribe``, thread-notification settings and disabled users, none of which
  this port models. The key is still returned because the shape is part of the contract;
* **inbound mail over IMAP**, and **``Email Queue`` as a table** - Celery is the queue
  (decided in phase 5).

A **stale attachment name is skipped** rather than crashing the send; see
``crm_app.communication.add_attachments`` for why that is a divergence worth making.
"""

from __future__ import annotations

import smtplib

from django.db import transaction

from crm_app import communication as communication_service
from crm_app import tasks
from frappe_core.exceptions import OutgoingEmailError, throw
from frappe_core.query import parse_json_param
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist


def _cint(value) -> int:
    """``frappe.utils.cint``: ``send_email``/``now`` arrive as ``1``, ``"1"`` or ``true``."""
    if isinstance(value, str):
        return 1 if value.strip().lower() in ("1", "true", "yes") else 0
    return 1 if value else 0


@whitelist("frappe.core.doctype.communication.email.make", methods=("POST",))
def make(
    doctype: str | None = None,
    name: str | None = None,
    content: str | None = None,
    subject: str | None = None,
    sent_or_received: str = "Sent",
    sender: str | None = None,
    sender_full_name: str | None = None,
    recipients=None,
    communication_medium: str = "Email",
    send_email=False,
    attachments=None,
    send_me_a_copy=False,
    cc=None,
    bcc=None,
    email_template: str | None = None,
    communication_type: str | None = None,
    now=False,
    in_reply_to: str | None = None,
    **kwargs,
):
    """``frappe/core/doctype/communication/email.py:make`` -> ``_make``, step for step.

    Returns ``{"name": ..., "emails_not_sent_to": ""}``.

    The order is upstream's and it is load-bearing: the row is inserted and its
    attachments copied **before** the outgoing-account check, so a deployment with no
    Email Account still gets the email recorded on the timeline and a 417 explaining why
    it did not go out. Reversing it would lose what the user typed.

    ``now`` truthy sends inside the request; otherwise the send is queued on
    ``crm.send_communication_email``, which retries transport failures. The frontend never
    passes ``now`` - the ``.http`` blocks and hand testing do.

    ``email_template`` is accepted and **not stored**: the port's ``Communication`` has no
    such column (``frappe_platform/models.py``), and upstream only keeps it as a note of
    which template the caller rendered - nothing server-side re-renders it, and
    ``CommunicationArea.vue`` sends the finished ``content``. Accepting it keeps a caller
    that passes it working rather than 500-ing on an unknown field.

    ``**kwargs`` swallows the arguments listed as unported in the module docstring, plus
    ``print_*`` and ``read_receipt``, exactly as upstream's own ``**kwargs`` swallows
    anything it no longer supports.
    """
    if doctype and name:
        # 404 when it is gone, 403 when it is not the caller's to see.
        _require_reference(doctype, str(name))

    sender = sender or communication_service.formatted_email(get_current_user())

    # Upstream's ``if isinstance(attachments, str): attachments = json.loads(attachments)``;
    # here the generic param decoder already does it, and a lone name is taken as a
    # one-item list rather than iterated character by character.
    parsed_attachments = parse_json_param(attachments, attachments) or []
    if isinstance(parsed_attachments, str):
        parsed_attachments = [parsed_attachments]

    with transaction.atomic():
        communication = communication_service.create_communication(
            doctype=doctype,
            name=name,
            content=content,
            subject=subject,
            sent_or_received=sent_or_received,
            sender=sender,
            sender_full_name=sender_full_name,
            recipients=recipients,
            communication_medium=communication_medium,
            attachments=parsed_attachments,
            cc=cc,
            bcc=bcc,
            communication_type=communication_type,
            in_reply_to=in_reply_to,
        )
        if parsed_attachments:
            communication_service.add_attachments(communication.pk, parsed_attachments)

    if _cint(send_email):
        # "Send me a copy" is resolved here, while there is a session user to ask
        # (mixins.py:88-93), and carried into the task as an address.
        copy_to = (
            communication_service.copy_address_for(get_current_user(), sender)
            if _cint(send_me_a_copy)
            else None
        )
        _send(communication, copy_to=copy_to, now=_cint(now))

    return {"name": communication.pk, "emails_not_sent_to": ""}


def _require_reference(doctype: str, name: str):
    """Read permission on the reference document - see the module docstring."""
    from crm_app.api.client import _get_checked

    _entry, instance = _get_checked(doctype, name, "read")
    return instance


def _send(communication, *, copy_to: str | None, now: int) -> None:
    """``_make``'s tail: refuse without an account, then send now or queue it."""
    if communication_service.outgoing_account_for(communication) is None:
        # Verbatim from email.py:_make. It names the screen the reader has to go to.
        raise OutgoingEmailError(
            "Unable to send mail because of a missing email account. "
            "Please setup default Email Account from Settings > Email Account"
        )

    if not now:
        tasks.send_communication_email.delay(communication.pk, copy_to)
        return

    try:
        communication_service.send_communication(communication.pk, copy_to=copy_to)
    except (smtplib.SMTPException, OSError) as exc:
        # Inline, there is no retry to fall back on, so the caller is told what the relay
        # said. Queued, the same failure is what `autoretry_for` catches.
        throw(f"Could not send the email: {exc}")
