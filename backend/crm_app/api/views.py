"""``crm.api.views.get_views``. Ported from ``crm/api/views.py``."""

from __future__ import annotations

from django.db.models import Q

from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist


@whitelist("crm.api.views.get_views")
def get_views(doctype: str):
    """``crm/api/views.py:5-16``.

    Upstream matches ``user == "" OR user == session_user`` - a blank user marks a view
    as global. Our ``CRM View Settings.user`` is a nullable FK, so blank is ``NULL``;
    both spellings are accepted so a row imported with an empty string still resolves.

    ``get_data`` also calls this (phase 0 stubbed it as ``_get_views``); phase 4 wires
    that seam up.
    """
    from frappe_core.query import base_queryset

    user = get_current_user()
    # Through base_queryset so any row rule a later phase registers for CRM View
    # Settings applies here too; the user/global filter is this endpoint's own scope
    # on top of it.
    queryset = base_queryset("CRM View Settings", user).filter(
        Q(user__isnull=True) | Q(user=user)
    )
    if doctype:
        queryset = queryset.filter(dt=doctype)
    return list(queryset.values())
