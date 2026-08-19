"""Phase 2 - the row-level permission engine.

Registered with the phase-0 registry by :func:`register`, which ``CrmAppConfig.ready``
calls. **No phase-0 code is edited**; these plug into the extension points
(PHASE_0_FOUNDATION.md section 8).

Upstream registers row-level rules for exactly three doctypes
(``crm/hooks.py:134-144``): CRM Lead, CRM Deal and CRM Notification. Everything else
falls back to plain role permissions.
"""

from frappe_core.registry import register_permission_hooks

from crm_app.permissions import (
    metadata_docs,
    notification,
    org_hierarchy,
    platform_docs,
    tree,
)


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

    # Phase 4 review, A2. `User` has been routable since phase 1 with no rule behind it,
    # so any authenticated caller could list every account, and rename or disable anyone.
    # Upstream gives `User` to System Manager alone; we are deliberately more permissive,
    # because the Vue profile screens edit the session user's own document through this
    # route. Self-escalation (`groups`, `is_superuser`) is closed separately by
    # `User.SENSITIVE_FIELDS` - a self-only rule cannot close it, since writing your own
    # roles on your own document is what self-only permits.
    register_permission_hooks(
        "User",
        permission_query_conditions=platform_docs.user_query_conditions,
        has_permission=platform_docs.user_has_permission,
    )

    # A3. Same shape: routable since phase 1 with no rule, so any caller could repoint
    # `smtp_server` at a host they control - every message the system sends, invitation
    # links included, then flows through it - or simply delete the account. Managers
    # write, everyone reads (the Profile screen's "send from" picker needs the list).
    register_permission_hooks(
        "Email Account",
        permission_query_conditions=platform_docs.email_account_query_conditions,
        has_permission=platform_docs.email_account_has_permission,
    )

    # A4. Telephony credentials. Upstream gives these to System Manager and Sales Manager
    # only, at every permlevel - no Sales User sees them. Here they were readable *and
    # rewritable* by any authenticated caller, which means pointing the integration at an
    # account the caller controls.
    for doctype in ("CRM Twilio Settings", "CRM Exotel Settings"):
        register_permission_hooks(
            doctype,
            permission_query_conditions=platform_docs.telephony_settings_query_conditions,
            has_permission=platform_docs.telephony_settings_has_permission,
        )

    # A4. `FCRM Settings` is read by every screen in the product - the activity timeline
    # takes its timestamp format from it - so upstream grants Sales User read and withholds
    # write. Same split here; the credential that should never have been on a
    # world-readable record is handled by `FCRMSettings.RESTRICTED_FIELDS`.
    register_permission_hooks(
        "FCRM Settings",
        permission_query_conditions=platform_docs.app_settings_query_conditions,
        has_permission=platform_docs.app_settings_has_permission,
    )


__all__ = ["register", "org_hierarchy", "notification"]
