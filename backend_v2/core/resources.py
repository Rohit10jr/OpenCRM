"""Resolve a document model's independently callable row rules."""

from functools import lru_cache

from django.core.exceptions import ImproperlyConfigured
from django.urls import URLResolver, clear_url_caches, get_resolver
from django.utils.module_loading import import_string

from core.views import DocumentViewSet

PRODUCTION_URLCONF = "config.urls"


def _patterns(urlconf):
    pending = list(get_resolver(urlconf).url_patterns)
    while pending:
        pattern = pending.pop()
        if isinstance(pattern, URLResolver):
            pending.extend(pattern.url_patterns)
        else:
            yield pattern


@lru_cache(maxsize=None)
def _routed_rules(urlconf):
    """Return model mappings and conflicting ViewSets for one URLconf."""

    by_model = {}
    conflicts = {}
    for pattern in _patterns(urlconf):
        viewset = getattr(pattern.callback, "cls", None)
        if not (
            isinstance(viewset, type)
            and issubclass(viewset, DocumentViewSet)
            and viewset is not DocumentViewSet
        ):
            continue
        model = viewset.serializer_class.Meta.model
        previous = by_model.setdefault(model, viewset)
        if previous is not viewset:
            conflicts.setdefault(model, {previous}).add(viewset)
    return by_model, conflicts


def routed_rule_map(urlconf=None):
    """Return the routed model-to-ViewSet map for ``urlconf``."""

    active_urlconf = PRODUCTION_URLCONF if urlconf is None else urlconf
    return _routed_rules(active_urlconf)[0]


def routed_rule_conflicts(urlconf=None):
    """Return models served by more than one distinct ViewSet class."""

    active_urlconf = PRODUCTION_URLCONF if urlconf is None else urlconf
    return _routed_rules(active_urlconf)[1]


def _declared_rules(model):
    path = getattr(model, "ROW_RULES", None)
    if not path:
        return None
    try:
        provider = import_string(path)
    except (AttributeError, ImportError) as exc:
        raise ImproperlyConfigured(
            f"{model._meta.label}.ROW_RULES cannot resolve {path!r}"
        ) from exc
    missing = [
        name
        for name in ("list_rule", "has_object_rule")
        if not callable(getattr(provider, name, None))
    ]
    if missing:
        raise ImproperlyConfigured(
            f"{model._meta.label}.ROW_RULES {path!r} is missing {missing}"
        )
    return provider


def rules_for(model, urlconf=None):
    """Return routed or explicitly declared row rules for ``model``."""

    return routed_rule_map(urlconf).get(model) or _declared_rules(model)


def clear_rules_cache():
    """Clear URLconf-derived mappings after tests replace URL patterns in place."""

    _routed_rules.cache_clear()
    clear_url_caches()
