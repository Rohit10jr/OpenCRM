"""CSV parsing contract for Data Import, with no persistence or endpoint behavior."""

from types import SimpleNamespace

import pytest

from crm_app.data_import.importer import (
    Column,
    ImportFile,
    Row,
    build_fields_dict_for_column_matching,
    read_csv_content,
)

pytestmark = pytest.mark.django_db


def _docs(csv_text, doctype="Contact", options=None):
    return ImportFile(doctype, csv_text, options, "Insert New Records")


def test_reads_utf8_and_windows_1252_bytes_and_removes_formula_escaping():
    assert read_csv_content("Name,Phone\nRenée,'+44123\n".encode()) == [
        ["Name", "Phone"],
        ["Renée", "+44123"],
    ]
    assert read_csv_content("Name\nAndré\n".encode("windows-1252"))[1] == ["André"]


@pytest.mark.parametrize(
    "content",
    [
        "\ufeffFirst Name,Last Name\nAda,Lovelace\n",
        '\ufeff"First Name",Last Name\nAda,Lovelace\n',
    ],
)
def test_bom_is_not_part_of_a_plain_or_quoted_first_header(content):
    imported = _docs(content)
    assert imported.columns[0].header_title == "First Name"
    assert imported.columns[0].df.fieldname == "first_name"


def test_blank_rows_are_skipped_without_renumbering_the_file():
    imported = _docs("First Name\n\nAda\n   \nGrace\n")
    assert [row.row_number for row in imported.data] == [3, 5]


@pytest.mark.parametrize("header", ["First Name", "first_name", "First Name (first_name)"])
def test_parent_headers_match_by_label_fieldname_and_combined_label(header):
    imported = _docs(f"{header}\nAda\n")
    assert imported.columns[0].df.fieldname == "first_name"


def test_explicit_mapping_and_dont_import_keep_upstream_warning_shapes():
    imported = _docs(
        "Given,Surname\nAda,Lovelace\n",
        options={"column_to_field_map": {"0": "first_name", "1": "Don't Import"}},
    )
    assert imported.get_payloads_for_import()[0].doc == {"first_name": "Ada"}
    assert imported.get_warnings() == [
        {
            "message": "Mapping column <strong>Given</strong> to field <strong>First Name</strong>",
            "type": "info",
        },
        {
            "col": "2",
            "message": "Skipping column <strong>Surname</strong>",
            "type": "info",
        },
    ]


def test_duplicate_untitled_unknown_and_id_columns_have_verbatim_info_warnings():
    imported = _docs("First Name,First Name,,Mystery,ID\nAda,Lovelace,x,y,CONTACT-1\n")
    assert imported.get_warnings() == [
        {
            "col": "2",
            "message": "Skipping Duplicate Column <strong>First Name</strong>",
            "type": "info",
        },
        {"col": "3", "message": "Skipping Untitled Column", "type": "info"},
        {
            "col": "4",
            "message": "Cannot match column <strong>Mystery</strong> with any field",
            "type": "info",
        },
        {
            "col": "5",
            "message": "Skipping column <strong>ID</strong>",
            "type": "info",
        },
    ]
    assert all(warning["type"] == "info" for warning in imported.get_warnings())


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["31-01-2025"], "%d-%m-%Y"),
        (["01-31-2025"], "%m-%d-%Y"),
        (["2025-01-31"], "%Y-%m-%d"),
    ],
)
def test_date_format_guessing(values, expected):
    imported = _docs(
        "Expected Closure Date\n" + "\n".join(values) + "\n",
        doctype="CRM Deal",
    )
    assert imported.columns[0].date_format == expected


def test_mixed_date_format_tie_uses_the_first_observed_format():
    imported = _docs(
        "Expected Closure Date\n31-01-2025\n01-31-2025\n",
        doctype="CRM Deal",
    )
    assert imported.columns[0].date_format == "%d-%m-%Y"
    assert imported.get_warnings()[0] == {
        "col": 1,
        "message": (
            "The column <strong>Expected Closure Date</strong> has 2 different date formats. "
            "Automatically setting <strong>dd-mm-yyyy</strong> as the default format as it is "
            "the most common. Please change other values in this column to this format."
        ),
        "type": "info",
    }


