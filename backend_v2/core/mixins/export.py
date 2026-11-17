"""Raw list exports for document resources that opt in."""

import csv
import html
import io
import re
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from rest_framework.decorators import action

from core.exceptions import throw
from core.inputs import build_payload, parse_json_param
from core.query import fetch_rows
from core.translate import _
CONTENT_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_TAG_RE = re.compile(r"<[^>]+>")

def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def format_duration(seconds, hide_days: bool = False) -> str:
    seconds = _int(seconds)
    negative = seconds < 0
    seconds = abs(seconds)
    days = (seconds // 86400) if not hide_days else 0
    hours = ((seconds % 86400) // 3600) if not hide_days else (seconds // 3600)
    minutes = (seconds % 3600) // 60
    seconds %= 60
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
    if "<" not in value or ">" not in value:
        return value
    text = html.unescape(
        _TAG_RE.sub(" ", value.replace("</p>", "\n").replace("<br>", "\n"))
    )
    return " ".join(text.split())

def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat(sep=" ") if hasattr(value, "hour") else value.isoformat()
    return value

def to_csv_bytes(data: list[list], delimiter=",", quoting=csv.QUOTE_NONNUMERIC) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, quoting=quoting)
    writer.writerows(
        [handle_html(value) if isinstance(value, str) else value for value in row]
        for row in data
    )
    return buffer.getvalue().encode("utf-8")

def to_xlsx_bytes(data: list[list], sheet_name: str) -> bytes:
    try:
        import xlsxwriter
    except ImportError:  # pragma: no cover - an environment failure
        throw(_("Excel export needs the XlsxWriter package; install it, or export as CSV"))
    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    sheet = workbook.add_worksheet(re.sub(r"[\[\]:*?/\\]", " ", sheet_name)[:31] or "Sheet1")
    sheet.set_row(0, cell_format=workbook.add_format({"bold": True}))
    widths: list[int] = []
    for row_index, row in enumerate(data):
        for column_index, value in enumerate(row):
            text = "" if value is None else str(value)
            if column_index >= len(widths):
                widths.append(0)
            widths[column_index] = max(widths[column_index], min(len(text), 60))
            sheet.write(row_index, column_index, value)
    for column_index, width in enumerate(widths):
        sheet.set_column(column_index, column_index, width + 2)
    workbook.close()
    return buffer.getvalue()

class ListExportMixin:
    def get_export_field_info(self, fields: list[str]) -> list[dict]:
        provider = getattr(self, "export_field_info", None)
        if not callable(provider):
            raise ImproperlyConfigured(
                f"{type(self).__name__} must define a callable export_field_info provider."
            )
        return provider(fields)

    @action(detail=False, methods=("get", "post"), url_path="export")
    def export(self, request):
        inputs = build_payload(request)
        fields = parse_json_param(inputs.get("fields"), inputs.get("fields")) or ["name"]
        if isinstance(fields, str):
            fields = [fields]
        fields = [str(field) for field in fields]
        info = self.get_export_field_info(fields)
        filters = parse_json_param(inputs.get("filters"), inputs.get("filters"))
        or_filters = parse_json_param(inputs.get("or_filters"), inputs.get("or_filters"))
        selection = parse_json_param(inputs.get("selected_items"), inputs.get("selected_items"))
        if selection:
            filters = {"name": ["in", list(selection)]}
            or_filters = None
        query_fields = fields if "owner" in fields else [*fields, "owner"]
        rows = fetch_rows(
            self.get_queryset(),
            user=request.user,
            fields=query_fields,
            filters=filters,
            or_filters=or_filters,
            order_by=inputs.get("order_by"),
            # The shared query layer uses zero (rather than None) for an unlimited slice.
            limit_page_length=0,
            selectable=self.readable_fields,
            filterable=self.filterable_fields,
            sortable=self.sortable_fields,
        )
        data: list[list] = [["Sr", *(column["label"] for column in info)]]
        for index, row in enumerate(rows, start=1):
            values = []
            for column in info:
                value = row.get(column["fieldname"])
                if column["fieldtype"] == "Duration" and value:
                    value = format_duration(value)
                values.append(_cell(value))
            data.append([index, *values])
        title = inputs.get("title") or self.document_type
        if inputs.get("file_format_type", "Excel") == "CSV":
            extension, content = "csv", to_csv_bytes(data)
        else:
            extension, content = "xlsx", to_xlsx_bytes(data, self.document_type)
        response = HttpResponse(content, content_type=CONTENT_TYPES[extension])
        response["Content-Disposition"] = f'attachment; filename="{title}.{extension}"'
        return response
