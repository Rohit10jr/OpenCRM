"""The singleton-value and document-permission base-class actions."""

import pytest

from tests_support.models import SingletonDocument, Widget


pytestmark = pytest.mark.django_db
SINGLETON_VALUE = "/api/v1/test-singleton/value/"
WIDGETS = "/api/v1/test-widgets/"


def test_get_single_value_returns_a_value_or_none(auth_api, administrator):
    assert auth_api.get(SINGLETON_VALUE, {"field": "value"}).json() == {
        "message": None
    }
    row = SingletonDocument.load(user=administrator)
    row.value = "Open"
    row.save(user=administrator)
    assert auth_api.get(SINGLETON_VALUE, {"field": "value"}).json() == {
        "message": "Open"
    }


def test_get_single_value_applies_the_object_rule(auth_api, administrator):
    row = SingletonDocument.load(user=administrator)
    row.value = "Private"
    row.save(user=administrator)
    response = auth_api.get(SINGLETON_VALUE, {"field": "value"})
    assert response.status_code == 403
    assert response.json()["message"] == "Not permitted to read Foundation Singleton"


def test_get_single_value_refuses_a_sensitive_field(auth_api, administrator):
    SingletonDocument.load(user=administrator)
    response = auth_api.get(SINGLETON_VALUE, {"field": "password"})
    assert response.status_code == 403
    assert response.json()["message"] == "Field 'password' is not readable"


def test_restricted_single_value_is_refused_for_sales_user_and_returned_for_manager(
    auth_api, api_as, administrator
):
    row = SingletonDocument.load(user=administrator)
    row.value = "Open"
    row.manager_note = "manager-only"
    row.save(user=administrator)

    refused = auth_api.get(SINGLETON_VALUE, {"field": "manager_note"})
    assert refused.status_code == 403
    assert refused.json()["message"] == "Field 'manager_note' is not readable"

    allowed = api_as(administrator).get(
        SINGLETON_VALUE, {"field": "manager_note"}
    )
    assert allowed.status_code == 200
    assert allowed.json() == {"message": "manager-only"}


def test_get_doc_permissions_does_not_raise_for_a_denied_row(
    auth_api, alice, bob
):
    row = Widget(widget_name="Theirs", status="Private", widget_owner=bob)
    row.save(user=alice)
    response = auth_api.get(f"{WIDGETS}{row.name}/permissions/")
    assert response.status_code == 200
    permissions = response.json()["message"]["permissions"]
    assert permissions == {
        "read": False,
        "write": True,
        "delete": True,
        "create": True,
        "share": True,
        "print": True,
        "email": True,
    }


def test_get_doc_permissions_returns_an_empty_map_for_a_missing_row(auth_api):
    response = auth_api.get(f"{WIDGETS}missing/permissions/")
    assert response.status_code == 200
    assert response.json() == {"message": {"permissions": {}}}


# --- A-31 finding 8: a missing or unlisted field is a 417, never a 500 ------------------


def test_get_single_value_without_a_field_is_refused(auth_api, administrator):
    SingletonDocument.load(user=administrator)
    response = auth_api.get(SINGLETON_VALUE)
    assert response.status_code == 417
    assert response.json()["exc_type"] == "ValidationError"


def test_get_single_value_refuses_a_field_outside_the_list(auth_api, administrator):
    SingletonDocument.load(user=administrator)
    response = auth_api.get(SINGLETON_VALUE, {"field": "no_such_field"})
    assert response.status_code == 417
    assert response.json()["message"] == "Field 'no_such_field' is not readable"


def test_get_single_value_answers_a_link_by_its_stored_name(auth_api, administrator):
    SingletonDocument.load(user=administrator)
    response = auth_api.get(SINGLETON_VALUE, {"field": "owner"})
    assert response.status_code == 200, response.content[:300]
    assert response.json() == {"message": "Administrator"}
