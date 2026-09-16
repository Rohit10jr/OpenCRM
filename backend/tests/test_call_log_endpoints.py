"""The call-log endpoints the frontend calls by their doctype-module path: get_call_log
and create_lead_from_call_log (crm/fcrm/doctype/crm_call_log/crm_call_log.py:189-297).
Both answered 404 until now (docs/http/14_unserved_paths.http, 1.7 and 1.8).
"""

import pytest

from crm_app.integrations.call_log import link_with_reference_doc
from crm_app.models import CRMCallLog, CRMLead, CRMLeadStatus, CRMTask, FCRMNote
from frappe_core.session import session_user
from frappe_platform.models import DynamicLink

pytestmark = pytest.mark.django_db

BASE = "/api/method/crm.fcrm.doctype.crm_call_log.crm_call_log."


def call(client, path, payload):
    return client.post(BASE + path, payload, format="json")


@pytest.fixture(autouse=True)
def lead_status(administrator):
    with session_user(administrator.name):
        CRMLeadStatus.objects.create(lead_status="New", type="Open")


@pytest.fixture
def log(alice):
    with session_user(alice.name):
        return CRMCallLog.objects.create(
            status="Completed", type="Outgoing", caller=alice, duration=65,
            recording_url="https://rec.test/1.mp3", **{"from": "+1 111", "to": "+1 222"},
        )


def test_get_call_log_parses_the_call_and_collects_its_notes_tasks_and_record(auth_api, alice, log):
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="ZZ Caller", lead_owner=alice)
        own_note = FCRMNote.objects.create(title="ZZ Own", content="<p>own</p>")
        linked_note = FCRMNote.objects.create(title="ZZ Linked", content="<p>linked</p>")
        task = CRMTask.objects.create(title="ZZ Follow up", status="Todo", priority="Medium")
        CRMCallLog.objects.filter(pk=log.pk).update(
            note=own_note, reference_doctype="CRM Lead", reference_docname=lead.name
        )
        log.refresh_from_db()
        link_with_reference_doc(log, "FCRM Note", linked_note.pk)
        link_with_reference_doc(log, "CRM Task", task.pk)

    response = call(auth_api, "get_call_log", {"name": log.pk})

    assert response.status_code == 200, response.content[:300]
    data = response.json()["message"]
    assert data["name"] == log.pk
    assert data["_duration"] == "1m 5s"
    assert data["activity_type"] == "outgoing_call"
    assert data["_caller"]["label"] == alice.full_name
    assert data["_lead"] == lead.name and "_deal" not in data
    assert [n["title"] for n in data["_notes"]] == ["ZZ Own", "ZZ Linked"]
    assert [t["title"] for t in data["_tasks"]] == ["ZZ Follow up"]
    assert data["recording_url_path"] == (
        f"/api/method/crm.integrations.api.get_recording_url?call_log_name={log.pk}"
    )


def test_get_call_log_takes_the_deal_from_a_link(auth_api, alice, log):
    with session_user(alice.name):
        link_with_reference_doc(log, "CRM Deal", "CRM-DEAL-2026-00001")
    data = call(auth_api, "get_call_log", {"name": log.pk}).json()["message"]
    assert data["_deal"] == "CRM-DEAL-2026-00001"
    assert data["_notes"] == [] and data["_tasks"] == []


def test_a_linked_lead_wins_over_the_reference(auth_api, alice, log):
    """crm_call_log.py:219-241: the reference sets _lead first, the links loop after it,
    so a lead linked later overwrites the one referenced."""
    with session_user(alice.name):
        referenced = CRMLead.objects.create(first_name="ZZ Referenced", lead_owner=alice)
        linked = CRMLead.objects.create(first_name="ZZ Linked", lead_owner=alice)
        CRMCallLog.objects.filter(pk=log.pk).update(reference_doctype="CRM Lead", reference_docname=referenced.name)
        log.refresh_from_db()
        link_with_reference_doc(log, "CRM Lead", linked.name)
    data = call(auth_api, "get_call_log", {"name": log.pk}).json()["message"]
    assert data["_lead"] == linked.name


