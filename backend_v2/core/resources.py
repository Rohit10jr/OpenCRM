"""Resolve a document model's independently callable row rules."""

import inspect
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


def routed_viewsets(urlconf=None):
    """Return the distinct document ViewSets routed by one URLconf."""

    active_urlconf = PRODUCTION_URLCONF if urlconf is None else urlconf
    viewsets = {
        getattr(pattern.callback, "cls", None) for pattern in _patterns(active_urlconf)
    }
    return {
        viewset
        for viewset in viewsets
        if (
            isinstance(viewset, type)
            and issubclass(viewset, DocumentViewSet)
            and viewset is not DocumentViewSet
        )
    }


@lru_cache(maxsize=None)
def _routed_rules(urlconf):
    """Return model mappings and conflicting ViewSets for one URLconf."""

    by_model = {}
    conflicts = {}
    for viewset in routed_viewsets(urlconf):
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
    if inspect.isclass(provider):
        for name in ("list_rule", "has_object_rule"):
            descriptor = inspect.getattr_static(provider, name, None)
            if not isinstance(descriptor, staticmethod):
                raise ImproperlyConfigured(
                    f"{model._meta.label}.ROW_RULES {path!r} method {name} "
                    "must be a staticmethod"
                )
    return provider


def rules_for(model, urlconf=None):
    """Return routed or explicitly declared row rules for ``model``."""

    return routed_rule_map(urlconf).get(model) or _declared_rules(model)


def clear_rules_cache():
    """Clear URLconf-derived mappings after tests replace URL patterns in place."""

    _routed_rules.cache_clear()
    clear_url_caches()
