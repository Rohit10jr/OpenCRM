"""``frappe.desk.reportview.export_query`` - the list views' Export dialog.

``ViewControls.vue:565-590`` builds a GET with the list's column keys, the standard
view's filters and order, ``file_format_type`` (Excel or CSV), ``title`` and, when rows
are ticked, ``selected_items``. Upstream (``frappe/desk/reportview.py:427-575``) runs the
report-builder query with those parameters and answers with the file itself, not JSON.

What is ported is the path this frontend reaches: the file, the selection, the two
formats. ``export_in_background`` (a queued job that emails the file),
``visible_names``, ``add_totals_row`` and ``translate_values`` are report-builder
options nothing here sends. ``can_export`` is a role-permission flag this port does not
model; the row rule of the doctype still decides which rows the caller sees, through the
same ``fetch_rows`` every list uses.
"""

from __future__ import annotations

import csv
import html
import io
import re
from typing import Any

from django.http import HttpResponse

from frappe_core import field_meta, registry
from frappe_core.exceptions import DoesNotExistError, throw
from frappe_core.metadata import STANDARD_FILTER_FIELDS
from frappe_core.query import fetch_rows, parse_json_param
from frappe_core.whitelist import whitelist

CONTENT_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

#: ``frappe/model/meta.py:get_default_df`` gives the standard columns a type; their
#: labels come from the same table every filterable-field list appends.
_STANDARD_LABELS = {f["fieldname"]: f["label"] for f in STANDARD_FILTER_FIELDS}
_STANDARD_TYPES = {
    "creation": "Datetime",
    "modified": "Datetime",
    "idx": "Int",
    "docstatus": "Int",
    "owner": "Link",
    "modified_by": "Link",
}

_TAG_RE = re.compile(r"<[^>]+>")


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def field_info(doctype: str, fields: list[str]) -> list[dict]:
    """``reportview.py:get_field_info``: label and type per exported column. The parent
    ``name`` column is labelled ``ID``; a standard column takes the framework's label."""
    info = []
    for fieldname in fields:
        if fieldname == "name":
            info.append({"fieldname": "name", "label": "ID", "fieldtype": "Data"})
            continue
        meta = field_meta.get_field(doctype, fieldname)
        if meta:
            info.append(
                {
                    "fieldname": fieldname,
                    "label": meta.get("label") or fieldname,
                    "fieldtype": meta.get("fieldtype") or "Data",
                }
            )
            continue
        info.append(
            {
                "fieldname": fieldname,
                "label": _STANDARD_LABELS.get(fieldname, fieldname),
                "fieldtype": _STANDARD_TYPES.get(fieldname, "Data"),
            }
        )
    return info


def format_duration(seconds, hide_days: bool = False) -> str:
    """``frappe/utils/data.py:812-841``: ``12885`` -> ``3h 34m 45s``."""
    seconds = _int(seconds)
    negative = seconds < 0
    seconds = abs(seconds)
    days = (seconds // (3600 * 24)) if not hide_days else 0
    hours = ((seconds % (3600 * 24)) // 3600) if not hide_days else (seconds // 3600)
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds:
        parts.append(f"{seconds}s")
    text = " ".join(parts)
    return f"-{text}" if negative and text else text


def handle_html(value: str) -> str:
    """``xlsxutils.py:handle_html``, without html2text: tags dropped, entities decoded,
    line breaks flattened, so a Text Editor column exports as prose."""
    if "<" not in value or ">" not in value:
        return value
    text = html.unescape(_TAG_RE.sub(" ", value.replace("</p>", "\n").replace("<br>", "\n")))
    return " ".join(text.split())


def _cell(value: Any) -> Any:
    """What goes in a cell: dates and datetimes as text, JSON caches as their text."""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat(sep=" ") if hasattr(value, "hour") else value.isoformat()
    return value


def to_csv_bytes(data: list[list], delimiter: str = ",", quoting: int = csv.QUOTE_NONNUMERIC) -> bytes:
    """``frappe/desk/utils.py:get_csv_bytes``, with ``pop_csv_params``' defaults."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, quoting=quoting)
    writer.writerows([[handle_html(v) if isinstance(v, str) else v for v in row] for row in data])
    return buffer.getvalue().encode("utf-8")


def to_xlsx_bytes(data: list[list], sheet_name: str) -> bytes:
    """``frappe/utils/xlsxutils.py:make_xlsx``: one sheet, bold header, columns sized to
    their content. XlsxWriter, as upstream; ``requirements.txt`` lists it."""
    try:
        import xlsxwriter
    except ImportError:  # pragma: no cover - the environment, not the code
        throw("Excel export needs the XlsxWriter package; install it, or export as CSV")

    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    sheet = workbook.add_worksheet(re.sub(r"[\[\]:*?/\\]", " ", sheet_name)[:31] or "Sheet1")
    sheet.set_row(0, cell_format=workbook.add_format({"bold": True}))
    widths: list[int] = []
    for row_index, row in enumerate(data):
        for col_index, value in enumerate(row):
            text = "" if value is None else str(value)
            if col_index >= len(widths):
                widths.append(0)
            widths[col_index] = max(widths[col_index], min(len(text), 60))
            sheet.write(row_index, col_index, value)
    for col_index, width in enumerate(widths):
        sheet.set_column(col_index, col_index, width + 2)
    workbook.close()
    return buffer.getvalue()


@whitelist("frappe.desk.reportview.export_query")
def export_query(
    doctype: str,
    fields=None,
    filters=None,
    or_filters=None,
    order_by=None,
    file_format_type: str = "Excel",
    title: str | None = None,
    selected_items=None,
    page_length=None,
    start=None,
    **_ignored,
):
    """``reportview.py:427-575`` for the parameters the list views send.

    ``page_length`` and ``start`` are accepted and ignored, as upstream's
    ``form_params["limit_page_length"] = None`` ignores them: an export is every row the
    filters match, which is what the dialog's "Export all N records" promises. Ticked
    rows replace the filters with a ``name in`` (488-489). ``owner`` is appended to the
    query as upstream does (472-476), for its owner-only export rule; here the rule is
    not modelled, so the column is fetched and not written.
    """
    if not registry.has_doctype(doctype):
        raise DoesNotExistError(f"DocType {doctype} not found")

    fields = parse_json_param(fields, fields) or ["name"]
    if isinstance(fields, str):
        fields = [fields]
    fields = [str(f) for f in fields]
    filters = parse_json_param(filters, filters)
    or_filters = parse_json_param(or_filters, or_filters)
    selection = parse_json_param(selected_items, selected_items)
    if selection:
        filters = {"name": ["in", list(selection)]}
        or_filters = None

    rows = fetch_rows(
        doctype,
        fields=[*fields, "owner"] if "owner" not in fields else fields,
        filters=filters,
        or_filters=or_filters,
        order_by=order_by,
        limit_page_length=None,
    )

    info = field_info(doctype, fields)
    data: list[list] = [["Sr", *(column["label"] for column in info)]]
    for index, row in enumerate(rows, start=1):
        values = []
        for column in info:
            value = row.get(column["fieldname"])
            if column["fieldtype"] == "Duration" and value:
                value = format_duration(value)
            values.append(_cell(value))
        data.append([index, *values])

    title = title or doctype
    if file_format_type == "CSV":
        extension, content = "csv", to_csv_bytes(data)
    else:
        extension, content = "xlsx", to_xlsx_bytes(data, doctype)

    response = HttpResponse(content, content_type=CONTENT_TYPES[extension])
    response["Content-Disposition"] = f'attachment; filename="{title}.{extension}"'
    return response
