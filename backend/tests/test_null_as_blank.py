"""Clearing a text field with ``null``: docs/FINDINGS.md 68.

Upstream's ``frappe.client.set_value`` takes None for any field and ``doc.set`` stores
it; the frontend relies on that. "Remove Image" on an organization's page sends
``organization_logo: null`` (``Organization.vue``). The port's text columns are
``blank=True, null=False`` and DRF refused the null, so the logo could be changed but
never removed.
"""

from urllib.parse import quote

import pytest

from crm_app.models import CRMOrganization
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

LOGO = "/files/acme.png"


@pytest.fixture
def acme(administrator):
    with session_user(administrator.name):
        return CRMOrganization.objects.create(
            organization_name="Acme",
            organization_logo=LOGO,
            website="https://acme.example.com",
            no_of_employees="11-50",
        )


def test_remove_image_clears_the_logo(auth_api, acme):
    """Exactly what the Remove Image menu item sends."""
    response = auth_api.post(
        "/api/method/frappe.client.set_value",
        {"doctype": "CRM Organization", "name": acme.name, "fieldname": {"organization_logo": None}},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"]["organization_logo"] == ""
    acme.refresh_from_db()
    assert acme.organization_logo == ""


def test_null_empties_text_and_select_fields_on_the_resource_route_too(auth_api, acme):
    response = auth_api.put(
        "/api/resource/" + quote("CRM Organization") + "/" + quote(acme.name),
        {"organization_logo": None, "website": None, "no_of_employees": None},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    acme.refresh_from_db()
    assert (acme.organization_logo, acme.website, acme.no_of_employees) == ("", "", "")


def test_a_field_left_out_is_untouched(auth_api, acme):
    """Partial writes stay partial: only the named field is emptied."""
    response = auth_api.post(
        "/api/method/frappe.client.set_value",
        {"doctype": "CRM Organization", "name": acme.name, "fieldname": "website", "value": None},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    acme.refresh_from_db()
    assert acme.website == ""
    assert acme.organization_logo == LOGO
