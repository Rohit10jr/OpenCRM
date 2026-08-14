"""Phase-2 extension points, wired but empty.

PHASE_0_FOUNDATION.md section 8. Phase 0 owns the *call sites*; phase 2 fills in the
logic by calling :func:`frappe_core.registry.register_permission_hooks`, mirroring how
upstream registers ``permission_query_conditions`` / ``has_permission`` in ``hooks.py``
for CRM Lead, CRM Deal and CRM Notification only.

A ``None`` return means "no restriction" - the same convention Frappe uses.

**Phase 2 must not edit this file or the views that call it.** If a rule cannot be
expressed through these two functions, that is a phase-0 defect to report, not a reason
to reach into the view layer.
"""

from __future__ import annotations

from django.db.models import Q

from frappe_core import registry
from frappe_core.session import get_current_user


def get_permission_query_conditions(doctype: str, user: str | None = None) -> Q | None:
    """Row-level list filter for ``doctype``, or ``None`` for unrestricted."""
    user = user or get_current_user()
    if not registry.has_doctype(doctype):
        return None
    hook = registry.get_entry(doctype).permission_query_conditions
    if hook is None:
        return None
    return hook(doctype, user)


def has_permission(doc, ptype: str = "read", user: str | None = None) -> bool | None:
    """Single-object check, or ``None`` for "no opinion" (i.e. allowed)."""
    user = user or get_current_user()
    doctype = getattr(type(doc), "get_doctype", lambda: None)()
    if not doctype or not registry.has_doctype(doctype):
        return None
    hook = registry.get_entry(doctype).has_permission
    if hook is None:
        return None
    return hook(doc, ptype, user)


def apply_permission_filter(queryset, doctype: str, user: str | None = None):
    """Narrow ``queryset`` by the registered row-level rule.

    Every list path - ``/api/resource/`` and ``get_data`` alike - goes through this one
    function, so a phase-2 rule cannot be bypassed by picking a different endpoint.
    """
    conditions = get_permission_query_conditions(doctype, user)
    if conditions is None:
        return queryset
    return queryset.filter(conditions)


def check_object_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
    """``has_permission`` with the ``None``-means-allowed convention resolved."""
    result = has_permission(doc, ptype, user)
    return True if result is None else bool(result)
