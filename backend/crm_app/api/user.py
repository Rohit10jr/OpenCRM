"""``crm.api.user.*`` - Group B role management. Ported from ``crm/api/user.py``.

These four mutate Django Groups, which is what the phase-2 permission engine reads. A
missing guard here is a privilege-escalation bug, so every ``frappe.only_for`` and every
role comparison upstream makes is reproduced, with the message verbatim.
"""

from __future__ import annotations

from frappe_core.exceptions import AuthenticationError
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.exceptions import ValidationError, throw
from frappe_core.query import parse_json_param
from frappe_core.session import GUEST_USER, get_current_user
from frappe_core.whitelist import whitelist

ASSIGNABLE_ROLES = ["System Manager", "Sales Manager", "Sales User"]


def _roles_of(user: str) -> set[str]:
    from frappe_platform.models import User

    obj = User._default_manager.filter(pk=user).first()
    return obj.get_roles() if obj else set()


def only_for(roles: list[str], user: str | None = None) -> None:
    """``frappe.only_for(roles, True)`` - raise unless the caller holds one of them."""
    user = user or get_current_user()
    if user == "Administrator":
        return
    if not _roles_of(user).intersection(set(roles)):
        raise FrappePermissionError("Not permitted")


def _set_roles(user_obj, roles: list[str]) -> None:
    from django.contrib.auth.models import Group

    for role in roles:
        group, _ = Group.objects.get_or_create(name=role)
        user_obj.groups.add(group)


def _remove_roles(user_obj, *roles: str) -> None:
    from django.contrib.auth.models import Group

    for role in roles:
        group = Group.objects.filter(name=role).first()
        if group is not None:
            user_obj.groups.remove(group)


@whitelist("crm.api.user.change_password")
def change_password(old_password: str, new_password: str):
    """``crm/api/user.py:9-48``. Messages verbatim.

    Upstream's ``LoginAttemptTracker`` lockout and ``rate_limit`` decorator are **not**
    ported - both are framework infrastructure with no analogue here. That is a real
    weakening of brute-force resistance and is logged in PROGRESS_PHASE_3.md rather than
    passed over.

    Strength checking goes through Django's configured
    ``AUTH_PASSWORD_VALIDATORS`` instead of Frappe's zxcvbn wrapper, which is the
    spec's instruction (PHASE_3_ENDPOINTS.md section 2, Group B).
    """
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError as DjangoValidationError

    from frappe_platform.models import User

    user = get_current_user()
    if user == GUEST_USER:
        raise AuthenticationError("You must be logged in to change your password")

    if old_password == new_password:
        throw(
            "New password cannot be the same as current password. "
            "Please choose a different password."
        )

    obj = User._default_manager.filter(pk=user).first()
    if obj is None or not obj.check_password(old_password):
        throw("Incorrect current password. Please try again.")

    try:
        validate_password(new_password, user=obj)
    except DjangoValidationError as exc:
        suggestions = " ".join(exc.messages)
        throw(f"Password is too weak. {suggestions}".strip())

    obj.set_password(new_password)
    obj.save(update_fields=["password"])
    return "Password Updated Successfully"


@whitelist("crm.api.user.add_existing_users")
def add_existing_users(users: str | list, role: str = "Sales User"):
    """``crm/api/user.py:51-70``. Messages verbatim."""
    only_for(["System Manager", "Sales Manager"])
    is_system_manager = "System Manager" in _roles_of(get_current_user())

    if role == "System Manager" and not is_system_manager:
        raise FrappePermissionError("Only System Managers can assign the System Manager role")
    if role == "Sales Manager" and not is_system_manager:
        raise FrappePermissionError("Only System Managers can assign the Sales Manager role")

    parsed = parse_json_param(users, []) or []
    if isinstance(parsed, str):
        parsed = [parsed]
    for user in parsed:
        update_user_role(user, role)


@whitelist("crm.api.user.update_user_role")
def update_user_role(user: str, new_role: str):
    """``crm/api/user.py:73-121``. Messages verbatim.

    The Sales-User downgrade guard is the subtle one: a user who *has reports* or who is
    a hierarchy root cannot be demoted, because either would orphan a subtree and
    silently change who can see what (``crm/api/user.py:106-113``).
    """
    from crm_app.models import CRMSalesHierarchy
    from frappe_platform.models import User

    only_for(["System Manager", "Sales Manager"])
    is_system_manager = "System Manager" in _roles_of(get_current_user())

    if new_role not in ASSIGNABLE_ROLES:
        throw("Cannot assign this role")

    user_obj = User._default_manager.filter(pk=user).first()
    if user_obj is None:
        throw(f"User {user} not found")

    target_is_system_manager = "System Manager" in _roles_of(user)

    if new_role == "System Manager" and not is_system_manager:
        raise FrappePermissionError("Only System Managers can assign the System Manager role")
    if target_is_system_manager and not is_system_manager:
        raise FrappePermissionError("Only System Managers can modify other System Managers")
    if new_role == "Sales Manager" and not is_system_manager:
        raise FrappePermissionError("Only System Managers can assign the Sales Manager role")

    if new_role == "System Manager":
        _set_roles(user_obj, ["System Manager", "Sales Manager", "Sales User"])
    elif new_role == "Sales Manager":
        _set_roles(user_obj, ["Sales Manager", "Sales User"])
        _remove_roles(user_obj, "System Manager")
    elif new_role == "Sales User":
        node = (
            CRMSalesHierarchy._default_manager.filter(user=user)
            .values("name", "reports_to")
            .first()
        )
        if node:
            has_reports = CRMSalesHierarchy._default_manager.filter(
                reports_to=node["name"]
            ).exists()
            if has_reports or not node["reports_to"]:
                throw(
                    "Remove this user from the sales hierarchy before changing "
                    "their role to Sales User"
                )
        _set_roles(user_obj, ["Sales User"])
        _remove_roles(user_obj, "Sales Manager", "System Manager")


@whitelist("crm.api.user.remove_crm_roles_from_user")
def remove_crm_roles_from_user(user: str):
    """``crm/api/user.py:124-163``. Messages verbatim.

    Upstream's ``role_profiles`` guard is skipped - Role Profile is a framework doctype
    this port does not model, so there is nothing to check. Noted in the phase report.
    """
    from crm_app.models import CRMSalesHierarchy
    from frappe_platform.models import User

    only_for(["System Manager", "Sales Manager"])

    if user == get_current_user():
        raise FrappePermissionError("You cannot remove yourself.")

    user_obj = User._default_manager.filter(pk=user).first()
    if user_obj is None:
        throw(f"User {user} not found")

    roles = _roles_of(user)
    current_user_is_system_manager = "System Manager" in _roles_of(get_current_user())

    if "System Manager" in roles and not current_user_is_system_manager:
        raise FrappePermissionError("Only System Managers can modify other System Managers")

    if "Sales User" in roles:
        _remove_roles(user_obj, "Sales User")
    if "Sales Manager" in roles:
        _remove_roles(user_obj, "Sales Manager")
    if "System Manager" in roles and current_user_is_system_manager:
        _remove_roles(user_obj, "System Manager")

    # Removing the node keeps the nested set consistent; the tree signal rebuilds bounds.
    CRMSalesHierarchy._default_manager.filter(user=user).delete()

    return f"User {user} has been removed from CRM roles."
