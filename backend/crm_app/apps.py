from django.apps import AppConfig


class CrmAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "crm_app"
    verbose_name = "CRM"

    def ready(self):
        # Phase 2: register the row-level permission hooks with the phase-0 registry.
        # This mirrors Frappe's hooks.py blocks and touches no phase-0 code.
        from crm_app.permissions import register

        register()

        # C8: what `frappe.delete_doc` does for every doctype and Django's FK cascade does
        # not. The polymorphic child tables have no FK, so their rows go with the parent
        # here (delete_doc.py:207-227), and the rows that *reference* a document - its
        # comments, assignments, versions, communications and attached files, bytes
        # included (delete_doc.py:200, `remove_all`) - go with it too. Wired onto every
        # registered doctype, not only the ones declaring a polymorphic child and not
        # only this app's: walking `crm_app`'s declaring models alone left an Address's
        # Dynamic Link rows and a note's attached file behind on delete
        # (`tests/test_address.py`, `tests/test_upload_file.py`). Child tables are left
        # out, their rows are replaced wholesale and reference nothing; so are the
        # reference doctypes themselves (a comment has no comments), which would
        # otherwise cost five queries per row in every cascade.
        from frappe_core import registry
        from frappe_core.children import REFERENCE_DOCTYPES, connect_cascade

        for doctype in registry.all_doctypes():
            entry = registry.get_entry(doctype)
            if not entry.is_child_table and doctype not in REFERENCE_DOCTYPES:
                connect_cascade(entry.model)

        # Upstream's `attach_files_to_document` runs on every document's `on_update`
        # (frappe/hooks.py:205,227): the file an Attach field names becomes the document's
        # attachment, and the File rule then lets anyone who may read the document fetch
        # it. Without it the brand logo, a private upload like every other, was readable
        # by its uploader alone (FINDINGS.md 85). Only a model that declares an Attach
        # field gets a receiver.
        from frappe_platform.files import connect_attach_on_save

        for doctype in registry.all_doctypes():
            entry = registry.get_entry(doctype)
            if not entry.is_child_table:
                connect_attach_on_save(entry.model, doctype)

        # Phase 3: importing the package runs the @whitelist decorators, which is what
        # makes each dotted path resolvable. Without this the method map is empty.
        from crm_app import api  # noqa: F401

        # Phase 4: wire get_data's saved-view seam. Registered after the api import so
        # every doctype is in the registry by the time we enumerate it.
        from crm_app import metadata_hooks

        metadata_hooks.register()

        # Phase 5: enqueue background work off model writes - the `modified` bump that
        # reorders a list when someone comments, and the invitation email.
        from crm_app import async_signals

        async_signals.connect_signals()

        # Phase 7: the provider-neutral telephony endpoints. Imported unconditionally and
        # deliberately - `is_call_integration_enabled` has to answer "no" with every flag
        # off, so the module cannot itself be behind a flag. Nothing it imports touches a
        # provider SDK; `tests/test_integration_isolation.py` holds that line.
        from crm_app.integrations import api as integrations_api  # noqa: F401

        # Provider adapters are imported unconditionally too, and that is deliberate.
        # Upstream registers `make_a_call` always and refuses inside it with "Please setup
        # Exotel intergration"; gating *registration* on the flag would turn that dialog
        # into a 404 and break the frontend contract. What must not happen at import time
        # is loading a provider SDK - none of these do; every `requests` import is inside
        # the function that makes the call.
        from crm_app.integrations.exotel import handler as exotel_handler  # noqa: F401
        from crm_app.integrations.twilio import handler as twilio_handler  # noqa: F401
        from crm_app.integrations.whatsapp import api as whatsapp_api  # noqa: F401
        from crm_app.integrations.whatsapp import signals as whatsapp_signals

        whatsapp_signals.connect_signals()

        from crm_app.integrations.erpnext import api as erpnext_api  # noqa: F401
        from crm_app.integrations.erpnext import customer as erpnext_customer

        erpnext_customer.connect_signals()
