"""Data Import template downloads through the public method URL."""

from __future__ import annotations

import csv
import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from crm_app.models import CRMDeal, CRMDealStatus, CRMProducts, CRMTask
from frappe_core.session import session_user
from frappe_platform.models import Contact, ContactEmail, DataImport

pytestmark = pytest.mark.django_db

PATH = "/api/method/frappe.core.doctype.data_import.data_import.download_template"
METHOD = "/api/method/"


@pytest.fixture
def system_manager(make_user):
    return make_user("template-manager@example.com", roles=["System Manager"])


@pytest.fixture
def sales_manager(make_user):
    return make_user(
        "template-sales@example.com", roles=["Sales Manager", "Sales User"]
    )


def download(client, doctype, fields, **changes):
    params = {
        "doctype": doctype,
        "export_fields": json.dumps(fields),
        "export_records": "blank_template",
        "file_type": "CSV",
        **changes,
    }
    return client.get(PATH, params)


def rows_of(response):
    return list(csv.reader(io.StringIO(response.content.decode("utf-8"))))


def test_blank_csv_has_header_and_two_empty_rows(api_as, system_manager):
    response = download(
        api_as(system_manager), "Contact", {"Contact": ["first_name", "last_name"]}
    )

    assert response.status_code == 200, response.content[:500]
    assert response["Content-Disposition"] == 'attachment; filename="Contact.csv"'
    assert rows_of(response) == [["First Name", "Last Name"], [], []]


def test_child_headers_and_label_clash_fallbacks(api_as, system_manager, monkeypatch):
    client = api_as(system_manager)
    contact = rows_of(
        download(
            client,
            "Contact",
            {
                "Contact": ["email_id"],
                "email_ids": ["email_id", "is_primary"],
                "phone_nos": ["phone", "is_primary_phone"],
            },
        )
    )[0]
    assert contact[1:] == [
        "Email ID (Email IDs)",
        "Is Primary (Email IDs)",
        "Number (Contact Numbers)",
        "Is Primary Phone (Contact Numbers)",
    ]

    # Force the child descriptor's label to match the selected parent label.  The
    # endpoint must then use upstream's child ``tablefield.fieldname`` fallback.
    monkeypatch.setattr(
        ContactEmail._meta.get_field("email_id"), "verbose_name", "Email Address"
    )
    monkeypatch.setattr(
        Contact._meta.get_field("email_id"),
        "verbose_name",
        "Email Address (Email IDs)",
    )
    clashing = rows_of(
        download(
            client,
            "Contact",
            {"Contact": ["email_id"], "email_ids": ["email_id"]},
        )
    )[0]
    assert clashing == ["Email Address (Email IDs)", "email_ids.email_id"]

    deal = rows_of(
        download(
            client,
            "CRM Deal",
            {"CRM Deal": ["products"], "products": ["product_name", "rate"]},
        )
    )[0]
    assert deal == ["Product Name (Products)", "Rate (Products)"]


def test_unknown_fields_and_keys_drop_and_name_adds_id(api_as, system_manager):
    response = download(
        api_as(system_manager),
        "CRM Task",
        {"CRM Task": ["name", "title", "not_a_field"], "not_a_table": ["title"]},
    )
    assert rows_of(response)[0] == ["ID", "Title"]


