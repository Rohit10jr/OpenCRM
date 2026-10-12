"""``frappe.desk.reportview.export_query``: docs/FINDINGS.md 51.

The Export dialog of every list view. Shapes follow ``frappe/desk/reportview.py:427-575``
for the parameters ``ViewControls.vue:565-590`` sends.
"""

import csv
import io
import json
import zipfile

import pytest

from crm_app.api.reportview import format_duration, handle_html
from crm_app.models import CRMLead, CRMTask
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

PATH = "/api/method/frappe.desk.reportview.export_query"
COLUMNS = ["title", "status", "priority", "due_date", "assigned_to", "modified"]


@pytest.fixture
def tasks(administrator):
    with session_user(administrator.name):
        return [
            CRMTask.objects.create(title="ZZ Call the client", status="Todo", priority="High"),
            CRMTask.objects.create(title="ZZ Send the quote", status="Backlog", priority="Low"),
        ]


def export(client, **params):
    """The dialog's request: the list's columns, filters and order, plus the format."""
    query = {
        "file_format_type": "CSV",
        "title": "CRM Task",
        "doctype": "CRM Task",
        "fields": json.dumps(COLUMNS),
        "filters": json.dumps({}),
        "order_by": "modified desc",
        "page_length": 20,
        "start": 0,
        "view": "Report",
        "with_comment_count": 1,
    }
    query.update(params)
    return client.get(PATH, query)


def rows_of(response) -> list[list[str]]:
    return list(csv.reader(io.StringIO(response.content.decode("utf-8"))))


def test_csv_export_of_the_task_list(api_as, administrator, tasks):
    response = export(api_as(administrator))
    assert response.status_code == 200, response.content[:300]
    assert response["Content-Type"].startswith("text/csv")
    assert response["Content-Disposition"] == 'attachment; filename="CRM Task.csv"'

    rows = rows_of(response)
    assert rows[0] == ["Sr", "Title", "Status", "Priority", "Due Date", "Assigned To", "Last Updated On"]
    titles = [row[1] for row in rows[1:]]
    assert "ZZ Call the client" in titles and "ZZ Send the quote" in titles
    assert [row[0] for row in rows[1:]][:2] == ["1", "2"]


def test_excel_export_is_a_workbook(api_as, administrator, tasks):
    pytest.importorskip("xlsxwriter")
    response = export(api_as(administrator), file_format_type="Excel")
    assert response.status_code == 200, response.content[:300]
    assert response["Content-Type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response["Content-Disposition"] == 'attachment; filename="CRM Task.xlsx"'

    with zipfile.ZipFile(io.BytesIO(response.content)) as book:
        names = book.namelist()
        assert "xl/worksheets/sheet1.xml" in names
        strings = book.read("xl/sharedStrings.xml").decode("utf-8")
    assert "Title" in strings and "ZZ Call the client" in strings


def test_ticked_rows_export_only_those(api_as, administrator, tasks):
    """``selected_items`` replaces the filters with ``name in`` (reportview.py:488-489)."""
    response = export(api_as(administrator), selected_items=json.dumps([tasks[1].pk]))
    rows = rows_of(response)
    assert [row[1] for row in rows[1:]] == ["ZZ Send the quote"]


def test_the_views_filters_and_order_apply(api_as, administrator, tasks):
    response = export(api_as(administrator), filters=json.dumps({"status": "Todo"}))
    assert [row[1] for row in rows_of(response)[1:]] == ["ZZ Call the client"]

    ordered = export(api_as(administrator), order_by="title asc")
    titles = [row[1] for row in rows_of(ordered)[1:] if row[1].startswith("ZZ")]
    assert titles == sorted(titles)


def test_page_length_does_not_cut_the_export(api_as, administrator, tasks):
    """Upstream drops ``limit_page_length`` for an export: every matching row."""
    response = export(api_as(administrator), page_length=1)
    assert len([row for row in rows_of(response)[1:] if row[1].startswith("ZZ")]) == 2


def test_the_row_rule_applies_to_an_export(api_as, alice, bob, administrator):
    """A Sales User exports the leads they may see, through the same query every list uses."""
    from crm_app.models import CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        CRMLead.objects.create(first_name="ZZ Mine", lead_owner=alice, status=status)
        CRMLead.objects.create(first_name="ZZ Theirs", lead_owner=bob, status=status)
    response = export(
        api_as(alice), doctype="CRM Lead", title="CRM Lead", fields=json.dumps(["first_name"])
    )
    assert response.status_code == 200, response.content[:300]
    names = [row[1] for row in rows_of(response)[1:]]
    assert "ZZ Mine" in names and "ZZ Theirs" not in names


def test_an_unknown_column_is_refused_not_dropped(api_as, administrator, tasks):
    response = export(api_as(administrator), fields=json.dumps(["title", "nonsense"]))
    assert response.status_code == 417


def test_an_unknown_doctype_is_a_404(api_as, administrator):
    assert export(api_as(administrator), doctype="Nonsense").status_code == 404


def test_anonymous_callers_are_refused(api):
    assert export(api).status_code == 401


def test_duration_and_html_formatting():
    assert format_duration(12885) == "3h 34m 45s"
    assert format_duration(-12885) == "-3h 34m 45s"
    assert format_duration(90000) == "1d 1h"
    assert format_duration(90000, hide_days=True) == "25h"
    assert handle_html("<p>Hello<br>there &amp; you</p>") == "Hello there & you"
    assert handle_html("plain") == "plain"
