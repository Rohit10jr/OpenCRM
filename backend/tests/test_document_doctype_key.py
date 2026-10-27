"""Every serialised document names its doctype: docs/FINDINGS.md 82.

Upstream's ``as_dict`` puts ``doctype`` on every document and every child row
(``base_document.py:704``), and the frontend leans on it: the SLA list's Duplicate
fetches a policy with ``frappe.client.get`` and posts the whole document back into
``frappe.client.insert`` under a new name. Without the key the insert refused it.
"""

import pytest

from crm_app.models import CRMServiceDay, CRMServiceLevelAgreement
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

GET = "/api/method/frappe.client.get"
INSERT = "/api/method/frappe.client.insert"


@pytest.fixture
def policy(alice):
    with session_user(alice.name):
        sla = CRMServiceLevelAgreement.objects.create(
            sla_name="ZZ Standard", apply_on="CRM Lead", enabled=True, default=True
        )
        CRMServiceDay.objects.create(
            parent_sla=sla, workday="Monday", start_time="09:00", end_time="17:00", idx=1
        )
        CRMServiceDay.objects.create(
            parent_sla=sla, workday="Tuesday", start_time="09:00", end_time="17:00", idx=2
        )
    return sla


@pytest.fixture
def auth_api(api_as, make_user):
    """A Sales Manager's client: the SLA Policies screen is a manager's, and since the
    route-surface review a Sales User may not read a policy at all (upstream's role
    table has no Sales User row; tests/test_route_surface_review.py). These tests are
    about the ``doctype`` key, so they act as the role the screen is for."""
    manager = make_user("sla.manager@example.com", roles=["Sales Manager", "Sales User"])
    return api_as(manager)


def test_a_document_and_its_child_rows_name_their_doctype(auth_api, policy):
    response = auth_api.post(GET, {"doctype": "CRM Service Level Agreement", "name": policy.pk}, format="json")
    assert response.status_code == 200, response.content[:300]
    data = response.json()["message"]
    assert data["doctype"] == "CRM Service Level Agreement"
    assert [row["doctype"] for row in data["working_hours"]] == ["CRM Service Day", "CRM Service Day"]


def test_the_resource_route_names_it_too(auth_api, policy):
    from urllib.parse import quote

    response = auth_api.get("/api/resource/" + quote("CRM Service Level Agreement") + "/" + quote(policy.pk))
    assert response.status_code == 200, response.content[:300]
    assert response.json()["data"]["doctype"] == "CRM Service Level Agreement"


def test_duplicate_posts_the_fetched_document_back_and_gets_a_copy(auth_api, policy):
    """``SlaPolicyList.vue:198-230``, the two calls as the screen makes them."""
    fetched = auth_api.post(
        GET, {"doctype": "CRM Service Level Agreement", "name": policy.pk}, format="json"
    ).json()["message"]

    response = auth_api.post(INSERT, {"doc": {**fetched, "default": False, "sla_name": "ZZ Copy"}}, format="json")
    assert response.status_code == 200, response.content[:300]
    created = response.json()["message"]
    assert created["name"] == "ZZ Copy"
    assert created["doctype"] == "CRM Service Level Agreement"
    assert created["default"] is False

    copy = CRMServiceLevelAgreement.objects.get(pk="ZZ Copy")
    assert list(copy.working_hours.order_by("idx").values_list("workday", flat=True)) == ["Monday", "Tuesday"]
    assert CRMServiceLevelAgreement.objects.get(pk=policy.pk).working_hours.count() == 2