def test_select_link_and_date_warnings_are_blocking_and_verbatim():
    imported = _docs(
        "No. of Employees,Salutation,Expected Closure Date\nImpossible,Missing,not-a-date\n",
        doctype="CRM Deal",
    )
    imported.get_payloads_for_import()
    warnings = imported.get_warnings()
    assert any(
        warning["message"].startswith("The following values are invalid: <strong>Impossible</strong>.")
        and "type" not in warning
        for warning in warnings
    )
    assert {
        "col": 2,
        "message": "The following values do not exist for Salutation: Missing",
        "type": "warning",
    } in warnings
    assert any(
        warning["message"] == "Value <strong>not-a-date</strong> must in <strong>yyyy-mm-dd</strong> format"
        and warning["row"] == 2
        for warning in warnings
    )


@pytest.mark.parametrize(
    ("value", "missing"),
    [("CRM Lead", False), ("Not A Real DocType", True)],
)
def test_doctype_links_validate_against_the_registry(value, missing):
    imported = _docs(
        f"Subject,Reference Document Type\nFollow up,{value}\n",
        doctype="CRM Task",
    )
    column_warning = {
        "col": 2,
        "message": f"The following values do not exist for DocType: {value}",
        "type": "warning",
    }
    assert (column_warning in imported.get_warnings()) is missing
    doc = imported.get_payloads_for_import()[0].doc
    assert doc.get("reference_doctype") == (None if missing else value)
    if missing:
        assert any(
            warning["message"]
            == f"Value <strong>{value}</strong> missing for <strong>DocType</strong>"
            for warning in imported.get_warnings()
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1d 2h 3m 4s", 93784), ("not-a-duration", None), ("", None)],
)
def test_duration_values_are_converted_or_blocked(value, expected):
    imported = _docs(
        f"From Number,Duration\n+123,{value}\n",
        doctype="CRM Call Log",
    )
    doc = imported.get_payloads_for_import()[0].doc
    assert doc.get("duration") == expected
    warning = {
        "row": 2,
        "col": 2,
        "field": {
            "fieldname": "duration",
            "fieldtype": "Duration",
            "label": "Duration",
            "options": None,
            "parent": "CRM Call Log",
            "default": None,
        },
        "message": (
            "Value <strong>not-a-duration</strong> must be in the valid duration format: d h m s"
        ),
    }
    assert (warning in imported.get_warnings()) is (value == "not-a-duration")


@pytest.mark.parametrize(
    ("fieldtype", "value", "expected"),
    [
        ("Check", "yes", 1),
        ("Check", "no", 0),
        ("Int", "12.8", 12),
        ("Int", "wrong", 0),
        ("Float", "1,234.5", 1234.5),
        ("Float", "wrong", 0.0),
    ],
)
def test_check_int_and_float_parsing(fieldtype, value, expected):
    row = object.__new__(Row)
    column = SimpleNamespace(df=SimpleNamespace(fieldtype=fieldtype))
    assert row.parse_value(value, column) == expected


def test_short_and_long_rows_warn_and_the_short_row_can_still_be_parsed():
    imported = _docs("First Name,Last Name\nAda\nGrace,Hopper,extra\n")
    assert imported.get_warnings() == [
        {"row": 2, "message": "Row has less values than columns"},
        {"row": 3, "message": "Row has more values than columns"},
    ]
    assert imported.get_payloads_for_import()[0].doc == {"first_name": "Ada"}


def test_contact_rows_group_two_emails_and_phones_and_supply_primary_flags():
    imported = _docs(
        "First Name,email_ids.email_id,phone_nos.phone\n"
        "Ada,ada@example.com,+111\n"
        ",ada.work@example.com,+222\n"
    )
    payload = imported.get_payloads_for_import()[0]
    assert [row["email_id"] for row in payload.doc["email_ids"]] == [
        "ada@example.com",
        "ada.work@example.com",
    ]
    assert [row["phone"] for row in payload.doc["phone_nos"]] == ["+111", "+222"]
    assert payload.doc["email_ids"][0]["is_primary"] == 1
    assert payload.doc["phone_nos"][0]["is_primary_phone"] == 1
    assert payload.doc["phone_nos"][0]["is_primary_mobile_no"] == 1


def test_contact_upstream_child_headers_resolve_without_blocking_warnings():
    imported = _docs(
        "First Name,Email ID (Email IDs),Number (Contact Numbers)\n"
        "Ada,ada@example.com,+111\n"
    )

    assert [
        f"{column.df.child_table_df.fieldname}.{column.df.fieldname}"
        for column in imported.columns[1:]
    ] == ["email_ids.email_id", "phone_nos.phone"]
    assert not [
        warning
        for warning in imported.get_warnings()
        if warning.get("type") != "info"
    ]


