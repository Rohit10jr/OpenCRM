"""`WhatsApp Message` — the one doctype phase 7 ports from `frappe_whatsapp`.

`RUNBOOK_PHASE_7.md`: *"Port `api/whatsapp.py`'s six endpoints and the message model behind
a named seam… **Do not vendor `frappe_whatsapp`.**"*

So this is the message model and nothing else. `WhatsApp Templates`, `WhatsApp Settings` and
`WhatsApp Account` are not ported — see `crm_app/integrations/whatsapp/provider.py` for what
that costs and where the seam is.

## The schema is inferred from what the endpoints read, and that is stated on purpose

`frappe_whatsapp` is not in this repo, so there is no JSON to transcribe. Every field here
appears in `crm/api/whatsapp.py`'s own `get_all` field list (`:130-150`) or in one of the
four `doc.update({...})` calls. Nothing is invented, and nothing is included on a guess
about what the upstream app might also store.

The consequence: a real `frappe_whatsapp` install has columns this does not. That matters
only if someone later tries to sync the two, and it is recorded rather than discovered.

## Access is deferred to the referenced document

A WhatsApp message is *about* a lead or a deal and carries which one. That makes it the
same shape as `Comment`, `Communication` and `File`, and it gets the same rule
(`crm_app/permissions/attachments.py`): read it if you can read the parent, write it if you
can write the parent.

Without that, the message body would leak exactly what the record itself refuses — which is
the defect `attachments.py` was written for, and a WhatsApp thread is more revealing than a
deal row.
"""

from __future__ import annotations

from django.db import models

from frappe_core.models import BaseDocument
from frappe_core.naming import Hash
from frappe_core.registry import register_doctype

MESSAGE_TYPE_CHOICES = [(c, c) for c in ("Manual", "Template", "Automated")]
DIRECTION_CHOICES = [("Incoming", "Incoming"), ("Outgoing", "Outgoing")]
STATUS_CHOICES = [
    (c, c) for c in ("", "Queued", "Sent", "Delivered", "Read", "Failed")
]


@register_doctype("WhatsApp Message")
class WhatsAppMessage(BaseDocument):
    """One message, inbound or outbound."""

    #: `whatsapp.py:37` — the direction decides which number is the contact's.
    type = models.CharField(max_length=20, choices=DIRECTION_CHOICES, default="Outgoing")

    message = models.TextField(blank=True, default="")
    #: `text`, `image`, `document`, `reaction`, … `reaction` is filtered out of the
    #: timeline (`whatsapp.py:252`) because it renders on the message it reacts to.
    content_type = models.CharField(max_length=40, blank=True, default="text")
    message_type = models.CharField(
        max_length=20, choices=MESSAGE_TYPE_CHOICES, blank=True, default="Manual"
    )
    attach = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, blank=True, default="")

    #: The provider's own id. Blank until the provider accepts the message, which is why
    #: it is not the primary key the way `CRM Call Log.id` is.
    message_id = models.CharField(max_length=140, blank=True, default="", db_index=True)

    is_reply = models.BooleanField(default=False)
    reply_to_message_id = models.CharField(max_length=140, blank=True, default="")

    #: Templates are not ported; the columns are, because the endpoints read them and a
    #: message sent by a real `frappe_whatsapp` would carry them.
    template = models.CharField(max_length=140, blank=True, default="")
    use_template = models.BooleanField(default=False)
    template_parameters = models.TextField(blank=True, default="")
    template_header_parameters = models.TextField(blank=True, default="")

    reference_doctype = models.CharField(max_length=140, blank=True, default="", db_index=True)
    reference_name = models.CharField(max_length=140, blank=True, default="", db_index=True)

    class Meta:
        ordering = ["creation"]
        name_strategy = Hash()
        indexes = [
            models.Index(
                fields=["reference_doctype", "reference_name"], name="wa_message_reference_idx"
            ),
        ]


# `from` and `to` are Python keywords — same treatment as CRM Call Log and CRM Status
# Change Log. The wire names are `from` and `to`, and the frontend reads both.
WhatsAppMessage.add_to_class("from", models.CharField(max_length=140, blank=True, default=""))
WhatsAppMessage.add_to_class("to", models.CharField(max_length=140, blank=True, default=""))

__all__ = ["WhatsAppMessage"]
