"""Uploaded bytes on disk: where they live and how they are named.

Upstream keeps a site's files under ``sites/<site>/public/files`` and
``sites/<site>/private/files``, and ``File.file_url`` is the path a browser fetches them
by: ``/files/<name>`` or ``/private/files/<name>``. Here the same two folders sit under
``MEDIA_ROOT`` as ``files`` and ``private/files``, the layout
``crm_app.communication.attachment_path`` has read for outgoing mail since phase 5, so a
URL and its disk path differ only by the root.

Ports ``frappe/core/doctype/file/utils.py`` (``get_content_hash``, ``generate_file_name``,
``get_file_name``, ``get_safe_file_name``, ``delete_file``, ``find_file_by_url``),
``frappe.utils.get_files_path`` and ``frappe/utils/image.py:optimize_image``.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import secrets
from pathlib import Path
from urllib.parse import unquote

from django.conf import settings

from frappe_core.exceptions import throw

URL_PREFIXES = ("http://", "https://")
PUBLIC_URL = "/files/"
PRIVATE_URL = "/private/files/"

#: ``frappe/utils/response.py:311-327``: served as a download, never inline, because a
#: browser would run what is inside them.
FORCE_DOWNLOAD_EXTENSIONS = (
    ".svg",
    ".svgz",
    ".html",
    ".htm",
    ".xhtml",
    ".xht",
    ".shtml",
    ".shtm",
    ".mhtml",
    ".mht",
    ".xml",
)


def max_file_size() -> int:
    """``frappe/core/api/file.py:get_max_file_size``: a site setting upstream, 25 MB by
    default; ``settings.MAX_FILE_SIZE`` here."""
    return int(getattr(settings, "MAX_FILE_SIZE", 25 * 1024 * 1024))


def get_files_path(*parts: str, is_private: bool = False) -> Path:
    """``frappe.utils.get_files_path``: ``MEDIA_ROOT/files`` or ``MEDIA_ROOT/private/files``."""
    root = Path(settings.MEDIA_ROOT)
    base = root / "private" / "files" if is_private else root / "files"
    return base.joinpath(*parts)


def file_url(file_name: str, is_private: bool) -> str:
    return (PRIVATE_URL if is_private else PUBLIC_URL) + file_name


def is_local_url(url: str | None) -> bool:
    return bool(url) and str(url).startswith((PUBLIC_URL, PRIVATE_URL))


def path_for_url(url: str | None) -> Path | None:
    """The disk path a local ``file_url`` names.

    ``None`` when the URL is not one of ours, or when it would resolve outside its
    folder: a ``file_url`` is a database value, and a row saying ``/files/../../x`` must
    not read or write anything (``utils.py:check_path_safety``).
    """
    if not url:
        return None
    clean = str(url).split("?")[0].split("#")[0]
    if clean.startswith(PRIVATE_URL):
        private, rest = True, clean[len(PRIVATE_URL) :]
    elif clean.startswith(PUBLIC_URL):
        private, rest = False, clean[len(PUBLIC_URL) :]
    else:
        return None
    base = get_files_path(is_private=private).resolve()
    try:
        candidate = (base / unquote(rest)).resolve()
    except OSError:
        return None
    if candidate == base or base not in candidate.parents:
        return None
    return candidate


def get_content_hash(content: bytes | str) -> str:
    if isinstance(content, str):
        content = content.encode()
    return hashlib.md5(content, usedforsecurity=False).hexdigest()  # nosec - a content id, not a secret


def get_safe_file_name(file_name: str) -> str:
    return re.sub(r"[/\\%?#]", "_", file_name)


def get_file_name(fname: str, optional_suffix: str | None = None) -> str:
    partial, extn = os.path.splitext(str(fname))
    suffix = optional_suffix or secrets.token_hex(3)
    return f"{partial}{suffix}{extn}"


def generate_file_name(
    name: str, suffix: str | None = None, is_private: bool = False, content_hash: str | None = None
) -> str:
    """``utils.py:226-249``: a name nothing else on disk is using.

    The name itself if it is free, or taken by the very same bytes; else the name with
    ``suffix``; else the name with a random suffix.
    """

    def different_file_exists_at_path(candidate: str) -> bool:
        path = get_files_path(candidate, is_private=is_private)
        if not path.exists():
            return False
        if content_hash:
            return get_content_hash(path.read_bytes()) != content_hash
        return True

    if not different_file_exists_at_path(name):
        return name
    candidate = get_file_name(name, suffix)
    if different_file_exists_at_path(candidate):
        return generate_file_name(name, is_private=is_private)
    return candidate


def write_file(path: Path, content: bytes) -> Path:
    """``file.py:840-856``, the disk half: written and fsynced."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def delete_file(url: str | None) -> None:
    """``utils.py:181-198``: the bytes behind a local ``file_url``, if they are there."""
    if not url:
        return
    if ".." in url.split("/"):
        throw(f"It is risky to delete this file: {url}. Please contact your System Manager.")
    head, name = os.path.split(url.strip("/"))
    path = get_files_path(name, is_private=head != "files")
    if path.exists():
        path.unlink()


def find_file_by_url(url: str, name: str | None = None):
    """``utils.py:494-507``: the first File row at ``url`` the session user may read.

    A file can hang off several documents; if any one of them lets the user in, the
    bytes are theirs to fetch.
    """
    from frappe_core.permissions import check_object_permission
    from frappe_platform.models import File

    rows = File._default_manager.filter(file_url=str(url))
    if name:
        rows = rows.filter(pk=str(name))
    for row in rows:
        if check_object_permission(row, "read"):
            return row
    return None


