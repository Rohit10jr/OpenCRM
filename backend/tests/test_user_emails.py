"""A user's outgoing email accounts: docs/FINDINGS.md 57.

Upstream's User carries ``user_emails``, rows of ``User Email`` (``user_email.json``).
Two things fill it: an Email Account save adds a row to the user whose address is the
account's (``email_account.py:1072-1115``), and Profile → Email Settings → Add Email
sends the rows through ``frappe.client.set_value``. The composer's From dropdown reads
the same rows (``EmailEditor.vue:266``). The table sits at permlevel 1 upstream: System
Manager writes it, anyone else's change is reset on save.
"""

import pytest

from frappe_core.session import session_user
from frappe_platform.models import EmailAccount, UserEmail

pytestmark = pytest.mark.django_db

SET_VALUE = "/api/method/frappe.client.set_value"
GET = "/api/method/frappe.client.get"


@pytest.fixture
def gmail(administrator):
    with session_user(administrator.name):
        return EmailAccount.objects.create(
            email_account_name="ZZ Gmail", email_id="zz.sales@example.com", service="GMail", enable_outgoing=True
        )


def rows_of(client, user):
    response = client.post(GET, {"doctype": "User", "name": user}, format="json")
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]["user_emails"]


def set_rows(client, user, rows, **more):
    return client.post(
        SET_VALUE, {"doctype": "User", "name": user, "fieldname": {"user_emails": rows, **more}}, format="json"
    )


def test_a_manager_adds_an_account_from_the_profile_and_it_stays(api_as, administrator, gmail):
    """Add Email → Update, then the x beside the entry → Update."""
    client = api_as(administrator)
    response = set_rows(client, administrator.name, [{"email_account": gmail.pk}])
    assert response.status_code == 200, response.content[:300]
    rows = rows_of(client, administrator.name)
    assert [(r["email_account"], r["email_id"], r["enable_outgoing"]) for r in rows] == [
        (gmail.pk, "zz.sales@example.com", True)
    ]

    response = set_rows(client, administrator.name, [])
    assert response.status_code == 200, response.content[:300]
    assert rows_of(client, administrator.name) == []


def test_a_sales_users_pick_is_dropped_as_upstream_resets_it(auth_api, alice, gmail):
    """Permlevel 1: the rest of the save goes through, the rows do not."""
    response = set_rows(auth_api, alice.name, [{"email_account": gmail.pk}], first_name="Alicia")
    assert response.status_code == 200, response.content[:300]
    assert rows_of(auth_api, alice.name) == []
    alice.refresh_from_db()
    assert alice.first_name == "Alicia"


def test_an_account_with_a_users_address_links_itself_to_that_user(administrator, alice):
    with session_user(administrator.name):
        account = EmailAccount.objects.create(
            email_account_name="ZZ Alice", email_id=alice.name, enable_outgoing=True
        )
        account.save()  # a second save adds nothing

    rows = list(UserEmail.objects.filter(parent_user=alice))
    assert [(r.email_account_id, r.email_id, r.enable_outgoing) for r in rows] == [
        (account.pk, alice.name, True)
    ]

    with session_user(administrator.name):
        account.enable_outgoing = False
        account.save()
    assert UserEmail.objects.get(parent_user=alice).enable_outgoing is False

    with session_user(administrator.name):
        account.delete()
    assert not UserEmail.objects.filter(parent_user=alice).exists()


def test_the_rows_come_back_with_the_user_for_the_composer(auth_api, alice, administrator):
    with session_user(administrator.name):
        account = EmailAccount.objects.create(
            email_account_name="ZZ Mine", email_id=alice.name, enable_outgoing=True
        )
    rows = rows_of(auth_api, alice.name)
    assert [(r["email_account"], r["email_id"]) for r in rows] == [(account.pk, alice.name)]
