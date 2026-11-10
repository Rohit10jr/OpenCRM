"""Parse Frappe Data Import CSV files without writing to the database.

The class and method names follow version-15
``frappe/core/doctype/data_import/importer.py`` so behavior can be compared directly.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable
from datetime import date, datetime, time
from html import escape

from frappe_core import field_meta, registry
from frappe_core.exceptions import throw

INVALID_VALUES = ("", None)
MAX_ROWS_IN_PREVIEW = 10
INSERT = "Insert New Records"
DURATION_PATTERN = re.compile(r"^(?:(\d+d)?((^|\s)\d+h)?((^|\s)\d+m)?((^|\s)\d+s)?)$")

FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")
DATE_FORMATS = (
    "%d/%b/%y",
    "%d-%m-%Y",
    "%m-%d-%Y",
    "%Y-%m-%d",
    "%d-%m-%y",
    "%m-%d-%y",
    "%y-%m-%d",
    "%y-%b-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y/%m/%d",
    "%d/%m/%y",
    "%m/%d/%y",
    "%y/%m/%d",
    "%d.%m.%Y",
    "%m.%d.%Y",
    "%Y.%m.%d",
    "%d.%m.%y",
    "%m.%d.%y",
    "%y.%m.%d",
    "%d %b %Y",
    "%d %B %Y",
    "%d-%b-%Y",
)
TIME_FORMATS = (
    "%H:%M:%S.%f",
    "%H:%M:%S",
    "%H:%M",
    "%I:%M:%S.%f %p",
    "%I:%M:%S %p",
    "%I:%M %p",
)


class _Dict(dict):
    """The attribute access used by upstream's ``frappe._dict``."""

    __getattr__ = dict.get

    def __setattr__(self, key, value):
        self[key] = value


def _bold(value) -> str:
    return f"<strong>{value}</strong>"


def _cstr(value) -> str:
    return "" if value is None else str(value)


def _cint(value) -> int:
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return 0


def _flt(value) -> float:
    if isinstance(value, str):
        value = value.replace(",", "")
    try:
        return float(value)
    except Exception:
        return 0.0


def _duration_to_seconds(duration: str) -> int:
    value = 0
    for suffix, multiplier in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if suffix in duration:
            amount, duration = duration.split(suffix, 1)
            value += _cint(amount) * multiplier
    return value


def _link_exists(target_doctype: str, value) -> bool:
    if target_doctype == "DocType":
        return registry.has_doctype(_cstr(value))
    if not registry.has_doctype(target_doctype):
        return True
    model = registry.get_model(target_doctype)
    return model._default_manager.filter(pk=value).exists()


def _unescape_formula_injection(value: str) -> str:
    if len(value) > 1 and value[0] == "'" and value[1:].startswith(FORMULA_TRIGGER_CHARS):
        return value[1:]
    return value


def read_csv_content(fcontent: bytes | str) -> list[list[str | None]]:
    """Port of ``frappe.utils.csvutils.read_csv_content`` for in-memory content."""
    if not isinstance(fcontent, str):
        decoded = False
        for encoding in ("utf-8", "windows-1250", "windows-1252"):
            try:
                fcontent = fcontent.decode(encoding)
                decoded = True
                break
            except UnicodeDecodeError:
                continue
        if not decoded:
            throw("Unknown file encoding. Tried utf-8, windows-1250, windows-1252.")

    # Upstream: the decoded content is re-encoded without removing a leading BOM.
    # Port only: stripping the Unicode marker before CSV tokenization preserves both a
    # plain and a quoted first header.
    fcontent = fcontent.removeprefix("\ufeff")
    encoded = fcontent.encode("utf-8")
    content = [line.decode("utf-8") for line in encoded.splitlines(True)]

    try:
        rows = []
        for row in csv.reader(content):
            parsed = []
            for value in row:
                value = _unescape_formula_injection(value.strip())
                parsed.append(value if value != "" else None)
            rows.append(parsed)
        return rows
    except Exception:
        throw("Not a valid Comma Separated Value (CSV File)")


