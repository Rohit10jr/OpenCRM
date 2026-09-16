"""Assigning a document notifies the assignee: FINDINGS.md 18.

``crm/api/todo.py`` is registered upstream in ``hooks.py:doc_events`` for ToDo:
``after_insert`` makes the assignee the lead's or deal's owner and notifies them with
"{owner} assigned a {doctype} {name} to you"; ``on_update`` notifies "Your assignment
on {doctype} {name} has been removed by {owner}" when the ToDo is cancelled, and clears
the owner. A task's notification lands on the task's own lead or deal.
"""

import pytest

from crm_app.models import CRMLead, CRMLeadStatus, CRMNotification, CRMTask
from frappe_core import assignment
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def lead(alice):
    with session_user(alice.name):
        CRMLeadStatus.objects.create(lead_status="New", type="Open")
        return CRMLead.objects.create(first_name="ZZ Solo", lead_owner=alice)


def _notifications(user):
    return CRMNotification.objects.filter(to_user=user, type="Assignment").order_by("creation")


def test_assigning_a_lead_notifies_the_assignee_and_makes_them_owner(alice, bob, lead):
    with session_user(alice.name):
        assignment.assign_to_user("CRM Lead", lead.name, bob.name)

    row = _notifications(bob).get()
    assert row.from_user_id == alice.name
    assert row.message == f"{alice.full_name} assigned a CRM Lead {lead.name} to you"
    assert "assigned a lead" in row.notification_text
    assert "ZZ Solo" in row.notification_text
    assert row.notification_type_doctype == "CRM Lead"
    assert row.notification_type_doc == lead.name
    assert row.reference_doctype == "CRM Lead"
    assert row.reference_name == lead.name
    lead.refresh_from_db()
    assert lead.lead_owner_id == bob.name, "crm/api/todo.py:after_insert mirrors assign_to"


def test_cancelling_the_assignment_notifies_and_clears_the_owner(alice, bob, lead):
    with session_user(alice.name):
        assignment.assign_to_user("CRM Lead", lead.name, bob.name)
        assignment.cancel_assignment("CRM Lead", lead.name, [bob.name])

    rows = list(_notifications(bob))
    assert len(rows) == 2
    assert rows[1].message == (
        f"Your assignment on CRM Lead {lead.name} has been removed by {alice.full_name}"
    )
    assert "has been removed by" in rows[1].notification_text
    lead.refresh_from_db()
    assert lead.lead_owner_id is None


def test_assigning_yourself_is_not_a_notification(alice, lead):
    with session_user(alice.name):
        assignment.assign_to_user("CRM Lead", lead.name, alice.name)
    assert not _notifications(alice).exists()


def test_a_task_notification_names_the_task_and_lands_on_its_lead(alice, bob, lead):
    with session_user(alice.name):
        task = CRMTask.objects.create(
            title="ZZ Call back",
            status="Todo",
            priority="Medium",
            assigned_to=bob,
            reference_doctype="CRM Lead",
            reference_docname=lead.name,
        )

    row = _notifications(bob).get()
    assert row.message == f"{alice.full_name} assigned a CRM Task {task.pk} to you"
    assert "assigned a new task" in row.notification_text
    assert "ZZ Call back" in row.notification_text
    assert row.notification_type_doctype == "CRM Task"
    assert row.notification_type_doc == str(task.pk)
    assert row.reference_doctype == "CRM Lead"
    assert row.reference_name == lead.name
    lead.refresh_from_db()
    assert lead.lead_owner_id == alice.name, "a task assignment does not touch the lead's owner"


def test_the_same_assignment_is_not_notified_twice(alice, bob, lead):
    with session_user(alice.name):
        assignment.assign_to_user("CRM Lead", lead.name, bob.name)
        assignment.assign_to_user("CRM Lead", lead.name, bob.name)
    assert _notifications(bob).count() == 1


def test_the_bell_routes_a_task_assignment_to_the_tasks_tab(auth_api, alice, bob, lead, api_as):
    with session_user(alice.name):
        CRMTask.objects.create(
            title="ZZ Route", status="Todo", priority="Medium", assigned_to=bob,
            reference_doctype="CRM Lead", reference_docname=lead.name,
        )
    response = api_as(bob).post("/api/method/crm.api.notifications.get_notifications", {}, format="json")
    assert response.status_code == 200
    (row,) = response.json()["message"]
    assert row["type"] == "Assignment"
    assert row["hash"] == "#tasks"
    assert row["reference_doctype"] == "lead"
    assert row["reference_name"] == lead.name
