"""Shared actions that document resources opt in to explicitly."""

from core.mixins.bulk_delete import BulkDeleteMixin
from core.mixins.bulk_update import BulkUpdateMixin
from core.mixins.linked import LinkedDocumentsMixin
from core.mixins.rename import RenameMixin

__all__ = (
    "BulkDeleteMixin",
    "BulkUpdateMixin",
    "LinkedDocumentsMixin",
    "RenameMixin",
)
