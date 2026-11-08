"""Data Import and Data Import Log's model, route, and metadata contract."""

from __future__ import annotations

import re
from urllib.parse import quote

import pytest

from frappe_core.session import session_user
from frappe_platform.models import DataImport, DataImportLog

pytestmark = pytest.mark.django_db

METHOD = "/api/method/frappe.client."


@pytest.fixture
def system_manager(make_user):
    return make_user("sysmgr-import@example.com", roles=["System Manager"])


@pytest.fixture
def sales_manager(make_user):
    return make_user(
        "sales-manager-import@example.com", roles=["Sales Manager", "Sales User"]
    )


def _payload(**changes):
    payload = {
        "reference_doctype": "Contact",
        "import_type": "Insert New Records",
        "mute_emails": True,
        "google_sheets_url": "",
    }
    payload.update(changes)
    return payload


def _method(client, method, body):
    return client.post(METHOD + method, body, format="json")


def _insert(client, **changes):
    return _method(
        client,
        "insert",
        {"doc": {"doctype": "Data Import", **_payload(**changes)}},
    )


def _detail(name):
    return f"/api/resource/Data Import/{quote(name, safe='')}"


def test_names_use_the_reference_doctype_and_generation_time(administrator):
    with session_user(administrator.name):
        first = DataImport.objects.create(**_payload())
        second = DataImport.objects.create(**_payload())

    pattern = r"^Contact Import on \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{6}$"
    assert re.fullmatch(pattern, first.name)
    assert re.fullmatch(pattern, second.name)
    assert first.name != second.name


def test_system_manager_can_create_list_and_set_value(api_as, system_manager):
    client = api_as(system_manager)
    response = client.post("/api/resource/Data Import", _payload(), format="json")
    assert response.status_code == 201, response.content[:500]
    document = response.json()["data"]

    response = client.get("/api/resource/Data Import")
    assert response.status_code == 200, response.content[:500]
    assert [row["name"] for row in response.json()["data"]] == [document["name"]]

    response = _method(
        client,
        "set_value",
        {
            "doctype": "Data Import",
            "name": document["name"],
            "fieldname": {"template_options": '{"column_to_field_map": {}}'},
        },
    )
    assert response.status_code == 200, response.content[:500]
    assert response.json()["message"]["template_options"] == '{"column_to_field_map": {}}'


def test_status_posted_on_insert_is_ignored(api_as, system_manager):
    response = _insert(api_as(system_manager), status="Success")
    assert response.status_code == 200, response.content[:500]
    assert response.json()["message"]["status"] == "Pending"


def test_set_value_ignores_whole_document_junk_and_returns_the_full_doc(
    api_as, system_manager
):
    client = api_as(system_manager)
    inserted = _insert(client).json()["message"]
    response = _method(
        client,
        "set_value",
        {
            "doctype": "Data Import",
            "name": inserted["name"],
            "fieldname": {
                **inserted,
                "template_options": '{"column_to_field_map": {"0": "first_name"}}',
                "creation": "1900-01-01T00:00:00Z",
                "owner": "Guest",
                "doctype": "Data Import",
                "_previousData": {"status": "Pending"},
            },
        },
    )

    assert response.status_code == 200, response.content[:500]
    document = response.json()["message"]
    assert document["name"] == inserted["name"]
    assert document["doctype"] == "Data Import"
    assert document["owner"] == system_manager.name
    assert document["creation"] == inserted["creation"]
    assert document["template_options"] == (
        '{"column_to_field_map": {"0": "first_name"}}'
    )


@pytest.mark.parametrize("actor", ["sales_manager", "alice"])
def test_sales_roles_cannot_use_resource_routes(
    api_as, request, actor, system_manager
):
    admin = api_as(system_manager)
    document = _insert(admin).json()["message"]
    client = api_as(request.getfixturevalue(actor))

    response = client.get("/api/resource/Data Import")
    assert response.status_code == 200, response.content[:500]
    assert response.json()["data"] == []
    assert client.get(_detail(document["name"])).status_code == 403
    assert client.post("/api/resource/Data Import", _payload(), format="json").status_code == 403
    assert client.put(_detail(document["name"]), {"mute_emails": False}, format="json").status_code == 403
    assert client.delete(_detail(document["name"])).status_code == 403


