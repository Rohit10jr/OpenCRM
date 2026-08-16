"""Phase 2 - the row-level permission engine.

Registered with the phase-0 registry by :func:`register`, which ``CrmAppConfig.ready``
calls. **No phase-0 code is edited**; these plug into the extension points
(PHASE_0_FOUNDATION.md section 8).

Upstream registers row-level rules for exactly three doctypes
(``crm/hooks.py:134-144``): CRM Lead, CRM Deal and CRM Notification. Everything else
falls back to plain role permissions.
"""

from frappe_core.registry import register_permission_hooks

from crm_app.permissions import metadata_docs, notification, org_hierarchy, tree


def register() -> None:
    """Wire the two hooks for the three doctypes upstream registers."""
    tree.connect_signals()
    register_permission_hooks(
        "CRM Lead",
        permission_query_conditions=org_hierarchy.get_lead_permission_query_conditions,
        has_permission=org_hierarchy.has_lead_permission,
        # Phase 5, C9: the same rule asked about a whole batch in one query. Cost only -
        # `filter_object_permitted` gets the identical answer without it.
        has_permission_batch=org_hierarchy.has_lead_permission_batch,
    )
    register_permission_hooks(
        "CRM Deal",
        permission_query_conditions=org_hierarchy.get_deal_permission_query_conditions,
        has_permission=org_hierarchy.has_deal_permission,
        has_permission_batch=org_hierarchy.has_deal_permission_batch,
    )
    register_permission_hooks(
        "CRM Notification",
        permission_query_conditions=notification.get_permission_query_conditions,
        has_permission=notification.has_permission,
    )

    # Phase 4. Upstream registers no hook for these three - it relies on the DocType's
    # role permissions, which this port does not model. Without a rule here they are
    # world-readable *and* world-writable through the generic /api/resource/ route:
    # private saved views leak, and CRM Form Script is an XSS vector because every
    # client executes what it serves. See crm_app/permissions/metadata_docs.py.
    register_permission_hooks(
        "CRM View Settings",
        permission_query_conditions=metadata_docs.view_settings_query_conditions,
        has_permission=metadata_docs.view_settings_has_permission,
    )
    register_permission_hooks(
        "CRM Form Script",
        permission_query_conditions=metadata_docs.form_script_query_conditions,
        has_permission=metadata_docs.form_script_has_permission,
    )
    register_permission_hooks(
        "CRM Fields Layout",
        permission_query_conditions=metadata_docs.fields_layout_query_conditions,
        has_permission=metadata_docs.fields_layout_has_permission,
    )


__all__ = ["register", "org_hierarchy", "notification"]
