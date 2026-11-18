"""`get_views`: the saved views a list screen offers (specs/CONFIGURATION.md 4.7; temp
A-39).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_phase4_metadata.py:236`` (another
user's view is not offered). The old `crm.api.views.get_views` is `GET /api/v1/views/`.
New: the empty `doctype` the store sends, Administrator's answer, the keys, the order,
the integer `name`, PE-12d for no `doctype`.
"""

import pytest

from configuration.models import CRMViewSettings
from configuration.view_settings import create_or_update_standard_view, create_view

pytestmark = pytest.mark.django_db

VIEWS = "/api/v1/views/"


def standard(user, doctype="CRM Lead"):
    return create_or_update_standard_view(
        {"doctype": doctype, "type": "list", "columns": [{"key": "email"}], "rows": ["name"]},
        user=user,
    )["name"]


def names(response):
    return [row["name"] for row in response.json()["message"]]


# --- ported ------------------------------------------------------------------------------


def test_get_views_only_returns_your_own_and_public_ones(alice, bob, api_as):
    standard(alice)
    assert api_as(bob).get(VIEWS, {"doctype": "CRM Lead"}).json() == {"message": []}
    assert len(api_as(alice).get(VIEWS, {"doctype": "CRM Lead"}).json()["message"]) == 1


# --- new ---------------------------------------------------------------------------------


def test_an_empty_doctype_answers_every_doctypes_views(alice, auth_api):
    lead, task = standard(alice), standard(alice, doctype="CRM Task")
    assert sorted(names(auth_api.get(VIEWS, {"doctype": ""}))) == sorted([lead, task])
    assert names(auth_api.get(VIEWS, {"doctype": "CRM Task"})) == [task]


def test_ownerless_views_are_offered_to_everyone(alice, bob, api_as):
    name = create_view({"doctype": "CRM Lead", "label": "Shared"}, user=alice)["name"]
    CRMViewSettings.objects.filter(pk=name).update(public=True, user=None)
    assert names(api_as(bob).get(VIEWS, {"doctype": "CRM Lead"})) == [name]


def test_administrator_gets_their_own_and_ownerless_views_only(alice, administrator, api_as):
    standard(alice)
    assert api_as(administrator).get(VIEWS, {"doctype": ""}).json() == {"message": []}


def test_the_rows_keep_backends_keys_and_newest_come_first(alice, auth_api):
    older = create_view({"doctype": "CRM Lead", "label": "Older"}, user=alice)["name"]
    newer = create_view({"doctype": "CRM Lead", "label": "Newer"}, user=alice)["name"]
    rows = auth_api.get(VIEWS, {"doctype": "CRM Lead"}).json()["message"]
    assert [row["name"] for row in rows] == [newer, older]
    row = rows[0]
    assert isinstance(row["name"], int)
    assert row["user_id"] == alice.name
    assert row["owner_id"] == alice.name
    assert "modified_by_id" in row
    assert isinstance(row["_assign"], str)


def test_pe12d_no_doctype_is_417(auth_api):
    response = auth_api.get(VIEWS)
    assert response.status_code == 417
    assert response.json()["message"] == "DocType is required"
