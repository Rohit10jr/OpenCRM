"""Contact: upstream's role table, reproduced (FINDINGS.md 86).

``contact.json``: Sales User and Sales Manager read, write and create every contact and
hold no delete; the ``All`` row holds delete with ``if_owner``. So the creator deletes
their own contact, a System Manager deletes any, and a manager is refused like a rep -
the hosted demo does the same. Found in the role passes (BROWSER_TESTING.md), where
both Grace and Ada deleted a contact Administrator had created.

Every door is checked: the resource route, ``frappe.client.delete``, and bulk delete,
which refuses the whole batch when one row is not the caller's to delete.
"""

import json
from urllib.parse import quote

import pytest

from frappe_core.session import session_user
from frappe_platform.models import Contact

pytestmark = pytest.mark.django_db

CONTACTS = "/api/resource/Contact"
CLIENT_DELETE = "/api/method/frappe.client.delete"
BULK_DELETE = "/api/method/crm.api.doc.delete_bulk_docs"


@pytest.fixture
def grace(make_user):
    return make_user("grace@example.com", first_name="Grace", roles=["Sales Manager", "Sales User"])


def contact_by(user, first_name):
    with session_user(user.name):
        return Contact.objects.create(first_name=first_name, last_name="Tester")


def test_a_rep_reads_and_edits_any_contact_but_deletes_only_her_own(api_as, alice, administrator):
    theirs = contact_by(administrator, "Admins")
    mine = contact_by(alice, "Alices")
    client = api_as(alice)

    assert client.get(f"{CONTACTS}/{quote(theirs.pk)}").status_code == 200
    response = client.put(f"{CONTACTS}/{quote(theirs.pk)}", {"last_name": "Edited"}, format="json")
    assert response.status_code == 200, response.content[:300]

    assert client.delete(f"{CONTACTS}/{quote(theirs.pk)}").status_code == 403
    assert Contact.objects.filter(pk=theirs.pk).exists(), "not hers to delete"

    assert client.delete(f"{CONTACTS}/{quote(mine.pk)}").status_code in (200, 202, 204)
    assert not Contact.objects.filter(pk=mine.pk).exists(), "the All row with if_owner"


def test_a_manager_is_refused_like_a_rep(api_as, grace, administrator):
    """``contact.json``: the Sales Manager row carries no delete either."""
    theirs = contact_by(administrator, "Admins")

    response = api_as(grace).post(
        CLIENT_DELETE, {"doctype": "Contact", "name": theirs.pk}, format="json"
    )

    assert response.status_code == 403, response.content[:300]
    assert response.json()["exc_type"] == "PermissionError"
    assert Contact.objects.filter(pk=theirs.pk).exists()


def test_a_system_manager_deletes_anyones(api_as, alice, administrator):
    hers = contact_by(alice, "Alices")

    response = api_as(administrator).post(
        CLIENT_DELETE, {"doctype": "Contact", "name": hers.pk}, format="json"
    )

    assert response.status_code == 200, response.content[:300]
    assert not Contact.objects.filter(pk=hers.pk).exists()


def test_bulk_delete_refuses_the_batch_when_one_row_is_not_hers(api_as, alice, administrator):
    """``authorize_bulk_delete`` asks the object rule per row (C9) and refuses the lot."""
    theirs = contact_by(administrator, "Admins")
    mine = contact_by(alice, "Alices")
    client = api_as(alice)

    response = client.post(
        BULK_DELETE, {"doctype": "Contact", "items": json.dumps([mine.pk, theirs.pk])}, format="json"
    )
    assert response.status_code == 403, response.content[:300]
    assert Contact.objects.filter(pk__in=[mine.pk, theirs.pk]).count() == 2, "nothing went"

    response = client.post(BULK_DELETE, {"doctype": "Contact", "items": json.dumps([mine.pk])}, format="json")
    assert response.status_code == 200, response.content[:300]
    assert not Contact.objects.filter(pk=mine.pk).exists()