def test_round_trip_blank_contact_template_previews_without_blocking_warnings(
    api_as, system_manager, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    client = api_as(system_manager)
    response = download(
        client,
        "Contact",
        {
            "Contact": ["first_name", "last_name"],
            "email_ids": ["email_id"],
            "phone_nos": ["phone"],
        },
    )
    rows = rows_of(response)
    rows[1] = ["Ada", "Lovelace", "ada@example.test", "+1 555 0100"]
    output = io.StringIO()
    csv.writer(output, quoting=csv.QUOTE_NONNUMERIC).writerows(rows)

    uploaded = client.post(
        METHOD + "upload_file",
        {
            "file": SimpleUploadedFile("Contact.csv", output.getvalue().encode()),
            "is_private": 1,
        },
        format="multipart",
    ).json()["message"]
    inserted = client.post(
        METHOD + "frappe.client.insert",
        {
            "doc": {
                "doctype": "Data Import",
                "reference_doctype": "Contact",
                "import_type": "Insert New Records",
                "mute_emails": True,
                "google_sheets_url": "",
                "import_file": uploaded["file_url"],
            }
        },
        format="json",
    )
    assert inserted.status_code == 200, inserted.content[:500]
    preview = client.get(
        METHOD
        + "frappe.core.doctype.data_import.data_import.get_preview_from_template",
        {"data_import": inserted.json()["message"]["name"]},
    )
    assert preview.status_code == 200, preview.content[:500]
    assert not [
        warning
        for warning in preview.json()["message"]["warnings"]
        if warning.get("type") != "info"
    ]

    name = inserted.json()["message"]["name"]
    started = client.post(
        METHOD + "frappe.core.doctype.data_import.data_import.form_start_import",
        {"data_import": name},
        format="json",
    )
    assert started.status_code == 200, started.content[:500]
    assert DataImport.objects.get(pk=name).status == "Success"
    contact = Contact.objects.get(first_name="Ada", last_name="Lovelace")
    assert contact.email_id == "ada@example.test"
    assert contact.phone == "+1 555 0100"


def test_record_limits_and_children_use_continuation_rows(api_as, system_manager):
    with session_user(system_manager.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deals = [
            CRMDeal.objects.create(status=status, lead_name=f"Deal {i}")
            for i in range(7)
        ]
        CRMProducts.objects.create(
            parenttype="CRM Deal",
            parent=str(deals[-1].pk),
            parentfield="products",
            idx=1,
            product_name="One",
            rate=10,
        )
        CRMProducts.objects.create(
            parenttype="CRM Deal",
            parent=str(deals[-1].pk),
            parentfield="products",
            idx=2,
            product_name="Two",
            rate=20,
        )
    fields = {"CRM Deal": ["lead_name"], "products": ["product_name", "rate"]}
    client = api_as(system_manager)

    five = rows_of(download(client, "CRM Deal", fields, export_records="5_records"))
    all_rows = rows_of(download(client, "CRM Deal", fields, export_records="all"))
    assert len([row for row in five[1:] if row and row[0]]) == 5
    assert len([row for row in all_rows[1:] if row and row[0]]) == 7
    assert all_rows[1][1:] == ["One", "10.0"]
    assert all_rows[2] == ["", "Two", "20.0"]


def test_contact_child_records_export_booleans_on_continuation_rows(
    api_as, system_manager
):
    with session_user(system_manager.name):
        contact = Contact.objects.create(first_name="Ada")
        ContactEmail.objects.create(
            parent_contact=contact,
            idx=1,
            email_id="ada@example.test",
            is_primary=True,
        )
        ContactEmail.objects.create(
            parent_contact=contact,
            idx=2,
            email_id="ada.alt@example.test",
            is_primary=False,
        )

    response = download(
        api_as(system_manager),
        "Contact",
        {"Contact": ["first_name"], "email_ids": ["email_id", "is_primary"]},
        export_records="all",
    )

    assert response.status_code == 200, response.content[:500]
    assert rows_of(response)[1:] == [
        ["Ada", "ada@example.test", "1"],
        ["", "ada.alt@example.test", "0"],
    ]


def test_excel_opens_and_csv_preserves_html(api_as, system_manager):
    with session_user(system_manager.name):
        CRMTask.objects.create(title="HTML", description="<p>Hello <b>there</b></p>")
    client = api_as(system_manager)
    csv_response = download(
        client, "CRM Task", {"CRM Task": ["description"]}, export_records="all"
    )
    assert rows_of(csv_response)[1] == ["<p>Hello <b>there</b></p>"]

    excel = download(
        client,
        "CRM Task",
        {"CRM Task": ["title"]},
        export_records="all",
        file_type="Excel",
    )
    assert excel.content.startswith(b"PK")
    try:
        import openpyxl
    except ImportError:
        return
    workbook = openpyxl.load_workbook(io.BytesIO(excel.content), read_only=True)
    assert workbook.active["A1"].value == "Title"


def test_bad_type_non_importable_and_sales_manager_are_refused(
    api_as, system_manager, sales_manager
):
    fields = {"CRM Task": ["title"]}
    assert (
        download(
            api_as(system_manager), "CRM Task", fields, file_type="PDF"
        ).status_code
        == 417
    )
    assert (
        download(api_as(system_manager), "User", {"User": ["name"]}).status_code == 403
    )
    assert download(api_as(sales_manager), "CRM Task", fields).status_code == 403


def test_list_hidden_field_is_refused_for_system_manager(
    api_as, system_manager, monkeypatch
):
    monkeypatch.setattr(CRMTask, "SENSITIVE_FIELDS", ("description",), raising=False)
    with session_user(system_manager.name):
        CRMTask.objects.create(title="Secret", description="never-export-this")
    response = download(
        api_as(system_manager),
        "CRM Task",
        {"CRM Task": ["title", "description"]},
        export_records="all",
    )
    assert response.status_code == 417
    assert b"never-export-this" not in response.content
