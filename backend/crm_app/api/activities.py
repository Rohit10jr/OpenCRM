"""``crm.api.activities.get_activities`` - Group C's most involved item.

Ported from ``crm/api/activities.py``. Returns a 5-tuple:
``(activities, calls, notes, tasks, attachments)``.

### What is not ported, and why

Upstream builds the ``changed`` / ``added`` / ``removed`` entries from the framework's
**``Version``** doctype - a per-save audit row holding a JSON diff
(``activities.py:66-113``). ``Version`` is not modelled in this port, and recording it
would mean diffing every document on every save: a framework-wide change with a write
cost on every table, well outside this phase.

So the field-change entries are absent, and the timeline contains creation, comments,
communications, calls, notes, tasks and attachments. `PHASE_3_ENDPOINTS.md` describes
this endpoint as merging *"Communication, Comment, ToDo and status-change history"* -
which is what is delivered, using the ported ``CRM Status Change Log`` for the status
history. Named in PROGRESS_PHASE_3.md as the gap it is.

Attachment-log entries are also absent: upstream derives them from Comments with
``comment_type`` in ``Attachment`` / ``Attachment Removed``, which nothing in this port
creates yet.
"""

from __future__ import annotations

import re

from frappe_core import permissions, registry
from frappe_core.exceptions import DoesNotExistError
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.query import base_queryset, fetch_rows
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

CALL_FIELDS = [
    "name", "caller", "receiver", "from", "to", "duration", "start_time",
    "end_time", "status", "type", "recording_url", "creation", "note",
]
NOTE_FIELDS = ["name", "title", "content", "owner", "modified", "creation"]
TASK_FIELDS = [
    "name", "title", "description", "assigned_to", "due_date", "priority",
    "status", "modified", "creation",
]
ATTACHMENT_FIELDS = [
    "name", "file_name", "file_url", "file_size", "is_private", "modified",
    "creation", "owner",
]


def get_attachments(doctype: str, name: str) -> list[dict]:
    """``activities.py:318-337``. ``file_type`` is absent - the model has no such column."""
    from frappe_platform.models import File

    return list(
        File._default_manager.filter(
            attached_to_doctype=doctype, attached_to_name=str(name)
        ).values(*ATTACHMENT_FIELDS)
    )


def get_linked_notes(name: str) -> list[dict]:
    """``activities.py:462-468``."""
    return fetch_rows(
        "FCRM Note",
        fields=NOTE_FIELDS,
        filters={"reference_docname": str(name)},
        limit_page_length=0,
    )


def get_linked_tasks(name: str) -> list[dict]:
    """``activities.py:471-488``."""
    return fetch_rows(
        "CRM Task",
        fields=TASK_FIELDS,
        filters={"reference_docname": str(name)},
        limit_page_length=0,
    )


def get_linked_calls(name: str) -> dict:
    """``activities.py:373-459``.

    Two sources, both ported now that ``Dynamic Link`` exists (C5):

    * calls whose ``reference_docname`` is this document;
    * calls linked through a ``Dynamic Link`` row - and those rows may point at an
      ``FCRM Note`` or a ``CRM Task`` instead, in which case upstream pulls the note or
      task out into its own bucket rather than showing it as a call.
    """
    from frappe_platform.models import DynamicLink

    calls = fetch_rows(
        "CRM Call Log",
        fields=CALL_FIELDS,
        filters={"reference_docname": str(name)},
        limit_page_length=0,
    )

    linked_call_names = list(
        DynamicLink._default_manager.filter(
            link_name=str(name), parenttype="CRM Call Log"
        ).values_list("parent", flat=True)
    )

    note_names: list[str] = []
    task_names: list[str] = []

    if linked_call_names:
        rows = list(
            DynamicLink._default_manager.filter(
                parenttype="CRM Call Log", parent__in=linked_call_names
            ).values("parent", "link_doctype", "link_name")
        )
        # Upstream filters the *joined rows*, not the calls: a call keeps its place in
        # the timeline as long as it has at least one link that is not a note or task
        # (``activities.py:441``). Discarding the call whenever any of its links is a
        # note would drop calls that are attached to both a note and the lead.
        extra_calls = set()
        for row in rows:
            if row["link_doctype"] == "FCRM Note":
                note_names.append(row["link_name"])
            elif row["link_doctype"] == "CRM Task":
                task_names.append(row["link_name"])
            else:
                extra_calls.add(row["parent"])

        already = {c["name"] for c in calls}
        remaining = [n for n in extra_calls if n not in already]
        if remaining:
            calls = calls + fetch_rows(
                "CRM Call Log",
                fields=CALL_FIELDS,
                filters={"name": ["in", remaining]},
                limit_page_length=0,
            )

    notes = (
        fetch_rows(
            "FCRM Note",
            fields=["name", "title", "content", "owner", "modified"],
            filters={"name": ["in", note_names]},
            limit_page_length=0,
        )
        if note_names
        else []
    )
    tasks = (
        fetch_rows(
            "CRM Task",
            fields=[
                "name", "title", "description", "assigned_to", "due_date",
                "priority", "status", "modified",
            ],
            filters={"name": ["in", task_names]},
            limit_page_length=0,
        )
        if task_names
        else []
    )

    return {"calls": calls, "notes": notes, "tasks": tasks}


