"""The ``System Settings`` single: docs/FINDINGS.md 64.

Settings -> Defaults loads the framework's ``System Settings`` and its metadata and
offers six fields (``DefaultsSettings.vue``). The port had neither, so the section went
blank (BROWSER_TESTING.md S5). The formats themselves came from
``settings.FRAPPE_SYSDEFAULTS`` through the boot call; now the row is where they live,
and the boot call reads it.

``system_settings.json`` gives the doctype to System Manager alone, reading included. A
Sales Manager is still offered the page and is refused, as upstream does
(``UPSTREAM_BUGS.md`` 50).
"""

import pytest

from frappe_platform.models import SYSDEFAULT_FIELDS, SystemSettings

pytestmark = pytest.mark.django_db

BOOT = "/api/method/crm.www.crm.get_context_for_dev"
GET = "/api/method/frappe.client.get"
SET_VALUE = "/api/method/frappe.client.set_value"
GETDOCTYPE = "/api/method/frappe.desk.form.load.getdoctype"
NAME = {"doctype": "System Settings", "name": "System Settings"}


def sysdefaults(client) -> dict:
    response = client.post(BOOT, {}, format="json")
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]["sysdefaults"]


def set_values(client, **values):
    return client.post(SET_VALUE, {**NAME, "fieldname": values}, format="json")


@pytest.fixture
def grace(make_user):
    return make_user("grace@example.com", first_name="Grace", roles=["Sales Manager", "Sales User"])


def test_the_row_starts_from_the_environments_formats(api, settings):
    """Migration 0019 wrote it from ``FRAPPE_SYSDEFAULTS``, so nothing changed the day it
    landed; the boot call answers the row."""
    row = SystemSettings.load()
    expected = {field: str(settings.FRAPPE_SYSDEFAULTS[field]) for field in SYSDEFAULT_FIELDS}
    assert row.sysdefaults() == expected
    assert sysdefaults(api) == expected


def test_the_defaults_page_loads_the_row_and_its_options(api_as, administrator):
    client = api_as(administrator)
    response = client.post(GET, NAME, format="json")
    assert response.status_code == 200, response.content[:300]
    doc = response.json()["message"]
    assert doc["name"] == "System Settings"
    assert doc["date_format"] == SystemSettings.load().date_format

    response = client.post(GETDOCTYPE, {"doctype": "System Settings"}, format="json")
    assert response.status_code == 200, response.content[:300]
    fields = {f["fieldname"]: f for f in response.json()["docs"][0]["fields"]}
    assert fields["date_format"]["fieldtype"] == "Select"
    assert fields["date_format"]["options"].split("\n") == [
        "yyyy-mm-dd", "dd-mm-yyyy", "dd/mm/yyyy", "dd.mm.yyyy", "mm/dd/yyyy", "mm-dd-yyyy",
    ]
    assert fields["time_format"]["options"].split("\n") == ["HH:mm:ss", "HH:mm"]
    assert fields["float_precision"]["options"].split("\n")[:2] == ["", "2"]
    assert fields["currency_precision"]["options"].split("\n")[:2] == ["", "0"]
    assert fields["number_format"]["options"].split("\n")[0] == "#,###.##"
    assert (fields["currency"]["fieldtype"], fields["currency"]["options"]) == ("Link", "Currency")


def test_a_saved_format_reaches_every_users_boot(api_as, administrator, auth_api):
    """The page saves through ``frappe.client.set_value`` with the changed fields
    (frappe-ui ``documentResource.save``); the next boot formats with them."""
    response = set_values(api_as(administrator), date_format="dd.mm.yyyy", currency="EUR")
    assert response.status_code == 200, response.content[:300]
    defaults = sysdefaults(auth_api)
    assert (defaults["date_format"], defaults["currency"]) == ("dd.mm.yyyy", "EUR")


def test_a_required_format_cannot_be_blanked_and_a_currency_must_exist(api_as, administrator):
    client = api_as(administrator)
    before = SystemSettings.load().date_format
    assert set_values(client, date_format="").status_code == 417
    assert set_values(client, currency="XYZ").status_code == 417
    row = SystemSettings.load()
    assert (row.date_format, row.currency) == (before, "")


@pytest.mark.parametrize("who", ["alice", "grace"])
def test_only_a_system_manager_reads_or_writes_it(api_as, request, who):
    """A Sales Manager is offered the page upstream and refused the data
    (``UPSTREAM_BUGS.md`` 50); the boot call still carries the formats."""
    client = api_as(request.getfixturevalue(who))
    assert client.post(GET, NAME, format="json").status_code == 403
    assert set_values(client, date_format="dd-mm-yyyy").status_code == 403
    assert client.get("/api/resource/System Settings/System Settings").status_code in (403, 404)
    assert SystemSettings.load().date_format != "dd-mm-yyyy"
    assert sysdefaults(client)["date_format"]


def test_a_missing_row_is_written_again_on_the_next_boot(api):
    """A ``transaction=True`` test empties the table; ``utils/index.js:82`` reads
    ``sysdefaults.date_format`` unguarded, so the boot call must never lack it."""
    SystemSettings.objects.all().delete()
    assert sysdefaults(api)["date_format"]
    assert SystemSettings.objects.count() == 1


def test_nobody_deletes_it(api_as, administrator):
    """``system_settings.json`` grants no delete; the boot call depends on the row."""
    client = api_as(administrator)
    response = client.post(
        "/api/method/frappe.client.delete", NAME, format="json"
    )
    assert response.status_code == 403, response.content[:300]
    assert SystemSettings.objects.filter(pk="System Settings").exists()
