"""The delete dialog's "Unlink": docs/FINDINGS.md 56, upstream bug 42.

Upstream's ``remove_linked_doc_reference`` blanks only the generic reference pair
(``crm/api/doc.py:721-749``). The port deliberately also clears direct Link fields when
the dialog identifies the document being deleted, while preserving the old call shape.
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


def test_unlink_clears_a_deals_organization_and_frees_the_organization(
    api_as, administrator, alice
):
    with session_user(administrator.name):
        organization = CRMOrganization.objects.create(organization_name="ZZ Linked Org")
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deal = CRMDeal.objects.create(status=status, deal_owner=alice, organization=organization)
    client = api_as(administrator)

    response = client.post(
        UNLINK,
        {
            "items": [{"doctype": "CRM Deal", "docname": deal.name}],
            "doctype": "CRM Organization",
            "docname": organization.pk,
        },
        format="json",
    )
    assert response.status_code == 200 and response.json()["message"] == "success"
    deal.refresh_from_db()
    assert deal.organization_id is None

    linked = client.post(
        LINKED, {"doctype": "CRM Organization", "docname": organization.pk}, format="json"
    ).json()["message"]
    assert linked == []

    deleted = client.post(
        "/api/method/frappe.client.delete",
        {"doctype": "CRM Organization", "name": organization.pk},
        format="json",
    )
    assert deleted.status_code == 200


def test_unlink_clears_a_converted_leads_deal_link(api_as, administrator, alice):
    from crm_app.models import CRMLeadStatus

    with session_user(administrator.name):
        lead_status = CRMLeadStatus.objects.create(lead_status="Qualified", type="Open")
        lead = CRMLead.objects.create(
            first_name="ZZ Converted", lead_owner=alice, status=lead_status, converted=True
        )
        deal_status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deal = CRMDeal.objects.create(status=deal_status, deal_owner=alice, lead=lead)

    response = api_as(administrator).post(
        UNLINK,
        {
            "items": [{"doctype": "CRM Deal", "docname": deal.name}],
            "doctype": "CRM Lead",
            "docname": lead.pk,
        },
        format="json",
    )
    assert response.status_code == 200 and response.json()["message"] == "success"
    deal.refresh_from_db()
    assert deal.lead_id is None


def test_unlink_without_the_deleted_document_keeps_the_link(api_as, administrator, alice):
    with session_user(administrator.name):
        organization = CRMOrganization.objects.create(organization_name="ZZ Legacy Org")
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deal = CRMDeal.objects.create(status=status, deal_owner=alice, organization=organization)

    response = api_as(administrator).post(
        UNLINK, {"items": [{"doctype": "CRM Deal", "docname": deal.name}]}, format="json"
    )
    assert response.status_code == 200 and response.json()["message"] == "success"
    deal.refresh_from_db()
    assert deal.organization_id == organization.pk


def test_unlink_does_not_clear_a_deal_the_user_cannot_write(
    api_as, administrator, alice, bob
):
    with session_user(administrator.name):
        organization = CRMOrganization.objects.create(organization_name="ZZ Protected Org")
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deal = CRMDeal.objects.create(status=status, deal_owner=alice, organization=organization)

    response = api_as(bob).post(
        UNLINK,
        {
            "items": [{"doctype": "CRM Deal", "docname": deal.name}],
            "doctype": "CRM Organization",
            "docname": organization.pk,
        },
        format="json",
    )
    assert response.status_code == 200 and response.json()["message"] == "success"
    deal.refresh_from_db()
    assert deal.organization_id == organization.pk


def test_bulk_unlink_clears_the_deals_organization_before_deleting_it(
    api_as, administrator, alice
):
    with session_user(administrator.name):
        organization = CRMOrganization.objects.create(organization_name="ZZ Bulk Org")
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deal = CRMDeal.objects.create(status=status, deal_owner=alice, organization=organization)

    response = api_as(administrator).post(
        "/api/method/crm.api.doc.delete_bulk_docs",
        {"doctype": "CRM Organization", "items": [organization.pk], "delete_linked": False},
        format="json",
    )
    assert response.status_code == 200 and response.json()["message"] == "success"
    assert not CRMOrganization.objects.filter(pk=organization.pk).exists()
    deal.refresh_from_db()
    assert deal.organization_id is None


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
