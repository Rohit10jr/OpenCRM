"""Phase 2 - the row-level permission engine.

Registered with the phase-0 registry by :func:`register`, which ``CrmAppConfig.ready``
calls. **No phase-0 code is edited**; these plug into the extension points
(PHASE_0_FOUNDATION.md section 8).

Upstream registers row-level rules for exactly three doctypes
(``crm/hooks.py:134-144``): CRM Lead, CRM Deal and CRM Notification. Everything else
falls back to plain role permissions.
"""

from frappe_core.registry import register_permission_hooks

from crm_app.permissions import notification, org_hierarchy, tree


def register() -> None:
    """Wire the two hooks for the three doctypes upstream registers."""
    tree.connect_signals()
    register_permission_hooks(
        "CRM Lead",
        permission_query_conditions=org_hierarchy.get_lead_permission_query_conditions,
        has_permission=org_hierarchy.has_lead_permission,
    )
    register_permission_hooks(
        "CRM Deal",
        permission_query_conditions=org_hierarchy.get_deal_permission_query_conditions,
        has_permission=org_hierarchy.has_deal_permission,
    )
    register_permission_hooks(
        "CRM Notification",
        permission_query_conditions=notification.get_permission_query_conditions,
        has_permission=notification.has_permission,
    )


__all__ = ["register", "org_hierarchy", "notification"]