def test_an_incoming_call_is_parsed_from_the_receivers_side(auth_api, alice):
    with session_user(alice.name):
        incoming = CRMCallLog.objects.create(
            status="Completed", type="Incoming", receiver=alice, duration=5, **{"from": "+1 333", "to": "+1 222"}
        )
    data = call(auth_api, "get_call_log", {"name": incoming.pk}).json()["message"]
    assert data["activity_type"] == "incoming_call"
    assert data["_receiver"]["label"] == alice.full_name
    assert data["_duration"] == "5s"
    assert data["show_recording"] is False and "recording_url_path" not in data


def test_any_sales_user_may_open_a_call(api_as, bob, log):
    """CRM Call Log carries no row rule, here or upstream: every Sales User reads and
    writes every call, so the read check on ``get_call_log`` is a formality."""
    assert call(api_as(bob), "get_call_log", {"name": log.pk}).status_code == 200


# --- create_lead_from_call_log ------------------------------------------------------------


def test_a_lead_is_created_from_the_call_and_linked_to_it(auth_api, alice, log):
    response = call(
        auth_api,
        "create_lead_from_call_log",
        {"call_log": log.pk, "lead_details": {"last_name": "Unknown", "not_a_field": "x"}},
    )
    assert response.status_code == 200, response.content[:300]
    lead = CRMLead.objects.get(pk=response.json()["message"])
    assert lead.lead_owner_id == alice.name
    assert lead.mobile_no == "+1 111"
    assert lead.first_name == "Lead from call +1 111"
    assert lead.last_name == "Unknown"
    assert DynamicLink.objects.filter(
        parenttype="CRM Call Log", parent=str(log.pk), link_doctype="CRM Lead", link_name=lead.pk
    ).exists()


def test_the_call_may_arrive_as_its_own_record(auth_api, alice, log):
    """CallLogDetailModal.vue sends the call it holds, not its name."""
    response = call(auth_api, "create_lead_from_call_log", {"call_log": {"name": log.pk, "type": "Outgoing"}})
    assert response.status_code == 200, response.content[:300]
    assert CRMLead.objects.filter(pk=response.json()["message"]).exists()


def test_the_given_details_win_over_the_defaults(auth_api, alice, bob, log):
    response = call(
        auth_api,
        "create_lead_from_call_log",
        {"call_log": log.pk, "lead_details": {"first_name": "ZZ Named", "mobile_no": "+1 999", "lead_owner": bob.name}},
    )
    lead = CRMLead.objects.get(pk=response.json()["message"])
    assert (lead.first_name, lead.mobile_no, lead.lead_owner_id) == ("ZZ Named", "+1 999", bob.name)


def test_refusals_use_upstreams_words(auth_api, api_as, bob, log):
    response = call(auth_api, "create_lead_from_call_log", {"call_log": ""})
    assert response.status_code == 417
    assert response.json()["message"] == "A valid call log is required."

    response = call(auth_api, "create_lead_from_call_log", {"call_log": log.pk, "lead_details": ["x"]})
    assert response.status_code == 417
    assert response.json()["message"] == "Invalid lead details supplied."

    response = call(auth_api, "create_lead_from_call_log", {"call_log": "ZZ-NO-SUCH-CALL"})
    assert response.status_code == 404, "frappe.get_doc runs before the permission check"
    assert response.json()["exc_type"] == "DoesNotExistError"


def test_only_the_leads_own_fields_are_taken_from_the_details(auth_api, alice, log):
    """``meta.fields`` upstream: name, owner and the other standard fields are not among
    them, so a caller cannot pick the lead's name or hand it to someone else."""
    response = call(
        auth_api,
        "create_lead_from_call_log",
        {"call_log": log.pk, "lead_details": {"name": "ZZ-PICKED", "owner": "bob@example.com", "creation": "2001-01-01", "idx": 9}},
    )
    assert response.status_code == 200, response.content[:300]
    lead = CRMLead.objects.get(pk=response.json()["message"])
    assert lead.name != "ZZ-PICKED" and lead.name.startswith("CRM-LEAD-")
    assert lead.owner_id == alice.name
    assert lead.idx == 0
