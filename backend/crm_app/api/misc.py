"""Endpoints defined directly in ``crm/api/__init__.py``.

Their dotted paths have **no module segment** - ``crm.api.invite_by_email``, not
``crm.api.misc.invite_by_email``. The file is named ``misc`` only because
``__init__.py`` is already taken by the package.
"""

from __future__ import annotations

import re
import secrets

from frappe_core import permissions, registry
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.exceptions import throw
from frappe_core.query import by_name
from frappe_core.session import GUEST_USER, get_current_user
from frappe_core.whitelist import whitelist

#: ``frappe.utils.validate_email_address`` accepts a comma/newline separated string.
_EMAIL_SPLIT = re.compile(r"[,\n;]+")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

INVITABLE_ROLES = ["System Manager", "Sales Manager", "Sales User"]


def split_emails(value: str) -> list[str]:
    return [e.strip() for e in _EMAIL_SPLIT.split(value or "") if e.strip()]


@whitelist("crm.api.get_translations", allow_guest=True)
def get_translations():
    """``crm/api/__init__.py:12-19``.

    Returns ``{}``: this port ships no translation catalogues, and the frontend treats
    an empty map as "use the source strings", which is the correct English behaviour.
    ``allow_guest`` matches upstream - the login page calls it before authenticating.
    """
    return {}


@whitelist("crm.api.get_user_signature")
def get_user_signature():
    """``crm/api/__init__.py:22-50``.

    Upstream reads ``User.email_signature``, falling back to the default outgoing
    Email Account's signature, then wraps whatever it finds in a ``<p class="signature">``.
    Returns ``None`` when there is nothing to append - the frontend checks for falsy.
    """
    from crm_app.models import FCRMSettings  # noqa: F401  (kept for symmetry)
    from frappe_platform.models import EmailAccount, User

    user = get_current_user()
    signature = (
        User._default_manager.filter(pk=user)
        .values_list("email_signature", flat=True)
        .first()
        if user
        else None
    )

    if not signature:
        signature = (
            EmailAccount._default_manager.filter(default_outgoing=True, add_signature=True)
            .values_list("signature", flat=True)
            .first()
        )

    if not signature:
        return None

    return f'<br><p class="signature">{signature}</p>'


@whitelist("crm.api.invite_by_email")
def invite_by_email(emails: str, role: str):
    """``crm/api/__init__.py:106-152``. Messages verbatim.

    Returns the three-way split upstream returns, which the invite dialog renders:
    who was already a member, who already had an invite, and who was actually invited.
    """
    from crm_app.models import CRMInvitation
    from crm_app.api.user import _roles_of, only_for
    from frappe_platform.models import User

    only_for(["Sales Manager", "System Manager"])
    user_roles = _roles_of(get_current_user())

    if role == "System Manager" and "System Manager" not in user_roles:
        raise FrappePermissionError("You are not allowed to invite System Managers")
    if role == "Sales Manager" and "System Manager" not in user_roles:
        raise FrappePermissionError("You are not allowed to invite Sales Managers")
    if role not in INVITABLE_ROLES:
        raise FrappePermissionError("Cannot invite for this role")

    if not emails:
        return None

    email_list = [e for e in split_emails(emails) if _EMAIL_RE.match(e)]
    if not email_list:
        return None

    existing_members = list(
        User._default_manager.filter(email__in=email_list).values_list("email", flat=True)
    )
    existing_invites = list(
        CRMInvitation._default_manager.filter(
            email__in=email_list, role__in=INVITABLE_ROLES
        ).values_list("email", flat=True)
    )

    to_invite = list(set(email_list) - set(existing_members) - set(existing_invites))

    for email in to_invite:
        CRMInvitation._default_manager.create(
            email=email, role=role, status="Pending", key=secrets.token_hex(20)
        )

    return {
        "existing_members": existing_members,
        "existing_invites": existing_invites,
        "to_invite": to_invite,
    }


@whitelist("crm.api.delete_attachment", methods=("DELETE", "POST"))
def delete_attachment(doctype: str, docname: str, file_url: str):
    """``crm/api/__init__.py:155-167``. Message verbatim.

    The permission check is on the **attached-to document**, not the File - which is the
    right boundary, since a File's own row carries no access rules.
    """
    from frappe_platform.models import File

    if not registry.has_doctype(doctype):
        throw(f"DocType {doctype} not found")

    reference = by_name(registry.get_model(doctype), docname).first()
    if reference is None or not permissions.check_object_permission(
        reference, "write", get_current_user()
    ):
        raise FrappePermissionError("You don't have permission to delete this attachment")

    File._default_manager.filter(
        file_url=file_url, attached_to_doctype=doctype, attached_to_name=str(docname)
    ).delete()


#: ``frappe.get_system_settings("allowed_file_extensions")`` default set, and
#: ``frappe.core.api.file.get_max_file_size`` which reads ``MAX_FILE_SIZE`` (25 MB
#: default in ``frappe/core/api/file.py``).
DEFAULT_ALLOWED_FILE_EXTENSIONS = [
    "JPG", "JPEG", "PNG", "GIF", "WEBP", "SVG", "PDF", "DOC", "DOCX", "XLS", "XLSX",
    "PPT", "PPTX", "CSV", "TXT", "ZIP", "MP3", "MP4", "MOV", "AVI",
]
DEFAULT_MAX_FILE_SIZE = 25 * 1024 * 1024


@whitelist("crm.api.get_file_uploader_defaults")
def get_file_uploader_defaults(doctype: str):
    """``crm/api/__init__.py:170-180``.

    ``max_number_of_files`` and ``make_attachments_public`` come from DocType meta
    upstream. No CRM doctype sets either (checked across all 39 JSONs), so they are
    ``None``/``False`` here - which is what upstream returns for those doctypes too.
    """
    return {
        "allowed_file_types": DEFAULT_ALLOWED_FILE_EXTENSIONS,
        "max_file_size": DEFAULT_MAX_FILE_SIZE,
        "max_number_of_files": None,
        "make_attachments_public": False,
    }
