"""Persistence helpers for Frappe-compatible CSV imports."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

from frappe_core.exceptions import DoesNotExistError, throw
from frappe_platform import files as file_store
from frappe_platform.models import DataImport, DataImportLog

from .importer import INSERT, ImportFile


IMPORTABLE_DOCTYPES = frozenset(
    {
        "CRM Lead",
        "CRM Deal",
        "Contact",
        "CRM Organization",
        "CRM Task",
        "CRM Call Log",
    }
)


def get_data_import(name: str) -> DataImport:
    document = DataImport._default_manager.filter(pk=str(name)).first()
    if document is None:
        raise DoesNotExistError(f"Data Import {name} not found")
    return document


def read_attached_file(data_import: DataImport) -> bytes:
    """Return the attached CSV bytes when the current user may read its File row."""
    file_doc = file_store.find_file_by_url(data_import.import_file)
    if file_doc is None:
        throw("Invalid template file for import")

    extension = Path(urlsplit(file_doc.file_url).path).suffix.lower()
    if extension != ".csv":
        # Upstream accepts Excel workbooks here.
        # Port only: CSV is this port's sole parser (``UPSTREAM_BUGS.md`` 76).
        throw(
            "Import template should be of type .csv, .xlsx or .xls",
            title="Template Error",
        )

    path = file_store.path_for_url(file_doc.file_url)
    if path is None:
        throw("Invalid template file for import")
    try:
        return path.read_bytes()
    except OSError:
        throw("Invalid template file for import")


def build_import_file(data_import: DataImport) -> ImportFile:
    return ImportFile(
        data_import.reference_doctype,
        read_attached_file(data_import),
        data_import.template_options,
        data_import.import_type or INSERT,
    )


def get_preview(data_import: DataImport) -> dict:
    preview = build_import_file(data_import).get_data_for_import_preview()
    logs = DataImportLog._default_manager.filter(data_import=str(data_import.pk)).order_by(
        "log_index"
    )[:10]
    preview["import_log"] = [
        {
            "row_indexes": _json_string(log.row_indexes),
            "success": log.success,
        }
        for log in logs
    ]
    return preview


def _json_string(value) -> str:
    if isinstance(value, str) and value:
        try:
            json.loads(value)
        except (TypeError, ValueError):
            pass
        else:
            return value
    return json.dumps(value or [])
