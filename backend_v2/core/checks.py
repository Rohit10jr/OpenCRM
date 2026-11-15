"""Django system checks for resource declarations."""

from django.core.checks import Error, register

from core.resources import PRODUCTION_URLCONF, routed_rule_conflicts


@register()
def check_resource_rule_viewsets(app_configs, **kwargs):
    errors = []
    for model, viewsets in sorted(
        routed_rule_conflicts(PRODUCTION_URLCONF).items(),
        key=lambda item: item[0]._meta.label,
    ):
        names = ", ".join(sorted(viewset.__name__ for viewset in viewsets))
        errors.append(
            Error(
                f"{model._meta.label} is served by different ViewSets: {names}.",
                hint="Route one ViewSet class per model; one class may use many prefixes.",
                obj=model,
                id="core.E001",
            )
        )
    return errors
