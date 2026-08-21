"""The shared call-log path — one write, both providers.

`PHASE_7_INTEGRATIONS.md` §2: *"Port the shared call-log path once; keep the provider
adapters separate."* Everything here is provider-neutral and **not** flag-gated: the
manual "Log a call" flow uses the same model with every integration off.

## Links are `Dynamic Link` rows, not a foreign key

`CRM Call Log.links` is a child table of `Dynamic Link` — the same polymorphic table
`Contact.links` uses (C5, phase 3). A call can point at a Lead, a Deal, an `FCRM Note` and
a `CRM Task` at once, so there is no single FK to hang it on.

`link_with_reference_doc` is idempotent (`crm_call_log.py:135-139`): it checks `has_link`
first. That matters because both providers call it from a webhook, and a webhook is
redelivered.

## Why `set_reference` exists separately

`reference_doctype` / `reference_docname` are the *primary* association — what the call
appears against in the timeline — and they are plain columns. The `links` table is the
looser "also mentions" set. Upstream writes both, and they are not the same thing: a call
resolved to a Lead sets the reference **and** appends a link.
"""

from __future__ import annotations

from django.db import transaction

#: Upstream's `telephony_medium` values. `Manual` is what `before_insert` stamps when
#: nothing else claims the call (`crm_call_log.py:50-54`).
MEDIUM_MANUAL = "Manual"
MEDIUM_TWILIO = "Twilio"
MEDIUM_EXOTEL = "Exotel"


def has_link(call_log, link_doctype: str, link_name: str) -> bool:
    """`crm_call_log.py:130-133`."""
    from frappe_platform.models import DynamicLink

    return DynamicLink._default_manager.filter(
        parenttype="CRM Call Log",
        parent=str(call_log.pk),
        link_doctype=link_doctype,
        link_name=str(link_name),
    ).exists()


def link_with_reference_doc(call_log, link_doctype: str, link_name: str) -> bool:
    """`crm_call_log.py:135-139`. Returns True if a row was added.

    Idempotent by the same check upstream makes. A redelivered webhook, or a second
    "add note" on the same call, must not accumulate duplicate links.
    """
    from frappe_platform.models import DynamicLink

    if not link_doctype or not link_name:
        return False
    if has_link(call_log, link_doctype, link_name):
        return False

    idx = (
        DynamicLink._default_manager.filter(
            parenttype="CRM Call Log", parent=str(call_log.pk)
        ).count()
        + 1
    )
    DynamicLink._default_manager.create(
        parenttype="CRM Call Log",
        parentfield="links",
        parent=str(call_log.pk),
        link_doctype=link_doctype,
        link_name=str(link_name),
        idx=idx,
    )
    return True


def get_links(call_log) -> list[dict]:
    from frappe_platform.models import DynamicLink

    return list(
        DynamicLink._default_manager.filter(
            parenttype="CRM Call Log", parent=str(call_log.pk)
        )
        .order_by("idx")
        .values("link_doctype", "link_name", "link_title")
    )


def set_reference(call_log, doctype: str | None, docname: str | None) -> None:
    """The *primary* association — the columns the timeline reads.

    Written with `update()` rather than `save()`: this runs from a webhook, where the
    ambient user is whatever the request authenticated as (often nobody), and `save()`
    would stamp `modified_by` with it. Same reasoning as the phase-5 cache writes.
    """
    if not doctype or not docname:
        return
    type(call_log)._default_manager.filter(pk=call_log.pk).update(
        reference_doctype=doctype, reference_docname=str(docname)
    )
    call_log.reference_doctype = doctype
    call_log.reference_docname = str(docname)


def resolve_and_link(call_log, number: str) -> tuple[str | None, str | None]:
    """Work out who a call was with, then record it both ways.

    Returns ``(docname, doctype)`` — upstream's order (`phone.get_contact_lead_or_deal_from_number`).

    Failure here must not fail the call log. A number that resolves to nothing is normal
    (an unknown caller), and `PHASE_7_INTEGRATIONS.md` §3 requires that a provider problem
    never breaks CRUD — so an unexpected error is swallowed and the call is still logged
    without an association.
    """
    from crm_app.integrations.phone import get_contact_lead_or_deal_from_number

    try:
        docname, doctype = get_contact_lead_or_deal_from_number(number)
    except Exception:  # pragma: no cover - defensive; a lookup must not lose the call
        import logging

        logging.getLogger(__name__).warning(
            "call log %s: could not resolve %r", call_log.pk, number, exc_info=True
        )
        return None, None

    if docname and doctype:
        set_reference(call_log, doctype, docname)
        link_with_reference_doc(call_log, doctype, docname)
    return docname, doctype


@transaction.atomic
def record_call(
    *,
    call_id: str,
    medium: str,
    call_type: str,
    status: str,
    from_number: str = "",
    to_number: str = "",
    duration: int | None = None,
    recording_url: str = "",
    start_time=None,
    end_time=None,
    caller=None,
    receiver=None,
) -> tuple[object, bool]:
    """Create or update one call log, keyed on the **provider's** call id.

    Returns ``(call_log, created)``.

    **This is the dedupe point.** `PHASE_7_INTEGRATIONS.md` §3 requires webhooks to dedupe
    by provider message id, and `CRM Call Log` is `autoname=field:id` — the provider's call
    id *is* the primary key, so a redelivered webhook updates the row it created rather
    than inserting a second one. That is a database constraint, not a check that can be
    forgotten.

    Fields are only overwritten when the new value is non-empty. A provider sends several
    callbacks per call (`ringing`, then `completed` with a duration and a recording), and a
    later one that omits a field must not blank what an earlier one set.
    """
    from crm_app.models import CRMCallLog

    call_log = CRMCallLog._default_manager.filter(pk=call_id).first()
    created = call_log is None

    if created:
        call_log = CRMCallLog(id=call_id, telephony_medium=medium, type=call_type, status=status)
        setattr(call_log, "from", from_number or "")
        setattr(call_log, "to", to_number or "")
        call_log.duration = duration
        call_log.recording_url = recording_url or ""
        call_log.start_time = start_time
        call_log.end_time = end_time
        call_log.caller = caller
        call_log.receiver = receiver
        call_log.save()
        return call_log, True

    updates: dict = {"status": status}
    if duration is not None:
        updates["duration"] = duration
    if recording_url:
        updates["recording_url"] = recording_url
    if start_time is not None:
        updates["start_time"] = start_time
    if end_time is not None:
        updates["end_time"] = end_time
    if from_number:
        updates["from"] = from_number
    if to_number:
        updates["to"] = to_number
    if caller is not None:
        updates["caller"] = caller
    if receiver is not None:
        updates["receiver"] = receiver

    CRMCallLog._default_manager.filter(pk=call_log.pk).update(**updates)
    call_log.refresh_from_db()
    return call_log, False
