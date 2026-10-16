"""Assignment Rule execution through real document saves (FINDINGS.md 80, brief 03)."""

import json
from datetime import date

import pytest
from django.core.cache import cache

from crm_app import assignment_rules
from crm_app.models import CRMDeal, CRMDealStatus, CRMLead, CRMLeadStatus
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.session import session_user
from frappe_platform.models import (
    ASSIGNMENT_DAYS,
    AssignmentRule,
    AssignmentRuleDay,
    AssignmentRuleUser,
    ToDo,
)

pytestmark = pytest.mark.django_db


def _rule(
    name,
    users,
    *,
    rule="Round Robin",
    priority=0,
    condition=None,
    document_type="CRM Lead",
    **fields,
):
    condition = condition or [["status", "equals", "New"]]
    item = AssignmentRule.objects.create(
        name=name,
        document_type=document_type,
        rule=rule,
        priority=priority,
        assign_condition="editor condition",
        assign_condition_json=json.dumps(condition),
        **fields,
    )
    for idx, day in enumerate(ASSIGNMENT_DAYS, 1):
        AssignmentRuleDay.objects.create(
            parent=item.pk,
            parenttype="Assignment Rule",
            parentfield="assignment_days",
            idx=idx,
            day=day,
        )
    for idx, value in enumerate(users, 1):
        user, weight = value if isinstance(value, tuple) else (value, 1)
        AssignmentRuleUser.objects.create(
            parent=item.pk,
            parenttype="Assignment Rule",
            parentfield="weighted_users" if rule == "Weighted Distribution" else "users",
            idx=idx,
            user=user,
            weight=weight,
        )
    return item


@pytest.fixture
def status():
    return CRMLeadStatus.objects.create(lead_status="New", type="Open")


def _lead(status, number=1, **values):
    values.setdefault("first_name", f"Lead {number}")
    return CRMLead.objects.create(status=status, **values)


def _open(lead):
    return ToDo.objects.filter(
        reference_type="CRM Lead", reference_name=str(lead.pk), status="Open"
    ).get()


def test_a_lead_created_with_an_owner_keeps_the_owner(status, make_user):
    """Upstream assigns the owner in ``after_insert``, which Frappe runs before
    ``on_update``, where the rules run; the rule then finds an assignment it did not make
    and assigns nobody (``assignment_rule.py`` ``apply``: assign only when cleared)."""
    owner = make_user("owner@example.com", first_name="Owner")
    rule_user = make_user("rule@example.com", first_name="Rule")
    _rule("Owner first", [rule_user])
    lead = _lead(status, lead_owner=owner)
    assert _open(lead).allocated_to_id == owner.pk
    assert _open(lead).assignment_rule is None


def test_round_robin_wraps_and_records_last_user(status, make_user):
    users = [make_user(f"rr{i}@example.com", first_name=f"R{i}") for i in range(3)]
    rule = _rule("Round robin", users)

    allocated = [_open(_lead(status, i)).allocated_to_id for i in range(4)]

    assert allocated == [users[0].pk, users[1].pk, users[2].pk, users[0].pk]
    rule.refresh_from_db()
    assert rule.last_user_id == users[0].pk


def test_load_balancing_uses_open_todos_and_keeps_user_order_for_ties(
    status, make_user
):
    users = [make_user(f"lb{i}@example.com", first_name=f"L{i}") for i in range(2)]
    _rule("Load balance", users, rule="Load Balancing")
    first = _lead(status, 1)
    second = _lead(status, 2)
    third = _lead(status, 3)
    assert [_open(doc).allocated_to_id for doc in (first, second, third)] == [
        users[0].pk,
        users[1].pk,
        users[0].pk,
    ]


def test_based_on_field_and_weighted_distribution(status, make_user):
    a = make_user("weight-a@example.com", first_name="A")
    b = make_user("weight-b@example.com", first_name="B")
    based = _rule(
        "Based on field",
        [],
        rule="Based on Field",
        field="owner",
        priority=10,
    )
    with session_user(a.pk):
        lead = _lead(status)
    assert _open(lead).allocated_to_id == a.pk

    based.disabled = True
    based.save()
    _rule("Weighted", [(a, 2), (b, 1)], rule="Weighted Distribution")
    assert [_open(_lead(status, i + 10)).allocated_to_id for i in range(6)] == [
        a.pk,
        a.pk,
        b.pk,
        a.pk,
        a.pk,
        b.pk,
    ]