def _status_change_activities(doctype: str, name: str, is_lead: bool) -> list[dict]:
    """Status history, from the ported ``CRM Status Change Log``.

    This is the part of upstream's ``Version``-derived timeline that *is* available:
    the CRM records status transitions in their own child table rather than relying on
    the framework's audit log.
    """
    from crm_app.models import CRMStatusChangeLog

    rows = CRMStatusChangeLog._default_manager.filter(
        parenttype=doctype, parent=str(name)
    ).order_by("idx")

    activities = []
    for row in rows:
        old_value = getattr(row, "from")
        value = getattr(row, "to")
        if not old_value and not value:
            continue
        activity_type = "changed"
        data = {
            "field": "status",
            "field_label": "Status",
            "old_value": old_value,
            "value": value,
        }
        if not old_value and value:
            activity_type = "added"
            data = {"field": "status", "field_label": "Status", "value": value}
        activities.append(
            {
                "activity_type": activity_type,
                "creation": row.to_date or row.creation,
                "owner": row.log_owner_id or row.owner_id,
                "data": data,
                "is_lead": is_lead,
                "options": "CRM Lead Status" if is_lead else "CRM Deal Status",
            }
        )
    return activities


def _comment_activities(doctype: str, name: str, is_lead: bool) -> list[dict]:
    from frappe_platform.models import Comment

    rows = Comment._default_manager.filter(
        reference_doctype=doctype, reference_name=str(name), comment_type="Comment"
    ).order_by("creation")
    return [
        {
            "name": row.name,
            "activity_type": "comment",
            "creation": row.creation,
            "owner": row.owner_id,
            "content": row.content,
            "attachments": get_attachments("Comment", row.name),
            "is_lead": is_lead,
        }
        for row in rows
    ]


def _communication_activities(doctype: str, name: str, is_lead: bool) -> list[dict]:
    """``activities.py:131-152``.

    Upstream draws on ``docinfo.communications + docinfo.automated_messages``, which is
    ``communication_type`` in ``Communication`` / ``Automated Message`` - the same pair
    ``crm/api/doc.py:645-663`` counts.
    """
    from frappe_platform.models import Communication

    rows = Communication._default_manager.filter(
        reference_doctype=doctype,
        reference_name=str(name),
        communication_type__in=["Communication", "Automated Message"],
    ).order_by("creation")

    return [
        {
            "activity_type": "communication",
            "communication_type": row.communication_type,
            "communication_date": row.communication_date or row.creation,
            "creation": row.creation,
            "data": {
                "subject": row.subject,
                "content": row.content,
                "sender_full_name": row.sender_full_name,
                "sender": row.sender,
                "recipients": row.recipients,
                "cc": row.cc,
                "bcc": row.bcc,
                "attachments": get_attachments("Communication", row.name),
                "read_by_recipient": row.read_by_recipient,
                # `delivery_status` is not a column in this port's Communication.
                "delivery_status": None,
            },
            "is_lead": is_lead,
        }
        for row in rows
    ]


