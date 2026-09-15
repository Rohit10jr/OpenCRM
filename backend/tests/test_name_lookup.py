"""A name the primary key cannot hold is "not found", never a 500: FINDINGS.md 24.

CRM Task is autoincrement, so its names are integers. ``frappe.get_doc("CRM Task",
"abc")`` upstream simply finds nothing; Django's ``filter(pk="abc")`` raised
``ValueError`` before any query ran, and every lookup by name let it through.
"""

from urllib.parse import quote

import pytest

from crm_app.models import CRMTask
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
