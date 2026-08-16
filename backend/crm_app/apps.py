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
