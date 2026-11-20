"""Role management: `crm.api.user.add_existing_users`, `update_user_role` and
`remove_crm_roles_from_user`.

Ported from `backend/crm_app/api/user.py:21-217`, messages verbatim. These mutate the
groups the row rules read, so every role check the old code makes is kept, in its order.
The target user is loaded directly: the old code applies only the manager-pair check,
never `User`'s object rule (a Sales Manager changes another user's role, `09` 3.2).
"""

from __future__ import annotations

from django.contrib.auth.models import Group

from accounts.models import CRMSalesHierarchy, User
from accounts.roles import ADMINISTRATOR
from core.exceptions import PermissionError, ValidationError
from core.query import parse_json_param

ASSIGNABLE_ROLES = ["System Manager", "Sales Manager", "Sales User"]
MANAGER_ROLES = ["System Manager", "Sales Manager"]


def only_for(roles, user) -> None:
    """`frappe.only_for(roles, True)`: Administrator, or one of the roles."""
    if user.name == ADMINISTRATOR:
        return
    if not user.get_roles().intersection(roles):
        raise PermissionError("Not permitted")


def _refuse_builtin(name) -> None:
    """PE-28: Administrator and Guest are never the target of a role action; their
    roles are fixed by the framework upstream, whatever their role rows say."""
    if name in User.BUILTIN_NAMES:
        raise PermissionError("Not permitted")


def _set_roles(account, roles) -> None:
    for role in roles:
        group, _ = Group.objects.get_or_create(name=role)
        account.groups.add(group)
    account.clear_roles_cache()


def _remove_roles(account, *roles) -> None:
    for role in roles:
        group = Group.objects.filter(name=role).first()
        if group is not None:
            account.groups.remove(group)
    account.clear_roles_cache()


def add_existing_users(user, users, role="Sales User") -> None:
    only_for(MANAGER_ROLES, user)
    is_system_manager = "System Manager" in user.get_roles()
    if role == "System Manager" and not is_system_manager:
        raise PermissionError("Only System Managers can assign the System Manager role")
    if role == "Sales Manager" and not is_system_manager:
        raise PermissionError("Only System Managers can assign the Sales Manager role")

    names = parse_json_param(users, []) or []
    if isinstance(names, str):
        names = [names]
    for name in names:
        # The old code re-reads the caller's roles on every call (user.py:21-25): a
        # caller who demotes themselves part-way is refused for the next name.
        user.clear_roles_cache()
        update_user_role(user, name, role)


def update_user_role(user, name, new_role) -> None:
    only_for(MANAGER_ROLES, user)
    is_system_manager = "System Manager" in user.get_roles()

    if new_role not in ASSIGNABLE_ROLES:
        raise ValidationError("Cannot assign this role")

    _refuse_builtin(name)
    account = User._default_manager.filter(pk=name).first()
    if account is None:
        raise ValidationError(f"User {name} not found")

    target_is_system_manager = "System Manager" in account.get_roles()
    if new_role == "System Manager" and not is_system_manager:
        raise PermissionError("Only System Managers can assign the System Manager role")
    if target_is_system_manager and not is_system_manager:
        raise PermissionError("Only System Managers can modify other System Managers")
    if new_role == "Sales Manager" and not is_system_manager:
        raise PermissionError("Only System Managers can assign the Sales Manager role")

    if new_role == "System Manager":
        _set_roles(account, ["System Manager", "Sales Manager", "Sales User"])
    elif new_role == "Sales Manager":
        _set_roles(account, ["Sales Manager", "Sales User"])
        _remove_roles(account, "System Manager")
    elif new_role == "Sales User":
        node = (
            CRMSalesHierarchy._default_manager.filter(user=name)
            .values("name", "reports_to")
            .first()
        )
        if node:
            has_reports = CRMSalesHierarchy._default_manager.filter(
                reports_to=node["name"]
            ).exists()
            if has_reports or not node["reports_to"]:
                # A demotion would orphan a subtree and change who sees what.
                raise ValidationError(
                    "Remove this user from the sales hierarchy before changing "
                    "their role to Sales User"
                )
        _set_roles(account, ["Sales User"])
        _remove_roles(account, "Sales Manager", "System Manager")


def remove_crm_roles_from_user(user, name) -> str:
    """Upstream's Role Profile guard is skipped: no Role Profile model here, as in the
    old backend (`user.py:186-187`)."""
    only_for(MANAGER_ROLES, user)
    if name == user.name:
        raise PermissionError("You cannot remove yourself.")

    _refuse_builtin(name)
    account = User._default_manager.filter(pk=name).first()
    if account is None:
        raise ValidationError(f"User {name} not found")

    roles = account.get_roles()
    caller_is_system_manager = "System Manager" in user.get_roles()
    if "System Manager" in roles and not caller_is_system_manager:
        raise PermissionError("Only System Managers can modify other System Managers")

    if "Sales User" in roles:
        _remove_roles(account, "Sales User")
    if "Sales Manager" in roles:
        _remove_roles(account, "Sales Manager")
    if "System Manager" in roles and caller_is_system_manager:
        _remove_roles(account, "System Manager")

    # No reports guard, as the old code; core rebuilds the bounds on delete.
    CRMSalesHierarchy._default_manager.filter(user=name).delete()
    return f"User {name} has been removed from CRM roles."
