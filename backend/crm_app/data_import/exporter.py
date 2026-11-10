"""Import-template export, ported from version-15's Data Import ``Exporter``."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from decimal import Decimal

from django.http import HttpResponse

from frappe_core import children, field_meta, registry
from frappe_core.query import base_queryset, fetch_rows, resolve_fields

from crm_app.api.reportview import CONTENT_TYPES, _cell, format_duration, to_xlsx_bytes


# ``frappe/model/__init__.py``.  Kept separate, as upstream does, even though every
# display fieldtype is also a no-value fieldtype in version 15.
display_fieldtypes = (
    "Section Break",
    "Column Break",
    "Tab Break",
    "Attachment Gallery",
    "HTML",
    "Button",
    "Image",
    "Fold",
    "Heading",
)
no_value_fields = (
    "Section Break",
    "Column Break",
    "Tab Break",
    "Attachment Gallery",
    "HTML",
    "Table",
    "Table MultiSelect",
    "Button",
    "Image",
    "Fold",
    "Heading",
)

FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


class _Dict(dict):
    __getattr__ = dict.get

    def __setattr__(self, key, value):
        self[key] = value


def _descriptor(doctype: str, field: dict) -> _Dict:
    return _Dict(
        fieldtype=field.get("fieldtype") or "Data",
        fieldname=field.get("fieldname"),
        label=(field.get("label") or "").strip(),
        parent=doctype,
        options=field.get("options"),
        reqd=field.get("reqd", 0),
        hide_days=field.get("hide_days", 0),
    )


def _escape_formula_injection(value):
    if isinstance(value, str) and value.startswith(FORMULA_TRIGGER_CHARS):
        return "'" + value
    return value


def _database_export_value(value):
    # Port only: Django returns Check and decimal cells as bool and Decimal, while
    # Frappe's database layer gives the exporter 0/1 and float values respectively.
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


def to_csv(data: Iterable[Iterable]) -> bytes:
    """``frappe.utils.csvutils.to_csv`` without the list-export HTML conversion."""
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)
    for row in data:
        writer.writerow([_escape_formula_injection(value) for value in row])
    return output.getvalue().encode("utf-8")


class Exporter:
    def __init__(
        self,
        doctype,
        export_fields=None,
        export_data=False,
        export_filters=None,
        export_page_length=None,
        file_type="CSV",
    ):
        self.doctype = doctype
        self.meta = field_meta.get_fields(doctype)
        self.export_fields = export_fields or {}
        self.export_filters = export_filters
        self.export_page_length = export_page_length
        self.file_type = file_type
        self.csv_array = []

        self.exportable_fields = self.get_all_exportable_fields()
        self.fields = self.serialize_exportable_fields()
        self.add_header()

        if export_data:
            self.data = self.get_data_to_export()
        else:
            self.data = []
        self.add_data()

    def get_all_exportable_fields(self):
        child_table_fields = {
            df["fieldname"]: df for df in self.meta if df.get("fieldtype") == "Table"
        }
        exportable_fields = _Dict()

        if not isinstance(self.export_fields, dict):
            return exportable_fields
        for key, fieldnames in self.export_fields.items():
            if not isinstance(fieldnames, list):
                continue
            if key == self.doctype:
                exportable_fields[key] = self.get_exportable_fields(key, fieldnames)
            elif key in child_table_fields:
                exportable_fields[key] = self.get_exportable_fields(
                    child_table_fields[key].get("options"), fieldnames
                )
        return exportable_fields

    def serialize_exportable_fields(self):
        fields = []
        for key, exportable_fields in self.exportable_fields.items():
            for exported in exportable_fields:
                df = _Dict(exported.copy())
                df.is_child_table_field = key != self.doctype
                if df.is_child_table_field:
                    df.child_table_df = _descriptor(
                        self.doctype, field_meta.get_field(self.doctype, key)
                    )
                fields.append(df)
        return fields

    def get_exportable_fields(self, doctype, fieldnames):
        if not doctype or not registry.has_doctype(doctype):
            return []

        blocked_types = display_fieldtypes + no_value_fields
        fields = []
        for fieldname in fieldnames:
            # ``name`` is a standard field rather than a DocField upstream.  The port's
            # model-derived metadata includes it, so skip it here to avoid adding it twice.
            if fieldname == "name":
                continue
            raw = field_meta.get_field(doctype, fieldname)
            if raw and raw.get("fieldtype") not in blocked_types:
                fields.append(_descriptor(doctype, raw))

        if "name" in fieldnames:
            fields.insert(
                0,
                _Dict(
                    fieldtype="Data",
                    fieldname="name",
                    label="ID",
                    reqd=1,
                    parent=doctype,
                    hide_days=0,
                ),
            )
        return fields

    def get_data_to_export(self):
        table_fields = [
            field for field in self.exportable_fields if field != self.doctype
        ]
        data = self.get_data_as_docs()

        # Upstream checks ``frappe.permissions.can_export`` here.  This port has no
        # equivalent permission type; the endpoint's System Manager/importable-doctype
        # gate and the permission-filtered list read below are the export authority.
        for doc in data:
            rows = self.add_data_row(self.doctype, None, doc, [], 0)
            for fieldname in table_fields:
                table_df = field_meta.get_field(self.doctype, fieldname)
                child_doctype = table_df.get("options")
                for index, child_row in enumerate(doc.get(fieldname, [])):
                    rows = self.add_data_row(
                        child_doctype,
                        child_row.get("parentfield"),
                        child_row,
                        rows,
                        index,
                    )
            yield from rows

    def add_data_row(self, doctype, parentfield, doc, rows, row_idx):
        if len(rows) < row_idx + 1:
            rows.append([""] * len(self.fields))
        row = rows[row_idx]

        for index, df in enumerate(self.fields):
            if df.parent != doctype:
                continue
            if df.is_child_table_field and df.child_table_df.fieldname != parentfield:
                continue
            value = doc.get(df.fieldname)
            if df.fieldtype == "Duration":
                value = format_duration(value or 0, bool(df.hide_days))
            row[index] = _cell(_database_export_value(value))
        return rows

    @staticmethod
    def _instance_value(instance, fieldname):
        model_field = type(instance)._meta.get_field(fieldname)
        return getattr(
            instance, model_field.attname if model_field.is_relation else fieldname
        )

    def get_data_as_docs(self):
        parent_fields = [
            df.fieldname for df in self.fields if df.parent == self.doctype
        ]
        selected = list(dict.fromkeys(["name", "owner", *parent_fields]))
        parent_data = fetch_rows(
            self.doctype,
            filters=self.export_filters,
            fields=selected,
            limit_page_length=self.export_page_length,
            order_by="creation desc",
        )

        # Child fields are read only through the port's child-table path.  Validate their
        # columns with the same field-security allowlist as a list request first.
        child_specs = children.discover_child_tables(registry.get_model(self.doctype))
        for key in self.exportable_fields:
            if key == self.doctype:
                continue
            spec = child_specs.get(key)
            if spec:
                requested = [
                    df.fieldname for df in self.fields if df.parent == spec["doctype"]
                ]
                resolve_fields(spec["model"], requested)

        names = [row["name"] for row in parent_data]
        instances = {
            str(instance.pk): instance
            for instance in base_queryset(self.doctype).filter(pk__in=names)
        }
        for doc in parent_data:
            instance = instances.get(str(doc["name"]))
            if instance is None:
                continue
            exported = dict(doc)
            for key in self.exportable_fields:
                if key == self.doctype or key not in child_specs:
                    continue
                spec = child_specs[key]
                requested = [
                    df.fieldname for df in self.fields if df.parent == spec["doctype"]
                ]
                exported[key] = [
                    {
                        **{
                            fieldname: self._instance_value(child, fieldname)
                            for fieldname in requested
                        },
                        "parentfield": getattr(child, "parentfield", key),
                    }
                    for child in children.read_children(instance, spec)
                ]
            yield exported

    def add_header(self):
        header = []
        for df in self.fields:
            is_parent = not df.is_child_table_field
            if is_parent:
                label = df.label or df.fieldname
            else:
                table_label = df.child_table_df.label or df.child_table_df.fieldname
                label = f"{df.label or df.fieldname} ({table_label})"

            if label in header:
                label = (
                    df.fieldname
                    if is_parent
                    else f"{df.child_table_df.fieldname}.{df.fieldname}"
                )
            header.append(label)
        self.csv_array.append(header)

    def add_data(self):
        self.csv_array += self.data

    def get_csv_array(self):
        return self.csv_array

    def get_csv_array_for_export(self):
        csv_array = self.csv_array
        if not self.data:
            csv_array += [[]] * 2
        return csv_array

    def build_response(self):
        data = self.get_csv_array_for_export()
        if self.file_type == "CSV":
            extension, content = "csv", to_csv(data)
        elif self.file_type == "Excel":
            extension, content = "xlsx", to_xlsx_bytes(data, self.doctype)
        else:  # The endpoint validates before constructing the exporter.
            return HttpResponse()

        response = HttpResponse(content, content_type=CONTENT_TYPES[extension])
        response["Content-Disposition"] = (
            f'attachment; filename="{self.doctype}.{extension}"'
        )
        return response

    def group_children_data_by_parent(self, children_data: dict[str, list]):
        """Keep upstream's public grouping helper for callers comparing the ports."""
        grouped = {}
        for fieldname, rows in children_data.items():
            for row in rows:
                parent = str(row.get("parent"))
                grouped.setdefault(parent, {}).setdefault(fieldname, []).append(row)
        return grouped
