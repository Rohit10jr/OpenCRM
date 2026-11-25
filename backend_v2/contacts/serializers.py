"""Serializers for the contacts resources."""

from core.serializers import DocumentSerializer

from .models import Address, Contact, CRMIndustry, CRMTerritory, Gender, Salutation

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


#: The old columns' order (`crm_app/models/taxonomy.py:113-152`).
TERRITORY_FIELDS = (
    "territory_name",
    "territory_manager",
    "lft",
    "rgt",
    "is_group",
    "old_parent",
    "parent_crm_territory",
)


class CRMTerritorySerializer(DocumentSerializer):
    class Meta:
        model = CRMTerritory
        fields = (*DOCUMENT_FIELDS, *TERRITORY_FIELDS)


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


CONTACT_FIELDS = (
    "first_name",
    "middle_name",
    "last_name",
    "full_name",
    "salutation",
    "company_name",
    "designation",
    "gender",
    "image",
    "status",
    "address",
    "user",
    "email_id",
    "mobile_no",
    "phone",
)


class ContactSerializer(DocumentSerializer):
    """The contact and its `email_ids` / `phone_nos` rows (specs/CONTACTS.md §3, §4).
    The document route saves the contact again once its rows are written, so the
    primary rules apply over the whole table (FINDINGS 8)."""

    CHILD_TABLES = {
        "email_ids": ("contacts.ContactEmail", "parent_contact"),
        "phone_nos": ("contacts.ContactPhone", "parent_contact"),
    }

    class Meta:
        model = Contact
        fields = (*DOCUMENT_FIELDS, *CONTACT_FIELDS, "email_ids", "phone_nos")


class AddressSerializer(DocumentSerializer):
    """The address and its Dynamic Link rows (`links`, the model's polymorphic table)."""

    class Meta:
        model = Address
        fields = (*DOCUMENT_FIELDS, *ADDRESS_FIELDS, "links")