class ImportFile:
    def __init__(self, doctype, file, template_options=None, import_type=None, *, console=False):
        self.doctype = doctype
        if isinstance(template_options, str):
            template_options = json.loads(template_options or "{}")
        self.template_options = template_options or {"column_to_field_map": {}}
        self.column_to_field_map = self.template_options.get("column_to_field_map", {})
        self.import_type = import_type or INSERT
        self.warnings = []
        self.console = console

        if not isinstance(file, (bytes, str)):
            throw("Invalid template file for import")
        if not file:
            throw("Invalid or corrupted content for import")
        self.raw_data = read_csv_content(file)
        self.parse_data_from_template()

    def parse_data_from_template(self):
        header = None
        data = []
        for i, row in enumerate(self.raw_data):
            if all(value in INVALID_VALUES for value in row):
                continue
            if not header:
                header = Header(
                    i,
                    row,
                    self.doctype,
                    self.raw_data[1:],
                    self.column_to_field_map,
                    self.import_type,
                )
            else:
                data.append(Row(i, row, self.doctype, header, self.import_type))

        if header is None or not data:
            throw("Import template should contain a Header and atleast one row.", title="Template Error")
        self.header = header
        self.columns = header.columns
        self.data = data

    def get_data_for_import_preview(self):
        columns = [_Dict({"header_title": "Sr. No", "skip_import": True})]
        columns.extend(column.as_dict() for column in self.columns)
        for column in columns:
            if column.get("df"):
                df = column["df"]
                column["df"] = {
                    key: df.get(key)
                    for key in (
                        "fieldtype",
                        "fieldname",
                        "label",
                        "options",
                        "parent",
                        "reqd",
                        "default",
                        "read_only",
                    )
                }

        out = _Dict(
            data=[[row.row_number, *row.as_list()] for row in self.data],
            columns=columns,
            warnings=self.get_warnings(),
        )
        total = len(out.data)
        if total > MAX_ROWS_IN_PREVIEW:
            out.data = out.data[:MAX_ROWS_IN_PREVIEW]
            out.max_rows_exceeded = True
            out.max_rows_in_preview = MAX_ROWS_IN_PREVIEW
            out.total_number_of_rows = total
        return out

    def get_payloads_for_import(self):
        payloads = []
        data = list(self.data)
        while data:
            doc, rows, data = self.parse_next_row_for_import(data)
            self._set_contact_primary_flags(doc)
            payloads.append(_Dict(doc=doc, rows=rows))
        return payloads

    def parse_next_row_for_import(self, data):
        doctypes = self.header.doctypes
        first_row = data[0]
        rows = [first_row]
        if len(doctypes) > 1:
            parent_indexes = self.header.get_column_indexes(self.doctype)
            for row in data[1:]:
                if all(value in INVALID_VALUES for value in row.get_values(parent_indexes)):
                    rows.append(row)
                    continue
                break

        parent_doc = None
        for row in rows:
            for doctype, table_df in doctypes:
                if doctype == self.doctype and parent_doc is None:
                    parent_doc = row.parse_doc(doctype)
                elif table_df and parent_doc is not None:
                    child_docs = row.parse_child_docs(doctype, parent_doc, table_df)
                    if child_docs:
                        parent_doc.setdefault(table_df.fieldname, []).extend(child_docs)
        return parent_doc, rows, data[len(rows) :]

    def _set_contact_primary_flags(self, doc):
        if self.doctype != "Contact" or not doc:
            return
        # Upstream: imported Contact child rows retain blank primary flags.
        # Port only: imported child rows must populate Contact's denormalized main
        # email and phone values when the file did not choose a primary.
        emails = doc.get("email_ids") or []
        if emails and not any(row.get("is_primary") for row in emails):
            emails[0]["is_primary"] = 1
        phones = doc.get("phone_nos") or []
        for flag in ("is_primary_phone", "is_primary_mobile_no"):
            if phones and not any(row.get(flag) for row in phones):
                phones[0][flag] = 1

    def get_warnings(self):
        warnings = list(self.warnings)
        for column in self.header.columns:
            warnings.extend(column.warnings)
        for row in self.data:
            warnings.extend(row.warnings)
        return warnings