def test_priority_condition_unassign_and_reopen(status, make_user):
    a = make_user("level-a@example.com", first_name="A")
    b = make_user("level-b@example.com", first_name="B")
    first = _rule(
        "L1",
        [a],
        priority=10,
        condition=[["organization", "equals", "L1"]],
        unassign_condition="editor condition",
        unassign_condition_json=json.dumps([["organization", "equals", "L2"]]),
    )
    _rule("L2", [b], condition=[["organization", "equals", "L2"]])
    lead = _lead(status, organization="L1")
    assert _open(lead).assignment_rule == first.pk

    lead.organization = "L2"
    lead.save()
    assert _open(lead).allocated_to_id == b.pk
    assert ToDo.objects.filter(assignment_rule=first.pk, status="Cancelled").exists()

    todo = _open(lead)
    todo.status = "Closed"
    todo.save()
    lead.first_name = "Save again"
    lead.save()
    todo.refresh_from_db()
    assert todo.status == "Open"


def test_days_description_due_date_and_due_date_update(status, make_user):
    user = make_user("dated@example.com", first_name="Dated")
    deal_status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
    rule = _rule(
        "Dated",
        [user],
        description="Call {{ first_name }}",
        due_date_based_on="expected_closure_date",
        document_type="CRM Deal",
        condition=[["status", "equals", "Qualification"]],
    )
    deal = CRMDeal.objects.create(
        status=deal_status,
        first_name="Ada",
        expected_closure_date=date(2026, 10, 20),
    )
    todo = ToDo.objects.get(reference_type="CRM Deal", reference_name=str(deal.pk))
    assert todo.assignment_rule == rule.pk
    assert todo.description == "Call Ada"
    assert todo.date == date(2026, 10, 20)

    deal.expected_closure_date = date(2026, 10, 24)
    deal.save()
    todo.refresh_from_db()
    assert todo.date == date(2026, 10, 24)


def test_outside_assignment_day_and_bad_condition_do_not_break_save(
    status, make_user, caplog, monkeypatch
):
    user = make_user("day@example.com", first_name="Day")
    rule = _rule("Wrong day", [user])
    AssignmentRuleDay.objects.filter(parent=rule.pk).exclude(day="Monday").delete()
    monkeypatch.setattr(assignment_rules, "assignment_day", "Tuesday")
    lead = _lead(status)
    assert not ToDo.objects.filter(reference_name=str(lead.pk)).exists()

    rule.delete()
    malformed = _rule("Malformed", [user])
    AssignmentRule.objects.filter(pk=malformed.pk).update(assign_condition_json="not json")
    lead = _lead(status, 2)
    assert not ToDo.objects.filter(reference_name=str(lead.pk)).exists()
    assert "Auto assignment failed:" in caplog.text


def test_no_rule_doctype_is_query_free_after_cache_warm(status, django_assert_num_queries):
    cache.clear()
    lead = _lead(status)
    lead.first_name = "warm"
    lead.save()
    with django_assert_num_queries(2):
        # The document UPDATE plus SLA selection. The warm empty assignment-rule lookup
        # still adds none; unlike assignment rules, upstream checks SLA policy on save.
        lead.first_name = "still warm"
        lead.save()


def test_deleted_rule_leaves_a_usable_todo(status, make_user):
    user = make_user("dangling@example.com", first_name="Dangling")
    rule = _rule("Disposable", [user])
    todo = _open(_lead(status))
    rule.delete()
    todo.status = "Cancelled"
    todo.save()
    assert ToDo.objects.get(pk=todo.pk).assignment_rule == "Disposable"


def test_bulk_apply_runs_inline_and_queues_batches(
    status, make_user, administrator, monkeypatch
):
    user = make_user("bulk-rule@example.com", first_name="Bulk")
    leads = [_lead(status, i) for i in range(6)]
    _rule("Bulk", [user])

    with session_user(administrator.pk):
        assignment_rules.bulk_apply("CRM Lead", json.dumps([leads[0].pk]))
    assert _open(leads[0]).allocated_to_id == user.pk

    queued = []
    monkeypatch.setattr(
        assignment_rules.apply_task,
        "delay",
        lambda *args: queued.append(args),
    )
    with session_user(administrator.pk):
        assignment_rules.bulk_apply("CRM Lead", [lead.pk for lead in leads])
    assert [args[1] for args in queued] == [lead.pk for lead in leads]
    assert all(args[2] == administrator.pk for args in queued)


def test_bulk_apply_refuses_a_document_the_caller_cannot_read(
    status, alice, bob, administrator
):
    with session_user(bob.pk):
        lead = _lead(status, lead_owner=bob)
    _rule("Protected bulk", [administrator])

    with session_user(alice.pk), pytest.raises(FrappePermissionError):
        assignment_rules.bulk_apply("CRM Lead", [lead.pk])
