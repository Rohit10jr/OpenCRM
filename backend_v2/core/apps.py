from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        # Wire every installed document model without a resource-app registry.
        from core import checks  # noqa: F401
        from core.children import connect_cascades

        connect_cascades()