class Row:
    def __init__(self, index, row, doctype, header, import_type):
        self.index = index
        self.row_number = index + 1
        self.doctype = doctype
        self.data = row
        self.header = header
        self.import_type = import_type
        self.warnings = []
        if len(row) != len(header.columns):
            message = (
                "Row has less values than columns"
                if len(row) < len(header.columns)
                else "Row has more values than columns"
            )
            self.warnings.append({"row": self.row_number, "message": message})

    def parse_doc(self, doctype, parent_doc=None, table_df=None):
        indexes = self.header.get_column_indexes(doctype, table_df)
        values = self.get_values(indexes)
        if all(value in INVALID_VALUES for value in values):
            return None
        return self._parse_doc(doctype, self.header.get_columns(indexes), values, parent_doc, table_df)

    def parse_child_docs(self, doctype, parent_doc, table_df):
        indexes = self.header.get_column_indexes(doctype, table_df)
        values = self.get_values(indexes)
        if all(value in INVALID_VALUES for value in values):
            return []
        columns = self.header.get_columns(indexes)
        contact_numbers = [
            (column, value)
            for column, value in zip(columns, values, strict=False)
            if column.contact_detail_field in ("phone", "mobile_no")
            and value not in INVALID_VALUES
        ]
        if self.doctype != "Contact" or table_df.fieldname != "phone_nos" or not contact_numbers:
            return [self._parse_doc(doctype, columns, values, parent_doc, table_df)]

        ordinary = [
            (column, value)
            for column, value in zip(columns, values, strict=False)
            if column.contact_detail_field not in ("phone", "mobile_no")
        ]
        base = self._parse_doc(
            doctype,
            [column for column, _value in ordinary],
            [value for _column, value in ordinary],
            parent_doc,
            table_df,
        )
        docs_by_number = {}
        for column, value in contact_numbers:
            value = self.validate_value(value, column)
            if value is None:
                continue
            number = self.parse_value(value, column)
            doc = docs_by_number.setdefault(number, _Dict(base))
            doc["phone"] = number
            flag = (
                "is_primary_phone"
                if column.contact_detail_field == "phone"
                else "is_primary_mobile_no"
            )
            doc[flag] = 1
        return list(docs_by_number.values())

    def _parse_doc(self, doctype, columns, values, parent_doc=None, table_df=None):
        doc = _Dict()
        for column, value in zip(columns, values, strict=False):
            df = column.df
            if value in INVALID_VALUES:
                value = None
            if value is not None:
                value = self.validate_value(value, column)
            if value is not None:
                doc[df.fieldname] = self.parse_value(value, column)
        return doc

    def validate_value(self, value, col):
        df = col.df
        if df.fieldtype == "Select":
            options = get_select_options(df)
            if options and _cstr(value) not in options:
                valid = ", ".join(_bold(option) for option in options)
                self.warnings.append(
                    {
                        "row": self.row_number,
                        "field": df_as_json(df),
                        "message": f"Value must be one of {valid}",
                    }
                )
                return None
        elif df.fieldtype == "Link" and not self.link_exists(value, df):
            self.warnings.append(
                {
                    "row": self.row_number,
                    "field": df_as_json(df),
                    "message": f"Value {_bold(escape(_cstr(value)))} missing for {_bold(df.options)}",
                }
            )
            return None
        elif df.fieldtype in ("Date", "Datetime"):
            parsed = self.get_date(value, col)
            if isinstance(parsed, str):
                self.warnings.append(
                    {
                        "row": self.row_number,
                        "col": col.column_number,
                        "field": df_as_json(df),
                        "message": (
                            f"Value {_bold(escape(_cstr(value)))} must in "
                            f"{_bold(get_user_format(col.date_format))} format"
                        ),
                    }
                )
                return None
            return parsed
        elif df.fieldtype == "Duration" and not DURATION_PATTERN.match(_cstr(value)):
            self.warnings.append(
                {
                    "row": self.row_number,
                    "col": col.column_number,
                    "field": df_as_json(df),
                    "message": (
                        f"Value {_bold(escape(_cstr(value)))} must be in the valid duration "
                        "format: d h m s"
                    ),
                }
            )
            # Upstream: parse_value throws for the invalid duration after warning.
            # Port only: keep the warning blocking and omit the invalid cell.
            return None
        return value

    def link_exists(self, value, df):
        return _link_exists(df.options, value)

    def parse_value(self, value, col):
        df = col.df
        if not isinstance(value, (datetime, date)):
            value = _cstr(value)
        valid_checks = ("t", "f", "true", "false", "yes", "no", "y", "n")
        if df.fieldtype == "Check" and value.lower().strip() in valid_checks:
            value = 1 if value.lower().strip() in ("t", "true", "y", "yes") else 0
        if df.fieldtype in ("Int", "Check"):
            return _cint(value)
        if df.fieldtype in ("Float", "Percent", "Currency"):
            return _flt(value)
        if df.fieldtype in ("Date", "Datetime"):
            parsed = self.get_date(value, col)
            if isinstance(parsed, datetime):
                return parsed.date().isoformat() if df.fieldtype == "Date" else parsed.isoformat()
            if isinstance(parsed, date):
                return parsed.isoformat()
            return parsed
        if df.fieldtype == "Duration":
            return _duration_to_seconds(value)
        return value

    def get_date(self, value, column):
        if isinstance(value, (datetime, date)):
            return value
        if column.date_format:
            try:
                return datetime.strptime(value, column.date_format)
            except ValueError:
                pass
        return value

    def get_values(self, indexes):
        # Upstream: indexing every requested position raises IndexError on a short row.
        # Port only: the blocking warning recorded in ``__init__`` is returned and
        # missing cells remain blank.
        return [self.data[index] if index < len(self.data) else None for index in indexes]

    def get(self, index):
        return self.data[index]

    def as_list(self):
        return self.data


