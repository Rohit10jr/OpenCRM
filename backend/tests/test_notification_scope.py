"""The notification bell is the caller's own: docs/FINDINGS.md 61.

Upstream's ``get_notifications`` and ``mark_as_read`` both filter on
``to_user = session.user`` (``crm/api/notifications.py:8-13``, ``52-57``) whoever is
asking. The port read through the permission rule instead, which is unrestricted for an
administrator, so Administrator's bell listed every user's notifications and "Mark all
as read" cleared them for everybody.
"""

import pytest

from crm_app.models import CRMNotification
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

LIST = "/api/method/crm.api.notifications.get_notifications"
MARK = "/api/method/crm.api.notifications.mark_as_read"


def notify(to_user, from_user, text):
    return CRMNotification.objects.create(
        from_user=from_user,
        to_user=to_user,
        type="Assignment",
        message=text,
        notification_text=text,
        notification_type_doctype="CRM Lead",
        notification_type_doc="CRM-LEAD-0001",
        reference_doctype="CRM Lead",
        reference_name="CRM-LEAD-0001",
    )


@pytest.fixture
def notifications(administrator, alice, bob):
    with session_user(administrator.name):
        return {
            "alice": notify(alice, administrator, "for alice"),
            "bob": notify(bob, alice, "for bob"),
            "admin": notify(administrator, alice, "for the administrator"),
        }


def listed(client) -> list[str]:
    response = client.post(LIST, {}, format="json")
    assert response.status_code == 200, response.content[:300]
    return [row["notification_text"] for row in response.json()["message"]]


def test_an_administrator_sees_only_their_own(api_as, administrator, notifications):
    assert listed(api_as(administrator)) == ["for the administrator"]


def test_a_sales_user_sees_only_their_own(api_as, alice, bob, notifications):
    assert listed(api_as(alice)) == ["for alice"]
    assert listed(api_as(bob)) == ["for bob"]


def test_mark_all_as_read_touches_only_the_callers(api_as, administrator, notifications):
    response = api_as(administrator).post(MARK, {}, format="json")
    assert response.status_code == 200, response.content[:300]
    for row in notifications.values():
        row.refresh_from_db()
    assert notifications["admin"].read is True
    assert notifications["alice"].read is False
    assert notifications["bob"].read is False


def test_the_resource_route_still_lets_an_administrator_read_them_all(api_as, administrator, notifications):
    """The permission rule is untouched: upstream's is unrestricted for a System
    Manager too. Only the bell is scoped."""
    response = api_as(administrator).get("/api/resource/CRM Notification")
    assert response.status_code == 200
    assert len(response.json()["data"]) == 3
