from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        # Import the generic post-delete receiver without requiring any resource app
        # to register its models with core.
        from core import children  # noqa: F401