class Header(Row):
    def __init__(self, index, row, doctype, raw_data, column_to_field_map=None, import_type=None):
        self.index = index
        self.row_number = index + 1
        self.data = row
        self.doctype = doctype
        self.seen = []
        self.columns = []
        column_to_field_map = column_to_field_map or {}
        for j, header in enumerate(row):
            values = [item[j] if j < len(item) else None for item in raw_data]
            map_to_field = column_to_field_map.get(str(j))
            column = Column(
                j, header, doctype, values, map_to_field, self.seen, import_type
            )
            self.seen.append(header)
            self.columns.append(column)

        doctypes = []
        seen = set()
        for column in self.columns:
            if not column.df:
                continue
            table_df = column.df.get("child_table_df")
            key = (column.df.parent, table_df.fieldname if table_df else None)
            if key not in seen:
                doctypes.append((column.df.parent, table_df))
                seen.add(key)
        self.doctypes = sorted(doctypes, key=lambda item: -1 if item[0] == doctype else 1)

    def get_column_indexes(self, doctype, tablefield=None):
        def is_table_field(df):
            if tablefield:
                child_table_df = df.get("child_table_df")
                return child_table_df and child_table_df.fieldname == tablefield.fieldname
            return True

        return [
            column.index
            for column in self.columns
            if not column.skip_import
            and column.df
            and column.df.parent == doctype
            and is_table_field(column.df)
        ]

    def get_columns(self, indexes):
        return [self.columns[index] for index in indexes]


