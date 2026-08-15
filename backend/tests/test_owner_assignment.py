"""C1a - assigning a lead or deal to its owner.

Upstream (``crm_lead.py:86-88,94-98`` and ``crm_deal.py:86-88,98-102``) assigns the
record to its owner on insert and again whenever the owner changes. Phase 1 ported the
columns but not this, so ``_assign`` stayed empty and the assignee chip was blank on
every lead and deal.

**What this is not.** The record is assigned to its *own owner*, who already satisfies
the permission rule's ``<x>_owner == user`` clause, so the ``ToDo`` written here grants
no access it did not already have. It drives the UI. The ``ToDo`` path matters for access
when someone *other* than the owner is assigned - that is the phase-3 assignment
endpoints, not this.

``share_with_agent`` is a deliberate no-op; see ``OwnerAssignmentMixin`` for why porting
it alone would write rows nothing reads.
"""

import pytest

from crm_app.models import CRMDeal, CRMDealStatus, CRMLead, CRMLeadStatus
from frappe_core.assignment import get_assigned_users
from frappe_core.session import session_user
from frappe_platform.models import ToDo

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(make_user):
    return make_user("owner@example.com", first_name="Owner", roles=["Sales User"])


@pytest.fixture
def other(make_user):
    return make_user("other@example.com", first_name="Other", roles=["Sales User"])


@pytest.fixture(autouse=True)
def statuses(administrator):
    """``status`` is mandatory because upstream's ``validate_status`` - which defaults it
    to "New" for a lead and "Qualification" for a deal - is **not ported** (it is on the
    same ``validate()`` chain as the assignment logic here). Until it is, every test has
    to supply one."""
    with session_user(administrator.name):
        return {
            "lead": CRMLeadStatus.objects.create(lead_status="New", type="Open"),
            "deal": CRMDealStatus.objects.create(deal_status="Qualification", type="Open"),
        }


def _assignees(doc):
    return get_assigned_users(doc.get_doctype(), doc.pk)


# --- create ---------------------------------------------------------------------


def test_a_new_lead_is_assigned_to_its_owner(alice, owner, statuses):
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", lead_owner=owner, status=statuses["lead"])

    assert _assignees(lead) == [owner.name]


def test_a_new_deal_is_assigned_to_its_owner(alice, owner, statuses):
    with session_user(alice.name):
        deal = CRMDeal.objects.create(deal_owner=owner, status=statuses["deal"])

    assert _assignees(deal) == [owner.name]


def test_the_assign_cache_is_updated_too(alice, owner, statuses):
    """``_assign`` is what the list view renders; the ToDo signal keeps it in sync."""
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", lead_owner=owner, status=statuses["lead"])

    lead.refresh_from_db()
    assert lead._assign == [owner.name]


def test_a_lead_with_no_owner_is_not_assigned(alice, statuses):
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", status=statuses["lead"])

    assert _assignees(lead) == []


# --- owner change ----------------------------------------------------------------


def test_changing_the_owner_assigns_the_new_one(alice, owner, other, statuses):
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", lead_owner=owner, status=statuses["lead"])

    reloaded = CRMLead.objects.get(pk=lead.pk)
    with session_user(alice.name):
        reloaded.lead_owner = other
        reloaded.save()

    assert other.name in _assignees(reloaded)


def test_the_previous_owner_keeps_their_assignment(alice, owner, other, statuses):
    """Upstream only *adds*; ``assign_agent`` never removes a ToDo.

    Unassigning is a separate action (``remove_assignments`` in the phase-3 API), so an
    owner change leaves the old assignee in place. Faithful, and easy to assume otherwise.
    """
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", lead_owner=owner, status=statuses["lead"])

    reloaded = CRMLead.objects.get(pk=lead.pk)
    with session_user(alice.name):
        reloaded.lead_owner = other
        reloaded.save()

    assert set(_assignees(reloaded)) == {owner.name, other.name}


def test_saving_without_changing_the_owner_creates_no_duplicate(alice, owner, statuses):
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", lead_owner=owner, status=statuses["lead"])

    reloaded = CRMLead.objects.get(pk=lead.pk)
    with session_user(alice.name):
        reloaded.first_name = "Ada Updated"
        reloaded.save()

    assert ToDo.objects.filter(reference_name=lead.pk).count() == 1


def test_reassigning_the_same_owner_creates_no_duplicate(alice, owner, statuses):
    """``assign_agent`` returns early when the agent is already an assignee."""
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", lead_owner=owner, status=statuses["lead"])
        lead.assign_agent(owner.name)
        lead.assign_agent(owner.name)

    assert ToDo.objects.filter(reference_name=lead.pk, allocated_to=owner).count() == 1


# --- the ToDo itself --------------------------------------------------------------


def test_the_todo_matches_upstreams_shape(alice, owner, statuses):
    """``frappe/desk/form/assign_to.py:85-97``."""
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", lead_owner=owner, status=statuses["lead"])

    todo = ToDo.objects.get(reference_name=lead.pk)
    assert todo.reference_type == "CRM Lead"
    assert todo.allocated_to_id == owner.name
    assert todo.status == "Open"
    assert todo.priority == "Medium"
    assert todo.assigned_by_id == alice.name
    assert todo.date is not None
    assert "CRM Lead" in todo.description


# --- the deliberate no-op ---------------------------------------------------------


def test_share_with_agent_is_a_no_op(alice, owner, statuses):
    """Pins the seam. If DocShare is ever ported, this test should be replaced, not
    deleted - its presence is what stops the stub being mistaken for an oversight."""
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", lead_owner=owner, status=statuses["lead"])

    assert lead.share_with_agent(owner.name) is None
