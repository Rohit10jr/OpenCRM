"""`crm.api.whatsapp.*` — the six endpoints.

Ports `crm/api/whatsapp.py`. Every `frappe.throw` message is preserved verbatim; they are
user-facing copy.

## `validate_access` is two checks, not one

Upstream checks a **role** (`ALLOWED_WHATSAPP_ROLES`) *and*, when a reference is given,
permission on the referenced document. Both are kept. The role check alone would let any
Sales User read any lead's thread; the document check alone would let a user with no CRM
role at all use the feature on records they happen to reach.
"""

from __future__ import annotations

import json
import logging

from crm_app.integrations.whatsapp import provider
from frappe_core import permissions, registry
from frappe_core.exceptions import (
    DoesNotExistError,
    PermissionError as FrappePermissionError,
)
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

logger = logging.getLogger(__name__)

#: `whatsapp.py:11`.
ALLOWED_WHATSAPP_ROLES = ("System Manager", "Sales Manager", "Sales User")

#: `whatsapp.py:130-150` — the fields the timeline reads.
MESSAGE_FIELDS = (
    "name", "type", "to", "from", "content_type", "message_type", "attach", "template",
    "use_template", "message_id", "is_reply", "reply_to_message_id", "creation", "message",
    "status", "reference_doctype", "reference_name", "template_parameters",
    "template_header_parameters",
)


def _roles(user: str) -> set[str]:
    from frappe_platform.models import User

    obj = User._default_manager.filter(pk=user).first()
    return obj.get_roles() if obj else set()


def validate_access(reference_doctype: str | None = None, reference_name: str | None = None,
                    permtype: str = "read"):
    """`whatsapp.py:14-34`, both halves."""
    user = get_current_user()

    if not (set(_roles(user)) & set(ALLOWED_WHATSAPP_ROLES)):
        raise FrappePermissionError(
            "Only sales users can access WhatsApp features.", title="Not Permitted"
        )

    if not (reference_doctype and reference_name):
        return None

    if not registry.has_doctype(reference_doctype):
        raise DoesNotExistError(
            f"Reference document {reference_doctype} {reference_name} does not exist."
        )

    model = registry.get_model(reference_doctype)
    doc = model._default_manager.filter(pk=reference_name).first()
    if doc is None:
        raise DoesNotExistError(
            f"Reference document {reference_doctype} {reference_name} does not exist."
        )

    if not permissions.check_object_permission(doc, permtype, user):
        raise FrappePermissionError(
            f"Not permitted to access reference document {reference_doctype} {reference_name}.",
            title="Not Permitted",
        )
    return doc


@whitelist("crm.api.whatsapp.is_whatsapp_enabled")
def is_whatsapp_enabled():
    return provider.is_enabled()


@whitelist("crm.api.whatsapp.is_whatsapp_installed")
def is_whatsapp_installed():
    return provider.is_installed()


def _serialise(message) -> dict:
    row = {}
    for field in MESSAGE_FIELDS:
        row[field] = getattr(message, field, None)
    row["name"] = message.pk
    return row


@whitelist("crm.api.whatsapp.get_whatsapp_messages")
def get_whatsapp_messages(reference_doctype: str, reference_name: str):
    """`whatsapp.py:113-252`.

    **A deal also shows its originating lead's thread.** Upstream reads `deal.lead` and
    pulls that lead's messages in as well (`:122-140`), so a conversation started before
    conversion does not vanish from the deal. `validate_access` is re-run on the lead —
    reading the deal does not imply reading the lead it came from.
    """
    from crm_app.models import WhatsAppMessage

    reference_doc = validate_access(reference_doctype, reference_name)
    messages = []

    if reference_doctype == "CRM Deal":
        lead = getattr(reference_doc, "lead_id", None)
        if lead:
            validate_access("CRM Lead", lead)
            messages += list(
                WhatsAppMessage._default_manager.filter(
                    reference_doctype="CRM Lead", reference_name=str(lead)
                ).order_by("creation")
            )

    messages += list(
        WhatsAppMessage._default_manager.filter(
            reference_doctype=reference_doctype, reference_name=str(reference_name)
        ).order_by("creation")
    )

    rows = [_serialise(m) for m in messages]

    for row in rows:
        if row.get("message_type") != "Template" or not row.get("template"):
            continue
        # Templates live in `frappe_whatsapp`; `render_template` returns None here, so the
        # message is left unenriched rather than given a fabricated body.
        rendered = provider.render_template(row["template"], _parameters(row))
        if rendered is not None:
            row["template_name"] = row["template"]
            row["template"] = rendered

    _attach_reply_context(rows)

    # `whatsapp.py:252` — reactions render on the message they react to, not on their own.
    return [row for row in rows if row.get("content_type") != "reaction"]


