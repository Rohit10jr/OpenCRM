"""Development users used by the HTTP and browser suites."""

import os

from django.contrib.auth.models import Group
from django.core.management.base import CommandError
from django.utils.translation import gettext as _

from .models import User
from .roles import (
    ADMINISTRATOR,
    ROLE_SALES_MANAGER,
    ROLE_SALES_USER,
    ROLE_SYSTEM_MANAGER,
)

PASSWORD_VARIABLES = (
    "ADMIN_PWD",
    "SALES_PWD",
    "MANAGER_PWD",
    "SALES2_PWD",
)

SEEDED_USERS = (
    ("ada@example.com", "Ada", ROLE_SALES_USER, "SALES_PWD"),
    ("grace@example.com", "Grace", ROLE_SALES_MANAGER, "MANAGER_PWD"),
    ("alan@example.com", "Alan", ROLE_SALES_USER, "SALES2_PWD"),
)


def _passwords() -> dict[str, str]:
    missing = [name for name in PASSWORD_VARIABLES if not os.environ.get(name)]
    if missing:
        variables = _(" and ").join(missing)
        raise CommandError(_("Set {0} in the environment first.").format(variables))
    return {name: os.environ[name] for name in PASSWORD_VARIABLES}


def seed_users(user: User, force: bool = False) -> int:
    """Create missing suite users and restore every suite login."""
    del user, force
    passwords = _passwords()
    created = 0

    groups = {
        role: Group.objects.get(name=role)
        for role in (
            ADMINISTRATOR,
            ROLE_SYSTEM_MANAGER,
            ROLE_SALES_MANAGER,
            ROLE_SALES_USER,
        )
    }
    desired_users = (
        (
            ADMINISTRATOR,
            "Administrator",
            (ADMINISTRATOR, ROLE_SYSTEM_MANAGER),
            "ADMIN_PWD",
        ),
        *(
            (name, first_name, (role,), variable)
            for name, first_name, role, variable in SEEDED_USERS
        ),
    )
    for name, first_name, roles, password_variable in desired_users:
        account = User.objects.filter(name=name).first()
        if account is None:
            account = User(
                name=name,
                email=name,
                first_name=first_name,
                enabled=True,
                user_type="System User",
            )
            created += 1

        account.enabled = True
        account.set_password(passwords[password_variable])
        account.save()
        account.groups.set([groups[role] for role in roles])

    return created


def clear_users(user: User, force: bool = False) -> int:
    """Remove only the three non-built-in accounts owned by this seed step."""
    del user, force
    names = [name for name, _first_name, _role, _variable in SEEDED_USERS]
    existing = User.objects.filter(name__in=names)
    removed = existing.count()
    existing.delete()
    return removed