def test_contact_primary_flags_from_the_file_are_not_replaced():
    imported = _docs(
        "First Name,email_ids.email_id,email_ids.is_primary,phone_nos.phone,"
        "phone_nos.is_primary_phone,phone_nos.is_primary_mobile_no\n"
        "Ada,first@example.com,no,+111,no,yes\n"
        ",second@example.com,yes,+222,yes,no\n"
    )
    doc = imported.get_payloads_for_import()[0].doc
    assert [row["is_primary"] for row in doc["email_ids"]] == [0, 1]
    assert [row["is_primary_phone"] for row in doc["phone_nos"]] == [0, 1]
    assert [row["is_primary_mobile_no"] for row in doc["phone_nos"]] == [1, 0]


def test_contact_bare_mapping_targets_child_tables():
    imported = _docs(
        "First Name,Email,Phone\nAda,ada@example.com,+111\n",
        options={"column_to_field_map": {"1": "email_id", "2": "phone"}},
    )
    doc = imported.get_payloads_for_import()[0].doc
    assert doc["email_ids"][0]["email_id"] == "ada@example.com"
    assert doc["phone_nos"][0]["phone"] == "+111"


@pytest.mark.parametrize(
    ("header", "value", "table", "field"),
    [
        ("Email Address", "ada@example.com", "email_ids", "email_id"),
        ("email_id", "ada@example.com", "email_ids", "email_id"),
        ("Phone", "+111", "phone_nos", "phone"),
        ("phone", "+111", "phone_nos", "phone"),
        ("Mobile No", "+222", "phone_nos", "phone"),
        ("mobile_no", "+222", "phone_nos", "phone"),
    ],
)
def test_contact_derived_parent_headers_target_child_tables(header, value, table, field):
    imported = _docs(f"First Name,{header}\nAda,{value}\n")
    doc = imported.get_payloads_for_import()[0].doc
    assert doc[table][0][field] == value


@pytest.mark.parametrize(
    ("phone", "mobile", "expected"),
    [
        ("+111", "+222", [("+111", 1, None), ("+222", None, 1)]),
        ("+111", "", [("+111", 1, 1)]),
        ("", "+222", [("+222", 1, 1)]),
        ("+111", "+111", [("+111", 1, 1)]),
    ],
)
def test_contact_phone_and_mobile_columns_create_distinct_primary_rows(phone, mobile, expected):
    imported = _docs(f"First Name,Phone,Mobile No\nAda,{phone},{mobile}\n")
    rows = imported.get_payloads_for_import()[0].doc["phone_nos"]
    assert [
        (row["phone"], row.get("is_primary_phone"), row.get("is_primary_mobile_no"))
        for row in rows
    ] == expected


def test_contact_phone_expansion_preserves_multi_row_child_grouping():
    imported = _docs(
        "First Name,Phone,Mobile No\n"
        "Ada,+111,+222\n"
        ",+333,\n"
    )
    rows = imported.get_payloads_for_import()[0].doc["phone_nos"]
    assert [row["phone"] for row in rows] == ["+111", "+222", "+333"]


def test_deal_products_are_grouped_under_the_table_wire_name():
    imported = _docs(
        "Expected Deal Value,products.product_name,products.rate,products.qty\n"
        "500,Consulting,100,2\n"
        ",Support,50,3\n",
        doctype="CRM Deal",
    )
    doc = imported.get_payloads_for_import()[0].doc
    assert doc == {
        "expected_deal_value": 500.0,
        "products": [
            {"product_name": "Consulting", "rate": 100.0, "qty": 2.0},
            {"product_name": "Support", "rate": 50.0, "qty": 3.0},
        ],
    }


def test_preview_shape_starts_at_row_two_and_is_capped_at_ten():
    imported = _docs("First Name\n" + "\n".join(f"Person {i}" for i in range(12)) + "\n")
    preview = imported.get_data_for_import_preview()
    assert preview.columns[0] == {"header_title": "Sr. No", "skip_import": True}
    assert preview.data[0] == [2, "Person 0"]
    assert len(preview.data) == 10
    assert preview.max_rows_exceeded is True
    assert preview.max_rows_in_preview == 10
    assert preview.total_number_of_rows == 12


def test_field_dictionary_uses_upstream_parent_and_child_collision_rules():
    fields = build_fields_dict_for_column_matching("CRM Deal")
    assert fields["Expected Deal Value"].fieldname == "expected_deal_value"
    assert fields["expected_deal_value"].fieldname == "expected_deal_value"
    assert fields["Expected Deal Value (expected_deal_value)"].fieldname == "expected_deal_value"
    assert fields["products.product_name"].parent == "CRM Products"
    assert fields["Product Name (Products)"].fieldname == "product_name"
