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

        # C8: the three polymorphic child tables have no FK, so nothing cascades when
        # their parent is deleted (frappe/model/delete_doc.py:207-227 does this
        # explicitly upstream). Wire the equivalent onto every model that declares one.
        from django.apps import apps as django_apps

        from frappe_core.children import connect_cascade

        for model in django_apps.get_app_config("crm_app").get_models():
            if getattr(model, "POLYMORPHIC_CHILD_TABLES", None):
                connect_cascade(model)

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
