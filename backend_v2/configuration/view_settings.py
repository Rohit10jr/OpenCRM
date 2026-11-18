"""Saved views: CRM View Settings' rules (specs/CONFIGURATION.md section 4.7).

The resource and the dedicated calls share these two rules, so every way in has the
same lock (old `crm_app/permissions/metadata_docs.py:61-91`,
`crm_app/api/view_settings.py:37-48`):

- **read:** the caller's own views, ownerless views and public views; Administrator and
  System Manager read every view;
- **write** (and delete): the owner; Sales Manager on a public view; Administrator and
  System Manager.
"""

from __future__ import annotations

from django.db.models import Q

from accounts.roles import ADMINISTRATOR, ROLE_SALES_MANAGER, ROLE_SYSTEM_MANAGER


def sees_every_view(user) -> bool:
    return user.name == ADMINISTRATOR or user.has_role(ROLE_SYSTEM_MANAGER)


def read_rule(user):
    """The list rule: `None` for every view, else a filter."""
    if sees_every_view(user):
        return None
    return Q(user=user) | Q(user__isnull=True) | Q(public=True)


def can_read(user, view) -> bool:
    if sees_every_view(user):
        return True
    return view.user_id == user.name or view.user_id is None or bool(view.public)


def can_write(user, view) -> bool:
    """Write and delete, the old `check_permission`."""
    if sees_every_view(user):
        return True
    if view.public and user.has_role(ROLE_SALES_MANAGER):
        return True
    return bool(view.user_id) and view.user_id == user.name
