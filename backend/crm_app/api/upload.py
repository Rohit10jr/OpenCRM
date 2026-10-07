"""``upload_file`` - ``frappe/handler.py:130-244``, the door every attachment comes in by.

The CRM's own uploader (``FilesUploader/filesUploaderHandler.ts``) and frappe-ui's
(``utils/fileUploadHandler.ts``, behind the editor's image button and the comment and
email boxes) both POST a multipart form to ``/api/method/upload_file``: the ``file`` part,
``is_private``, ``folder`` and, when attaching to a record, ``doctype`` / ``docname`` /
``fieldname``. The answer is the File row; the editor writes its ``file_url`` into the
note, the attachments panel lists it.

Upstream registers the handler under its bare name (``handler.py:get_attr`` looks a
dotless ``cmd`` up in its own globals), which is why the path here has no module.
"""

from __future__ import annotations

from mimetypes import guess_type

from django.db import transaction

from frappe_core import permissions, registry
from frappe_core.exceptions import DoesNotExistError
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.exceptions import throw
from frappe_core.session import get_current_user
from frappe_core.views import _candidate_instance
from frappe_core.whitelist import whitelist
from frappe_platform import files as file_store

#: ``handler.py:28-45``: what a user without desk access may upload.
ALLOWED_MIMETYPES = (
    "image/png",
    "image/jpeg",
    "image/gif",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "text/plain",
    "video/quicktime",
    "video/mp4",
    "text/csv",
)


def _truthy(value) -> bool:
    return str(value).strip().lower() not in ("", "0", "false", "none", "null")


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def check_write_permission(doctype: str | None = None, name: str | None = None) -> None:
    """``handler.py:247-261``.

    No doctype, nothing to check. A doctype alone is "may I write this kind of
    record"; a name that exists is "may I write this record"; a name that does not exist
    yet (the frontend attaches to ``new-crm-lead-1`` while the dialog is still open) is
    the doctype check again, and the file is relinked when the record is saved.
    """
    if not doctype:
        return
    if not registry.has_doctype(doctype):
        raise DoesNotExistError(f"DocType {doctype} not found")
    entry = registry.get_entry(doctype)
    user = get_current_user()
    instance = entry.model._default_manager.filter(pk=str(name)).first() if name else None
    if instance is None:
        instance = _candidate_instance(entry, {})
    if not permissions.check_object_permission(instance, "write", user):
        raise FrappePermissionError(f"Not permitted to write {doctype}", title="Not Permitted")


@whitelist("upload_file", methods=("POST",), wants_request=True)
def upload_file(
    _request,
    file=None,
    is_private=1,
    doctype: str | None = None,
    docname: str | None = None,
    fieldname: str | None = None,
    file_url: str | None = None,
    folder: str | None = None,
    method: str | None = None,
    file_name: str | None = None,
    optimize=None,
    max_width=None,
    max_height=None,
    library_file_name: str | None = None,
    chunk_index=None,
    total_chunk_count=None,
    chunk_byte_offset=None,
    total_file_size=None,
    **_ignored,
):
    """``handler.py:131-244``, for a signed-in user.

    The guest branch (``allow_guests_to_upload_files``) is dead here: the method is not
    guest-callable, so ``MethodView`` has already turned an anonymous caller away.

    Three inputs make a file: the ``file`` part; ``file_url``, a link to a file that
    already exists here or elsewhere, stored without any bytes moving; or
    ``library_file_name``, an existing File row whose bytes the new row shares. Chunked
    uploads are assembled in a ``.temp-`` file next to the destination and answered with
    nothing until the last chunk lands, exactly as upstream does.

    ``method`` - upstream hands the bytes to a whitelisted function of the caller's
    choosing instead of making a File - is refused: no screen of this frontend sends it,
    and the ``frappe.local.uploaded_file`` convention it relies on does not exist here.
    """
    from frappe_platform.models import File, User

    user = get_current_user()
    files = getattr(_request, "FILES", None) or {}
    upload = file if file is not None and hasattr(file, "read") else files.get("file")
    is_private = _truthy(is_private) if is_private not in (None, "") else True
    folder = folder or "Home"
    filename = file_name
    content: bytes | None = None

    if library_file_name:
        source = File._default_manager.filter(pk=str(library_file_name)).first()
        if source is None or not permissions.check_object_permission(source, "read", user):
            raise FrappePermissionError("Not permitted", title="Not Permitted")
        is_private = bool(source.is_private)
        file_url = source.file_url
        filename = source.file_name

    check_write_permission(doctype, docname)

    if upload is not None:
        filename = upload.name
        if chunk_index is not None:
            current_chunk = _int(chunk_index)
            total_chunks = _int(total_chunk_count, 1)
            offset = _int(chunk_byte_offset)
        else:
            current_chunk, total_chunks, offset = 0, 1, 0

        temp_path = file_store.get_files_path(
            ".temp-" + file_store.get_safe_file_name(filename), is_private=is_private
        )
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        with temp_path.open("ab" if current_chunk > 0 else "wb") as handle:
            handle.seek(offset)
            handle.write(upload.read())
            if handle.tell() < _int(total_file_size) or current_chunk != total_chunks - 1:
                return None

        content = temp_path.read_bytes()
        temp_path.unlink()
        content_type = guess_type(filename)[0]
        if _truthy(optimize) and content_type and content_type.startswith("image/"):
            args = {"content": content, "content_type": content_type}
            if max_width:
                args["max_width"] = _int(max_width)
            if max_height:
                args["max_height"] = _int(max_height)
            content = file_store.optimize_image(**args)

    if content is not None:
        user_type = (
            User._default_manager.filter(pk=user).values_list("user_type", flat=True).first()
        )
        if user_type != "System User" and guess_type(filename)[0] not in ALLOWED_MIMETYPES:
            throw("You can only upload JPG, PNG, GIF, PDF, TXT, CSV or Microsoft documents.")

    if method:
        throw("upload_file does not accept a method here")

    row = File(
        attached_to_doctype=doctype or "",
        attached_to_name=str(docname) if docname else "",
        attached_to_field=fieldname or "",
        folder=folder,
        file_name=filename or "",
        file_url=file_url or "",
        is_private=is_private,
    )
    row._content = content
    with transaction.atomic():
        row.save()
    return registry.get_entry("File").get_serializer_class()(row).data
