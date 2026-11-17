"""`get_users` and `get_user_info` (specs/ACCOUNTS.md section 4.2).

The first three cases are ported from ``backend/tests/test_phase3_endpoints.py:1123-1150``:
`crm.api.session.get_users` becomes `GET /api/v1/users/directory/`, its body inputs the
query string. The rest are new: no old test covers them.
"""

import json

import pytest

pytestmark = pytest.mark.django_db
DIRECTORY = "/api/v1/users/directory/"
INFO = "/api/v1/users/info/"


def test_get_users_requires_a_crm_role(make_user, api_as):
    outsider = make_user("outsider@example.com")
    response = api_as(outsider).get(DIRECTORY)
    assert response.status_code == 403
    assert response.json()["messages"] == ["You are not permitted to access CRM resources."]


def test_get_users_returns_the_pair(auth_api, alice):
    response = auth_api.get(DIRECTORY)
    assert response.status_code == 200
    users, crm_users = response.json()["message"]
    assert alice.name in [u["name"] for u in crm_users]


def test_a_sales_user_cannot_escalate_with_include_all(auth_api, alice, make_user):
    make_user("nonmember@example.com")
    response = auth_api.get(DIRECTORY, {"include_all": True})
    users, crm_users = response.json()["message"]
    assert "nonmember@example.com" not in [u["name"] for u in users]


def test_a_system_manager_sees_every_enabled_user_with_include_all(make_user, api_as):
    boss = make_user("boss@example.com", roles=["System Manager"])
    make_user("nonmember@example.com", full_name="Zed")
    make_user("disabled@example.com", enabled=False, roles=["Sales User"])

    users, crm_users = api_as(boss).get(DIRECTORY, {"include_all": "1"}).json()["message"]

    names = [u["name"] for u in users]
    assert "nonmember@example.com" in names
    assert "disabled@example.com" not in names
    assert "nonmember@example.com" not in [u["name"] for u in crm_users]


def test_get_users_row_shape(auth_api, alice):
    users, _ = auth_api.get(DIRECTORY).json()["message"]
    row = next(u for u in users if u["name"] == alice.name)
    assert row["session_user"] is True
    assert row["roles"] == ["Sales User", "All", "Guest"]
    assert row["role"] == "Sales User"
    assert row["is_telephony_agent"] is False
    assert set(row) == {
        "name", "email", "enabled", "user_image", "first_name", "last_name",
        "full_name", "user_type", "language", "session_user", "roles", "role",
        "is_telephony_agent",
    }
    admin = next(u for u in users if u["name"] == "Administrator")
    assert (admin["roles"], admin["role"]) == (["System Manager", "All"], "System Manager")


def test_get_user_info_returns_five_fields_including_built_in_and_disabled(
    auth_api, make_user
):
    make_user("off@example.com", enabled=False)
    response = auth_api.post(
        INFO, {"users": ["Administrator", "off@example.com"]}, format="json"
    )
    rows = {row["name"]: row for row in response.json()["message"]}
    assert set(rows) == {"Administrator", "off@example.com"}
    assert set(rows["off@example.com"]) == {
        "name", "email", "full_name", "user_image", "user_type"
    }


def test_get_user_info_takes_a_json_list_in_the_query(auth_api, alice):
    response = auth_api.get(INFO, {"users": json.dumps([alice.name])})
    assert [row["name"] for row in response.json()["message"]] == [alice.name]


def test_get_user_info_caps_at_200_names(auth_api, alice):
    names = [f"nobody{i}@example.com" for i in range(200)] + [alice.name]
    response = auth_api.post(INFO, {"users": names}, format="json")
    assert response.json()["message"] == []


def test_get_user_info_requires_a_crm_role(make_user, api_as):
    outsider = make_user("outsider@example.com")
    assert api_as(outsider).post(INFO, {"users": ["x"]}, format="json").status_code == 403
