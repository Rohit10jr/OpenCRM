"""``frappe.client.get_value``: docs/FINDINGS.md 47.

The seeded forecasting script asks it for a deal status's probability whenever a deal's
status changes; the port never served it. Shapes follow ``frappe/client.py:get_value``.
"""

import pytest

from crm_app.models import CRMDealStatus
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

PATH = "/api/method/frappe.client.get_value"


@pytest.fixture
def won(administrator):
    with session_user(administrator.name):
        return CRMDealStatus.objects.create(
            deal_status="Won", color="green", type="Won", probability=100, position=6
        )


def get_value(client, **params):
    response = client.post(PATH, params, format="json")
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]


def test_the_forecasting_scripts_call(auth_api, won):
    """``call("frappe.client.get_value", {doctype, fieldname: "probability", filters:
    {name: status}})`` - the exact call the seeded script makes."""
    value = get_value(
        auth_api, doctype="CRM Deal Status", fieldname="probability", filters={"name": "Won"}
    )
    assert value == {"probability": 100.0}


def test_several_fields_and_a_name_as_the_filter(auth_api, won):
    value = get_value(
        auth_api, doctype="CRM Deal Status", fieldname=["probability", "color"], filters="Won"
    )
    assert value == {"probability": 100.0, "color": "green"}


def test_the_default_field_is_the_name(auth_api, won):
    assert get_value(auth_api, doctype="CRM Deal Status", filters="Won") == {"name": "Won"}


def test_without_as_dict_the_bare_values_come_back(auth_api, won):
    one = get_value(
        auth_api, doctype="CRM Deal Status", fieldname="probability", filters="Won", as_dict=0
    )
    assert one == 100.0
    several = get_value(
        auth_api,
        doctype="CRM Deal Status",
        fieldname=["probability", "color"],
        filters="Won",
        as_dict=0,
    )
    assert several == [100.0, "green"]
    none = get_value(
        auth_api, doctype="CRM Deal Status", fieldname="probability", filters="Lost", as_dict=0
    )
    assert none is None


def test_no_match_answers_an_empty_dict(auth_api, won):
    value = get_value(auth_api, doctype="CRM Deal Status", fieldname="probability", filters="Lost")
    assert value == {}


def test_an_unknown_doctype_is_404(auth_api):
    response = auth_api.post(PATH, {"doctype": "No Such Thing", "fieldname": "name"}, format="json")
    assert response.status_code == 404
    assert response.json()["exc_type"] == "DoesNotExistError"


def test_the_row_rules_apply(api_as, alice, administrator):
    """The rows come through ``fetch_rows`` like ``get_list``'s, so a doctype a Sales User
    may not read answers nothing rather than leaking a field."""
    from crm_app.models import CRMTwilioSettings

    with session_user(administrator.name):
        CRMTwilioSettings.load()
    response = api_as(alice).post(
        PATH, {"doctype": "CRM Twilio Settings", "fieldname": "enabled"}, format="json"
    )
    assert response.status_code in (200, 403), response.content[:300]
    if response.status_code == 200:
        assert response.json()["message"] == {}
