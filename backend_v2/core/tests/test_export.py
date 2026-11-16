"""Port generic export cases to Widget; Task/Lead remain ACTIVITIES/SALES work."""

import csv
import io
import json
import zipfile
import pytest
from core.mixins.export import format_duration, handle_html
from tests_support.models import Widget
pytestmark = pytest.mark.django_db
URL = "/api/v1/test-widgets/export/"
COLUMNS = ["widget_name", "status", "quantity", "due_date", "notes", "modified"]


def save_widget(user, name, **values):
    document = Widget(name=name, widget_owner=values.pop("widget_owner", user), **values)
    document.save(user=user)
    return document

@pytest.fixture
def widgets(alice):
    return [
        save_widget(alice, "Export Alpha", widget_name="Alpha", status="Open",
                    quantity=7, notes="<p>Hello<br>there &amp; you</p>"),
        save_widget(alice, "Export Beta", widget_name="Beta", status="Closed",
                    quantity=9, notes="plain"),
    ]

def export(client, method="get", **params):
    query = {
        "file_format_type": "CSV",
        "title": "Foundation Widget",
        "fields": json.dumps(COLUMNS),
        "filters": json.dumps({}),
        "order_by": "widget_name asc",
        "page_length": 20,
        "start": 0,
        "view": "Report",
        "with_comment_count": 1,
    }
    query.update(params)
    if method == "post":
        return client.post(URL, query, format="json")
    return client.get(URL, query)

def rows_of(response):
    return list(csv.reader(io.StringIO(response.content.decode("utf-8"))))

def test_csv_is_a_raw_quoted_download_with_headers(auth_api, widgets):
    response = export(auth_api)
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert response["Content-Disposition"] == 'attachment; filename="Foundation Widget.csv"'
    assert not response.content.startswith(b'{"message"')
    rows = rows_of(response)
    assert rows[0] == ["Sr", *COLUMNS]
    assert [row[1] for row in rows[1:]] == ["Alpha", "Beta"]
    assert response.content.splitlines()[1].startswith(b'1,"Alpha","Open",7,')
    assert rows[1][5] == "Hello there & you"

def test_excel_export_is_a_named_workbook(auth_api, widgets):
    response = export(auth_api, file_format_type="anything but CSV")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response["Content-Disposition"].endswith('Foundation Widget.xlsx"')
    with zipfile.ZipFile(io.BytesIO(response.content)) as book:
        assert "xl/worksheets/sheet1.xml" in book.namelist()
        workbook = book.read("xl/workbook.xml").decode()
        strings = book.read("xl/sharedStrings.xml").decode()
    assert 'name="Foundation Widget"' in workbook
    assert "widget_name" in strings and "Alpha" in strings

def test_filters_order_and_selected_rows_apply(auth_api, widgets):
    filtered = export(auth_api, filters=json.dumps({"status": "Closed"}))
    assert [row[1] for row in rows_of(filtered)[1:]] == ["Beta"]

    descending = export(auth_api, order_by="widget_name desc")
    assert [row[1] for row in rows_of(descending)[1:]] == ["Beta", "Alpha"]

    selected = export(
        auth_api,
        method="post",
        selected_items=[widgets[0].name],
        filters={"status": "Closed"},
        or_filters={"status": "Closed"},
    )
    assert [row[1] for row in rows_of(selected)[1:]] == ["Alpha"]

def test_selected_name_may_contain_a_slash(auth_api, alice):
    selected = save_widget(alice, "R/GA", widget_name="Slash")
    response = export(auth_api, selected_items=json.dumps([selected.name]))
    assert [row[1] for row in rows_of(response)[1:]] == ["Slash"]

def test_page_length_and_start_are_ignored_without_the_twenty_row_cap(auth_api, alice):
    for number in range(21):
        save_widget(alice, f"All {number:02}", widget_name=f"All {number:02}")
    response = export(
        auth_api,
        fields=json.dumps(["widget_name"]),
        page_length=1,
        start=20,
    )
    assert len(rows_of(response)[1:]) == 21


def test_list_row_permissions_apply(auth_api, alice, bob):
    save_widget(alice, "Mine", widget_name="Mine")
    save_widget(bob, "Theirs", widget_name="Theirs")
    response = export(auth_api, fields=json.dumps(["widget_name"]))
    assert [row[1] for row in rows_of(response)[1:]] == ["Mine"]


def test_unknown_and_hidden_fields_are_refused(auth_api):
    unknown = export(auth_api, fields=json.dumps(["widget_name", "nonsense"]))
    assert unknown.status_code == 417
    hidden = auth_api.get(
        "/api/v1/test-secured/export/",
        {"file_format_type": "CSV", "fields": json.dumps(["secret"])},
    )
    assert hidden.status_code == 417


def test_authentication_is_required(api):
    assert export(api).status_code == 401


def test_title_and_default_filename(auth_api, widgets):
    titled = export(auth_api, title="Chosen", fields="widget_name")
    assert titled["Content-Disposition"] == 'attachment; filename="Chosen.csv"'
    assert rows_of(titled)[0] == ["Sr", "widget_name"]
    defaulted = auth_api.get(URL)
    assert defaulted["Content-Disposition"] == (
        'attachment; filename="Foundation Widget.xlsx"'
    )


def test_duration_and_html_formatting_helpers():
    assert format_duration(12885) == "3h 34m 45s"
    assert format_duration(-12885) == "-3h 34m 45s"
    assert format_duration(90000) == "1d 1h"
    assert format_duration(90000, hide_days=True) == "25h"
    assert handle_html("<p>Hello<br>there &amp; you</p>") == "Hello there & you"
    assert handle_html("plain") == "plain"
