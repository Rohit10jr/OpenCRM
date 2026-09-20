"""A name the primary key cannot hold is "not found", never a 500: FINDINGS.md 24.

CRM Task is autoincrement, so its names are integers. ``frappe.get_doc("CRM Task",
"abc")`` upstream simply finds nothing; Django's ``filter(pk="abc")`` raised
``ValueError`` before any query ran, and every lookup by name let it through.
"""

import json
from urllib.parse import quote

import pytest

from crm_app.models import CRMOrganization, CRMTask
from frappe_core.query import by_name
from frappe_core.session import session_user
from frappe_platform.models import Contact

pytestmark = pytest.mark.django_db

PLACEHOLDER = "{{old_tasks.response.body.$.data[0].name}}"  # what REST Client sent


def test_by_name_finds_nothing_for_a_name_the_key_cannot_hold(alice):
    with session_user(alice.name):
        task = CRMTask.objects.create(title="ZZ Real", status="Todo", priority="Medium")
        contact = Contact.objects.create(first_name="ZZ", last_name="Jane")
    assert by_name(CRMTask, str(task.pk)).first() == task
    assert by_name(CRMTask, task.pk).first() == task
    assert by_name(CRMTask, "abc").first() is None
    assert by_name(CRMTask, None).first() is None
    assert by_name(Contact, contact.pk).first() == contact, "a string key casts to itself"


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_the_resource_route_answers_404(auth_api, method):
    response = getattr(auth_api, method)(
        "/api/resource/" + quote("CRM Task") + "/" + quote(PLACEHOLDER), {}, format="json"
    )
    assert response.status_code == 404, response.content[:300]
    assert response.json()["exc_type"] == "DoesNotExistError"


def test_the_method_endpoints_answer_404_too(auth_api):
    response = auth_api.post(
        "/api/method/frappe.client.get", {"doctype": "CRM Task", "name": PLACEHOLDER}, format="json"
    )
    assert response.status_code == 404, response.content[:300]
    assert response.json()["exc_type"] == "DoesNotExistError"

    response = auth_api.post(
        "/api/method/crm.api.doc.get_linked_docs_of_document",
        {"doctype": "CRM Task", "docname": PLACEHOLDER},
        format="json",
    )
    assert response.status_code == 404, response.content[:300]


# --- FINDINGS.md 25: a name that already exists ---------------------------------------------


def test_a_duplicate_name_answers_upstreams_sentence(api_as, administrator):
    """base_document.py:598-606 - the unique-key error on insert becomes
    "<DocType> <strong>name</strong> already exists", titled "Duplicate Name"."""
    with session_user(administrator.name):
        CRMOrganization.objects.create(organization_name="ZZ Twice")

    response = api_as(administrator).post(
        "/api/resource/" + quote("CRM Organization"),
        {"organization_name": "ZZ Twice"},
        format="json",
    )

    assert response.status_code == 409, response.content[:300]
    body = response.json()
    assert body["exc_type"] == "DuplicateEntryError"
    assert body["message"] == "CRM Organization <strong>ZZ Twice</strong> already exists"
    assert json.loads(json.loads(body["_server_messages"])[0])["title"] == "Duplicate Name"
    assert CRMOrganization.objects.filter(organization_name="ZZ Twice").count() == 1


def test_a_duplicate_name_through_client_insert_says_the_same(api_as, administrator):
    """frappe.client.insert goes through the same serializer, so the same sentence."""
    with session_user(administrator.name):
        CRMOrganization.objects.create(organization_name="ZZ Again")

    response = api_as(administrator).post(
        "/api/method/frappe.client.insert",
        {"doc": {"doctype": "CRM Organization", "organization_name": "ZZ Again"}},
        format="json",
    )

    assert response.status_code == 409, response.content[:300]
    assert response.json()["message"] == "CRM Organization <strong>ZZ Again</strong> already exists"
