"""The ``Salutation`` and ``Gender`` doctypes: docs/FINDINGS.md 66.

Upstream's contact, lead and deal forms pick both from a dropdown: each is a Link to a
small framework doctype (``contact.json``, ``crm_lead.json``, ``crm_deal.json``). The
port had neither doctype, so the lead's and deal's dropdowns were empty and the
contact's two fields were plain text boxes. And a Link is validated: a value that names
no document is refused on save (``base_document.py:1040-1054``).
"""

import pytest

from crm_app.models import CRMLead
from frappe_core import field_meta
from frappe_core.exceptions import LinkValidationError
from frappe_core.session import session_user
from frappe_platform import reference_data
from frappe_platform.models import Contact, Gender, Salutation

pytestmark = pytest.mark.django_db

SEARCH = "/api/method/frappe.desk.search.search_link"
INSERT = "/api/method/frappe.client.insert"
TARGETS = {"salutation": "Salutation", "gender": "Gender"}


def search(client, doctype, txt=""):
    response = client.post(SEARCH, {"doctype": doctype, "txt": txt}, format="json")
    assert response.status_code == 200, response.content[:300]
    return [row["value"] for row in response.json()["message"]]


# --------------------------------------------------------------------------- the lists


def test_every_database_has_upstreams_lists(administrator):
    """A migration writes them, as the framework's setup wizard does for a site."""
    assert set(Salutation.objects.values_list("pk", flat=True)) == set(reference_data.SALUTATIONS)
    assert set(Gender.objects.values_list("pk", flat=True)) == set(reference_data.GENDERS)
    with session_user(administrator.name):
        assert (reference_data.add_salutations(), reference_data.add_genders()) == (0, 0)


def test_a_deleted_row_is_put_back_by_the_install_step(administrator):
    with session_user(administrator.name):
        Salutation.objects.filter(pk="Prof").delete()
        assert reference_data.add_salutations() == 1
    assert Salutation.objects.filter(pk="Prof").exists()


def test_a_sales_user_gets_both_dropdowns(auth_api):
    assert set(search(auth_api, "Salutation")) == set(reference_data.SALUTATIONS)
    assert set(search(auth_api, "Gender")) == set(reference_data.GENDERS)
    assert set(search(auth_api, "Salutation", "Mr")) == {"Mr", "Mrs"}
    assert search(auth_api, "Gender", "Fem") == ["Female"]


def test_everyone_reads_and_only_an_admin_adds_one(auth_api, api_as, administrator):
    assert auth_api.get("/api/resource/Gender/Male").status_code == 200
    refused = auth_api.post("/api/resource/Salutation", {"salutation": "Sir"}, format="json")
    assert refused.status_code == 403
    allowed = api_as(administrator).post("/api/resource/Salutation", {"salutation": "Sir"}, format="json")
    assert allowed.status_code == 201, allowed.content[:300]
    assert Salutation.objects.filter(pk="Sir").exists()


# --------------------------------------------------------------------------- metadata


def test_the_contacts_two_fields_are_links_in_its_metadata():
    """What the create dialog and the side panel read: a Link renders as a dropdown."""
    fields = {f["fieldname"]: f for f in field_meta.get_fields("Contact")}
    for fieldname, target in TARGETS.items():
        assert (fields[fieldname]["fieldtype"], fields[fieldname]["options"]) == ("Link", target)


def test_wherever_a_crm_doctype_has_the_fields_they_point_at_the_two_lookups():
    """Their metadata is upstream's JSON and always said Link; only the target doctypes
    were missing, which is why the lead's dropdowns listed nothing."""
    seen = 0
    for doctype in ("CRM Lead", "CRM Deal", "CRM Contacts"):
        fields = {f["fieldname"]: f for f in field_meta.get_fields(doctype)}
        for fieldname, target in TARGETS.items():
            if fieldname in fields:
                assert fields[fieldname]["fieldtype"] == "Link", (doctype, fieldname)
                assert fields[fieldname]["options"] == target, (doctype, fieldname)
                seen += 1
    assert seen >= 2


# --------------------------------------------------------------------------- validation


def test_a_picked_value_is_stored_on_the_contact(auth_api):
    response = auth_api.post(
        INSERT,
        {"doc": {"doctype": "Contact", "first_name": "ZZ Ravi", "salutation": "Mr", "gender": "Male"}},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    contact = Contact.objects.get(pk=response.json()["message"]["name"])
    assert (contact.salutation, contact.gender) == ("Mr", "Male")


def test_a_salutation_that_does_not_exist_is_refused_as_upstream_refuses_it(auth_api):
    """``Could not find <Label>: <value>``, a LinkValidationError, 417."""
    response = auth_api.post(
        INSERT,
        {"doc": {"doctype": "Contact", "first_name": "ZZ Nobody", "salutation": "Sir"}},
        format="json",
    )
    assert response.status_code == 417
    body = response.json()
    assert body["exc_type"] == "LinkValidationError"
    assert "Could not find Salutation: Sir" in body["exception"]
    assert not Contact.objects.filter(first_name="ZZ Nobody").exists()


def test_both_bad_links_are_named_in_one_message(auth_api):
    response = auth_api.post(
        INSERT,
        {"doc": {"doctype": "Contact", "first_name": "ZZ Two", "salutation": "Sir", "gender": "Robot"}},
        format="json",
    )
    assert response.status_code == 417
    assert "Could not find Salutation: Sir, Gender: Robot" in response.json()["exception"]


def test_a_lead_is_held_to_the_same_rule(alice, administrator):
    """The lead's columns are text too; the rule comes from its metadata, not a list."""
    from crm_app.models import CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
    with session_user(alice.name):
        with pytest.raises(LinkValidationError, match="Could not find"):
            CRMLead.objects.create(first_name="ZZ Lead", lead_owner=alice, salutation="Sir", status=status)
        lead = CRMLead.objects.create(
            first_name="ZZ Lead", lead_owner=alice, salutation="Dr", gender="Female", status=status
        )
    assert (lead.salutation, lead.gender) == ("Dr", "Female")


def test_a_case_only_difference_is_stored_in_the_lists_spelling(auth_api):
    """MariaDB matches a Link without regard to case and upstream rewrites the value to
    the stored name; the same typed value must behave the same here."""
    response = auth_api.post(
        INSERT,
        {"doc": {"doctype": "Contact", "first_name": "ZZ Case", "salutation": "mr", "gender": "MALE"}},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    contact = Contact.objects.get(pk=response.json()["message"]["name"])
    assert (contact.salutation, contact.gender) == ("Mr", "Male")


def test_an_empty_value_is_not_a_link_to_check(auth_api):
    response = auth_api.post(
        INSERT, {"doc": {"doctype": "Contact", "first_name": "ZZ Plain"}}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
