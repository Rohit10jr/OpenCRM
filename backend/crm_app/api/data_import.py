"""Whitelisted Data Import methods from the version-15 framework."""

from frappe_core import permissions
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

from crm_app.data_import.documents import get_data_import, get_preview
from crm_app.data_import.run import (
    claim_import,
    get_import_logs as load_import_logs,
    release_import,
    start_data_import_task,
)


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


@whitelist("frappe.core.doctype.data_import.data_import.form_start_import", methods=("POST",))
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
