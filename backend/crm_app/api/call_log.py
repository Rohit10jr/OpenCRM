"""``crm.fcrm.doctype.crm_call_log.crm_call_log.*`` - the two call-log endpoints the
frontend calls by their doctype-module path: opening a call (``get_call_log``, from the
Call Logs page and the timeline's call area) and "Create lead" on a call from an
unknown number (``create_lead_from_call_log``, ``CallLogDetailModal.vue``). Ported
from ``crm/fcrm/doctype/crm_call_log/crm_call_log.py:135-147`` and ``:189-297`` (main).
Paths seven and eight of the twenty ``docs/http/14_unserved_paths.http`` recorded.
"""

from __future__ import annotations

from django.db import transaction

from frappe_core import permissions, registry
from frappe_core.exceptions import DoesNotExistError
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.exceptions import throw
from frappe_core.query import parse_json_param
from frappe_core.session import get_current_user
from frappe_core.views import _candidate_instance
from frappe_core.whitelist import whitelist


def _as_dict(doctype: str, instance) -> dict:
    """``frappe.get_cached_doc(...).as_dict()``: the document through its serializer."""
    return registry.get_entry(doctype).get_serializer_class()(instance).data


@whitelist("crm.fcrm.doctype.crm_call_log.crm_call_log.get_call_log")
def get_call_log(name: str):
    """``crm_call_log.py:189-242``: the call as the timeline reads it - parsed like a
    list row (``_duration``, ``_caller``, ``_receiver``, ``activity_type``), its note and
    the notes and tasks linked to it under ``_notes`` and ``_tasks``, and the lead or
    deal it belongs to under ``_lead`` or ``_deal``, from its reference or its links.
    ``recording_url_path`` is the download route upstream's ``as_dict`` adds when there
    is a recording."""
    from crm_app.api.doc import _require_readable
    from crm_app.integrations.call_log import get_links
    from crm_app.models import CRMTask, FCRMNote
    from crm_app.models.telephony import parse_call_log

    instance = _require_readable("CRM Call Log", name)
    call = dict(_as_dict("CRM Call Log", instance))
    if call.get("recording_url"):
        call["recording_url_path"] = (
            f"/api/method/crm.integrations.api.get_recording_url?call_log_name={instance.pk}"
        )
    call = parse_call_log(call)

    notes: list[dict] = []
    tasks: list[dict] = []
    if instance.note_id:
        note = FCRMNote._default_manager.filter(pk=instance.note_id).first()
        if note is not None:
            notes.append(_as_dict("FCRM Note", note))

    if instance.reference_doctype and instance.reference_docname:
        if instance.reference_doctype == "CRM Lead":
            call["_lead"] = instance.reference_docname
        elif instance.reference_doctype == "CRM Deal":
            call["_deal"] = instance.reference_docname

    for link in get_links(instance):
        link_doctype, link_name = link["link_doctype"], link["link_name"]
        if link_doctype == "CRM Task":
            task = CRMTask._default_manager.filter(pk=link_name).first()
            if task is not None:
                tasks.append(_as_dict("CRM Task", task))
        elif link_doctype == "FCRM Note":
            note = FCRMNote._default_manager.filter(pk=link_name).first()
            if note is not None:
                notes.append(_as_dict("FCRM Note", note))
        elif link_doctype == "CRM Lead":
            call["_lead"] = link_name
        elif link_doctype == "CRM Deal":
            call["_deal"] = link_name

    call["_tasks"] = tasks
    call["_notes"] = notes
    return call


@whitelist("crm.fcrm.doctype.crm_call_log.crm_call_log.create_lead_from_call_log", methods=("POST",))
def create_lead_from_call_log(call_log=None, lead_details=None, **extra):
    """``crm_call_log.py:245-297``. ``call_log`` is the call's name or the call's own
    dict (the modal sends the record it holds); ``lead_details`` the fields the user
    filled in, of which only real lead fields are kept. The owner defaults to the
    caller, the mobile to the call's ``from`` number, and the first name to "Lead from
    call <number>". The new lead is linked to the call, and its name returned."""
    from crm_app.integrations.call_log import link_with_reference_doc
    from crm_app.models import CRMCallLog
    from frappe_core.models import BaseDocument

    parsed = parse_json_param(call_log, call_log) if call_log else {}
    if isinstance(parsed, str):
        call_log_name = parsed
    elif isinstance(parsed, dict):
        call_log_name = parsed.get("name")
    else:
        call_log_name = None
    if not call_log_name:
        throw("A valid call log is required.")

    # ``frappe.get_doc`` first, so a call that does not exist is 404 before any
    # permission question is asked; then ``call_doc.has_permission("write")``.
    call = CRMCallLog._default_manager.filter(pk=call_log_name).first()
    if call is None:
        raise DoesNotExistError(f"CRM Call Log {call_log_name} not found")
    if not permissions.check_object_permission(call, "write", get_current_user()):
        raise FrappePermissionError("You are not permitted to update this call log.")

    details = parse_json_param(lead_details, lead_details) if lead_details else {}
    if details and not isinstance(details, dict):
        throw("Invalid lead details supplied.")

    # ``meta.fields`` upstream: the doctype's own fields, never the standard ones
    # (name, owner, creation, ...), which BaseDocument declares here.
    entry = registry.get_entry("CRM Lead")
    standard = {f.name for f in BaseDocument._meta.local_fields}
    valid_fieldnames = {
        f.name for f in entry.model._meta.get_fields() if getattr(f, "concrete", False)
    } - standard
    sanitized = {k: v for k, v in (details or {}).items() if k in valid_fieldnames}
    if not sanitized.get("lead_owner"):
        sanitized["lead_owner"] = get_current_user()
    if not sanitized.get("mobile_no"):
        sanitized["mobile_no"] = getattr(call, "from") or ""
    if not sanitized.get("first_name"):
        reference_label = sanitized.get("mobile_no") or call.pk
        sanitized["first_name"] = f"Lead from call {reference_label}"

    if not permissions.check_object_permission(
        _candidate_instance(entry, sanitized), "create", get_current_user()
    ):
        raise FrappePermissionError("You are not permitted to create leads.")

    with transaction.atomic():
        serializer = entry.get_serializer_class()(data=sanitized)
        serializer.is_valid(raise_exception=True)
        lead = serializer.save()
        link_with_reference_doc(call, "CRM Lead", lead.pk)
    return lead.pk
