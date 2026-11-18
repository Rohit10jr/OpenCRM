"""Django system checks for resource declarations."""

from django.core.checks import Error, register

from core.mixins.export import ListExportMixin
from core.resources import PRODUCTION_URLCONF, routed_rule_conflicts, routed_viewsets


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


@register()
def check_export_field_info_viewsets(app_configs, **kwargs):
    errors = []
    for viewset in sorted(
        routed_viewsets(PRODUCTION_URLCONF), key=lambda item: item.__name__
    ):
        if not issubclass(viewset, ListExportMixin):
            continue
        provider = getattr(viewset, "export_field_info", None)
        if callable(provider) and not getattr(
            provider, "test_only_export_placeholder", False
        ):
            continue
        errors.append(
            Error(
                f"{viewset.__name__} must define a production export_field_info provider.",
                hint=(
                    "Supply field labels and field types from the resource metadata; "
                    "the tests_support placeholder is test-only."
                ),
                obj=viewset,
                id="core.E002",
            )
        )
    return errors


@register()
def check_mail_account_provider(app_configs, **kwargs):
    """`MAIL_ACCOUNT_PROVIDER` must resolve to a module exposing the two calls, so a typo
    never falls back quietly to the config account (spec CONFIGURATION section 4.4)."""
    from importlib import import_module

    from django.conf import settings

    path = getattr(settings, "MAIL_ACCOUNT_PROVIDER", "") or ""
    if not path:
        return []
    try:
        module = import_module(path)
    except ImportError as exc:
        return [
            Error(
                f"MAIL_ACCOUNT_PROVIDER {path!r} does not resolve: {exc}",
                hint="Name the module that provides the saved Email Account lookups.",
                id="core.E003",
            )
        ]
    missing = [
        name
        for name in ("saved_outgoing_account", "default_signature")
        if not callable(getattr(module, name, None))
    ]
    if missing:
        return [
            Error(
                f"MAIL_ACCOUNT_PROVIDER {path!r} lacks {', '.join(missing)}",
                hint="Expose saved_outgoing_account(sender=None, reference_doctype=None) "
                "and default_signature().",
                id="core.E003",
            )
        ]
    return []
