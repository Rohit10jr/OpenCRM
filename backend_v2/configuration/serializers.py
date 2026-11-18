"""Serializers for the configuration resources."""

from core.serializers import DocumentSerializer

from .models import SYSDEFAULT_FIELDS, SystemSettings

DOCUMENT_FIELDS = (
    "name",
    "owner",
    "modified_by",
    "creation",
    "modified",
    "idx",
    "docstatus",
    "_assign",
    "_liked_by",
    "_comments",
    "_user_tags",
)


class SystemSettingsSerializer(DocumentSerializer):
    class Meta:
        model = SystemSettings
        fields = (*DOCUMENT_FIELDS, *SYSDEFAULT_FIELDS)
