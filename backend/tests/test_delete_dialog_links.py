"""What the delete dialog lists as "linked documents": docs/FINDINGS.md 75.

``get_linked_docs_of_document`` feeds the dialog on a record's page, and the same scan
runs inside ``delete_bulk_docs``. Upstream's list (``frappe/model/delete_doc.py``,
``get_linked_docs`` and ``get_dynamic_linked_docs``) leaves out two things the port
listed: a document's own child rows, which are not links at all, and the doctypes the
framework's ``ignore_links_on_delete`` hook names, which go with the document. For a
child table's real links upstream lists the parent document, not the row.
"""

import pytest

from crm_app.integrations.call_log import link_with_reference_doc
from crm_app.models import (
    CRMCallLog,
    CRMContacts,
    CRMDeal,
    CRMDealStatus,
    CRMLead,
    CRMLeadStatus,
    CRMTask,
)
from frappe_core.session import session_user
from frappe_platform.models import Comment, Contact, DynamicLink

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


# docs/FINDINGS.md 93: a call log tied to the record only through its ``links`` rows
# (Create Lead from a call log, the telephony handlers) is listed as the call log, as
# ``get_dynamic_linked_docs`` reports a child row as its parent (delete_doc.py:394-420).
# Unlink All does nothing for it: upstream bug 63, reproduced.


@pytest.fixture
def lead(alice):
    """A lead alice owns and made herself, so no assignment notification points at it."""
    with session_user(alice.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        return CRMLead.objects.create(first_name="ZZ Caller", lead_owner=alice, status=status)


def _call_log(alice, log_id, **reference):
    with session_user(alice.name):
        return CRMCallLog.objects.create(
            id=log_id, status="Completed", type="Incoming", caller=alice,
            **{"from": "4543234232", "to": "654323456"}, **reference,
        )


def _linked_through_links_row(alice, doctype, name, log_id="CA-f93-links"):
    """What ``CRM Call Log.link_with_reference_doc`` leaves: a ``links`` row and no
    ``reference_docname``."""
    log = _call_log(alice, log_id)
    with session_user(alice.name):
        link_with_reference_doc(log, doctype, name)
    return log


def _items(client, doctype, name):
    return [{"doctype": d, "docname": n} for d, n in linked(client, doctype, name)]


def test_a_call_log_linked_through_its_links_rows_is_listed_as_the_call_log(api_as, administrator, alice, lead):
    log = _linked_through_links_row(alice, "CRM Lead", lead.pk)
    response = api_as(administrator).post(LINKED, {"doctype": "CRM Lead", "docname": lead.pk}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"] == [
        {
            "doc": "CRM Call Log",
            "title": "Call from 4543234232 to 654323456",
            "reference_docname": log.pk,
            "reference_doctype": "CRM Call Log",
        }
    ]


def test_a_deals_dialog_lists_a_call_log_linked_through_its_links_rows(api_as, administrator, alice):
    with session_user(alice.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deal = CRMDeal.objects.create(status=status, deal_owner=alice)
    log = _linked_through_links_row(alice, "CRM Deal", deal.pk)
    assert linked(api_as(administrator), "CRM Deal", deal.pk) == [("CRM Call Log", log.pk)]


def test_a_call_log_with_both_kinds_of_link_is_listed_once(api_as, administrator, alice, lead):
    """``crm/api/doc.py:688`` deduplicates by ``reference_docname``."""
    log = _call_log(alice, "CA-f93-both", reference_doctype="CRM Lead", reference_docname=lead.pk)
    with session_user(alice.name):
        link_with_reference_doc(log, "CRM Lead", lead.pk)
    assert linked(api_as(administrator), "CRM Lead", lead.pk) == [("CRM Call Log", log.pk)]


def test_unlink_all_leaves_a_links_row_call_log_listed_and_the_delete_refused(api_as, administrator, alice, lead):
    """Upstream bug 63, reproduced: ``remove_doc_link`` blanks only the reference pair,
    which was already empty, and says nothing."""
    log = _linked_through_links_row(alice, "CRM Lead", lead.pk)
    client = api_as(administrator)
    response = client.post(
        UNLINK, {"items": _items(client, "CRM Lead", lead.pk), "remove_contact": False, "delete": False}, format="json"
    )
    assert response.status_code == 200 and response.json()["message"] == "success"
    assert linked(client, "CRM Lead", lead.pk) == [("CRM Call Log", log.pk)]
    assert DynamicLink.objects.filter(parenttype="CRM Call Log", parent=log.pk, link_name=lead.pk).exists()

    response = client.post(DELETE, {"doctype": "CRM Lead", "name": lead.pk}, format="json")
    assert response.status_code == 417, response.content[:300]
    assert response.json()["exc_type"] == "LinkExistsError"
    assert response.json()["message"] == (
        f"Cannot delete or cancel because CRM Lead {lead.pk} is linked with CRM Call Log {log.pk} at Row: 1"
    )
    assert CRMLead.objects.filter(pk=lead.pk).exists()


def test_delete_all_deletes_a_links_row_call_log_and_the_lead_then_deletes(api_as, administrator, alice, lead):
    log = _linked_through_links_row(alice, "CRM Lead", lead.pk)
    client = api_as(administrator)
    response = client.post(
        UNLINK, {"items": _items(client, "CRM Lead", lead.pk), "remove_contact": False, "delete": True}, format="json"
    )
    assert response.status_code == 200
    assert not CRMCallLog.objects.filter(pk=log.pk).exists()
    assert not DynamicLink.objects.filter(parenttype="CRM Call Log", parent=log.pk).exists()
    assert linked(client, "CRM Lead", lead.pk) == []

    response = client.post(DELETE, {"doctype": "CRM Lead", "name": lead.pk}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert not CRMLead.objects.filter(pk=lead.pk).exists()


def test_a_logged_call_unlinks_cleanly_and_the_lead_deletes(api_as, administrator, alice, lead):
    """Log a Call fills ``reference_docname`` (``AllModals.vue:98-106``): Unlink All works."""
    log = _call_log(alice, "CA-f93-logged", reference_doctype="CRM Lead", reference_docname=lead.pk)
    client = api_as(administrator)
    assert linked(client, "CRM Lead", lead.pk) == [("CRM Call Log", log.pk)]
    response = client.post(
        UNLINK, {"items": _items(client, "CRM Lead", lead.pk), "remove_contact": False, "delete": False}, format="json"
    )
    assert response.status_code == 200
    assert linked(client, "CRM Lead", lead.pk) == []

    response = client.post(DELETE, {"doctype": "CRM Lead", "name": lead.pk}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert CRMCallLog.objects.get(pk=log.pk).reference_docname == ""


def test_bulk_delete_with_linked_docs_deletes_a_links_row_call_log(api_as, administrator, alice, lead):
    """Upstream's ``delete_bulk_docs`` clears each document's dialog list
    (``crm/api/doc.py:815-829``), so the call log goes with ``delete_linked``."""
    log = _linked_through_links_row(alice, "CRM Lead", lead.pk)
    response = api_as(administrator).post(
        BULK, {"doctype": "CRM Lead", "items": [lead.pk], "delete_linked": True}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
    assert not CRMLead.objects.filter(pk=lead.pk).exists()
    assert not CRMCallLog.objects.filter(pk=log.pk).exists()
