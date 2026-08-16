"""The DocType registry - one lookup surface for phases 2, 3 and 4.

PHASE_0_FOUNDATION.md section 4. Registering a model makes it routable::

    @register_doctype("CRM Lead")
    class CRMLead(BaseDocument):
        class Meta:
            name_strategy = NamingSeries("CRM-LEAD-.YYYY.-")

That is the whole contract for a phase-1 agent. Everything else the framework needs -
serializer, list defaults, filterable fields, permission hooks - is derived, with an
override available for each.

The registry replaces Frappe's ``get_controller(doctype)`` + ``frappe.get_meta``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from django.db import models

#: Doctype string -> entry. Populated at import time by the decorator, so every module
#: defining doctypes must be imported before the registry is read; ``AppConfig.ready``
#: handles that for the local apps.
_REGISTRY: dict[str, "DocTypeEntry"] = {}


class DocTypeNotFound(KeyError):
    """Raised when a doctype string has no registered model."""

    def __init__(self, doctype: str):
        self.doctype = doctype
        super().__init__(doctype)

    def __str__(self) -> str:
        return f"DocType {self.doctype} not found"


@dataclass
class DocTypeEntry:
    """Everything the framework knows about one doctype."""

    doctype: str
    model: type[models.Model]
    is_child_table: bool = False
    is_single: bool = False
    #: Set by phase 2 via :func:`register_permission_hooks`.
    permission_query_conditions: Callable | None = None
    has_permission: Callable | None = None
    #: Optional batched form of ``has_permission``, added in phase 5 for C9. Takes
    #: ``(doctype, instances, ptype, user)`` and returns the subset of ``instances`` that
    #: passes, in a bounded number of queries. Absent means "call ``has_permission`` per
    #: object", which is correct but N round-trips.
    has_permission_batch: Callable | None = None
    #: Set by phase 4 via :func:`register_metadata_hooks`.
    list_columns_provider: Callable | None = None
    filterable_fields_provider: Callable | None = None
    #: Explicit serializer override; otherwise generated on demand.
    serializer_class: type | None = field(default=None, repr=False)

    # -- controller-defined defaults ------------------------------------------------
    # Frappe puts these on the doctype controller and probes with hasattr(); we do the
    # same against the model class, so a phase-1 agent ports the staticmethod verbatim.

    def default_list_data(self) -> dict:
        """``{"columns": [...], "rows": [...]}``.

        Falls back to Frappe's own fallback in ``api/doc.py:get_data`` - the Name and
        Last Modified columns - when the model defines none.
        """
        provider = getattr(self.model, "default_list_data", None)
        if callable(provider):
            return provider()
        return {
            "columns": [
                {"label": "Name", "type": "Data", "key": "name", "width": "16rem"},
                {
                    "label": "Last Modified",
                    "type": "Datetime",
                    "key": "modified",
                    "width": "8rem",
                },
            ],
            "rows": ["name"],
        }

    def has_default_list_data(self) -> bool:
        return callable(getattr(self.model, "default_list_data", None))

    def default_kanban_settings(self) -> dict | None:
        provider = getattr(self.model, "default_kanban_settings", None)
        if callable(provider):
            return provider()
        return None

    def non_filterable_fields(self) -> list[str]:
        """Mirrors ``get_controller(doctype).get_non_filterable_fields()``."""
        provider = getattr(self.model, "get_non_filterable_fields", None)
        if callable(provider):
            return list(provider() or [])
        return []

    def parse_list_data(self, data):
        """Mirrors ``api/doc.py:parse_list_data``."""
        provider = getattr(self.model, "parse_list_data", None)
        if callable(provider):
            return provider(data)
        return data

    def get_serializer_class(self):
        if self.serializer_class is None:
            from frappe_core.serializers import build_serializer_class

            self.serializer_class = build_serializer_class(self.model)
        return self.serializer_class


def register_doctype(
    doctype: str,
    *,
    is_child_table: bool | None = None,
    is_single: bool | None = None,
    serializer_class: type | None = None,
):
    """Class decorator registering a model under its Frappe DocType string.

    ``is_child_table`` / ``is_single`` default to whatever the model declared in its
    ``Meta``, so a phase-1 agent can set them in either place.
    """

    def decorator(model_cls):
        doc_meta = getattr(model_cls, "_doc_meta", None) or {}
        entry = DocTypeEntry(
            doctype=doctype,
            model=model_cls,
            is_child_table=(
                doc_meta.get("is_child_table", False)
                if is_child_table is None
                else is_child_table
            ),
            is_single=(
                doc_meta.get("is_single", False) if is_single is None else is_single
            ),
            serializer_class=serializer_class,
        )
        _REGISTRY[doctype] = entry
        # Let the model answer get_doctype() without a registry round-trip.
        model_cls._doc_meta = {**doc_meta, "doctype": doctype}
        if not hasattr(model_cls, "get_doctype"):
            # `BaseDocument` provides this, but a registered model need not be one -
            # `User` derives from `AbstractBaseUser` because Django requires it of
            # AUTH_USER_MODEL. Without this, resolving a Link target that points at User
            # silently yields None, and every FK-target check passes vacuously.
            model_cls.get_doctype = classmethod(
                lambda cls: (cls._doc_meta or {}).get("doctype")
            )
        return model_cls

    return decorator


def get_entry(doctype: str) -> DocTypeEntry:
    try:
        return _REGISTRY[doctype]
    except KeyError:
        raise DocTypeNotFound(doctype) from None


def get_model(doctype: str) -> type[models.Model]:
    return get_entry(doctype).model


def has_doctype(doctype: str) -> bool:
    return doctype in _REGISTRY


def all_doctypes() -> list[str]:
    return sorted(_REGISTRY)


def routable_doctypes() -> list[str]:
    """Doctypes with a standalone ``/api/resource/`` route.

    Child tables are excluded - PHASE_1_MODELS.md section 3: they are reached through
    the parent and serialised inline.
    """
    return sorted(dt for dt, e in _REGISTRY.items() if not e.is_child_table)


def register_permission_hooks(
    doctype: str,
    *,
    permission_query_conditions: Callable | None = None,
    has_permission: Callable | None = None,
    has_permission_batch: Callable | None = None,
) -> None:
    """Phase-2 entry point. Mirrors Frappe's ``hooks.py`` blocks.

    Upstream registers these for CRM Lead, CRM Deal and CRM Notification only.

    ``has_permission_batch`` has no upstream counterpart; it exists because upstream's
    per-object check is one query per object and phase 3's ``delete_bulk_docs`` has to
    ask the question about a whole batch (C9). It is an optimisation only - omitting it
    changes cost, never the answer.
    """
    entry = get_entry(doctype)
    if permission_query_conditions is not None:
        entry.permission_query_conditions = permission_query_conditions
    if has_permission is not None:
        entry.has_permission = has_permission
    if has_permission_batch is not None:
        entry.has_permission_batch = has_permission_batch


def register_metadata_hooks(
    doctype: str,
    *,
    list_columns_provider: Callable | None = None,
    filterable_fields_provider: Callable | None = None,
) -> None:
    """Phase-4 entry point."""
    entry = get_entry(doctype)
    if list_columns_provider is not None:
        entry.list_columns_provider = list_columns_provider
    if filterable_fields_provider is not None:
        entry.filterable_fields_provider = filterable_fields_provider


def _reset_for_tests() -> None:
    """Drop every registration. Test-only."""
    _REGISTRY.clear()
