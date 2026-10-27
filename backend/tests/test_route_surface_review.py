"""The final six decisions in the routable-doctype review (Brief 10).

The four open doctypes reproduce upstream's full-CRUD grant to every CRM role. SLA
policies reproduce the manager-only role table, while internal policy selection remains
available to a Sales User's lead save. Tag reproduces version-15's split: everybody may
read, write and create a tag name, but only System Manager may delete one.
"""

from urllib.parse import quote

import pytest

from crm_app.models import CRMLead, CRMLeadStatus, CRMServiceLevelAgreement
from frappe_core.doc_caches import add_tag, get_tags
from frappe_core.session import session_user
from frappe_platform.models import Tag

pytestmark = pytest.mark.django_db

RESOURCE = "/api/resource/"
CLIENT_GET = "/api/method/frappe.client.get"


@pytest.fixture
def sales_manager(make_user):
    return make_user(
        "route-manager@example.com",
        first_name="Route Manager",
        roles=["Sales Manager"],
    )


@pytest.fixture
def system_manager(make_user):
    return make_user(
        "route-system@example.com",
        first_name="Route System",
        roles=["System Manager"],
    )


def _resource(doctype: str, name: str | None = None) -> str:
    path = RESOURCE + quote(doctype)
    return f"{path}/{quote(name)}" if name is not None else path


@pytest.fixture
def sla_policy(system_manager):
    with session_user(system_manager.name):
        return CRMServiceLevelAgreement.objects.create(
            sla_name="Route Review SLA",
            apply_on="CRM Lead",
            enabled=True,
            default=True,
        )


def test_a_sales_user_cannot_access_sla_policies(auth_api, sla_policy):
    url = _resource("CRM Service Level Agreement")
    detail = _resource("CRM Service Level Agreement", sla_policy.pk)

    assert auth_api.get(url).json()["data"] == []
    assert auth_api.get(detail).status_code == 403
    assert auth_api.post(
        url,
        {"sla_name": "Sales User SLA", "apply_on": "CRM Lead"},
        format="json",
    ).status_code == 403
    assert auth_api.put(detail, {"enabled": False}, format="json").status_code == 403
    assert auth_api.delete(detail).status_code == 403
    assert auth_api.post(
        CLIENT_GET,
        {"doctype": "CRM Service Level Agreement", "name": sla_policy.pk},
        format="json",
    ).status_code == 403

    sla_policy.refresh_from_db()
    assert sla_policy.enabled is True


@pytest.mark.parametrize("actor_fixture", ["sales_manager", "system_manager"])
def test_each_manager_can_do_everything_to_an_sla(
    api_as, request, actor_fixture, sla_policy
):
    actor = request.getfixturevalue(actor_fixture)
    client = api_as(actor)
    name = f"{actor_fixture} SLA"
    url = _resource("CRM Service Level Agreement")

    created = client.post(
        url,
        {"sla_name": name, "apply_on": "CRM Deal", "enabled": True},
        format="json",
    )
    assert created.status_code == 201, created.content[:300]
    assert client.get(_resource("CRM Service Level Agreement", name)).status_code == 200
    assert any(row["name"] == name for row in client.get(url).json()["data"])
    assert client.post(
        CLIENT_GET,
        {"doctype": "CRM Service Level Agreement", "name": name},
        format="json",
    ).status_code == 200

    changed = client.put(
        _resource("CRM Service Level Agreement", name),
        {"enabled": False},
        format="json",
    )
    assert changed.status_code == 200, changed.content[:300]
    assert client.delete(_resource("CRM Service Level Agreement", name)).status_code == 200
    assert not CRMServiceLevelAgreement.objects.filter(pk=name).exists()


def test_a_sales_users_new_lead_still_gets_an_sla(auth_api, alice, sla_policy):
    with session_user("Administrator"):
        CRMLeadStatus.objects.create(lead_status="New", type="Open")

    response = auth_api.post(
        _resource("CRM Lead"),
        {"first_name": "SLA Route", "lead_owner": alice.name},
        format="json",
    )

    assert response.status_code == 201, response.content[:300]
    lead = CRMLead.objects.get(pk=response.json()["data"]["name"])
    assert lead.sla_id == sla_policy.pk


def test_a_sales_user_can_create_read_write_and_apply_a_tag(auth_api, alice):
    url = _resource("Tag")
    # The port's Tag has no field but its name (the tag text), so create sends the name
    # and the write sends nothing to change; a 200 is the write permission being granted.
    created = auth_api.post(url, {"name": "route-review"}, format="json")
    assert created.status_code == 201, created.content[:300]
    assert auth_api.get(_resource("Tag", "route-review")).status_code == 200

    changed = auth_api.put(_resource("Tag", "route-review"), {}, format="json")
    assert changed.status_code == 200, changed.content[:300]

    with session_user(alice.name):
        status = CRMLeadStatus.objects.create(lead_status="Taggable", type="Open")
        lead = CRMLead.objects.create(
            status=status,
            first_name="Tagged",
            lead_owner=alice,
        )
        add_tag(lead, "route-review")

    lead.refresh_from_db()
    assert get_tags(lead) == ["route-review"]
    assert Tag.objects.filter(pk="route-review").exists()


@pytest.mark.parametrize("actor_fixture", ["alice", "sales_manager"])
def test_a_sales_user_and_sales_manager_cannot_delete_a_tag(
    api_as, request, actor_fixture
):
    tag = Tag.objects.create(name=f"keep-{actor_fixture}")
    response = api_as(request.getfixturevalue(actor_fixture)).delete(
        _resource("Tag", tag.pk)
    )
    assert response.status_code == 403
    assert Tag.objects.filter(pk=tag.pk).exists()


def test_a_system_manager_can_delete_a_tag(api_as, system_manager):
    tag = Tag.objects.create(name="delete-system-manager")
    response = api_as(system_manager).delete(_resource("Tag", tag.pk))
    assert response.status_code == 200, response.content[:300]
    assert not Tag.objects.filter(pk=tag.pk).exists()


@pytest.mark.parametrize(
    ("doctype", "payload"),
    [
        ("CRM Organization", {"organization_name": "Route Review Org"}),
        (
            "CRM Call Log",
            {
                "id": "route-review-call",
                "status": "Completed",
                "type": "Outgoing",
                "from": "+1 111",
                "to": "+1 222",
            },
        ),
        ("CRM Telephony Agent", None),
        ("CRM Product", {"product_code": "ROUTE-REVIEW-PRODUCT"}),
    ],
)
def test_a_sales_user_can_create_and_read_each_reviewed_open_doctype(
    auth_api, alice, doctype, payload
):
    if doctype == "CRM Telephony Agent":
        payload = {"user": alice.name}

    response = auth_api.post(_resource(doctype), payload, format="json")
    assert response.status_code == 201, response.content[:300]
    name = response.json()["data"]["name"]
    assert auth_api.get(_resource(doctype, name)).status_code == 200