@pytest.mark.parametrize("actor", ["sales_manager", "alice"])
def test_sales_roles_cannot_use_frappe_client_methods(
    api_as, request, actor, system_manager
):
    admin = api_as(system_manager)
    document = _insert(admin).json()["message"]
    client = api_as(request.getfixturevalue(actor))

    response = _method(client, "get_list", {"doctype": "Data Import"})
    assert response.status_code == 200, response.content[:500]
    assert response.json()["message"] == []
    assert _insert(client).status_code == 403
    assert _method(
        client,
        "set_value",
        {
            "doctype": "Data Import",
            "name": document["name"],
            "fieldname": {"mute_emails": False},
        },
    ).status_code == 403
    assert _method(
        client,
        "delete",
        {"doctype": "Data Import", "name": document["name"]},
    ).status_code == 403


@pytest.mark.parametrize("actor", ["sales_manager", "alice"])
def test_data_import_log_is_still_refused_through_frappe_client(
    api_as, request, actor, system_manager, administrator
):
    with session_user(administrator.name):
        parent = DataImport.objects.create(**_payload())
        log = DataImportLog.objects.create(data_import=parent.name, log_index=1)
    client = api_as(request.getfixturevalue(actor))

    response = _method(client, "get_list", {"doctype": "Data Import Log"})
    assert response.status_code == 200, response.content[:500]
    assert response.json()["message"] == []
    assert _method(
        client,
        "get",
        {"doctype": "Data Import Log", "name": log.name},
    ).status_code == 403
    assert _method(
        client,
        "insert",
        {
            "doc": {
                "doctype": "Data Import Log",
                "data_import": parent.name,
                "log_index": 2,
            }
        },
    ).status_code == 403
    assert _method(
        client,
        "set_value",
        {
            "doctype": "Data Import Log",
            "name": log.name,
            "fieldname": {"success": True},
        },
    ).status_code == 403
    assert _method(
        client,
        "delete",
        {"doctype": "Data Import Log", "name": log.name},
    ).status_code == 403


def test_deleting_a_data_import_deletes_its_logs(
    api_as, system_manager, administrator
):
    with session_user(administrator.name):
        parent = DataImport.objects.create(**_payload())
        log = DataImportLog.objects.create(data_import=parent.name, log_index=1)

    response = _method(
        api_as(system_manager),
        "delete",
        {"doctype": "Data Import", "name": parent.name},
    )
    assert response.status_code == 200, response.content[:500]
    assert not DataImportLog.objects.filter(pk=log.name).exists()


def test_contact_getdoctype_includes_both_tables_and_child_metas(auth_api):
    response = auth_api.post(
        "/api/method/frappe.desk.form.load.getdoctype",
        {"doctype": "Contact"},
        format="json",
    )
    assert response.status_code == 200, response.content[:500]
    docs = response.json()["docs"]
    assert [doc["name"] for doc in docs] == [
        "Contact",
        "Contact Email",
        "Contact Phone",
    ]

    fields = {field["fieldname"]: field for field in docs[0]["fields"]}
    assert fields["email_ids"] == {
        "fieldname": "email_ids",
        "fieldtype": "Table",
        "label": "Email IDs",
        "options": "Contact Email",
        "idx": fields["email_ids"]["idx"],
    }
    assert fields["phone_nos"] == {
        "fieldname": "phone_nos",
        "fieldtype": "Table",
        "label": "Contact Numbers",
        "options": "Contact Phone",
        "idx": fields["phone_nos"]["idx"],
    }
    assert "links" not in fields
