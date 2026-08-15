from django.apps import AppConfig


class FrappeCoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "frappe_core"
    verbose_name = "Frappe Core"

    def ready(self):
        # Importing the package runs the @whitelist decorators, which is what makes
        # /api/method/<dotted.path> resolvable. Without this the map is empty.
        from frappe_core import api  # noqa: F401

        # Keeps `_comments` in step with the Comment rows it caches (C3).
        from frappe_core import doc_caches

        doc_caches.connect_signals()
