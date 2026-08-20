"""``crm.api.session.*`` - Group B. Ported from ``crm/api/session.py``."""

from __future__ import annotations

from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.query import fetch_rows, parse_json_param
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

#: ``crm/api/session.py:4``
CRM_ALLOWED_ROLES = ["System Manager", "Sales Manager", "Sales User"]

#: ``crm/api/session.py:20-30``
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

#: ``crm/api/session.py:113`` - first match wins.
ROLE_PRIORITY = ("System Manager", "Sales Manager", "Sales User", "Guest")

#: ``crm/api/session.py:139`` - enumeration cap on get_user_info.
USER_INFO_LIMIT = 200


def get_session_role_flags(user: str | None = None) -> dict:
    """``crm/api/session.py:7-18``. Message preserved verbatim."""
    from frappe_platform.models import User

    user = user or get_current_user()
    obj = User._default_manager.filter(pk=user).first()
    roles = obj.get_roles() if obj else set()

    if not roles.intersection(set(CRM_ALLOWED_ROLES)):
        raise FrappePermissionError("You are not permitted to access CRM resources.")

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
    """``crm/api/session.py:47-48`` - the param arrives as a string over HTTP."""
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes")
    return bool(value)


@whitelist("crm.api.session.get_users")
def get_users(include_all: bool = False):
    """``crm/api/session.py:33-127``. Returns ``(users, crm_users)``.

    ``include_all`` is honoured only for a System Manager - upstream forces it back to
    False otherwise (line 49-50), so a Sales User cannot enumerate every account by
    passing the flag.
    """
    from django.contrib.auth.models import Group

    from crm_app.models import CRMTelephonyAgent
    from frappe_platform.models import User

    session_roles = get_session_role_flags()
    include_all = _coerce_bool(include_all)
    if not session_roles["is_system_manager"]:
        include_all = False

    crm_user_names = set(
        User._default_manager.filter(groups__name__in=CRM_ALLOWED_ROLES)
        .values_list("name", flat=True)
        .distinct()
    )
    crm_user_names.add("Administrator")

    queryset = User._default_manager.filter(enabled=True)
    if not include_all:
        queryset = queryset.filter(name__in=list(crm_user_names))
    queryset = queryset.order_by("full_name")

    rows = list(queryset.values(*USER_FIELDS))
    if not rows:
        return [], []

    role_scope = User._default_manager.all() if include_all else User._default_manager.filter(
        name__in=list(crm_user_names)
    )
    roles_by_user: dict[str, list[str]] = {}
    for user_name, role in Group.objects.filter(user__in=role_scope).values_list(
        "user__name", "name"
    ):
        roles_by_user.setdefault(user_name, []).append(role)

    telephony_agents = set(CRMTelephonyAgent._default_manager.values_list("user", flat=True))
    session_user = get_current_user()
    crm_users = []

    for user in rows:
        if session_user == user["name"]:
            user["session_user"] = True

        if user["name"] == "Administrator":
            # crm/api/session.py:97-100 - the admin's Has Role table is not guaranteed
            # to list System Manager, so it is special-cased to avoid a lockout.
            user["roles"] = ["System Manager", "All"]
            user["role"] = "System Manager"
        else:
            # Mirrors frappe.get_roles(), which appends the implicit All and Guest.
            user["roles"] = [*roles_by_user.get(user["name"], []), "All", "Guest"]
            user["role"] = ""
            for role in ROLE_PRIORITY:
                if role in user["roles"]:
                    user["role"] = role
                    break

        user["is_telephony_agent"] = user["name"] in telephony_agents

        if user["role"] in CRM_ALLOWED_ROLES:
            crm_users.append(user)

    if not include_all:
        # Fast path - both positions are the CRM users (line 124-126).
        return crm_users, crm_users
    return rows, crm_users


@whitelist("crm.api.session.get_user_info")
def get_user_info(users: str | list):
    """``crm/api/session.py:130-152``. Gated behind a CRM role; capped at 200 names."""
    from frappe_platform.models import User

    get_session_role_flags()

    parsed = parse_json_param(users, []) or []
    if isinstance(parsed, str):
        parsed = [parsed]
    if not parsed:
        return []

    return list(
        User._default_manager.filter(name__in=list(parsed)[:USER_INFO_LIMIT]).values(
            "name", "email", "full_name", "user_image", "user_type"
        )
    )


@whitelist("crm.api.session.get_organizations")
def get_organizations():
    """``crm/api/session.py:155-165``.

    Upstream selects ``*`` with no permission filter. This reads through
    ``fetch_rows``, so the phase-2 hook applies - CRM Organization has no row rule
    today, making the two identical, but an endpoint that bypasses the layer would
    become a leak the moment one is added.
    """
    get_session_role_flags()
    return fetch_rows(
        "CRM Organization", fields=["*"], order_by="name asc", limit_page_length=0
    )
