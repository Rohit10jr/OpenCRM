"""A1 - doctypes deliberately withheld from ``/api/resource/``.

The route is generic: one pair of views serves every registered doctype off a registry
lookup. So a doctype cannot be individually "commented out" - the exclusion has to be
data, which is what ``routable=False`` is.

**Why a flag rather than a permission rule.** A rule leaves the route standing and
narrows who may use it; the flag removes the route. For a doctype nothing addresses,
the smaller surface is free. The rule remains the right answer for the doctypes the
frontend genuinely uses - `specs/UNROUTED_DOCTYPES.md` records which is which, and spells
out the rule we would write if `ToDo` ever needs publishing again.

The escalation test below is the one that matters. It is written as the attack, so it
fails loudly if the route ever comes back without a rule.
"""

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from crm_app.models import CRMDeal, CRMDealStatus
from frappe_core import registry
from frappe_core.session import session_user

UNROUTED = ["ToDo", "Version"]


def _client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


# --- the flag itself --------------------------------------------------------------------


def test_the_unrouted_set_is_exactly_what_we_intend():
    """Stated explicitly, so un-routing something is a decision and not a side effect."""
    actual = {dt for dt in registry.all_doctypes() if not registry.get_entry(dt).routable}
    assert actual == set(UNROUTED)


@pytest.mark.django_db
def test_a_version_row_cannot_be_read_over_http(alice, bob, administrator, api_as):
    """A2's regression, closed. A `Version` row carries the old and new values, so the
    audit trail leaked the money on a deal the caller is refused."""
    from crm_app.models import CRMDeal, CRMDealStatus

    with session_user(administrator.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deal = CRMDeal.objects.create(status=status, deal_owner=bob, deal_value=100)
        deal.deal_value = 8888888
        deal.save()

    client = api_as(alice)
    assert client.get(f"/api/resource/CRM Deal/{deal.name}").status_code == 403
    assert client.get("/api/resource/Version").status_code == 404


@pytest.mark.django_db
def test_the_timeline_still_gets_field_changes(bob, administrator, api_as):
    """The legitimate path. `get_activities` checks read on the referenced document and
    then queries `versions_for` over the ORM, so un-routing costs the feature nothing."""
    from crm_app.models import CRMDeal, CRMDealStatus
    from frappe_core.versions import versions_for

    with session_user(administrator.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deal = CRMDeal.objects.create(status=status, deal_owner=bob, deal_value=100)
        deal.deal_value = 8888888
        deal.save()

        assert versions_for("CRM Deal", deal.name), "the audit trail must still be recorded"


def test_registration_still_works_for_an_unrouted_doctype():
    """`routable=False` withholds a route, nothing else. The doctype is still registered,
    still has a model, and every internal caller still resolves it."""
    for doctype in UNROUTED:
        entry = registry.get_entry(doctype)
        assert entry.model.__name__ == doctype
        assert entry.model.get_doctype() == doctype


@pytest.mark.parametrize("doctype", UNROUTED)
def test_an_unrouted_doctype_is_absent_from_routable_doctypes(doctype):
    assert doctype not in registry.routable_doctypes()


# --- the route is gone ------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("doctype", UNROUTED)
def test_every_verb_is_404(auth_api, doctype):
    """404, not 403: the same answer an unknown doctype gets, so a prober learns nothing
    about which doctypes exist."""
    assert auth_api.get(f"/api/resource/{doctype}").status_code == 404
    assert auth_api.post(f"/api/resource/{doctype}", {}, format="json").status_code == 404
    assert auth_api.get(f"/api/resource/{doctype}/x").status_code == 404
    assert auth_api.put(f"/api/resource/{doctype}/x", {}, format="json").status_code == 404
    assert auth_api.delete(f"/api/resource/{doctype}/x").status_code == 404


# --- the attack this closes -------------------------------------------------------------


@pytest.mark.django_db
def test_a_user_cannot_self_assign_their_way_into_an_invisible_deal(alice, bob, administrator):
    """**The reason ToDo is unrouted.**

    Before the flag this ran: 403 on the deal, 201 creating the ToDo, then 200 with the
    deal's value. The permission check was never bypassed - it *passed*, because
    `org_hierarchy` grants access to a record you are assigned to and the caller had just
    written that assignment. Nothing errored, so nothing logged.

    Upstream Frappe CRM has the same hole (UPSTREAM_BUGS_PHASE_3-6.md #16).
    """
    with session_user(administrator.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deal = CRMDeal.objects.create(status=status, deal_owner=bob, deal_value=4242424)

    client = _client(alice)
    assert client.get(f"/api/resource/CRM Deal/{deal.name}").status_code == 403

    grab = client.post(
        "/api/resource/ToDo",
        {
            "allocated_to": alice.name,
            "reference_type": "CRM Deal",
            "reference_name": deal.name,
            "status": "Open",
            "description": "mine now",
        },
        format="json",
    )
    assert grab.status_code == 404, "the ToDo route is back - it needs a permission rule"

    # Still invisible, by both routes.
    assert client.get(f"/api/resource/CRM Deal/{deal.name}").status_code == 403
    assert client.get("/api/resource/CRM Deal").json()["data"] == []


# --- the legitimate path is untouched ---------------------------------------------------


@pytest.mark.django_db
def test_assignment_still_works_through_the_gated_endpoint(alice, bob, administrator):
    """The point of un-routing rather than deleting: assignment is a real feature, and it
    goes through an endpoint that checks write permission on the document first."""
    from frappe_core.assignment import assign_to_user, get_assigned_users

    with session_user(administrator.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deal = CRMDeal.objects.create(status=status, deal_owner=bob, deal_value=100)
        assign_to_user("CRM Deal", deal.name, alice.name)

    assert alice.name in get_assigned_users("CRM Deal", deal.name)
    # And the assignment does what assignments are for.
    assert _client(alice).get(f"/api/resource/CRM Deal/{deal.name}").status_code == 200
