"""Whitelisted Data Import methods from the version-15 framework."""

from frappe_core import permissions
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

from crm_app.data_import.documents import get_data_import, get_preview


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
