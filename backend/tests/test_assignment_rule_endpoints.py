"""The two CRM Assignment Rule endpoints (FINDINGS.md 80, brief 04)."""

import json

import pytest
from frappe_core.session import session_user
from frappe_platform.models import AssignmentRule, AssignmentRuleDay, AssignmentRuleUser

pytestmark = pytest.mark.django_db

METHOD = "/api/method/crm.api.assignment_rule."


@pytest.fixture
def manager(make_user):
    return make_user(
        "manager@example.com",
        first_name="Manager",
        roles=["Sales Manager", "Sales User"],
    )


def _rule(name, document_type, *, users=(), weighted_users=(), **values):
    defaults = {
        "description": "Automatic Assignment",
        "priority": 0,
        "disabled": False,
        "rule": "Round Robin",
        "assign_condition": 'status == "New"',
        "assign_condition_json": json.dumps([["status", "equals", "New"]]),
    }
    defaults.update(values)
    rule = AssignmentRule.objects.create(
        name=name, document_type=document_type, **defaults
    )
    for idx, day in enumerate(("Monday", "Tuesday"), 1):
        AssignmentRuleDay.objects.create(
            parent=rule.pk,
            parenttype="Assignment Rule",
            parentfield="assignment_days",
            idx=idx,
            day=day,
        )
    for parentfield, rows in (("users", users), ("weighted_users", weighted_users)):
        for idx, value in enumerate(rows, 1):
            user, weight = value if isinstance(value, tuple) else (value, 1)
            AssignmentRuleUser.objects.create(
                parent=rule.pk,
                parenttype="Assignment Rule",
                parentfield=parentfield,
                idx=idx,
                user=user,
                weight=weight,
            )
    return rule


def _call(client, method, payload=None):
    return client.post(METHOD + method, payload or {}, format="json")


def test_list_returns_lead_and_deal_rules_with_users_for_a_sales_user(
    api_as, alice, administrator
):
    with session_user(administrator.name):
        _rule("Lead rule", "CRM Lead", users=[administrator])
        _rule("Deal rule", "CRM Deal", priority=4, disabled=True)
        _rule("Contact rule", "Contact", users=[administrator])

    response = _call(api_as(alice), "get_assignment_rules_list")
    assert response.status_code == 200, response.content[:500]
    rows = {row["name"]: row for row in response.json()["message"]}
    assert rows == {
        "Lead rule": {
            "name": "Lead rule",
            "description": "Automatic Assignment",
            "disabled": False,
            "priority": 0,
            "users_exists": True,
        },
        "Deal rule": {
            "name": "Deal rule",
            "description": "Automatic Assignment",
            "disabled": True,
            "priority": 4,
            "users_exists": False,
        },
    }


def test_administrator_can_duplicate_every_field_and_both_child_doctypes(
    api_as, administrator, make_user
):
    weighted = make_user("weighted@example.com", first_name="Weighted")
    with session_user(administrator.name):
        _rule(
            "Original",
            "CRM Deal",
            users=[administrator],
            weighted_users=[(weighted, 3)],
            rule="Weighted Distribution",
            description="Qualify {{ first_name }}",
            priority=3,
            disabled=True,
            due_date_based_on="expected_closure_date",
            unassign_condition='status == "Lost"',
            unassign_condition_json=json.dumps([["status", "equals", "Lost"]]),
        )
        AssignmentRule.objects.filter(pk="Original").update(
            last_user=administrator,
            current_index=7,
        )

    response = _call(
        api_as(administrator),
        "duplicate_assignment_rule",
        {"docname": "Original", "new_name": "Original (Copy)"},
    )
    assert response.status_code == 200, response.content[:500]
    copied = response.json()["message"]
    assert copied["name"] == "Original (Copy)"
    assert copied["document_type"] == "CRM Deal"
    assert copied["rule"] == "Weighted Distribution"
    assert copied["description"] == "Qualify {{ first_name }}"
    assert copied["priority"] == 3
    assert copied["disabled"] is True
    assert copied["due_date_based_on"] == "expected_closure_date"
    assert copied["assign_condition_json"] == json.dumps(
        [["status", "equals", "New"]]
    )
    assert copied["unassign_condition_json"] == json.dumps(
        [["status", "equals", "Lost"]]
    )
    assert copied["last_user"] == administrator.name
    assert copied["current_index"] == 7
    assert [row["day"] for row in copied["assignment_days"]] == [
        "Monday",
        "Tuesday",
    ]
    assert [(row["user"], row["weight"]) for row in copied["users"]] == [
        (administrator.name, 1)
    ]
    assert [
        (row["user"], row["weight"]) for row in copied["weighted_users"]
    ] == [(weighted.name, 3)]


def test_sales_manager_is_refused_by_the_create_permission(
    api_as, administrator, manager
):
    with session_user(administrator.name):
        _rule("Original", "CRM Lead", users=[administrator])

    response = _call(
        api_as(manager),
        "duplicate_assignment_rule",
        {"docname": "Original", "new_name": "Manager copy"},
    )
    assert response.status_code == 403, response.content[:500]
    assert response.json()["exc_type"] == "PermissionError"
    assert response.json()["message"] == "Not permitted to create Assignment Rule"
    assert not AssignmentRule.objects.filter(pk="Manager copy").exists()