logger = logging.getLogger(__name__)

#: ``Attach`` and ``Attach Image``: the two fieldtypes whose value is a file URL.
ATTACH_FIELDTYPES = ("Attach", "Attach Image")
#: ``utils.py:367``: a value that names a file, as opposed to a data URL or free text.
_FILE_URL_PREFIXES = ("/files", "/private/files", "http://", "https://")


def attach_fields_of(doctype: str) -> list[str]:
    """The Attach and Attach Image fields ``doctype`` declares, by name.

    From the DocType JSON for a CRM doctype; from the model's ``ATTACH_FIELDS`` for a
    platform doctype, which ships none (``frappe_core.field_meta._derive_from_model``).
    """
    from frappe_core import field_meta

    return [
        field["fieldname"]
        for field in field_meta.get_fields(doctype)
        if field.get("fieldtype") in ATTACH_FIELDTYPES
    ]


def attach_files_to_document(instance, doctype: str, fieldnames=None) -> None:
    """``utils.py:354-415`` (``attach_files_to_document``), the ``on_update`` hook upstream
    runs for every doctype (``frappe/hooks.py:205,227``): the file an Attach field names
    becomes an attachment of the document.

    This is what makes a private upload readable by colleagues. frappe-ui uploads
    privately unless told otherwise, and the image uploaders - brand logo and favicon,
    profile photo, the lead, contact and organization images - neither tell it otherwise
    nor name a document, so the File row lands unattached, readable by its owner alone
    (``file_has_permission``). Attached, the File rule defers to the document: anyone who
    may read FCRM Settings may fetch the brand logo (FINDINGS.md 85).

    Per field: an attachment this document already has is left alone; an unattached row
    at that URL is stamped with the document and field, ``is_private`` following the URL
    as upstream sets it (``:398``); no row at all gets a URL-only one in Home/Attachments
    (``:404-415``). That last insert cannot fail the save that triggered it - upstream
    logs and moves on, and so does this.
    """
    from frappe_platform.models import File

    if fieldnames is None:
        fieldnames = attach_fields_of(doctype)
    name = str(instance.pk)
    for fieldname in fieldnames:
        value = getattr(instance, fieldname, None) or ""
        if not isinstance(value, str) or not value.startswith(_FILE_URL_PREFIXES):
            continue
        rows = File._default_manager.filter(file_url=value)
        if rows.filter(
            attached_to_doctype=doctype, attached_to_name=name, attached_to_field=fieldname
        ).exists():
            continue
        unattached = rows.filter(
            attached_to_doctype="", attached_to_name="", attached_to_field=""
        ).first()
        if unattached is not None:
            # update(), as upstream's db.set_value: the insert path does not run again
            # and no bytes are touched.
            File._default_manager.filter(pk=unattached.pk).update(
                attached_to_doctype=doctype,
                attached_to_name=name,
                attached_to_field=fieldname,
                is_private=value.startswith("/private"),
            )
            continue
        try:
            File(
                file_url=value,
                attached_to_doctype=doctype,
                attached_to_name=name,
                attached_to_field=fieldname,
                folder="Home/Attachments",
            ).save()
        except Exception:  # noqa: BLE001 - upstream's breadth: the document's save must stand
            logger.exception("Error Attaching File: %s %s.%s", doctype, name, fieldname)


def connect_attach_on_save(model, doctype: str) -> None:
    """Wire :func:`attach_files_to_document` to ``post_save`` of a model that declares an
    Attach field. A model that declares none gets no receiver, so the check costs nothing
    on the saves that could never attach anything."""
    from django.db.models.signals import post_save

    fieldnames = attach_fields_of(doctype)
    if not fieldnames:
        return

    def receiver(sender, instance, raw=False, **kwargs):
        if raw:  # a fixture load; upstream's hook does not run there either
            return
        attach_files_to_document(instance, doctype, fieldnames)

    post_save.connect(
        receiver,
        sender=model,
        weak=False,
        dispatch_uid=f"frappe_platform.files.attach.{model._meta.label}",
    )


def optimize_image(
    content: bytes,
    content_type: str,
    max_width: int = 1024,
    max_height: int = 768,
    optimize: bool = True,
    quality: int = 85,
) -> bytes:
    """``frappe/utils/image.py:optimize_image``: shrink an uploaded picture.

    Needs Pillow, which ``requirements.txt`` lists. Without it the bytes come back
    untouched, which is also what upstream does when Pillow fails on the picture (it
    ``msgprint``s "Failed to optimize image" and returns the original).
    """
    if content_type == "image/svg+xml":
        return content
    try:
        from PIL import Image
    except ImportError:
        return content
    try:
        image = Image.open(io.BytesIO(content))
        exif = image.getexif()
        width, height = image.size
        max_height = max(min(max_height, height * 0.8), 200)
        max_width = max(min(max_width, width * 0.8), 200)
        image_format = content_type.split("/")[1]
        image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(
            output,
            format=image_format,
            optimize=optimize,
            quality=quality,
            save_all=True if image_format == "gif" else None,
            exif=exif,
        )
        optimized = output.getvalue()
        return optimized if len(optimized) < len(content) else content
    except Exception:  # noqa: BLE001 - upstream catches everything here too
        return content
