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
