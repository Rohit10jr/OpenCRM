from django.apps import AppConfig


class ConfigurationConfig(AppConfig):
    name = "configuration"

    def ready(self):
        from configuration import kanban_counts  # noqa: F401 - registers its check
