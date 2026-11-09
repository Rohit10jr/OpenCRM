"""Data Import save validation and CSV preview contract."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
import pytest

from frappe_core.exceptions import ValidationError
from frappe_core.session import session_user
from frappe_platform import files as file_store
from frappe_platform.models import DataImport, DataImportLog, File

pytestmark = pytest.mark.django_db

METHOD = "/api/method/"
PREVIEW = METHOD + "frappe.core.doctype.data_import.data_import.get_preview_from_template"


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def system_manager(make_user):
    return make_user("sysmgr-validation@example.com", roles=["System Manager"])


@pytest.fixture
def other_system_manager(make_user):
    return make_user("other-sysmgr-validation@example.com", roles=["System Manager"])


@pytest.fixture
def sales_manager(make_user):
    return make_user(
        "sales-manager-validation@example.com", roles=["Sales Manager", "Sales User"]
    )


def upload(client, name="contacts.csv", content=b"First Name,Last Name\nAda,Lovelace\n"):
    response = client.post(
        METHOD + "upload_file",
        {
            "file": SimpleUploadedFile(name, content, content_type="text/csv"),
            "is_private": 1,
        },
        format="multipart",
    )
    assert response.status_code == 200, response.content[:500]
    return response.json()["message"]


def insert(client, **changes):
    doc = {
        "doctype": "Data Import",
        "reference_doctype": "Contact",
        "import_type": "Insert New Records",
        "mute_emails": True,
        "google_sheets_url": "",
        **changes,
    }
    return client.post(METHOD + "frappe.client.insert", {"doc": doc}, format="json")


def set_value(client, name, fields):
    return client.post(
        METHOD + "frappe.client.set_value",
        {"doctype": "Data Import", "name": name, "fieldname": fields},
        format="json",
    )


def message(response):
    return response.json()["messages"][0]


def test_uploaded_csv_attaches_and_sets_payload_count(api_as, system_manager, media):
    client = api_as(system_manager)
    uploaded = upload(client, content=b"First Name\nAda\nGrace\n")
    response = insert(client, import_file=uploaded["file_url"])

    assert response.status_code == 200, response.content[:500]
    document = response.json()["message"]
    assert document["payload_count"] == 2
    file_doc = File.objects.get(pk=uploaded["name"])
    assert (file_doc.attached_to_doctype, file_doc.attached_to_name) == (
        "Data Import",
        document["name"],
    )


def test_changing_the_file_clears_template_options(api_as, system_manager, media):
    client = api_as(system_manager)
    first = upload(client, "first.csv")
    document = insert(client, import_file=first["file_url"]).json()["message"]
    mapped = set_value(
        client,
        document["name"],
        {"template_options": '{"column_to_field_map": {"0": "first_name"}}'},
    )
    assert mapped.json()["message"]["template_options"] != ""

    second = upload(client, "second.csv", b"First Name\nGrace\n")
    changed = set_value(
        client,
        document["name"],
        {
            **mapped.json()["message"],
            "import_file": second["file_url"],
            "template_options": mapped.json()["message"]["template_options"],
        },
    )
    assert changed.status_code == 200, changed.content[:500]
    assert changed.json()["message"]["template_options"] == ""


def test_insert_with_a_file_keeps_template_options(api_as, system_manager, media):
    client = api_as(system_manager)
    uploaded = upload(client)
    options = '{"column_to_field_map": {"0": "first_name"}}'

    response = insert(
        client,
        import_file=uploaded["file_url"],
        template_options=options,
    )

    assert response.status_code == 200, response.content[:500]
    assert response.json()["message"]["template_options"] == options


def test_insert_without_a_file_clears_template_options(api_as, system_manager):
    response = insert(
        api_as(system_manager),
        template_options='{"column_to_field_map": {"0": "first_name"}}',
    )

    assert response.status_code == 200, response.content[:500]
    assert response.json()["message"]["template_options"] == ""


def test_job_saves_skip_validation_but_other_partial_saves_do_not(
    api_as, system_manager, media
):
    client = api_as(system_manager)
    uploaded = upload(client, content=b"First Name\nAda\nGrace\n")
    document = insert(client, import_file=uploaded["file_url"]).json()["message"]
    data_import = DataImport.objects.get(pk=document["name"])
    original_payload_count = data_import.payload_count
    file_store.path_for_url(data_import.import_file).unlink()

    with session_user(system_manager.name):
        data_import.status = "Success"
        data_import.save(update_fields=["status"])

    data_import.refresh_from_db()
    assert data_import.status == "Success"
    assert data_import.payload_count == original_payload_count

    with session_user(system_manager.name):
        data_import.mute_emails = False
        with pytest.raises(ValidationError, match="Invalid template file for import"):
            data_import.save(update_fields=["mute_emails"])


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        (
            {"reference_doctype": "User"},
            "Data Import is not allowed for User. Enable 'Allow Import' in DocType settings.",
        ),
        (
            {"google_sheets_url": "https://docs.google.com/sheets/d/one"},
            "Google Sheets imports are not supported",
        ),
        (
            {"import_type": "Update Existing Records"},
            "Updating existing records is not supported",
        ),
    ],
)
def test_unsupported_imports_are_refused(api_as, system_manager, changes, expected):
    response = insert(api_as(system_manager), **changes)
    assert response.status_code == 417
    assert message(response) == expected


def test_blank_import_type_becomes_insert(api_as, system_manager):
    response = insert(api_as(system_manager), import_type="")
    assert response.status_code == 200, response.content[:500]
    assert response.json()["message"]["import_type"] == "Insert New Records"


@pytest.mark.parametrize(
    ("name", "content", "expected"),
    [
        (
            "contacts.xlsx",
            b"not an xlsx",
            "Import template should be of type .csv, .xlsx or .xls",
        ),
        (
            "header.csv",
            b"First Name\n",
            "Import template should contain a Header and atleast one row.",
        ),
    ],
)
def test_invalid_templates_are_refused(api_as, system_manager, media, name, content, expected):
    client = api_as(system_manager)
    uploaded = upload(client, name, content)
    response = insert(client, import_file=uploaded["file_url"])
    assert response.status_code == 417
    assert message(response) == expected


def test_a_file_url_without_a_readable_file_row_is_refused(api_as, system_manager):
    response = insert(api_as(system_manager), import_file="/private/files/missing.csv")
    assert response.status_code == 417
    assert message(response) == "Invalid template file for import"


def test_insert_and_set_value_refuse_another_users_private_file(
    api_as, system_manager, other_system_manager, media
):
    victim = api_as(other_system_manager)
    private_file = upload(victim, "private.csv", b"First Name\nSecret\n")
    file_doc = File.objects.get(pk=private_file["name"])
    original_attachment = (file_doc.attached_to_doctype, file_doc.attached_to_name)

    attacker = api_as(system_manager)
    inserted = insert(attacker, import_file=private_file["file_url"])
    assert inserted.status_code == 417
    assert message(inserted) == "Invalid template file for import"

    document = insert(attacker).json()["message"]
    updated = set_value(
        attacker,
        document["name"],
        {"import_file": private_file["file_url"]},
    )
    assert updated.status_code == 417
    assert message(updated) == "Invalid template file for import"

    file_doc.refresh_from_db()
    assert (file_doc.attached_to_doctype, file_doc.attached_to_name) == original_attachment


def test_warnings_do_not_block_save(api_as, system_manager, media):
    client = api_as(system_manager)
    uploaded = upload(client, content=b"Mystery\nvalue\n")
    response = insert(client, import_file=uploaded["file_url"])
    assert response.status_code == 200, response.content[:500]
    assert response.json()["message"]["payload_count"] == 1


def test_preview_has_serial_numbers_and_import_log(api_as, system_manager, media):
    client = api_as(system_manager)
    uploaded = upload(client)
    document = insert(client, import_file=uploaded["file_url"]).json()["message"]
    with session_user(system_manager.name):
        for index in reversed(range(11)):
            DataImportLog.objects.create(
                data_import=document["name"],
                log_index=index,
                row_indexes=f"[{index + 2}]",
                success=index % 2 == 0,
            )

    response = client.post(PREVIEW, {"data_import": document["name"]}, format="json")
    assert response.status_code == 200, response.content[:500]
    preview = response.json()["message"]
    assert preview["columns"][0] == {"header_title": "Sr. No", "skip_import": True}
    assert preview["data"][0][0] == 2
    assert preview["import_log"] == [
        {"row_indexes": f"[{index + 2}]", "success": index % 2 == 0}
        for index in range(10)
    ]


def test_preview_without_a_file_returns_none(api_as, system_manager):
    client = api_as(system_manager)
    document = insert(client).json()["message"]

    response = client.post(PREVIEW, {"data_import": document["name"]}, format="json")
    assert response.status_code == 200, response.content[:500]
    assert response.json()["message"] is None


def test_sales_manager_cannot_preview(api_as, system_manager, sales_manager, media):
    owner = api_as(system_manager)
    uploaded = upload(owner)
    document = insert(owner, import_file=uploaded["file_url"]).json()["message"]

    response = api_as(sales_manager).post(
        PREVIEW, {"data_import": document["name"]}, format="json"
    )
    assert response.status_code == 403


def test_preview_ignores_a_crafted_file_argument(
    api_as, system_manager, other_system_manager, media
):
    victim = api_as(other_system_manager)
    private_file = upload(victim, "private.csv", b"First Name\nSecret\n")

    attacker = api_as(system_manager)
    own_file = upload(attacker, "own.csv", b"First Name\nMine\n")
    document = insert(attacker, import_file=own_file["file_url"]).json()["message"]

    response = attacker.post(
        PREVIEW,
        {
            "data_import": document["name"],
            "import_file": private_file["file_url"],
        },
        format="json",
    )
    assert response.status_code == 200, response.content[:500]
    assert response.json()["message"]["data"][0][1] == "Mine"


def test_preview_refuses_a_persisted_private_file_the_owner_cannot_read(
    api_as, system_manager, other_system_manager, media
):
    victim = api_as(other_system_manager)
    private_file = upload(victim, "private.csv", b"First Name\nSecret\n")

    attacker = api_as(system_manager)
    own_file = upload(attacker, "own.csv", b"First Name\nMine\n")
    document = insert(attacker, import_file=own_file["file_url"]).json()["message"]
    DataImport.objects.filter(pk=document["name"]).update(import_file=private_file["file_url"])

    response = attacker.post(PREVIEW, {"data_import": document["name"]}, format="json")
    assert response.status_code == 417
    assert message(response) == "Invalid template file for import"
