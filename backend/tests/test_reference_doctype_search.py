"""``search_link`` on ``DocType``: docs/FINDINGS.md 54.

The Reference Document Type field of a note, task or call log is a Link to ``DocType``;
the Reference Doc beside it is a Dynamic Link that searches whatever the first one
names. Shapes follow ``frappe/desk/search.py:search_widget`` for ``doctype == "DocType"``.
"""

import pytest

from crm_app.models import CRMLead, FCRMNote
from frappe_core import registry
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

PATH = "/api/method/frappe.desk.search.search_link"


def search(client, doctype="DocType", **params):
    response = client.post(PATH, {"doctype": doctype, "txt": "", **params}, format="json")
    assert response.status_code == 200, response.content[:300]
    return [row["value"] for row in response.json()["message"]]


def test_a_sales_user_can_pick_a_reference_doctype(auth_api):
    """Upstream runs the DocType search with ``ignore_permissions``; alice, a Sales User
    with no DocType permission, must get the list."""
    values = search(auth_api, txt="CRM Le")
    assert "CRM Lead" in values
    assert all(registry.has_doctype(value) for value in values)


def test_names_that_start_with_the_text_come_first(auth_api):
    values = search(auth_api, txt="crm", page_length=200)
    assert values.index("CRM Lead") < values.index("ERPNext CRM Settings")
    assert values == sorted(values, key=lambda n: (n.lower().find("crm"), n.lower()))


def test_ten_at_a_time_unless_asked_otherwise(auth_api):
    assert len(search(auth_api)) == 10
    assert len(search(auth_api, page_length=3)) == 3


def test_a_condition_on_name_in_the_links_filters_is_honoured(auth_api):
    wanted = ["CRM Lead", "CRM Deal"]
    assert search(auth_api, filters={"name": ["in", wanted]}) == sorted(wanted)
    assert search(auth_api, filters=[["DocType", "name", "in", wanted]]) == sorted(wanted)
    assert search(auth_api, filters={"name": "CRM Task"}) == ["CRM Task"]


def test_a_doctype_the_port_does_not_have_is_still_a_404(auth_api):
    response = auth_api.post(PATH, {"doctype": "Nonsense", "txt": ""}, format="json")
    assert response.status_code == 404


def test_the_reference_pair_can_be_picked_and_saved(auth_api, api_as, alice, administrator):
    """The dialog's two steps: pick ``CRM Lead``, then a lead through the Dynamic Link,
    then create the note against it."""
    with session_user(administrator.name):
        lead = CRMLead.objects.create(first_name="ZZ Referenced", lead_owner=alice)

    assert "CRM Lead" in search(auth_api, txt="CRM Lead")
    assert lead.name in search(auth_api, doctype="CRM Lead", txt="ZZ Referenced")

    response = auth_api.post(
        "/api/method/frappe.client.insert",
        {
            "doc": {
                "doctype": "FCRM Note",
                "title": "ZZ About the lead",
                "reference_doctype": "CRM Lead",
                "reference_docname": lead.name,
            }
        },
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    note = FCRMNote.objects.get(pk=response.json()["message"]["name"])
    assert (note.reference_doctype, note.reference_docname) == ("CRM Lead", lead.name)
