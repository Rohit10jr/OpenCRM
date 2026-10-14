"""Email Template: upstream's role table, reproduced (FINDINGS.md 87).

``email_template.json``: ``Desk User`` reads, and that is the role every System User
holds (``frappe/permissions.py:36``), so every CRM user; ``System Manager`` alone creates,
writes and deletes. CRM adds nothing to the table and shows its Templates page to every
role, so a Sales User or Sales Manager sees the list, picks a template in the mail
editor, and is refused on New, on an edit and on delete. Found in the role passes
(BROWSER_TESTING.md S11), where both Grace and Ada did all three here.
"""

from urllib.parse import quote

import pytest

from frappe_core.session import session_user
from frappe_platform.models import EmailTemplate

pytestmark = pytest.mark.django_db

TEMPLATES = "/api/resource/Email Template"
METHOD = "/api/method/frappe.client."


@pytest.fixture
def grace(make_user):
    return make_user("grace@example.com", first_name="Grace", roles=["Sales Manager", "Sales User"])


@pytest.fixture
def template(administrator):
    with session_user(administrator.name):
        return EmailTemplate.objects.create(name="ZZ Welcome", subject="Hi", response="<p>Hello</p>")


@pytest.mark.parametrize("who", ["alice", "grace"])
def test_a_rep_and_a_manager_read_but_neither_writes(api_as, request, who, template):
    client = api_as(request.getfixturevalue(who))

    assert client.get(f"{TEMPLATES}/{quote(template.pk)}").status_code == 200
    listed = client.get(TEMPLATES).json()["data"]
    assert any(row["name"] == template.pk for row in listed), "the picker's list"

    response = client.post(TEMPLATES, {"name": "ZZ Mine", "subject": "s", "response": "r"}, format="json")
    assert response.status_code == 403, response.content[:300]
    response = client.put(f"{TEMPLATES}/{quote(template.pk)}", {"subject": "Changed"}, format="json")
    assert response.status_code == 403, response.content[:300]
    assert client.delete(f"{TEMPLATES}/{quote(template.pk)}").status_code == 403

    assert EmailTemplate.objects.get(pk=template.pk).subject == "Hi"
    assert not EmailTemplate.objects.filter(pk="ZZ Mine").exists()


def test_the_pages_own_doors_refuse_a_manager_too(api_as, grace, template):
    """The Templates page writes through ``frappe.client.*``: the same rule answers."""
    client = api_as(grace)

    response = client.post(
        METHOD + "set_value",
        {"doctype": "Email Template", "name": template.pk, "fieldname": "subject", "value": "Changed"},
        format="json",
    )
    assert response.status_code == 403, response.content[:300]
    # rename_doc answers a plain throw, 417, as upstream's validate_rename does
    # (`client_rename_doc`, crm_app/api/client.py).
    response = client.post(
        METHOD + "rename_doc",
        {"doctype": "Email Template", "old_name": template.pk, "new_name": "ZZ Renamed"},
        format="json",
    )
    assert response.status_code == 417, response.content[:300]
    assert response.json()["messages"] == [f"You need write permission on Email Template {template.pk} to rename"]
    assert EmailTemplate.objects.filter(pk=template.pk).exists()
    response = client.post(METHOD + "delete", {"doctype": "Email Template", "name": template.pk}, format="json")
    assert response.status_code == 403, response.content[:300]
    assert response.json()["exc_type"] == "PermissionError"

    assert EmailTemplate.objects.get(pk=template.pk).subject == "Hi"


def test_a_system_manager_does_all_of_it(api_as, administrator, template):
    client = api_as(administrator)

    response = client.post(TEMPLATES, {"name": "ZZ Admin", "subject": "s", "response": "r"}, format="json")
    assert response.status_code == 201, response.content[:300]
    response = client.put(f"{TEMPLATES}/{quote(template.pk)}", {"subject": "Changed"}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert EmailTemplate.objects.get(pk=template.pk).subject == "Changed"
    assert client.delete(f"{TEMPLATES}/{quote(template.pk)}").status_code in (200, 202, 204)
    assert not EmailTemplate.objects.filter(pk=template.pk).exists()