def _parameters(row: dict) -> list:
    raw = row.get("template_parameters")
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _attach_reply_context(rows: list[dict]) -> None:
    """`whatsapp.py:229-250` — a reply carries a preview of what it replies to."""
    by_message_id = {r["message_id"]: r for r in rows if r.get("message_id")}
    for row in rows:
        target = row.get("reply_to_message_id")
        if not target:
            continue
        original = by_message_id.get(target)
        if original:
            row["reply_to_message"] = original.get("message")
            row["reply_to_from"] = original.get("from")


@whitelist("crm.api.whatsapp.create_whatsapp_message")
def create_whatsapp_message(
    reference_doctype: str,
    reference_name: str,
    message: str = "",
    to: str = "",
    attach: str = "",
    reply_to: str = "",
    content_type: str = "text",
):
    """`whatsapp.py:255-294`."""
    from crm_app.models import WhatsAppMessage

    validate_access(reference_doctype, reference_name)

    fields = {
        "reference_doctype": reference_doctype,
        "reference_name": str(reference_name),
        "message": message or attach,
        "to": to,
        "attach": attach,
        "content_type": content_type,
    }

    if reply_to:
        original = WhatsAppMessage._default_manager.filter(pk=reply_to).first()
        if original is None:
            raise DoesNotExistError("Referenced WhatsApp message does not exist.")
        if not permissions.check_object_permission(original, "read", get_current_user()):
            raise FrappePermissionError(
                "Not permitted to access the referenced WhatsApp message.",
                title="Not Permitted",
            )
        # Upstream re-validates against the *original's* reference as well: replying is a
        # way of reaching a second document.
        validate_access(original.reference_doctype, original.reference_name)
        fields["is_reply"] = True
        fields["reply_to_message_id"] = original.message_id

    record = WhatsAppMessage._default_manager.create(**fields)
    return record.pk


@whitelist("crm.api.whatsapp.send_whatsapp_template")
def send_whatsapp_template(reference_doctype: str, reference_name: str, template: str, to: str):
    """`whatsapp.py:297-313`."""
    from crm_app.models import WhatsAppMessage

    validate_access(reference_doctype, reference_name)

    record = WhatsAppMessage._default_manager.create(
        reference_doctype=reference_doctype,
        reference_name=str(reference_name),
        message_type="Template",
        message="Template message",
        content_type="text",
        use_template=True,
        template=template,
        to=to,
    )
    return record.pk


@whitelist("crm.api.whatsapp.react_on_whatsapp_message")
def react_on_whatsapp_message(emoji: str, reply_to_name: str):
    """`whatsapp.py:316-341`.

    Note the argument-free `validate_access()` first: upstream checks the **role** before
    it will even look up the message, so a caller with no CRM role cannot use this endpoint
    to probe which message ids exist.
    """
    from crm_app.models import WhatsAppMessage

    validate_access()

    original = WhatsAppMessage._default_manager.filter(pk=reply_to_name).first()
    if original is None:
        raise DoesNotExistError("Referenced WhatsApp message does not exist.")
    if not permissions.check_object_permission(original, "read", get_current_user()):
        raise FrappePermissionError(
            "Not permitted to access the referenced WhatsApp message.", title="Not Permitted"
        )

    validate_access(original.reference_doctype, original.reference_name)

    # `whatsapp.py:329` — react to the other party's number.
    to = getattr(original, "from") if original.type == "Incoming" else original.to

    record = WhatsAppMessage._default_manager.create(
        reference_doctype=original.reference_doctype,
        reference_name=original.reference_name,
        message=emoji,
        to=to or "",
        reply_to_message_id=original.message_id,
        content_type="reaction",
    )
    return record.pk
