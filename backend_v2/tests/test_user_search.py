"""User link search: ported from ``backend/tests/test_phase3_endpoints.py:1389``.

`frappe.desk.search.search_link` with ``doctype: User`` becomes
`GET /api/v1/users/search/` (specs/ACCOUNTS.md section 4.3, FINDINGS 46).
"""

import json

import pytest

pytestmark = pytest.mark.django_db
SEARCH = "/api/v1/users/search/"


def test_search_link_user_takes_the_frontends_ignore_user_type_key(auth_api, alice, make_user):
    make_user("portal@example.com", first_name="Portal", user_type="Website User")
    make_user("off@example.com", first_name="Off", enabled=False)

    def names(filters):
        response = auth_api.get(SEARCH, {"filters": json.dumps(filters)})
        assert response.status_code == 200, response.content[:300]
        return [row["value"] for row in response.json()["message"]]

    listed = names({"ignore_user_type": 1})
    assert alice.name in listed
    assert "off@example.com" not in listed, "disabled accounts stay out (user_query)"
    assert "portal@example.com" in listed, "a System User asking with the flag sees Website Users"

    plain = names({})
    assert alice.name in plain
    assert "portal@example.com" not in plain, "without the flag, Website Users are hidden"


def test_a_website_user_asking_with_the_flag_still_sees_no_website_users(make_user, api_as):
    """The flag counts only from a System User (old `client.py:56-58`)."""
    portal = make_user("portal@example.com", user_type="Website User", roles=["Sales User"])
    make_user("other.portal@example.com", user_type="Website User")

    response = api_as(portal).get(SEARCH, {"filters": json.dumps({"ignore_user_type": 1})})

    assert "other.portal@example.com" not in [r["value"] for r in response.json()["message"]]


def test_search_hides_the_built_ins_from_a_normal_user(auth_api):
    response = auth_api.get(SEARCH, {"txt": "Admin"})
    assert "Administrator" not in [r["value"] for r in response.json()["message"]]
