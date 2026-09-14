"""Task, Note and Call Log declare what their screens need: FINDINGS.md 16.

Upstream's controllers each define ``default_list_data`` (crm_task.py:57,
fcrm_note.py:24, crm_call_log.py:57); the call log also parses every list row
(``parse_list_data`` -> ``parse_call_log``) and carries its ``links`` child table. The
port had none of the three, so ``get_data`` fell back to Name and Last Modified.
"""

from urllib.parse import quote

import pytest

from crm_app.models import CRMCallLog, CRMTask, FCRMNote
from crm_app.models.telephony import seconds_to_duration
from frappe_core.api.doc import get_data
from frappe_core.session import session_user
from frappe_platform.models import DynamicLink

pytestmark = pytest.mark.django_db


def _list(doctype):
    return get_data(doctype=doctype, filters={}, order_by="modified desc")


def test_task_columns_and_rows(alice):
    with session_user(alice.name):
        CRMTask.objects.create(title="ZZ Call back", status="Todo", priority="Medium")
    result = _list("CRM Task")
    assert [c["key"] for c in result["columns"]] == [
        "title", "status", "priority", "due_date", "assigned_to", "modified"
    ]
    for key in ("description", "assigned_to", "reference_doctype", "reference_docname"):
        assert key in result["rows"]
    assert result["data"][0]["title"] == "ZZ Call back"


def test_note_rows_feed_the_card_grid(alice):
    with session_user(alice.name):
        FCRMNote.objects.create(title="ZZ Meeting", content="<p>hi</p>")
    result = _list("FCRM Note")
    for key in ("title", "content", "reference_doctype", "reference_docname", "owner"):
        assert key in result["rows"]
    assert result["data"][0]["content"] == "<p>hi</p>"


def test_call_log_columns_and_parsed_rows(alice):
    """``parse_call_log``: ``_duration`` in crm.utils' words, ``activity_type`` by
    direction, and ``_caller`` / ``_receiver`` as label-plus-image pairs the timeline
    reads directly. An unknown number is "Unknown"."""
    with session_user(alice.name):
        CRMCallLog.objects.create(
            status="Completed", type="Outgoing", caller=alice, duration=65,
            **{"from": "+1 111", "to": "+1 222"},
        )
    result = _list("CRM Call Log")
    assert result["columns"][0]["key"] == "caller"
    assert [c["key"] for c in result["columns"]][-1] == "creation"
    row = result["data"][0]
    assert row["_duration"] == "1m 5s"
    assert row["activity_type"] == "outgoing_call"
    assert row["show_recording"] is False
    assert row["_caller"] == {"label": alice.full_name, "image": alice.user_image}
    assert row["_receiver"] == {"label": "Unknown", "image": None}


def test_an_incoming_call_swaps_the_sides(alice):
    with session_user(alice.name):
        CRMCallLog.objects.create(
            status="Completed", type="Incoming", receiver=alice, duration=3600,
            **{"from": "+1 111", "to": "+1 222"},
        )
    row = _list("CRM Call Log")["data"][0]
    assert row["_duration"] == "1h"
    assert row["activity_type"] == "incoming_call"
    assert row["_caller"]["label"] == "Unknown"
    assert row["_receiver"]["label"] == alice.full_name


@pytest.mark.parametrize(
    "seconds,expected",
    [(0, "0s"), (None, "0s"), (1, "1s"), (60, "1m"), (61, "1m 1s"), (3600, "1h"),
     (3601, "1h 1s"), (3660, "1h 1m"), (3661, "1h 1m 1s")],
)
def test_seconds_to_duration_matches_crm_utils(seconds, expected):
    assert seconds_to_duration(seconds) == expected


def test_the_call_log_document_carries_its_links(auth_api, alice):
    with session_user(alice.name):
        log = CRMCallLog.objects.create(status="Completed", type="Outgoing", **{"from": "1", "to": "2"})
        DynamicLink.objects.create(
            parenttype="CRM Call Log", parentfield="links", parent=str(log.pk),
            link_doctype="CRM Lead", link_name="CRM-LEAD-2026-00001", idx=1,
        )
    response = auth_api.get("/api/resource/" + quote("CRM Call Log") + "/" + quote(str(log.pk)))
    assert response.status_code == 200
    links = response.json()["data"]["links"]
    assert len(links) == 1
    assert links[0]["link_doctype"] == "CRM Lead"
    assert links[0]["link_name"] == "CRM-LEAD-2026-00001"
