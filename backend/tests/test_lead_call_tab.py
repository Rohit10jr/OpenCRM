"""A call log pointed at a lead shows on that lead's Calls tab: docs/FINDINGS.md 69.

``crm/api/activities.py:376-467`` ends with ``parse_call_log`` over every call it
found, and ``CallArea.vue`` reads ``_caller`` and ``_receiver`` straight off each row.
The port returned the rows raw, so the tab had a call it could not draw.
"""

import pytest

from crm_app.models import CRMCallLog, CRMLead, CRMLeadStatus
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def lead(alice, administrator):
    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
    with session_user(alice.name):
        return CRMLead.objects.create(first_name="Ada", lead_owner=alice, status=status)


def calls_tab(client, name):
    """The second of the five buckets ``get_activities`` answers with."""
    response = client.post("/api/method/crm.api.activities.get_activities", {"name": name}, format="json")
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"][1]


def test_a_call_pointed_at_a_lead_arrives_parsed(auth_api, alice, lead):
    with session_user(alice.name):
        call = CRMCallLog.objects.create(
            status="Completed",
            type="Incoming",
            duration=600,
            receiver=alice,
            reference_doctype="CRM Lead",
            reference_docname=lead.name,
            **{"from": "234567765", "to": "123456789"},
        )

    rows = calls_tab(auth_api, lead.name)

    assert [row["name"] for row in rows] == [call.name]
    row = rows[0]
    assert row["activity_type"] == "incoming_call"
    assert row["_caller"] == {"label": "Unknown", "image": None}
    assert row["_receiver"]["label"] == alice.full_name
    assert row["_duration"] == "10m"
    assert row["show_recording"] is False


def test_repointing_a_call_in_the_dialog_puts_it_on_the_lead(auth_api, alice, lead):
    """What the call log dialog does on Update: the two reference fields, nothing else."""
    with session_user(alice.name):
        call = CRMCallLog.objects.create(
            status="Completed", type="Outgoing", caller=alice, **{"from": "1", "to": "2"}
        )
    assert calls_tab(auth_api, lead.name) == []

    response = auth_api.post(
        "/api/method/frappe.client.set_value",
        {
            "doctype": "CRM Call Log",
            "name": call.name,
            "fieldname": {"reference_doctype": "CRM Lead", "reference_docname": lead.name},
        },
        format="json",
    )
    assert response.status_code == 200, response.content[:300]

    rows = calls_tab(auth_api, lead.name)
    assert [row["name"] for row in rows] == [call.name]
    assert rows[0]["activity_type"] == "outgoing_call"
    assert rows[0]["_caller"]["label"] == alice.full_name
    assert rows[0]["_receiver"] == {"label": "Unknown", "image": None}