class Column:
    def __init__(
        self, index, header, doctype, column_values, map_to_field=None, seen=None, import_type=None
    ):
        self.index = index
        self.column_number = index + 1
        self.doctype = doctype
        self.header_title = header
        self.column_values = column_values
        self.map_to_field = map_to_field
        self.seen = seen or []
        self.import_type = import_type or INSERT
        self.date_format = None
        self.df = None
        self.contact_detail_field = None
        self.skip_import = None
        self.warnings = []
        self.parse()
        self.validate_values()

    def parse(self):
        header_title = self.header_title
        column_number = str(self.column_number)
        lookup = self.map_to_field if self.map_to_field and self.map_to_field != "Don't Import" else header_title

        df = get_df_for_column_header(self.doctype, lookup)
        # Upstream: Contact's derived parent fields are accepted and then overwritten
        # from child rows on save.
        # Port only: whether matched by label, fieldname, or an explicit map, resolve
        # those fields to their real child tables.
        if self.doctype == "Contact" and df and df.parent == "Contact":
            child_lookup = {
                "email_id": "email_ids.email_id",
                "phone": "phone_nos.phone",
                "mobile_no": "phone_nos.phone",
            }.get(df.fieldname)
            if child_lookup:
                self.contact_detail_field = df.fieldname
                df = get_df_for_column_header(self.doctype, child_lookup)
        if self.map_to_field and self.map_to_field != "Don't Import":
            if df:
                self.warnings.append(
                    {
                        "message": (
                            f"Mapping column {_bold(escape(header_title) if header_title else '<i>Untitled Column</i>')} "
                            f"to field {_bold(df.label)}"
                        ),
                        "type": "info",
                    }
                )
            else:
                self.warnings.append(
                    {
                        "message": f"Could not map column {column_number} to field {self.map_to_field}",
                        "type": "info",
                    }
                )

        skip_import = not bool(df)
        if header_title in self.seen:
            self.warnings.append(
                {
                    "col": column_number,
                    "message": f"Skipping Duplicate Column {_bold(escape(header_title or ''))}",
                    "type": "info",
                }
            )
            df = None
            skip_import = True
        elif self.map_to_field == "Don't Import":
            skip_import = True
            self.warnings.append(
                {
                    "col": column_number,
                    "message": f"Skipping column {_bold(escape(header_title or ''))}",
                    "type": "info",
                }
            )
        # Upstream: name and ID columns are parsed, including their update-oriented
        # autoname mapping.
        # Port only: insert imports cannot honor an explicit document name, so accepting
        # one here would give a false promise.
        elif self.import_type != "Update Existing Records" and lookup in ("name", "ID"):
            df = None
            skip_import = True
            self.warnings.append(
                {
                    "col": column_number,
                    "message": f"Skipping column {_bold(escape(header_title or ''))}",
                    "type": "info",
                }
            )
        elif header_title and not df:
            self.warnings.append(
                {
                    "col": column_number,
                    "message": f"Cannot match column {_bold(escape(header_title))} with any field",
                    "type": "info",
                }
            )
        elif not header_title and not df:
            self.warnings.append(
                {"col": column_number, "message": "Skipping Untitled Column", "type": "info"}
            )
        self.df = df
        self.skip_import = skip_import

    def guess_date_format_for_column(self):
        def guess(value):
            if isinstance(value, (datetime, date, time)):
                return {
                    "Date": "%Y-%m-%d",
                    "Datetime": "%Y-%m-%d %H:%M:%S",
                    "Time": "%H:%M:%S",
                }.get(self.df.fieldtype)
            return guess_date_format(value) if isinstance(value, str) else None

        formats = [fmt for value in self.column_values if (fmt := guess(value))]
        if not formats:
            return None
        # Upstream: a set supplies the candidates, making equal-frequency ties
        # process-random.
        # Port only: the earliest format observed wins an exact tie.
        unique = list(dict.fromkeys(formats))
        most_common = max(unique, key=formats.count)
        if len(unique) > 1:
            message = (
                "The column {0} has {1} different date formats. Automatically setting {2} "
                "as the default format as it is the most common. Please change other values "
                "in this column to this format."
            )
            self.warnings.append(
                {
                    "col": self.column_number,
                    "message": message.format(
                        _bold(escape(self.header_title or "")),
                        len(unique),
                        _bold(get_user_format(most_common)),
                    ),
                    "type": "info",
                }
            )
        return most_common

    def validate_values(self):
        if not self.df or self.skip_import or not any(self.column_values):
            return
        if self.df.fieldtype == "Link":
            values = list(dict.fromkeys(_cstr(value) for value in self.column_values if value))
            missing = [value for value in values if not _link_exists(self.df.options, value)]
            if missing:
                self.warnings.append(
                    {
                        "col": self.column_number,
                        "message": (
                            f"The following values do not exist for {self.df.options}: "
                            + ", ".join(escape(value) for value in missing)
                        ),
                        "type": "warning",
                    }
                )
        elif self.df.fieldtype in ("Date", "Time", "Datetime"):
            self.date_format = self.guess_date_format_for_column()
            if not self.date_format:
                if self.df.fieldtype == "Time":
                    self.date_format, display = "%H:%M:%S", "HH:mm:ss"
                else:
                    self.date_format, display = "%Y-%m-%d", "yyyy-mm-dd"
                self.warnings.append(
                    {
                        "col": self.column_number,
                        "message": (
                            f"{self.df.fieldtype} format could not be determined from the values "
                            f"in this column. Defaulting to {display}."
                        ),
                        "type": "info",
                    }
                )
        elif self.df.fieldtype == "Select":
            options = get_select_options(self.df)
            invalid = sorted({_cstr(value) for value in self.column_values if value} - set(options))
            if options and invalid:
                self.warnings.append(
                    {
                        "col": self.column_number,
                        "message": (
                            "The following values are invalid: {0}. Values must be one of {1}"
                        ).format(
                            ", ".join(_bold(escape(value)) for value in invalid),
                            ", ".join(_bold(option) for option in options),
                        ),
                    }
                )

    def as_dict(self):
        out = _Dict(
            index=self.index,
            column_number=self.column_number,
            doctype=self.doctype,
            header_title=self.header_title,
            map_to_field=self.map_to_field,
            date_format=self.date_format,
            df=self.df,
            skip_import=self.skip_import,
            warnings=self.warnings,
        )
        if self.df and self.df.get("is_child_table_field"):
            out.is_child_table_field = True
            out.child_table_df = self.df.child_table_df
        return out


