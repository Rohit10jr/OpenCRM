"""Deleting a document takes its dependants with it: FINDINGS.md 19.

``frappe/model/delete_doc.py`` removes the ToDo, Version and Comment rows keyed to the
document (``delete_dynamic_links``), clears a Communication's reference rather than
deleting the email (``clear_references``), and removes its attachments (``remove_all``).
The port left every one of them pointing at a name that no longer existed.
"""

from urllib.parse import quote

import pytest

from crm_app.models import CRMLead, CRMLeadStatus, CRMNotification
from frappe_core.session import session_user
from frappe_core.versions import Version
from frappe_platform.models import Comment, Communication, File, ToDo

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_api(api_as, administrator):
    return api_as(administrator)


@pytest.fixture
def lead_with_dependants(alice, bob):
    with session_user(alice.name):
        CRMLeadStatus.objects.create(lead_status="New", type="Open")
        lead = CRMLead.objects.create(first_name="ZZ Doomed", lead_owner=alice)
        name = lead.name
        Comment.objects.create(
            comment_type="Comment", content="bye", reference_doctype="CRM Lead", reference_name=name
        )
        ToDo.objects.create(
            allocated_to=bob, description="call", reference_type="CRM Lead", reference_name=name
        )
        Version.objects.create(ref_doctype="CRM Lead", docname=name, data="{}")
        File.objects.create(
            file_name="brief.pdf", file_url="/private/files/brief.pdf", is_private=True,
            attached_to_doctype="CRM Lead", attached_to_name=name,
        )
        Communication.objects.create(
            subject="Re: ZZ", content="mail", reference_doctype="CRM Lead", reference_name=name
        )
        # A different document's rows must survive.
        other = CRMLead.objects.create(first_name="ZZ Survivor", lead_owner=alice)
        Comment.objects.create(
            comment_type="Comment", content="stay", reference_doctype="CRM Lead", reference_name=other.name
        )
    return lead, other


def test_deleting_a_lead_removes_its_references(admin_api, lead_with_dependants):
    lead, other = lead_with_dependants
    name = lead.name

    response = admin_api.delete("/api/resource/" + quote("CRM Lead") + "/" + quote(name))
    assert response.status_code == 200, response.content[:300]

    assert not Comment.objects.filter(reference_doctype="CRM Lead", reference_name=name).exists()
    assert not ToDo.objects.filter(reference_type="CRM Lead", reference_name=name).exists()
    assert not Version.objects.filter(ref_doctype="CRM Lead", docname=name).exists()
    assert not File.objects.filter(attached_to_doctype="CRM Lead", attached_to_name=name).exists()
    # The email is kept, unlinked (delete_doc.py:471 clear_references).
    mail = Communication.objects.get(subject="Re: ZZ")
    assert mail.reference_doctype == "" and mail.reference_name == ""
    assert Comment.objects.filter(reference_name=other.name).count() == 1


def test_the_orm_delete_path_cleans_up_too(alice, lead_with_dependants):
    lead, other = lead_with_dependants
    name = lead.name
    with session_user(alice.name):
        lead.delete()
    assert not Comment.objects.filter(reference_name=name).exists()
    assert not ToDo.objects.filter(reference_name=name).exists()


def test_notifications_are_left_alone_as_upstream_leaves_them(admin_api, lead_with_dependants, bob):
    """Upstream registers no delete hook for CRM Notification, so the bell keeps the row;
    only what delete_dynamic_links names goes."""
    lead, other = lead_with_dependants
    before = CRMNotification.objects.filter(to_user=bob).count()
    admin_api.delete("/api/resource/" + quote("CRM Lead") + "/" + quote(lead.name))
    assert CRMNotification.objects.filter(to_user=bob).count() == before
