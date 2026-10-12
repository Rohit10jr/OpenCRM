"""What the delete dialog lists as "linked documents": docs/FINDINGS.md 75.

``get_linked_docs_of_document`` feeds the dialog on a record's page, and the same scan
runs inside ``delete_bulk_docs``. Upstream's list (``frappe/model/delete_doc.py``,
``get_linked_docs`` and ``get_dynamic_linked_docs``) leaves out two things the port
listed: a document's own child rows, which are not links at all, and the doctypes the
framework's ``ignore_links_on_delete`` hook names, which go with the document. For a
child table's real links upstream lists the parent document, not the row.
"""

import pytest

from crm_app.models import CRMContacts, CRMDeal, CRMDealStatus, CRMTask
from frappe_core.session import session_user
from frappe_platform.models import Comment, Contact

pytestmark = pytest.mark.django_db

LINKED = "/api/method/crm.api.doc.get_linked_docs_of_document"
UNLINK = "/api/method/crm.api.doc.remove_linked_doc_reference"
DELETE = "/api/method/frappe.client.delete"
BULK = "/api/method/crm.api.doc.delete_bulk_docs"


@pytest.fixture
def deal(administrator, alice):
    """A deal as the dialog makes it: one contact row, one comment, one task."""
    with session_user(administrator.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        contact = Contact.objects.create(first_name="ZZ Dialog")
        deal = CRMDeal.objects.create(status=status, deal_owner=alice)
        CRMContacts.objects.create(parent_deal=deal, contact=contact, is_primary=True)
        Comment.objects.create(
            comment_type="Comment", reference_doctype="CRM Deal", reference_name=deal.pk, content="hi"
        )
        CRMTask.objects.create(title="ZZ follow up", reference_doctype="CRM Deal", reference_docname=deal.pk)
    return deal


def linked(client, doctype, name):
    response = client.post(LINKED, {"doctype": doctype, "docname": name}, format="json")
    assert response.status_code == 200, response.content[:300]
    return [(row["reference_doctype"], row["reference_docname"]) for row in response.json()["message"]]


def test_a_deals_own_contact_row_and_its_comments_are_not_linked_documents(api_as, administrator, deal):
    task = CRMTask.objects.get(reference_docname=deal.pk)
    rows = linked(api_as(administrator), "CRM Deal", deal.pk)
    assert ("CRM Task", str(task.pk)) in rows
    # The task's creation may notify the deal's owner; a CRM Notification is a linked
    # document upstream lists too. What must be absent is the deal's own row and its
    # comment.
    assert {doctype for doctype, _ in rows} <= {"CRM Task", "CRM Notification"}


def test_unlink_all_then_delete_works_and_the_comment_goes_with_the_deal(api_as, administrator, deal):
    """The page dialog's Unlink path: before the fix the contact row stayed listed, so
    the Delete button never showed; and an unlinked comment was left orphaned."""
    client = api_as(administrator)
    items = [{"doctype": d, "docname": n} for d, n in linked(client, "CRM Deal", deal.pk)]
    response = client.post(UNLINK, {"items": items, "remove_contact": False, "delete": False}, format="json")
    assert response.status_code == 200 and response.json()["message"] == "success"
    assert linked(client, "CRM Deal", deal.pk) == []

    response = client.post(DELETE, {"doctype": "CRM Deal", "name": deal.pk}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert not CRMDeal.objects.filter(pk=deal.pk).exists()
    assert not Comment.objects.filter(reference_doctype="CRM Deal", reference_name=deal.pk).exists()
    assert not Comment.objects.filter(reference_name="", content="hi").exists()
    assert CRMTask.objects.get(title="ZZ follow up").reference_docname == ""


def test_bulk_delete_deletes_the_comments_instead_of_orphaning_them(api_as, administrator, deal):
    client = api_as(administrator)
    response = client.post(BULK, {"doctype": "CRM Deal", "items": [deal.pk], "delete_linked": False}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert not CRMDeal.objects.filter(pk=deal.pk).exists()
    assert not Comment.objects.filter(content="hi").exists()
    assert CRMTask.objects.get(title="ZZ follow up").reference_docname == ""


def test_a_contacts_dialog_lists_the_deal_it_is_on_and_unlink_takes_it_off(api_as, administrator, deal):
    """``delete_doc.py:352-384``: a link from a child row is reported as its parent.
    ``remove_contact`` then clears the deal's contact rows (``crm/api/doc.py:752-766``)."""
    client = api_as(administrator)
    contact = Contact.objects.get(first_name="ZZ Dialog")
    assert linked(client, "Contact", contact.pk) == [("CRM Deal", deal.pk)]

    response = client.post(
        UNLINK,
        {"items": [{"doctype": "CRM Deal", "docname": deal.pk}], "remove_contact": True, "delete": False},
        format="json",
    )
    assert response.status_code == 200
    assert deal.contacts.count() == 0
    assert linked(client, "Contact", contact.pk) == []
