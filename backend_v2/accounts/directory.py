"""The user directory: `crm.api.session.get_users` and `get_user_info`.

Ported from `backend/crm_app/api/session.py:33-155`. The caller is passed in (S16).
"""

from __future__ import annotations

from django.contrib.auth.models import Group

from accounts.models import User
from accounts.roles import ADMINISTRATOR
from core.exceptions import PermissionError
from core.query import parse_json_param

CRM_ALLOWED_ROLES = ["System Manager", "Sales Manager", "Sales User"]
USER_FIELDS = [
    "name",
    "email",
    "enabled",
    "user_image",
    "first_name",
    "last_name",
    "full_name",
    "user_type",
    "language",
]
ROLE_PRIORITY = ("System Manager", "Sales Manager", "Sales User", "Guest")
USER_INFO_LIMIT = 200
USER_INFO_FIELDS = ("name", "email", "full_name", "user_image", "user_type")


def session_role_flags(user) -> dict:
    """`crm/api/session.py:7-18`: a CRM role is required."""
    roles = user.get_roles() if user is not None else set()
    if not roles.intersection(CRM_ALLOWED_ROLES):
        raise PermissionError("You are not permitted to access CRM resources.")
    return {
        "is_system_manager": "System Manager" in roles,
        "is_sales_manager": "Sales Manager" in roles and "System Manager" not in roles,
        "is_sales_user": (
            "Sales User" in roles
            and "Sales Manager" not in roles
            and "System Manager" not in roles
        ),
    }


def _coerce_bool(value) -> bool:
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes")
    return bool(value)


def get_users(user, include_all=False):
    """Answer `[users, crm_users]`; `include_all` counts only for a System Manager."""
    flags = session_role_flags(user)
    include_all = _coerce_bool(include_all) and flags["is_system_manager"]

    users = User._default_manager
    crm_user_names = set(
        users.filter(groups__name__in=CRM_ALLOWED_ROLES)
        .values_list("name", flat=True)
        .distinct()
    )
    crm_user_names.add(ADMINISTRATOR)

    queryset = users.filter(enabled=True)
    if not include_all:
        queryset = queryset.filter(name__in=list(crm_user_names))
    rows = list(queryset.order_by("full_name").values(*USER_FIELDS))
    if not rows:
        return [], []

    role_scope = (
        users.all() if include_all else users.filter(name__in=list(crm_user_names))
    )
    roles_by_user: dict[str, list[str]] = {}
    for user_name, role in Group.objects.filter(user__in=role_scope).values_list(
        "user__name", "name"
    ):
        roles_by_user.setdefault(user_name, []).append(role)

    crm_users = []
    for row in rows:
        if row["name"] == user.name:
            row["session_user"] = True
        if row["name"] == ADMINISTRATOR:
            # Its stored roles are not guaranteed to list System Manager (session.py:97-100).
            row["roles"] = ["System Manager", "All"]
            row["role"] = "System Manager"
        else:
            row["roles"] = [*roles_by_user.get(row["name"], []), "All", "Guest"]
            row["role"] = next(
                (role for role in ROLE_PRIORITY if role in row["roles"]), ""
            )
        # CRM Telephony Agent arrives with INTEGRATIONS (specs/ACCOUNTS.md section 2).
        row["is_telephony_agent"] = False
        if row["role"] in CRM_ALLOWED_ROLES:
            crm_users.append(row)

    if not include_all:
        return crm_users, crm_users
    return rows, crm_users


def get_user_info(user, names):
    """Five fields for at most 200 names; built-in and disabled users included."""
    session_role_flags(user)
    names = parse_json_param(names, []) or []
    if isinstance(names, str):
        names = [names]
    if not names:
        return []
    return list(
        User._default_manager.filter(name__in=list(names)[:USER_INFO_LIMIT]).values(
            *USER_INFO_FIELDS
        )
    )