def handle_multiple_versions(versions: list) -> list:
    """``activities.py:340-366``.

    Consecutive change entries by the **same owner** collapse into one, with the rest
    hung off ``other_versions`` - that is what makes the timeline show "Alice changed 4
    fields" rather than four separate rows.
    """
    activities: list = []
    grouped: list = []
    previous = None

    for version in versions:
        is_version = version["activity_type"] in ("changed", "added", "removed")
        if not is_version:
            activities.append(version)
        if previous is None:
            previous = version
            if is_version:
                grouped.append(version)
            continue
        if is_version and previous.get("owner") and version["owner"] == previous["owner"]:
            grouped.append(version)
        else:
            if grouped:
                activities.append(parse_grouped_versions(grouped))
            grouped = []
            if is_version:
                grouped.append(version)
        previous = version
        if version is versions[-1] and grouped:
            activities.append(parse_grouped_versions(grouped))

    return activities


def parse_grouped_versions(versions: list) -> dict:
    """``activities.py:369-375``."""
    version = versions[0]
    if len(versions) == 1:
        return version
    version["other_versions"] = versions[1:]
    return version


def _require_readable(doctype: str, name: str):
    """Upstream guards both branches with ``frappe.has_permission``; message verbatim."""
    instance = registry.get_model(doctype)._default_manager.filter(pk=name).first()
    if instance is None:
        raise DoesNotExistError("Document not found")
    if not permissions.check_object_permission(instance, "read", get_current_user()):
        raise FrappePermissionError("Not permitted")
    return instance


def get_lead_activities(name: str):
    """``activities.py:172-315``."""
    lead = _require_readable("CRM Lead", name)

    activities = [
        {
            "activity_type": "creation",
            "creation": lead.creation,
            "owner": lead.owner_id,
            "data": "created this lead",
            "is_lead": True,
        }
    ]
    activities += _status_change_activities("CRM Lead", name, is_lead=True)
    activities += _comment_activities("CRM Lead", name, is_lead=True)
    activities += _communication_activities("CRM Lead", name, is_lead=True)

    linked = get_linked_calls(name)
    calls = linked["calls"]
    notes = get_linked_notes(name) + linked["notes"]
    tasks = get_linked_tasks(name) + linked["tasks"]
    attachments = get_attachments("CRM Lead", name)

    activities.sort(key=lambda a: a["creation"], reverse=True)
    activities = handle_multiple_versions(activities)
    return activities, calls, notes, tasks, attachments


def get_deal_activities(name: str):
    """``activities.py:23-169``.

    A deal converted from a lead **inherits the lead's whole timeline**, and its own
    creation entry reads "converted the lead to this deal" rather than "created this
    deal" (``activities.py:49-52``).
    """
    deal = _require_readable("CRM Deal", name)

    activities: list = []
    calls: list = []
    notes: list = []
    tasks: list = []
    attachments: list = []
    creation_text = "created this deal"

    if deal.lead_id:
        # The lead may be unreadable to this user even though the deal is not; in that
        # case upstream would raise. Inheriting nothing is the safer read.
        try:
            activities, calls, notes, tasks, attachments = get_lead_activities(deal.lead_id)
        except (FrappePermissionError, DoesNotExistError):
            activities, calls, notes, tasks, attachments = [], [], [], [], []
        else:
            creation_text = "converted the lead to this deal"

    activities.append(
        {
            "activity_type": "creation",
            "creation": deal.creation,
            "owner": deal.owner_id,
            "data": creation_text,
            "is_lead": False,
        }
    )
    activities += _status_change_activities("CRM Deal", name, is_lead=False)
    activities += _comment_activities("CRM Deal", name, is_lead=False)
    activities += _communication_activities("CRM Deal", name, is_lead=False)

    linked = get_linked_calls(name)
    calls = calls + linked["calls"]
    notes = notes + get_linked_notes(name) + linked["notes"]
    tasks = tasks + get_linked_tasks(name) + linked["tasks"]
    attachments = attachments + get_attachments("CRM Deal", name)

    activities.sort(key=lambda a: a["creation"], reverse=True)
    activities = handle_multiple_versions(activities)
    return activities, calls, notes, tasks, attachments


@whitelist("crm.api.activities.get_activities")
def get_activities(name: str):
    """``activities.py:13-20``. Deal first, then lead, else 404. Message verbatim."""
    from crm_app.models import CRMDeal, CRMLead

    if CRMDeal._default_manager.filter(pk=name).exists():
        return get_deal_activities(name)
    if CRMLead._default_manager.filter(pk=name).exists():
        return get_lead_activities(name)
    raise DoesNotExistError("Document not found")
