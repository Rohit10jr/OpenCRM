"""Small model metadata readers used in place of a doctype registry."""

from collections.abc import Mapping
from functools import lru_cache
from types import MappingProxyType

from django.apps import apps


def doctype_of(model) -> str:
    """Return the Frappe doctype declared by a model, or its class name."""
    return str(getattr(model, "DOCTYPE", model.__name__))


def is_child_table(model) -> bool:
    """Return whether a model represents an inline child table."""
    return bool(getattr(model, "IS_CHILD_TABLE", False))


def is_single(model) -> bool:
    """Return whether a model represents a singleton document."""
    return bool(getattr(model, "IS_SINGLE", False))


@lru_cache(maxsize=1)
def declared_doctypes() -> Mapping[str, type]:
    """Return the static process-local mapping declared by installed models.

    Read-only: the result is cached for the process, so a caller that changed it would
    change every later lookup."""

    return MappingProxyType(
        {
            doctype_of(model): model
            for model in apps.get_models()
            if getattr(model, "DOCTYPE", None)
        }
    )


def model_for_doctype(doctype: str):
    return declared_doctypes().get(str(doctype))
