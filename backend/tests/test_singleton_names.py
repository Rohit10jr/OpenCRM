"""A single's one row is named after its doctype, as upstream names it: FINDINGS.md 37.

``frappe.get_single("FCRM Settings")`` loads the document named ``FCRM Settings``, and the
frontend hardcodes that name in five places. Phase 1 named the row ``Settings`` instead,
so every settings screen answered 404 the first time the app ran in a browser.
"""

import json
from urllib.parse import quote

import pytest

from crm_app.models import CRMTwilioSettings, FCRMSettings
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

FCRM = "/api/resource/" + quote("FCRM Settings")


def test_a_loaded_singleton_is_named_after_its_doctype(administrator):
    with session_user(administrator.name):
        assert FCRMSettings.load().pk == "FCRM Settings"
        assert CRMTwilioSettings.load().pk == "CRM Twilio Settings"


def test_a_created_singleton_takes_the_same_name(administrator):
    with session_user(administrator.name):
        row = FCRMSettings.objects.create(brand_name="Acme")
    assert row.pk == "FCRM Settings"


def test_the_frontend_can_fetch_it_by_that_name(api_as, alice, administrator):
    """``stores/settings.js`` and ``router.js`` ask for doctype and name both
    ``FCRM Settings``, through ``frappe.client.get`` and the resource route."""
    with session_user(administrator.name):
        FCRMSettings.objects.create(brand_name="Acme")

    client = api_as(alice)
    response = client.post(
        "/api/method/frappe.client.get",
        {"doctype": "FCRM Settings", "name": "FCRM Settings"},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"]["name"] == "FCRM Settings"

    response = client.get(FCRM + "/" + quote("FCRM Settings"))
    assert response.status_code == 200, response.content[:300]
    assert response.json()["data"]["brand_name"] == "Acme"


def test_a_second_row_is_refused_with_the_doctype_name(api_as, administrator):
    """FINDINGS.md 25's sentence, now with upstream's name for the single."""
    with session_user(administrator.name):
        FCRMSettings.objects.create(brand_name="Acme")

    response = api_as(administrator).post(FCRM, {"brand_name": "Again"}, format="json")
    assert response.status_code == 409, response.content[:300]
    body = response.json()
    assert body["message"] == "FCRM Settings <strong>FCRM Settings</strong> already exists"
    assert json.loads(json.loads(body["_server_messages"])[0])["title"] == "Duplicate Name"
