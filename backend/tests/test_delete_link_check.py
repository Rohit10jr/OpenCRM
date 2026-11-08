"""A delete is refused while other documents still reference the record: FINDINGS.md 76.

Upstream's ``frappe.delete_doc`` runs ``check_if_doc_is_linked`` and
``check_if_doc_is_dynamically_linked`` (``frappe/model/delete_doc.py:141-153``, version-15)
and refuses with ``LinkExistsError`` while a task, note, call log or notification still
names the record through a Dynamic Link field. The port refused only for a foreign key.
The check reads without user permissions, as upstream's does, so a reference the caller
cannot see still blocks the delete; the message names the referencing document and no
more, as upstream's does.
"""

from urllib.parse import quote

import pytest

from crm_app.integrations.call_log import link_with_reference_doc
from crm_app.models import (
    CRMCallLog,
    CRMDeal,
    CRMDealStatus,
    CRMNotification,
    CRMTask,
    FCRMNote,
    WhatsAppMessage,
)
from frappe_core.session import session_user
from frappe_platform.models import Comment

pytestmark = pytest.mark.django_db

LINKED = "/api/method/crm.api.doc.get_linked_docs_of_document"
UNLINK = "/api/method/crm.api.doc.remove_linked_doc_reference"
DELETE = "/api/method/frappe.client.delete"
BULK = "/api/method/crm.api.doc.delete_bulk_docs"


