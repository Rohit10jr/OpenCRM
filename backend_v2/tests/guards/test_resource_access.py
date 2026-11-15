"""Guard every routed document model's explicit access decision."""

from django.apps import apps
from django.urls import URLResolver, get_resolver

from core.access import Access
from core.doctypes import is_child_table
from core.field_access import encrypted_fields, sensitive_fields
from core.models import BaseDocument
from core.views import DocumentViewSet
from core.withheld import WITHHELD_DOCUMENT_TYPES


# These installed models are FOUNDATION fixtures for subsystems such as naming, trees,
# links, and history. They need not all have routes; routed fixture ViewSets are still
# discovered below and held to the same access-declaration rules as production ones.
TEST_MODEL_EXCLUSIONS = {
    "tests_support": (
        "Test-only scaffolding deliberately includes models with no resource route."
    ),
}


def _patterns(urlconf):
    pending = list(get_resolver(urlconf).url_patterns)
    while pending:
        pattern = pending.pop()
        if isinstance(pattern, URLResolver):
            pending.extend(pattern.url_patterns)
        else:
            yield pattern


def _resource_viewsets(urlconfs=("config.urls", "config.test_urls")):
    found = set()
    for urlconf in urlconfs:
        for pattern in _patterns(urlconf):
            viewset = getattr(pattern.callback, "cls", None)
            if (
                isinstance(viewset, type)
                and issubclass(viewset, DocumentViewSet)
                and viewset is not DocumentViewSet
            ):
                found.add(viewset)
    return found


def _model(viewset):
    return viewset.serializer_class.Meta.model


def _declared_sensitive_fields(model):
    concrete = {
        field.name
        for field in model._meta.get_fields()
        if getattr(field, "concrete", False)
    }
    return (sensitive_fields(model) | encrypted_fields(model)) & concrete


def test_every_resource_viewset_declares_a_valid_access_decision():
    failures = []
    for viewset in sorted(_resource_viewsets(), key=lambda item: item.__name__):
        access = viewset.__dict__.get("access")
        if not isinstance(access, Access) or access.kind not in {"open", "ruled"}:
            failures.append(f"{viewset.__name__}: declare Access.open or Access.ruled")
            continue
        if access.kind == "open" and len(access.reason.strip()) <= 30:
            failures.append(f"{viewset.__name__}: open access needs a real reason")
        if access.kind == "ruled":
            missing = {
                method
                for method in ("list_rule", "has_object_rule")
                if method not in viewset.__dict__
            }
            if missing:
                failures.append(f"{viewset.__name__}: missing rules {sorted(missing)}")
        secrets = _declared_sensitive_fields(_model(viewset))
        if secrets and access.kind != "ruled":
            failures.append(
                f"{viewset.__name__}: fields {sorted(secrets)} require ruled access"
            )

    assert not failures, "Invalid resource access declarations:\n" + "\n".join(failures)


def test_every_production_document_model_is_served_or_withheld():
    served = {
        _model(viewset) for viewset in _resource_viewsets(("config.urls",))
    }
    production = {
        model
        for model in apps.get_models()
        if issubclass(model, BaseDocument)
        and not is_child_table(model)
        and model._meta.app_label not in TEST_MODEL_EXCLUSIONS
    }
    withheld = {
        model
        for model in production
        if getattr(model, "DOCTYPE", None) in WITHHELD_DOCUMENT_TYPES
    }

    missing = sorted(
        model._meta.label for model in production if model not in served | withheld
    )
    assert not missing, (
        f"Document models without a routed ViewSet or withheld reason: {missing}"
    )
    assert not served & withheld, "A document type cannot be both served and withheld"


def test_withheld_document_types_are_exact_current_models_with_reasons():
    # Internal timeline behaviour remains covered by core/tests/test_versions.py.
    known = {
        model.DOCTYPE: model
        for model in apps.get_models()
        if issubclass(model, BaseDocument) and getattr(model, "DOCTYPE", None)
    }
    stale = sorted(set(WITHHELD_DOCUMENT_TYPES) - set(known))
    assert not stale, f"Withheld document types no longer backed by models: {stale}"
    assert all(
        len(reason.strip()) > 30 for reason in WITHHELD_DOCUMENT_TYPES.values()
    ), "Every withheld document type needs a real reason"
    assert set(WITHHELD_DOCUMENT_TYPES) == {"Version"}


def test_test_model_exclusions_are_installed_and_reasoned():
    installed = {config.label for config in apps.get_app_configs()}
    assert set(TEST_MODEL_EXCLUSIONS) <= installed
    assert all(len(reason.strip()) > 30 for reason in TEST_MODEL_EXCLUSIONS.values())
