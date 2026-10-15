"""Assignment Rule's generic-route contract (FINDINGS.md 80, brief 02)."""

import json

import pytest

from frappe_platform.models import AssignmentRule

pytestmark = pytest.mark.django_db

METHOD = "/api/method/frappe.client."
CODE_ONLY = (
    "This condition was written as code. Build it with the condition editor in "
    "Settings → Assignment Rules; conditions written as code are not evaluated here."
)


@pytest.fixture
def manager(make_user):
    return make_user(
        "manager@example.com",
        first_name="Manager",
        roles=["Sales Manager", "Sales User"],
    )


def _payload(name="ZZ Assignment Rule", **changes):
    assign_json = [["status", "equals", "New"]]
    unassign_json = [["status", "equals", "Closed"]]
    payload = {
        # This is the exact shape AssignmentRuleView.vue sends. assignment_rule_name is
        # a UI-only key and must remain harmless to the generic serializer.
        "doctype": "Assignment Rule",
        "document_type": "CRM Lead",
        "rule": "Round Robin",
        "priority": 2,
        "users": [{"user": "Administrator"}],
        "disabled": False,
        "description": "Automatic Assignment",
        "assignment_days": [{"day": "Monday"}, {"day": "Tuesday"}],
        "name": name,
        "assignment_rule_name": name,
        "assign_condition": 'status == "New"',
        "unassign_condition": 'status == "Closed"',
        "assign_condition_json": json.dumps(assign_json),
        "unassign_condition_json": json.dumps(unassign_json),
    }
    payload.update(changes)
    return payload


def _call(client, method, body):
    return client.post(METHOD + method, body, format="json")


def _insert(client, payload):
    return _call(client, "insert", {"doc": payload})


def test_upstream_defaults_and_select_options_are_declared():
    from frappe_platform.models import ASSIGNMENT_DAYS, ASSIGNMENT_RULE_TYPES, AssignmentRuleDay

    assert AssignmentRule._meta.get_field("description").default == "Automatic Assignment"
    assert AssignmentRule._meta.get_field("disabled").default is False
    assert [value for value, _label in AssignmentRule._meta.get_field("rule").choices] == list(
        ASSIGNMENT_RULE_TYPES
    )
    assert [value for value, _label in AssignmentRuleDay._meta.get_field("day").choices] == list(
        ASSIGNMENT_DAYS
    )


