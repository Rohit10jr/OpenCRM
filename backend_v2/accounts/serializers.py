"""Serializers for the accounts resources."""

from core.serializers import DocumentSerializer

from .models import CRMSalesHierarchy, User

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


class CRMSalesHierarchySerializer(DocumentSerializer):
    class Meta:
        model = CRMSalesHierarchy
        fields = (
            *DOCUMENT_FIELDS,
            "full_name",
            "user",
            "reports_to",
            "old_parent",
            "lft",
            "rgt",
            "is_group",
        )


class UserSerializer(DocumentSerializer):
    """`User` as the old generated serializer showed it: every concrete field but the
    credentials (`backend/frappe_core/serializers.py:244-281`)."""

    class Meta:
        model = User
        fields = (
            "name",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "user_image",
            "enabled",
            "user_type",
            "time_zone",
            "mobile_no",
            "phone",
            "onboarding_status",
            "language",
            "email_signature",
            "creation",
            "modified",
        )

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None and "name" in fields:
            # PE-7 (proposed): a name sent on update is ignored, never a second row.
            fields["name"].read_only = True
        return fields

    def to_internal_value(self, data):
        if isinstance(data, dict) and "user_emails" in data:
            # User Email arrives with CONFIGURATION (specs/ACCOUNTS.md section 2).
            data = {key: value for key, value in data.items() if key != "user_emails"}
        return super().to_internal_value(data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # The old serializer always emits the child table, empty for a user with no rows.
        data["user_emails"] = []
        return data
