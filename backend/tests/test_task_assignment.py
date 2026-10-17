"""A task's assigned_to is an assignment: FINDINGS.md 15.

``crm_task.py:30-56``: ``after_insert`` assigns the task to ``assigned_to`` through
``assign_to.add``, so a ToDo exists and ``_assign`` names the user; ``validate`` on a
later save unassigns the previous user and assigns the new one. The task board's
assignee chip reads ``_assign`` and the assignee's own task list is built from ToDo.
"""

from urllib.parse import quote

import json

import pytest

from crm_app.models import CRMTask
from frappe_core import assignment
from frappe_core.session import session_user
from frappe_platform.models import ToDo

pytestmark = pytest.mark.django_db

TASKS = "/api/resource/" + quote("CRM Task")
SET_VALUE = "/api/method/frappe.client.set_value"
BULK_UPDATE = "/api/method/frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs"


def _todos(task, user):
    return ToDo.objects.filter(
        reference_type="CRM Task", reference_name=str(task.pk), allocated_to=user
    )


def test_a_new_task_is_assigned_to_its_assignee(alice, bob):
    with session_user(alice.name):
        task = CRMTask.objects.create(
            title="ZZ Call back", status="Todo", priority="Medium", assigned_to=bob
        )
    task.refresh_from_db()
    assert task._assign == [bob.name]
    todo = _todos(task, bob).get()
    assert todo.status == "Open"
    assert todo.description == "ZZ Call back"


def test_a_task_without_an_assignee_gets_no_todo(alice):
    with session_user(alice.name):
        task = CRMTask.objects.create(title="ZZ Loose", status="Backlog", priority="Low")
    task.refresh_from_db()
    assert task._assign == []
    assert not ToDo.objects.filter(reference_type="CRM Task", reference_name=str(task.pk)).exists()


def test_changing_the_assignee_moves_the_assignment(alice, bob):
    with session_user(alice.name):
        task = CRMTask.objects.create(title="ZZ Move", status="Todo", priority="Medium", assigned_to=bob)
        task = CRMTask.objects.get(pk=task.pk)
        task.assigned_to = alice
        task.save()
    task.refresh_from_db()
    assert task._assign == [alice.name]
    assert _todos(task, bob).get().status == "Cancelled"
    assert _todos(task, alice).get().status == "Open"


def test_set_value_clearing_the_assignee_cancels_the_assignment(auth_api, alice, bob):
    with session_user(alice.name):
        task = CRMTask.objects.create(
            title="ZZ Clear", status="Todo", priority="Medium", assigned_to=bob
        )

    response = auth_api.post(
        SET_VALUE,
        {
            "doctype": "CRM Task",
            "name": task.pk,
            "fieldname": {"assigned_to": None},
        },
        format="json",
    )

    assert response.status_code == 200, response.content[:300]
    task.refresh_from_db()
    assert task.assigned_to is None
    assert task._assign == []
    assert _todos(task, bob).get().status == "Cancelled"


def test_bulk_update_clearing_the_assignee_cancels_both_assignments(auth_api, alice, bob):
    with session_user(alice.name):
        tasks = [
            CRMTask.objects.create(
                title=f"ZZ Bulk clear {index}",
                status="Todo",
                priority="Medium",
                assigned_to=bob,
            )
            for index in range(2)
        ]

    response = auth_api.post(
        BULK_UPDATE,
        {
            "doctype": "CRM Task",
            "docnames": [task.pk for task in tasks],
            "action": "update",
            "data": {"assigned_to": None},
        },
        format="json",
    )

    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"] == []
    for task in tasks:
        task.refresh_from_db()
        assert task.assigned_to is None
        assert task._assign == []
        assert _todos(task, bob).get().status == "Cancelled"


def test_clearing_a_task_that_never_had_an_assignee_changes_nothing(auth_api, alice):
    with session_user(alice.name):
        task = CRMTask.objects.create(
            title="ZZ Never assigned", status="Backlog", priority="Low"
        )

    response = auth_api.post(
        SET_VALUE,
        {
            "doctype": "CRM Task",
            "name": task.pk,
            "fieldname": {"assigned_to": None},
        },
        format="json",
    )

    assert response.status_code == 200, response.content[:300]
    task.refresh_from_db()
    assert task.assigned_to is None
    assert task._assign == []
    assert not ToDo.objects.filter(
        reference_type="CRM Task", reference_name=str(task.pk)
    ).exists()


def test_clearing_assigned_to_keeps_a_separate_manual_assignment(
    auth_api, alice, bob, make_user
):
    carol = make_user("carol@example.com")
    with session_user(alice.name):
        task = CRMTask.objects.create(
            title="ZZ Keep manual", status="Todo", priority="Medium", assigned_to=bob
        )
        assignment.assign_to_user("CRM Task", task.pk, carol.name)

    response = auth_api.post(
        SET_VALUE,
        {
            "doctype": "CRM Task",
            "name": task.pk,
            "fieldname": {"assigned_to": None},
        },
        format="json",
    )

    assert response.status_code == 200, response.content[:300]
    task.refresh_from_db()
    assert task.assigned_to is None
    assert task._assign == [carol.name]
    assert _todos(task, bob).get().status == "Cancelled"
    assert _todos(task, carol).get().status == "Open"


def test_saving_without_changing_the_assignee_adds_nothing(alice, bob):
    with session_user(alice.name):
        task = CRMTask.objects.create(title="ZZ Same", status="Todo", priority="Medium", assigned_to=bob)
        task = CRMTask.objects.get(pk=task.pk)
        task.status = "In Progress"
        task.save()
    assert _todos(task, bob).count() == 1


def test_the_document_route_assigns_too(auth_api, alice, bob):
    response = auth_api.post(
        TASKS,
        {"title": "ZZ Via API", "status": "Todo", "priority": "Medium", "assigned_to": bob.name},
        format="json",
    )
    assert response.status_code == 201, response.content[:300]
    name = response.json()["data"]["name"]
    # `_assign` is a JSON string on the wire, as upstream sends it (FINDINGS.md 40).
    assert json.loads(auth_api.get(f"{TASKS}/{name}").json()["data"]["_assign"]) == [bob.name]

    response = auth_api.put(f"{TASKS}/{name}", {"assigned_to": alice.name}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert json.loads(auth_api.get(f"{TASKS}/{name}").json()["data"]["_assign"]) == [alice.name]
