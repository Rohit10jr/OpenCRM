"""Serializers for the contacts resources."""

from core.serializers import DocumentSerializer

from .models import CRMIndustry, Gender, Salutation

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


class SalutationSerializer(DocumentSerializer):
    class Meta:
        model = Salutation
        fields = (*DOCUMENT_FIELDS, "salutation")


class GenderSerializer(DocumentSerializer):
    class Meta:
        model = Gender
        fields = (*DOCUMENT_FIELDS, "gender")


class CRMIndustrySerializer(DocumentSerializer):
    class Meta:
        model = CRMIndustry
        fields = (*DOCUMENT_FIELDS, "industry")
