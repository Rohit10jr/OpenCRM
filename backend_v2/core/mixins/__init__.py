"""Shared actions that document resources opt in to explicitly."""

from core.mixins.bulk_delete import BulkDeleteMixin
from core.mixins.bulk_update import BulkUpdateMixin
from core.mixins.linked import LinkedDocumentsMixin

__all__ = ("BulkDeleteMixin", "BulkUpdateMixin", "LinkedDocumentsMixin")
