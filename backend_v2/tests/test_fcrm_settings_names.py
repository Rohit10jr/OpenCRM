"""Ported from ``backend/tests/test_singleton_names.py:21-50``, the FCRM Settings half
(REBUILD_PLAN S14); CRM Twilio Settings is INTEGRATIONS'. (backend_v2's own
`tests/test_singleton_names.py` covers the FOUNDATION singleton stack.)

A single's one row is named after its doctype. `frappe.client.get` and the resource route
on FCRM Settings are `GET /api/v1/crm-settings/` (specs/CONFIGURATION.md 4.3); the old
resource answered under `data`, the singleton under `message`. The old fixture created
the row; here the data migration has written it. `test_a_second_row_is_refused_with_the_doctype_name`
(409 in backend/) is `12` 1.14: the singleton route has no POST and answers 405 (PE-1).
"""

import pytest

from configuration.models import FCRMSettings

pytestmark = pytest.mark.django_db

SETTINGS = "/api/v1/crm-settings/"


def test_a_loaded_singleton_is_named_after_its_doctype(administrator):
    assert FCRMSettings.load_or_create(user=administrator).pk == "FCRM Settings"


def test_a_created_singleton_takes_the_same_name(administrator):
    FCRMSettings.objects.all().delete()
    row = FCRMSettings(brand_name="Acme")
    row.save(user=administrator)
    assert row.pk == "FCRM Settings"


def test_the_frontend_can_fetch_it_by_that_name(api_as, alice):
    FCRMSettings.objects.filter(pk="FCRM Settings").update(brand_name="Acme")
    response = api_as(alice).get(SETTINGS)
    assert response.status_code == 200, response.content[:300]
    body = response.json()["message"]
    assert (body["name"], body["brand_name"]) == ("FCRM Settings", "Acme")


def test_a_second_row_is_refused(api_as, administrator):
    """405 under PE-1 (409 "already exists" in backend/)."""
    response = api_as(administrator).post(SETTINGS, {"brand_name": "Again"}, format="json")
    assert response.status_code == 405, response.content[:300]
    assert FCRMSettings.objects.count() == 1
