"""PE-24 (owner, 20 Nov 2026; temp A-48 3c, A-63 item 1): rename is served where
upstream's `allow_rename` is on, for the resources already built, and needs the
resource's write rule; PE-31 sets a `FieldValue` naming field. New: the old backend's
rename call takes any doctype, so no old test pins these resources.
"""

import pytest

from configuration.models import Country, CRMFieldsLayout, CRMFormScript, Currency
from contacts.models import Address, CRMIndustry, DynamicLink, Salutation

pytestmark = pytest.mark.django_db


def rename(client, resource, name, new_name):
    return client.post(f"/api/v1/{resource}/{name}/rename/", {"new_name": new_name}, format="json")


@pytest.fixture
def boss(make_user):
    return make_user("boss@example.com", roles=["System Manager"])


@pytest.fixture
def manager(make_user):
    return make_user("manager@example.com", roles=["Sales Manager"])


def test_a_currency_is_renamed_with_its_unique_naming_field(boss, administrator, api_as):
    Currency(currency_name="TST", enabled=True).save(user=administrator)
    response = rename(api_as(boss), "currencies", "TST", "TSX")
    assert response.status_code == 200, response.content[:300]
    assert response.json() == {"message": "TSX"}
    assert Currency.objects.get(pk="TSX").currency_name == "TSX"
    assert not Currency.objects.filter(pk="TST").exists()


def test_a_salutation_takes_the_new_name_in_its_field(boss, administrator, api_as):
    Salutation(salutation="Captain").save(user=administrator)
    assert rename(api_as(boss), "salutations", "Captain", "Capt").status_code == 200
    assert Salutation.objects.get(pk="Capt").salutation == "Capt"


def test_an_industry_is_renamed_by_a_crm_user(alice, administrator, api_as):
    CRMIndustry(industry="Robotics").save(user=administrator)
    assert rename(api_as(alice), "industries", "Robotics", "Robots").status_code == 200
    assert CRMIndustry.objects.get(pk="Robots").industry == "Robots"


def test_an_address_keeps_its_links_through_a_rename(alice, administrator, api_as):
    address = Address(
        address_title="Depot", address_type="Office", address_line1="1 Main St",
        city="Pune", country=Country.objects.get(pk="India"),
    )
    address.save(user=administrator)
    DynamicLink(
        parenttype="Address", parent=str(address.pk), parentfield="links", idx=1,
        link_doctype="User", link_name=alice.name,
    ).save(user=administrator)

    response = rename(api_as(alice), "addresses", address.pk, "Depot-North")
    assert response.status_code == 200, response.content[:300]
    assert DynamicLink.objects.filter(parenttype="Address", parent="Depot-North").count() == 1
    assert not DynamicLink.objects.filter(parenttype="Address", parent=address.pk).exists()


def test_a_fields_layout_is_renamed_by_the_manager_pair(manager, administrator, api_as):
    CRMFieldsLayout(dt="CRM Task", type="Side Panel", layout="[]").save(user=administrator)
    response = rename(api_as(manager), "fields-layouts", "CRM Task-Side Panel", "Task Panel")
    assert response.status_code == 200, response.content[:300]
    assert CRMFieldsLayout.objects.filter(pk="Task Panel", dt="CRM Task").exists()


def test_a_form_script_is_renamed_by_a_system_manager(boss, administrator, api_as):
    CRMFormScript(name="Old Script", dt="CRM Task").save(user=administrator)
    assert rename(api_as(boss), "form-scripts", "Old Script", "New Script").status_code == 200
    assert CRMFormScript.objects.filter(pk="New Script").exists()


@pytest.mark.parametrize(
    "resource,model,values,name",
    [
        ("currencies", Currency, {"currency_name": "TST"}, "TST"),
        ("salutations", Salutation, {"salutation": "Captain"}, "Captain"),
        ("form-scripts", CRMFormScript, {"name": "Old Script", "dt": "CRM Task"}, "Old Script"),
    ],
)
def test_a_caller_without_the_write_rule_is_refused(
    alice, administrator, api_as, resource, model, values, name
):
    model(**values).save(user=administrator)
    response = rename(api_as(alice), resource, name, "Other")
    assert response.status_code == 417
    assert response.json()["message"].startswith("You need write permission on")
    assert model.objects.filter(pk=name).exists()


def test_an_outsider_cannot_rename_an_industry(make_user, administrator, api_as):
    """PE-29's rule is the write rule rename asks."""
    CRMIndustry(industry="Robotics").save(user=administrator)
    response = rename(api_as(make_user("outsider@example.com")), "industries", "Robotics", "Robots")
    assert response.status_code == 417
    assert CRMIndustry.objects.filter(pk="Robotics").exists()


@pytest.mark.parametrize(
    "resource",
    [
        "genders",
        "countries",
        "languages",
        "view-settings",
        "global-settings",
        "sales-hierarchies",
        # Upstream allows these two; they wait for ACCOUNTS §10 (PE-24).
        "users",
        "invitations",
    ],
)
def test_no_rename_where_upstream_allows_none(boss, api_as, resource):
    response = rename(api_as(boss), resource, "anything", "other")
    assert response.status_code in (404, 405)