@pytest.fixture
def deal(alice):
    """A deal alice owns and made herself, so no assignment notification points at it."""
    with session_user(alice.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        return CRMDeal.objects.create(status=status, deal_owner=alice)


def _refusal(response, message):
    assert response.status_code == 417, response.content[:300]
    body = response.json()
    assert body["exc_type"] == "LinkExistsError"
    assert body["message"] == message


def _delete_resource(client, doctype, name):
    return client.delete("/api/resource/" + quote(doctype) + "/" + quote(str(name)))


def _make_referrer(kind, deal, alice):
    with session_user(alice.name):
        if kind == "CRM Task":
            return CRMTask.objects.create(
                title="ZZ follow up", reference_doctype="CRM Deal", reference_docname=deal.pk
            )
        if kind == "FCRM Note":
            return FCRMNote.objects.create(
                title="ZZ note", content="<p>n</p>", reference_doctype="CRM Deal", reference_docname=deal.pk
            )
        return CRMCallLog.objects.create(
            id="CA-link-check-1", status="Completed", type="Outgoing", caller=alice,
            reference_doctype="CRM Deal", reference_docname=deal.pk,
            **{"from": "+1 111", "to": "+1 222"},
        )


@pytest.mark.parametrize("kind", ["CRM Task", "FCRM Note", "CRM Call Log"])
def test_client_delete_is_refused_while_a_reference_remains(api_as, administrator, alice, deal, kind):
    referrer = _make_referrer(kind, deal, alice)
    response = api_as(administrator).post(DELETE, {"doctype": "CRM Deal", "name": deal.pk}, format="json")
    _refusal(response, f"Cannot delete or cancel because CRM Deal {deal.pk} is linked with {kind} {referrer.pk}")
    assert CRMDeal.objects.filter(pk=deal.pk).exists()


@pytest.mark.parametrize("kind", ["CRM Task", "FCRM Note", "CRM Call Log"])
def test_resource_delete_is_refused_while_a_reference_remains(api_as, administrator, alice, deal, kind):
    referrer = _make_referrer(kind, deal, alice)
    response = _delete_resource(api_as(administrator), "CRM Deal", deal.pk)
    _refusal(response, f"Cannot delete or cancel because CRM Deal {deal.pk} is linked with {kind} {referrer.pk}")
    assert CRMDeal.objects.filter(pk=deal.pk).exists()


def _whatsapp_message(deal, alice):
    with session_user(alice.name):
        return WhatsAppMessage.objects.create(
            type="Outgoing", message="hi", reference_doctype="CRM Deal", reference_name=deal.pk,
            **{"to": "+1 222"},
        )


def test_a_whatsapp_message_blocks_the_delete(api_as, administrator, alice, deal):
    message = _whatsapp_message(deal, alice)
    response = api_as(administrator).post(DELETE, {"doctype": "CRM Deal", "name": deal.pk}, format="json")
    _refusal(response, f"Cannot delete or cancel because CRM Deal {deal.pk} is linked with WhatsApp Message {message.pk}")
    assert CRMDeal.objects.filter(pk=deal.pk).exists()


def test_the_dialogs_unlink_clears_a_whatsapp_message_so_the_delete_works(api_as, alice, deal):
    message = _whatsapp_message(deal, alice)
    client = api_as(alice)
    response = client.post(LINKED, {"doctype": "CRM Deal", "docname": deal.pk}, format="json")
    items = [
        {"doctype": row["reference_doctype"], "docname": row["reference_docname"]}
        for row in response.json()["message"]
    ]
    assert items == [{"doctype": "WhatsApp Message", "docname": str(message.pk)}]
    response = client.post(UNLINK, {"items": items, "remove_contact": False, "delete": False}, format="json")
    assert response.status_code == 200

    response = client.post(DELETE, {"doctype": "CRM Deal", "name": deal.pk}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert WhatsAppMessage.objects.get(pk=message.pk).reference_name == ""


def test_a_reference_in_a_child_table_names_the_parent_and_the_row(api_as, administrator, alice, deal):
    """``delete_doc.py:410-419``: a Dynamic Link in a child table is reported as its parent
    document, ``at Row: <idx>``. A call log's ``links`` rows are such a table."""
    with session_user(alice.name):
        log = CRMCallLog.objects.create(
            id="CA-link-check-2", status="Completed", type="Outgoing", caller=alice,
            **{"from": "+1 111", "to": "+1 222"},
        )
        link_with_reference_doc(log, "CRM Deal", deal.pk)
    response = api_as(administrator).post(DELETE, {"doctype": "CRM Deal", "name": deal.pk}, format="json")
    _refusal(
        response,
        f"Cannot delete or cancel because CRM Deal {deal.pk} is linked with CRM Call Log {log.pk} at Row: 1",
    )


def test_a_reference_the_caller_cannot_see_still_blocks_the_delete(api_as, alice, bob, deal):
    """The case the dialog cannot catch: alice's list is permission-filtered, so a
    notification addressed to bob does not appear, Unlink All leaves it, and the delete
    must still refuse. The message names it as upstream's would, and no more."""
    with session_user(bob.name):
        hidden = CRMNotification.objects.create(
            type="Mention", from_user=bob, to_user=bob, message="private",
            reference_doctype="CRM Deal", reference_name=deal.pk,
        )
    client = api_as(alice)
    response = client.post(LINKED, {"doctype": "CRM Deal", "docname": deal.pk}, format="json")
    assert response.json()["message"] == []

    response = client.post(DELETE, {"doctype": "CRM Deal", "name": deal.pk}, format="json")
    _refusal(response, f"Cannot delete or cancel because CRM Deal {deal.pk} is linked with CRM Notification {hidden.pk}")
    assert "private" not in response.content.decode()
    assert CRMDeal.objects.filter(pk=deal.pk).exists()

    response = client.post(BULK, {"doctype": "CRM Deal", "items": [deal.pk], "delete_linked": True}, format="json")
    _refusal(response, f"Cannot delete or cancel because CRM Deal {deal.pk} is linked with CRM Notification {hidden.pk}")
    assert CRMDeal.objects.filter(pk=deal.pk).exists()


def test_comments_do_not_block_and_go_with_the_deal(api_as, administrator, alice, deal):
    """Comment is in ``ignore_links_on_delete``; ``delete_dynamic_links`` removes it."""
    with session_user(alice.name):
        Comment.objects.create(
            comment_type="Comment", reference_doctype="CRM Deal", reference_name=deal.pk, content="hi"
        )
    response = api_as(administrator).post(DELETE, {"doctype": "CRM Deal", "name": deal.pk}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert not CRMDeal.objects.filter(pk=deal.pk).exists()
    assert not Comment.objects.filter(content="hi").exists()


def test_the_dialogs_unlink_then_delete_still_works(api_as, alice, deal):
    task = _make_referrer("CRM Task", deal, alice)
    client = api_as(alice)
    response = client.post(LINKED, {"doctype": "CRM Deal", "docname": deal.pk}, format="json")
    items = [
        {"doctype": row["reference_doctype"], "docname": row["reference_docname"]}
        for row in response.json()["message"]
    ]
    assert items == [{"doctype": "CRM Task", "docname": str(task.pk)}]
    response = client.post(UNLINK, {"items": items, "remove_contact": False, "delete": False}, format="json")
    assert response.status_code == 200

    response = client.post(DELETE, {"doctype": "CRM Deal", "name": deal.pk}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert not CRMDeal.objects.filter(pk=deal.pk).exists()
    assert CRMTask.objects.get(pk=task.pk).reference_docname == ""


def test_the_dialogs_delete_all_then_delete_still_works(api_as, alice, deal):
    task = _make_referrer("CRM Task", deal, alice)
    items = [{"doctype": "CRM Task", "docname": str(task.pk)}]
    client = api_as(alice)
    response = client.post(UNLINK, {"items": items, "remove_contact": False, "delete": True}, format="json")
    assert response.status_code == 200
    assert not CRMTask.objects.filter(pk=task.pk).exists()

    response = client.post(DELETE, {"doctype": "CRM Deal", "name": deal.pk}, format="json")
    assert response.status_code == 200, response.content[:300]


def test_bulk_delete_clears_the_references_it_can_see_and_deletes(api_as, alice, deal):
    task = _make_referrer("CRM Task", deal, alice)
    response = api_as(alice).post(
        BULK, {"doctype": "CRM Deal", "items": [deal.pk], "delete_linked": True}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
    assert not CRMDeal.objects.filter(pk=deal.pk).exists()
    assert not CRMTask.objects.filter(pk=task.pk).exists()


def test_deleting_a_linked_document_that_is_itself_referenced_is_skipped(api_as, alice, bob, deal):
    """``remove_linked_doc_reference`` deletes each item with ``frappe.delete_doc`` and
    skips the one that raises (``crm/api/doc.py:780-790``): a task a notification points
    at stays, unlinked."""
    task = _make_referrer("CRM Task", deal, alice)
    with session_user(bob.name):
        CRMNotification.objects.create(
            type="Assignment", from_user=bob, to_user=alice, message="assigned",
            notification_type_doctype="CRM Task", notification_type_doc=task.pk,
        )
    items = [{"doctype": "CRM Task", "docname": str(task.pk)}]
    response = api_as(alice).post(UNLINK, {"items": items, "remove_contact": False, "delete": True}, format="json")
    assert response.status_code == 200 and response.json()["message"] == "success"
    assert CRMTask.objects.get(pk=task.pk).reference_docname == ""