def test_the_screen_can_create_get_update_rename_and_delete(api_as, administrator):
    client = api_as(administrator)
    response = _insert(client, _payload())
    assert response.status_code == 200, response.content[:500]
    assert response.json()["message"]["name"] == "ZZ Assignment Rule"

    response = _call(
        client, "get", {"doctype": "Assignment Rule", "name": "ZZ Assignment Rule"}
    )
    assert response.status_code == 200, response.content[:500]
    document = response.json()["message"]
    assert document["doctype"] == "Assignment Rule"
    assert [row["user"] for row in document["users"]] == ["Administrator"]
    assert [row["day"] for row in document["assignment_days"]] == ["Monday", "Tuesday"]
    assert json.loads(document["assign_condition_json"]) == [["status", "equals", "New"]]
    assert json.loads(document["unassign_condition_json"]) == [
        ["status", "equals", "Closed"]
    ]

    response = _call(
        client,
        "set_value",
        {
            "doctype": "Assignment Rule",
            "name": "ZZ Assignment Rule",
            "fieldname": {"disabled": True},
        },
    )
    assert response.status_code == 200, response.content[:500]
    assert response.json()["message"]["disabled"] is True

    response = _call(
        client,
        "rename_doc",
        {
            "doctype": "Assignment Rule",
            "old_name": "ZZ Assignment Rule",
            "new_name": "ZZ Renamed Rule",
        },
    )
    assert response.status_code == 200, response.content[:500]
    assert AssignmentRule.objects.filter(pk="ZZ Renamed Rule").exists()

    response = _call(
        client, "delete", {"doctype": "Assignment Rule", "name": "ZZ Renamed Rule"}
    )
    assert response.status_code == 200, response.content[:500]
    assert not AssignmentRule.objects.filter(pk="ZZ Renamed Rule").exists()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"document_type": "ToDo"},
            "Assignment Rule is not allowed on document type <strong>ToDo</strong>",
        ),
        (
            {
                "assignment_days": [
                    {"day": "Monday"},
                    {"day": "Tuesday"},
                    {"day": "Monday"},
                    {"day": "Tuesday"},
                ]
            },
            "The following Assignment Days have been repeated: Monday and Tuesday",
        ),
        (
            {
                "assignment_days": [
                    {"day": "Monday"},
                    {"day": "Tuesday"},
                    {"day": "Wednesday"},
                    {"day": "Monday"},
                    {"day": "Tuesday"},
                    {"day": "Wednesday"},
                ]
            },
            "The following Assignment Days have been repeated: Monday, Tuesday and Wednesday",
        ),
        ({"assign_condition_json": ""}, CODE_ONLY),
        ({"unassign_condition_json": ""}, CODE_ONLY),
        ({"close_condition": "status == 'Closed'"}, CODE_ONLY),
        (
            {"assign_condition_json": "not json"},
            "Condition is not valid JSON: Expecting value",
        ),
        (
            {"assign_condition_json": '[["status", "approximately", "New"]]'},
            "Unknown condition operator: 'approximately'",
        ),
    ],
)
def test_save_validations_return_the_required_message(
    api_as, administrator, changes, message
):
    response = _insert(api_as(administrator), _payload(**changes))
    assert response.status_code == 417, response.content[:500]
    assert response.json()["message"] == message


def test_a_rule_needs_at_least_one_assignment_day(api_as, administrator):
    """``assignment_days`` is ``reqd`` (version-15 ``assignment_rule.json``):
    ``base_document.py:742-745``'s table message."""
    response = _insert(api_as(administrator), _payload(assignment_days=[]))
    assert response.status_code == 417, response.content[:500]
    assert response.json()["message"] == "Error: Data missing in table: Assignment Days"
    assert not AssignmentRule.objects.exists()


@pytest.mark.parametrize("who", ["alice", "manager"])
def test_sales_user_and_sales_manager_cannot_insert_or_get(
    api_as, administrator, request, who
):
    admin = api_as(administrator)
    assert _insert(admin, _payload()).status_code == 200

    client = api_as(request.getfixturevalue(who))
    response = _insert(client, _payload(name=f"ZZ {who}"))
    assert response.status_code == 403, response.content[:500]
    response = _call(
        client, "get", {"doctype": "Assignment Rule", "name": "ZZ Assignment Rule"}
    )
    assert response.status_code == 403, response.content[:500]


def test_users_and_weighted_users_are_kept_apart(api_as, administrator, make_user):
    weighted = make_user("weighted@example.com", first_name="Weighted")
    client = api_as(administrator)
    response = _insert(
        client,
        _payload(
            rule="Weighted Distribution",
            users=[{"user": administrator.name}],
            weighted_users=[{"user": weighted.name, "weight": 3}],
        ),
    )
    assert response.status_code == 200, response.content[:500]
    document = response.json()["message"]
    assert [(row["user"], row["weight"]) for row in document["users"]] == [
        (administrator.name, 1)
    ]
    assert [
        (row["user"], row["weight"]) for row in document["weighted_users"]
    ] == [(weighted.name, 3)]

    response = _call(
        client,
        "set_value",
        {
            "doctype": "Assignment Rule",
            "name": "ZZ Assignment Rule",
            "fieldname": {"users": [{"user": weighted.name}]},
        },
    )
    assert response.status_code == 200, response.content[:500]
    document = response.json()["message"]
    assert [row["user"] for row in document["users"]] == [weighted.name]
    assert [row["user"] for row in document["weighted_users"]] == [weighted.name]
    assert document["weighted_users"][0]["weight"] == 3
