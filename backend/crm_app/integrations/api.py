"""`crm.integrations.api.*` — the provider-neutral telephony endpoints.

Ports `crm/integrations/api.py`. These are **not** flag-gated: the frontend calls
`is_call_integration_enabled` on load to decide whether to render a dial button at all, so
it has to answer with both flags off. It answers `false`, which is the point.

`get_recording_url` is deliberately not here — it is the SSRF-sensitive recording proxy and
lands with its own tests in `recording.py`.
"""

from __future__ import annotations

from django.conf import settings

from crm_app.integrations import call_log as call_log_path
from crm_app.integrations.phone import (
    get_contact_by_phone_number as _get_contact_by_phone_number,
)
from crm_app.integrations.phone import (
    get_contact_lead_or_deal_from_number as _get_contact_lead_or_deal,
)
from frappe_core import permissions
from frappe_core.exceptions import DoesNotExistError, PermissionError as FrappePermissionError
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist


def _provider_enabled(flag: str, doctype: str) -> bool:
    """A provider counts as enabled only when **both** the deployment flag and the
    settings row say so.

    Upstream has only the settings checkbox (`api.py:37-43`), because it has no deployment
    flag. Ours is an `and`: an operator who has not turned the integration on for this
    deployment must not have it activated by a row in the database. The flag is the outer
    gate and the checkbox is the inner one.
    """
    if not getattr(settings, flag, False):
        return False

    from frappe_core import registry

    model = registry.get_model(doctype)
    return bool(
        model._default_manager.filter(pk=model.SINGLETON_NAME)
        .values_list("enabled", flat=True)
        .first()
    )


def get_user_default_calling_medium(user: str | None = None) -> str | None:
    """`crm/integrations/api.py:46-56`."""
    from crm_app.models import CRMTelephonyAgent

    user = user or get_current_user()
    medium = (
        CRMTelephonyAgent._default_manager.filter(user_id=user)
        .values_list("default_medium", flat=True)
        .first()
    )
    return medium or None


@whitelist("crm.integrations.api.is_call_integration_enabled")
def is_call_integration_enabled():
    """`crm/integrations/api.py:36-43`.

    Called on every page load, with both integrations off in the default deployment, so it
    must be cheap and must not import a provider SDK.
    """
    return {
        "integrations": {
            "twilio": _provider_enabled("ENABLE_TWILIO", "CRM Twilio Settings"),
            "exotel": _provider_enabled("ENABLE_EXOTEL", "CRM Exotel Settings"),
        },
        "default_calling_medium": get_user_default_calling_medium(),
    }


@whitelist("crm.integrations.api.set_default_calling_medium")
def set_default_calling_medium(medium: str):
    """`crm/integrations/api.py:59-71`.

    Upstream inserts with `ignore_permissions=True`, which is right: the row is keyed on
    `frappe.session.user` and is the caller's own preference. Reproduced — but note it is
    scoped to *self*, never to an arbitrary user, which is what makes ignoring permissions
    safe here.
    """
    from crm_app.models import CRMTelephonyAgent

    user = get_current_user()
    agent = CRMTelephonyAgent._default_manager.filter(user_id=user).first()
    if agent is None:
        CRMTelephonyAgent._default_manager.create(user_id=user, default_medium=medium)
    else:
        CRMTelephonyAgent._default_manager.filter(pk=agent.pk).update(default_medium=medium)

    return get_user_default_calling_medium(user)


def _writable_call_log(call_sid: str):
    """`frappe.has_permission("CRM Call Log", "write", call_sid)` — `api.py:78-79`.

    Both callers below then write a *linked* document, so the check is on the call log,
    not on the note or task. Upstream's message text is preserved verbatim.
    """
    from crm_app.models import CRMCallLog

    call_log = CRMCallLog._default_manager.filter(pk=call_sid).first()
    if call_log is None:
        raise DoesNotExistError(f"CRM Call Log {call_sid} not found")
    if not permissions.check_object_permission(call_log, "write", get_current_user()):
        raise FrappePermissionError("Not permitted", title="Not Permitted")
    return call_log


@whitelist("crm.integrations.api.add_note_to_call_log")
def add_note_to_call_log(call_sid: str, note: dict):
    """`crm/integrations/api.py:74-95`. Creates the note, or updates an existing one."""
    from crm_app.models import FCRMNote

    call_log = _writable_call_log(call_sid)
    note = note or {}

    if not note.get("name"):
        record = FCRMNote._default_manager.create(
            title=note.get("title") or "Call Note",
            content=note.get("content") or "",
        )
    else:
        record = FCRMNote._default_manager.filter(pk=note["name"]).first()
        if record is None:
            raise DoesNotExistError(f"FCRM Note {note['name']} not found")
        FCRMNote._default_manager.filter(pk=record.pk).update(content=note.get("content") or "")
        record.refresh_from_db()

    call_log_path.link_with_reference_doc(call_log, "FCRM Note", record.pk)
    return {"name": record.pk, "title": record.title, "content": record.content}


@whitelist("crm.integrations.api.add_task_to_call_log")
def add_task_to_call_log(call_sid: str, task: dict):
    """`crm/integrations/api.py:98-134`."""
    from crm_app.models import CRMTask

    call_log = _writable_call_log(call_sid)
    task = task or {}

    fields = {
        "title": task.get("title") or "",
        "description": task.get("description") or "",
        "assigned_to_id": task.get("assigned_to") or None,
        "due_date": task.get("due_date") or None,
        "status": task.get("status") or "",
        "priority": task.get("priority") or "",
    }

    if not task.get("name"):
        record = CRMTask._default_manager.create(**fields)
    else:
        record = CRMTask._default_manager.filter(pk=task["name"]).first()
        if record is None:
            raise DoesNotExistError(f"CRM Task {task['name']} not found")
        for key, value in fields.items():
            setattr(record, key, value)
        record.save()

    call_log_path.link_with_reference_doc(call_log, "CRM Task", record.pk)
    return {
        "name": record.pk,
        "title": record.title,
        "description": record.description,
        "status": record.status,
        "priority": record.priority,
    }


@whitelist("crm.integrations.api.get_contact_by_phone_number")
def get_contact_by_phone_number(phone_number: str):
    """`crm/integrations/api.py:157-165`."""
    return _get_contact_by_phone_number(phone_number)


@whitelist("crm.integrations.api.get_contact_lead_or_deal_from_number")
def get_contact_lead_or_deal_from_number(number: str):
    """`crm/integrations/api.py:140-154` — returns ``[docname, doctype]``."""
    docname, doctype = _get_contact_lead_or_deal(number)
    return [docname, doctype]
