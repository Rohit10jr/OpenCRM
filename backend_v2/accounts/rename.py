"""The User rename (specs/ACCOUNTS.md §10, PE-32).

`UserViewSet`'s rename hooks delegate here. Upstream's order (v15
`frappe/model/rename_doc.py:150-153,348-372`): the document is fetched, `before_rename`
runs (User's checks, `frappe/core/doctype/user/user.py:563-581`), then
`validate_rename` (exists, same name, taken), then permission.
"""

from __future__ import annotations

from django.core.cache import cache
from django.db import transaction
from django.utils.html import escape

from accounts.authentication import new_token_version, revoke_all_tokens
from accounts.models import User
from accounts.roles import ADMINISTRATOR, ROLE_SYSTEM_MANAGER
from core.exceptions import InvalidEmailAddressError, ValidationError
from core.models import validate_email_address
from core.rename import repoint_json_name_lists


def normalised_new_name(old_name: str, new_name: str) -> str:
    """§10.2 rows 3-4: refuse a built-in, then a new name that is not exactly one plain
    address; answer it stripped and lowercased, as `User.save` stores names."""
    if old_name in User.BUILTIN_NAMES:
        raise ValidationError(f"User {old_name} cannot be renamed")
    normalised = str(new_name).strip().lower()
    # Raises "<value> is not a valid Email Address" for anything that does not parse.
    checked = validate_email_address(normalised)
    if checked != normalised or "," in normalised or "\n" in normalised:
        # A list or a display name parses, but is not one plain address.
        raise InvalidEmailAddressError(f"{escape(normalised)} is not a valid Email Address")
    return normalised


def name_taken(new_name: str, old_name: str) -> bool:
    """§10.2 row 6: case-insensitive, and not the row being renamed, so a legacy
    mixed-case row can take its own lowercase form."""
    return User._default_manager.filter(pk__iexact=new_name).exclude(pk=old_name).exists()


def may_rename(user) -> bool:
    """§10.1: System Manager or Administrator only (not the User write rule)."""
    return user.name == ADMINISTRATOR or user.has_role(ROLE_SYSTEM_MANAGER)


def on_user_renamed(old_name: str, new_name: str) -> None:
    """§10.4, inside the rename's transaction; no step saves either instance (§10.3)."""
    User._default_manager.filter(pk=new_name).update(
        email=new_name,
        reset_password_key="",
        last_reset_password_key_generated_on=None,
        token_version=new_token_version(),
    )
    # After the FK repoint, so the outstanding tokens already name the new row.
    revoke_all_tokens(User._default_manager.get(pk=new_name))
    repoint_json_name_lists(old_name, new_name)
    transaction.on_commit(lambda: cache.delete(f"login_attempts:{old_name}"))
