"""Salutation, Gender and CRM Industry (specs/CONTACTS.md §3, §4; milestone 1).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_salutation_gender.py:35-63``: every
database has upstream's lists, a sales user gets both dropdowns, everyone reads and only
an admin adds one. The old `frappe.desk.search.search_link` is each resource's own
`search/`, and the old resource POST's 201 `data` is 200 `message`. `:43-47` (a deleted
row put back) is in `test_restore_defaults.py`; `:66-160`: the Contact parts are at
the end of this file (milestone 3), the CRM Lead and Deal ones wait for SALES. New: CRM Industry open to every CRM user (PE-29).
"""

import pytest

from contacts import reference_rows
from contacts.models import CRMIndustry, Gender, Salutation

pytestmark = pytest.mark.django_db


def search(client, resource, txt=""):
    response = client.get(f"/api/v1/{resource}/search/", {"txt": txt})
    assert response.status_code == 200, response.json()
    return [row["value"] for row in response.json()["message"]]


# --- ported ------------------------------------------------------------------------------


def test_every_database_has_upstreams_lists():
    """The data migration writes them, as the framework's setup wizard does."""
    assert set(Salutation.objects.values_list("pk", flat=True)) == set(reference_rows.SALUTATIONS)
    assert set(Gender.objects.values_list("pk", flat=True)) == set(reference_rows.GENDERS)


def test_a_sales_user_gets_both_dropdowns(auth_api):
    assert set(search(auth_api, "salutations")) == set(reference_rows.SALUTATIONS)
    assert set(search(auth_api, "genders")) == set(reference_rows.GENDERS)
    assert set(search(auth_api, "salutations", "Mr")) == {"Mr", "Mrs"}
    assert search(auth_api, "genders", "Fem") == ["Female"]


def test_everyone_reads_and_only_an_admin_adds_one(auth_api, api_as, administrator):
    assert auth_api.get("/api/v1/genders/Male/").status_code == 200
    refused = auth_api.post("/api/v1/salutations/", {"salutation": "Sir"}, format="json")
    assert refused.status_code == 403
    allowed = api_as(administrator).post("/api/v1/salutations/", {"salutation": "Sir"}, format="json")
    assert allowed.status_code == 200, allowed.json()
    assert allowed.json()["message"]["name"] == "Sir"
    assert Salutation.objects.filter(pk="Sir").exists()


# --- new ---------------------------------------------------------------------------------


@pytest.mark.parametrize("resource", ["salutations", "genders"])
def test_a_sales_user_may_not_change_or_delete_one(auth_api, resource):
    name = "Mr" if resource == "salutations" else "Male"
    assert auth_api.patch(f"/api/v1/{resource}/{name}/", {}, format="json").status_code == 403
    assert auth_api.delete(f"/api/v1/{resource}/{name}/").status_code == 403


def test_a_system_manager_writes_them(make_user, api_as):
    manager = make_user("sysman@example.com", roles=["System Manager"])
    response = api_as(manager).post("/api/v1/genders/", {"gender": "Agender"}, format="json")
    assert response.status_code == 200
    assert api_as(manager).delete("/api/v1/genders/Agender/").status_code == 200


def test_a_salutation_is_unique(api_as, administrator):
    """The unique column's own check refuses it (417, ValidationError), before the name
    would collide."""
    response = api_as(administrator).post("/api/v1/salutations/", {"salutation": "Mr"}, format="json")
    assert response.status_code == 417
    assert response.json()["exc_type"] == "ValidationError"
    assert response.json()["message"] == "salutation: salutation with this Salutation already exists."
    assert Salutation.objects.filter(salutation="Mr").count() == 1


def test_a_duplicate_industry_is_409(auth_api):
    """The name collides (the column is not unique), as `backend/` answers."""
    assert auth_api.post("/api/v1/industries/", {"industry": "Twice"}, format="json").status_code == 200
    response = auth_api.post("/api/v1/industries/", {"industry": "Twice"}, format="json")
    assert response.status_code == 409
    assert response.json()["exc_type"] == "DuplicateEntryError"
    assert response.json()["message"] == "CRM Industry <strong>Twice</strong> already exists"


def test_an_industry_with_no_name_is_417(auth_api):
    response = auth_api.post("/api/v1/industries/", {"industry": ""}, format="json")
    assert response.status_code == 417
    assert response.json()["message"] == "Industry is required"


def test_crm_industry_is_open_to_every_crm_user(auth_api, api):
    """PE-29: a CRM role is needed (`auth_api` is a Sales User); tests/test_crm_role_rule.py
    has the caller with none."""
    response = auth_api.post("/api/v1/industries/", {"industry": "Robotics"}, format="json")
    assert response.status_code == 200
    assert response.json()["message"]["name"] == "Robotics"
    assert auth_api.patch("/api/v1/industries/Robotics/", {}, format="json").status_code == 200
    assert search(auth_api, "industries", "Robo") == ["Robotics"]
    assert auth_api.delete("/api/v1/industries/Robotics/").status_code == 200
    assert not CRMIndustry.objects.filter(pk="Robotics").exists()
    assert api.get("/api/v1/industries/").status_code == 401


# --- the Contact parts, ported at CONTACTS milestone 3 (old `:69-73`, `:93-125`, `:143-160`) ---
# `frappe.client.insert` of a Contact is `POST /api/v1/contacts/`; the Lead and Deal cases
# (`:76-87`, `:128-140`) wait for SALES.

CONTACT_TARGETS = {"salutation": "Salutation", "gender": "Gender"}


def test_the_contacts_two_fields_are_links_in_its_metadata():
    from configuration import field_meta

    fields = {f["fieldname"]: f for f in field_meta.get_fields("Contact")}
    for fieldname, target in CONTACT_TARGETS.items():
        assert (fields[fieldname]["fieldtype"], fields[fieldname]["options"]) == ("Link", target)


def _insert(client, **doc):
    return client.post("/api/v1/contacts/", doc, format="json")


def test_a_picked_value_is_stored_on_the_contact(auth_api):
    from contacts.models import Contact

    response = _insert(auth_api, first_name="ZZ Ravi", salutation="Mr", gender="Male")
    assert response.status_code == 200, response.content[:300]
    contact = Contact.objects.get(pk=response.json()["message"]["name"])
    assert (contact.salutation, contact.gender) == ("Mr", "Male")


def test_a_salutation_that_does_not_exist_is_refused_as_upstream_refuses_it(auth_api):
    from contacts.models import Contact

    response = _insert(auth_api, first_name="ZZ Nobody", salutation="Sir")
    assert response.status_code == 417
    body = response.json()
    assert body["exc_type"] == "LinkValidationError"
    assert "Could not find Salutation: Sir" in body["message"]
    assert not Contact.objects.filter(first_name="ZZ Nobody").exists()


def test_both_bad_links_are_named_in_one_message(auth_api):
    response = _insert(auth_api, first_name="ZZ Two", salutation="Sir", gender="Robot")
    assert response.status_code == 417
    assert "Could not find Salutation: Sir, Gender: Robot" in response.json()["message"]


def test_a_case_only_difference_is_stored_in_the_lists_spelling(auth_api):
    from contacts.models import Contact

    response = _insert(auth_api, first_name="ZZ Case", salutation="mr", gender="MALE")
    assert response.status_code == 200, response.content[:300]
    contact = Contact.objects.get(pk=response.json()["message"]["name"])
    assert (contact.salutation, contact.gender) == ("Mr", "Male")


def test_an_empty_value_is_not_a_link_to_check(auth_api):
    assert _insert(auth_api, first_name="ZZ Plain").status_code == 200
