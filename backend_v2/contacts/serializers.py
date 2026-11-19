"""Serializers for the contacts resources."""

from core.serializers import DocumentSerializer

from .models import Address, CRMIndustry, Gender, Salutation

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


ADDRESS_FIELDS = (
    "address_title",
    "address_type",
    "address_line1",
    "address_line2",
    "city",
    "county",
    "state",
    "country",
    "pincode",
    "email_id",
    "phone",
    "fax",
    "is_primary_address",
    "is_shipping_address",
    "disabled",
)


class AddressSerializer(DocumentSerializer):
    """The address and its Dynamic Link rows (`links`, the model's polymorphic table)."""

    class Meta:
        model = Address
        fields = (*DOCUMENT_FIELDS, *ADDRESS_FIELDS, "links")