def _field_descriptor(doctype: str, field: dict, table_df=None) -> _Dict:
    descriptor = _Dict(
        fieldtype=field.get("fieldtype") or "Data",
        fieldname=field.get("fieldname"),
        label=(field.get("label") or "").strip(),
        options=field.get("options"),
        parent=doctype,
        reqd=field.get("reqd", 0),
        default=field.get("default"),
        read_only=field.get("read_only", 0),
    )
    if table_df:
        descriptor.is_child_table_field = True
        descriptor.child_table_df = table_df
    return descriptor


def build_fields_dict_for_column_matching(parent_doctype):
    """Build upstream's label/fieldname/header map from generated field metadata."""
    out = {}
    table_fields = [
        field for field in field_meta.get_fields(parent_doctype) if field.get("fieldtype") == "Table"
    ]
    doctypes = [(parent_doctype, None)] + [
        (field["options"], _field_descriptor(parent_doctype, field)) for field in table_fields
    ]
    for doctype, table_df in doctypes:
        table_ref = (table_df.label or table_df.fieldname) if table_df else None
        name_df = _field_descriptor(
            doctype,
            {"fieldtype": "Data", "fieldname": "name", "label": "ID", "reqd": 1},
            table_df,
        )
        name_headers = (
            ("name", "ID", "ID")
            if doctype == parent_doctype
            else (f"{table_df.fieldname}.name", f"ID ({table_ref})", f"ID ({table_ref})")
        )
        for header in name_headers:
            out[header] = name_df

        standard = (
            [
                {"label": "Parent", "fieldname": "parent"},
                {"label": "Parent Type", "fieldname": "parenttype"},
                {"label": "Parent Field", "fieldname": "parentfield"},
                {"label": "Row Index", "fieldname": "idx"},
            ]
            if registry.get_entry(doctype).is_child_table
            else [
                {"label": "Owner", "fieldname": "owner"},
                {"label": "Document Status", "fieldname": "docstatus", "fieldtype": "Int"},
            ]
        )
        fields: Iterable[dict] = [*standard, *field_meta.get_fields(doctype)]
        for raw in fields:
            if raw.get("fieldtype") in field_meta.NO_VALUE_FIELDTYPES:
                continue
            df = _field_descriptor(doctype, raw, table_df)
            label = df.label
            if doctype == parent_doctype:
                if label not in out:
                    out[label] = df
                out[df.fieldname] = df
                out[f"{label} ({df.fieldname})"] = df
            else:
                for header in (
                    f"{table_df.fieldname}.{df.fieldname}",
                    f"{label} ({table_ref})",
                ):
                    out[header] = df

    autoname = field_meta.get_doctype_properties(parent_doctype).get("autoname") or ""
    if autoname.startswith("field:"):
        fieldname = autoname.removeprefix("field:")
        raw = field_meta.get_field(parent_doctype, fieldname)
        if raw:
            autoname_df = _field_descriptor(parent_doctype, raw)
            for header in (
                f"ID ({autoname_df.label})",
                "ID",
                "name",
            ):
                out[header] = autoname_df
    return out


def get_df_for_column_header(doctype, header):
    return build_fields_dict_for_column_matching(doctype).get(header)


def guess_date_format(value: str) -> str | None:
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(value, fmt)
            return fmt
        except ValueError:
            pass
    for fmt in TIME_FORMATS:
        try:
            datetime.strptime(value, fmt)
            return fmt
        except ValueError:
            pass
    if " " in value:
        date_value, time_value = value.split(" ", 1)
        date_fmt = guess_date_format(date_value)
        time_fmt = guess_date_format(time_value)
        if date_fmt in DATE_FORMATS and time_fmt in TIME_FORMATS:
            return f"{date_fmt} {time_fmt}"
    return None


def get_user_format(date_format):
    return date_format.replace("%Y", "yyyy").replace("%y", "yy").replace("%m", "mm").replace("%d", "dd")


def df_as_json(df):
    return {
        "fieldname": df.fieldname,
        "fieldtype": df.fieldtype,
        "label": df.label,
        "options": df.options,
        "parent": df.parent,
        "default": df.default,
    }


def get_select_options(df):
    return [option for option in (df.options or "").split("\n") if option]
