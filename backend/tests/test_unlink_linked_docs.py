"""The delete dialog's "Unlink": docs/FINDINGS.md 56, upstream bug 42.

``remove_linked_doc_reference`` blanks the generic reference pair
(``crm/api/doc.py:721-749``). That is the whole of it upstream, so a document that
points at the record through a Link field - a deal's ``organization`` - is not unlinked
at all. Both halves are pinned here: the case it was written for, and the one it misses.
"""

import pytest

from crm_app.models import CRMDeal, CRMDealStatus, CRMLead, CRMOrganization, CRMTask
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

UNLINK = "/api/method/crm.api.doc.remove_linked_doc_reference"
LINKED = "/api/method/crm.api.doc.get_linked_docs_of_document"


def test_unlink_clears_the_reference_pair_of_a_task(api_as, administrator, alice):
    """What it was written for: a lead's tasks, notes and calls."""
    from crm_app.models import CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        lead = CRMLead.objects.create(first_name="ZZ Unlink", lead_owner=alice, status=status)
        task = CRMTask.objects.create(
            title="ZZ follow up", reference_doctype="CRM Lead", reference_docname=lead.name
        )
    client = api_as(administrator)
    response = client.post(
        UNLINK, {"items": [{"doctype": "CRM Task", "docname": task.pk}]}, format="json"
    )
    assert response.status_code == 200 and response.json()["message"] == "success"
    task.refresh_from_db()
    assert (task.reference_doctype, task.reference_docname) == ("", "")


def test_unlink_leaves_a_deal_on_its_organization_as_upstream_does(api_as, administrator, alice):
    """Upstream bug 42: a deal has no reference pair, so nothing is cleared, the deal is
    still listed as linked, and the organization still cannot be deleted."""
    with session_user(administrator.name):
        organization = CRMOrganization.objects.create(organization_name="ZZ Linked Org")
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deal = CRMDeal.objects.create(status=status, deal_owner=alice, organization=organization)
    client = api_as(administrator)

    response = client.post(
        UNLINK, {"items": [{"doctype": "CRM Deal", "docname": deal.name}]}, format="json"
    )
    assert response.status_code == 200 and response.json()["message"] == "success"
    deal.refresh_from_db()
    assert deal.organization_id == organization.pk

    linked = client.post(
        LINKED, {"doctype": "CRM Organization", "docname": organization.pk}, format="json"
    ).json()["message"]
    assert [row["reference_docname"] for row in linked] == [deal.name]

    refused = client.post(
        "/api/method/frappe.client.delete",
        {"doctype": "CRM Organization", "name": organization.pk},
        format="json",
    )
    assert refused.status_code == 417
    assert "is linked with CRM Deal" in refused.json()["exception"]


def test_delete_in_the_dialog_removes_the_deal_and_frees_the_organization(api_as, administrator, alice):
    with session_user(administrator.name):
        organization = CRMOrganization.objects.create(organization_name="ZZ Freed Org")
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deal = CRMDeal.objects.create(status=status, deal_owner=alice, organization=organization)
    client = api_as(administrator)

    client.post(
        UNLINK,
        {"items": [{"doctype": "CRM Deal", "docname": deal.name}], "delete": True},
        format="json",
    )
    assert not CRMDeal.objects.filter(pk=deal.pk).exists()
    deleted = client.post(
        "/api/method/frappe.client.delete",
        {"doctype": "CRM Organization", "name": organization.pk},
        format="json",
    )
    assert deleted.status_code == 200
