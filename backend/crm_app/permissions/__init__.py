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
    attachments,
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

    # Phase 7. Two hold access tokens; the third holds the raw Facebook payload for a lead
    # that failed to import - a real person's name, email and phone, in a table with no
    # other rule protecting it. Managers only, reads closed.
    # `Facebook Lead Form` holds no secret itself, and gets the same rule anyway: it is
    # reachable only from the sync settings screen, which is manager-only, and leaving one
    # doctype of a four-doctype feature open is how the next reader concludes the feature
    # was meant to be public.
    for doctype in (
        "Lead Sync Source",
        "Facebook Page",
        "Facebook Lead Form",
        "Failed Lead Sync Log",
        # `ERPNext CRM Settings` holds an API key/secret pair that authenticates as a user
        # on the remote ERPNext site. Upstream grants it to System Manager only.
        "ERPNext CRM Settings",
    ):
        register_permission_hooks(
            doctype,
            permission_query_conditions=platform_docs.lead_sync_query_conditions,
            has_permission=platform_docs.lead_sync_has_permission,
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

    # Address and Country (FINDINGS.md 45): upstream's role tables, reproduced. Every
    # role reads, writes and creates an address and only System Manager deletes one;
    # everyone reads the country list and System Manager maintains it.
    register_permission_hooks(
        "Address",
        permission_query_conditions=platform_docs.address_query_conditions,
        has_permission=platform_docs.address_has_permission,
    )
    register_permission_hooks(
        "Country",
        permission_query_conditions=platform_docs.country_query_conditions,
        has_permission=platform_docs.country_has_permission,
    )
    # Contact (FINDINGS.md 86, the role passes): upstream's role table, reproduced. Every
    # role reads, writes and creates any contact; delete is the `All` row's with
    # `if_owner`, so the creator or a System Manager. Without this any CRM user deleted
    # any contact - the security exception CLAUDE.md names, read as a missing hook.
    register_permission_hooks(
        "Contact",
        permission_query_conditions=platform_docs.contact_query_conditions,
        has_permission=platform_docs.contact_has_permission,
    )
    # Email Template (FINDINGS.md 87, the role passes): upstream's role table, reproduced.
    # Every role reads; System Manager alone creates, writes and deletes.
    register_permission_hooks(
        "Email Template",
        permission_query_conditions=platform_docs.email_template_query_conditions,
        has_permission=platform_docs.email_template_has_permission,
    )
    # Language (FINDINGS.md 58): the same shape, reference data every role reads and
    # System Manager maintains.
    register_permission_hooks(
        "Language",
        permission_query_conditions=platform_docs.language_query_conditions,
        has_permission=platform_docs.language_has_permission,
    )
    # Currency (FINDINGS.md 63): the same shape again, the list behind the deal,
    # organization and dashboard currency pickers.
    register_permission_hooks(
        "Currency",
        permission_query_conditions=platform_docs.currency_query_conditions,
        has_permission=platform_docs.currency_has_permission,
    )
    # System Settings (FINDINGS.md 64): System Manager alone, reading included, as
    # system_settings.json grants. The boot call reads the row server-side.
    register_permission_hooks(
        "System Settings",
        permission_query_conditions=platform_docs.system_settings_query_conditions,
        has_permission=platform_docs.system_settings_has_permission,
    )
    # Salutation and Gender (FINDINGS.md 66): the two lookups behind the contact, lead
    # and deal forms. Everyone reads, System Manager maintains.
    for doctype in ("Salutation", "Gender"):
        register_permission_hooks(
            doctype,
            permission_query_conditions=platform_docs.reference_data_query_conditions,
            has_permission=platform_docs.reference_data_has_permission,
        )

    # The org tree is an *input to this very engine* - `org_hierarchy` resolves "owned by
    # anyone in my subtree" against it on every Lead and Deal read. Unruled, a Sales User
    # could add themselves and reparent a colleague underneath, taking that colleague's
    # whole pipeline in one call. System Manager only, as upstream has it; deliberately
    # tighter than the manager pair used elsewhere, because the chart is what decides what
    # a Sales Manager can see.
    register_permission_hooks(
        "CRM Sales Hierarchy",
        permission_query_conditions=platform_docs.sales_hierarchy_query_conditions,
        has_permission=platform_docs.sales_hierarchy_has_permission,
    )

    # An invitation holds the role being granted and the key that redeems it. Upstream
    # grants Sales User read on this doctype and redeems by key alone, so reading a
    # pending System Manager invitation is enough to become one (bug #21). Managers only
    # here, and the key never reaches the wire at all. Disarmed ahead of phase 8: nothing
    # can redeem an invitation today because `accept_invitation` is unimplemented, and this
    # rule is what must already be in place when it lands.
    register_permission_hooks(
        "CRM Invitation",
        permission_query_conditions=platform_docs.invitation_query_conditions,
        has_permission=platform_docs.invitation_has_permission,
    )

    # Comment, Communication and File are *about* another document and carry which one.
    # Unruled, each leaked what the record itself refused: email bodies, private file
    # URLs, internal remarks - and a comment could be forged onto a record the author
    # cannot see. One rule, three registrations: defer to the referenced document.
    for doctype, conditions, permission in (
        ("Comment", attachments.comment_query_conditions, attachments.comment_has_permission),
        (
            "Communication",
            attachments.communication_query_conditions,
            attachments.communication_has_permission,
        ),
        ("File", attachments.file_query_conditions, attachments.file_has_permission),
        (
            "WhatsApp Message",
            attachments.whatsapp_message_query_conditions,
            attachments.whatsapp_message_has_permission,
        ),
    ):
        register_permission_hooks(
            doctype,
            permission_query_conditions=conditions,
            has_permission=permission,
            # Opts this doctype into the destination re-check on update: moving a row onto
            # a document you cannot write is the same hole as creating one there.
            reference_fields=attachments.REFERENCE_FIELDS[doctype],
        )


__all__ = ["register", "org_hierarchy", "notification"]
