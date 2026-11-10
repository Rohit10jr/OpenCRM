"""Whitelisted Data Import methods from the version-15 framework."""

from frappe_core import permissions
from frappe_core import registry
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.exceptions import throw
from frappe_core.query import fetch_rows, parse_json_param
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

from crm_app.api.user import only_for
from crm_app.data_import.documents import (
    IMPORTABLE_DOCTYPES,
    get_data_import,
    get_preview,
)
from crm_app.data_import.exporter import Exporter
from crm_app.data_import.run import (
    claim_import,
    get_import_logs as load_import_logs,
    release_import,
    start_data_import_task,
)


@whitelist("frappe.core.doctype.data_import.data_import.download_template")
def download_template(
    doctype: str,
    export_fields=None,
    export_records: str | None = None,
    export_filters=None,
    file_type: str = "CSV",
    **_ignored,
):
    """Download an import template using version-15's ``Exporter`` wire shape."""
    # Port only: upstream permits any user with read permission.  The port has no
    # DocType import permission and limits Data Import itself to its administrators
    # (``UPSTREAM_BUGS.md`` 82).
    only_for(["System Manager"])
    if doctype not in IMPORTABLE_DOCTYPES:
        raise FrappePermissionError(
            f"{doctype} is not available for data import", title="Not Permitted"
        )

    # Upstream's read-permission check remains after the narrower port gate.  The port
    # has no model-level ``has_permission(doctype, "read")`` flag, so perform the same
    # permission-filtered list read its generic route uses.  This also applies to blank
    # templates, whose Exporter otherwise has no reason to query a row.
    if not registry.has_doctype(doctype):
        raise FrappePermissionError(
            f"Not permitted to read {doctype}", title="Not Permitted"
        )
    fetch_rows(doctype, fields=["name"], limit_page_length=1)

    # Upstream leaves the response empty for an unknown type.  Port only: fail clearly
    # instead, so the caller does not download a zero-byte file (``UPSTREAM_BUGS.md`` 83).
    if file_type not in ("CSV", "Excel"):
        throw("File type must be CSV or Excel")

    exporter = Exporter(
        doctype,
        export_fields=parse_json_param(export_fields, {}) or {},
        export_data=export_records != "blank_template",
        export_filters=parse_json_param(export_filters, export_filters),
        export_page_length=5 if export_records == "5_records" else None,
        file_type=file_type,
    )
    return exporter.build_response()


@whitelist("frappe.core.doctype.data_import.data_import.get_preview_from_template")
def get_preview_from_template(
    data_import: str,
    import_file: str | None = None,
    google_sheets_url: str | None = None,
):
    document = get_data_import(data_import)
    user = get_current_user()
    if not permissions.check_object_permission(document, "read", user):
        raise FrappePermissionError(
            f"Not permitted to read Data Import {data_import}", title="Not Permitted"
        )

    if not document.import_file:
        return None

    # Upstream replaces the document's source with the caller-supplied arguments.
    # Port only: ignore both arguments and preview the persisted attachment, preventing
    # this endpoint from becoming a reader for an arbitrary File URL
    # (``UPSTREAM_BUGS.md`` 77).
    return get_preview(document)


@whitelist("frappe.core.doctype.data_import.data_import.get_import_logs")
def get_import_logs(data_import: str):
    document = get_data_import(data_import)
    user = get_current_user()
    if not permissions.check_object_permission(document, "read", user):
        raise FrappePermissionError(
            f"Not permitted to read Data Import {data_import}", title="Not Permitted"
        )
    return load_import_logs(data_import)


@whitelist(
    "frappe.core.doctype.data_import.data_import.form_start_import", methods=("POST",)
)
def form_start_import(data_import: str):
    document = get_data_import(data_import)
    user = get_current_user()
    if not permissions.check_object_permission(document, "write", user):
        raise FrappePermissionError(
            f"Not permitted to write Data Import {data_import}", title="Not Permitted"
        )

    claimed_at = claim_import(data_import)
    if claimed_at is None:
        return False
    try:
        # The user name is a JSON Celery argument; the worker must recreate the request
        # identity and reauthorize because roles can change while a job is queued.
        start_data_import_task.delay(str(data_import), str(user))
    except Exception:
        release_import(data_import, claimed_at)
        raise
    return True
