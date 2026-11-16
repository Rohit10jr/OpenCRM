"""Shared actions that document resources opt in to explicitly."""

from core.mixins.bulk_delete import BulkDeleteMixin
from core.mixins.bulk_update import BulkUpdateMixin
from core.mixins.export import ListExportMixin
from core.mixins.linked import LinkedDocumentsMixin
from core.mixins.rename import RenameMixin
from core.mixins.search import LinkSearchMixin

__all__ = (
    "BulkDeleteMixin",
    "BulkUpdateMixin",
    "LinkedDocumentsMixin",
    "LinkSearchMixin",
    "ListExportMixin",
    "RenameMixin",
)
