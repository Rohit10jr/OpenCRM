"""Serializers for the accounts resources."""

from core.serializers import DocumentSerializer

from .models import CRMInvitation, CRMSalesHierarchy, User

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

    #: Child-table keys the old User document always carries (its serializer emits every
    #: reverse FK it discovers, backend/frappe_core/children.py:38-51), empty here until
    #: their units build them: User Email (CONFIGURATION) and Assignment Rule User
    #: (ASSIGNMENTS). Never written through User.
    EMPTY_CHILD_KEYS = ("user_emails", "assignmentruleuser_set")

    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = {
                key: value for key, value in data.items() if key not in self.EMPTY_CHILD_KEYS
            }
        return super().to_internal_value(data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for key in self.EMPTY_CHILD_KEYS:
            data[key] = []
        return data


class CRMInvitationSerializer(DocumentSerializer):
    """`key` is sensitive on the model and never on the wire, even for a manager."""

    class Meta:
        model = CRMInvitation
        fields = (
            *DOCUMENT_FIELDS,
            "email",
            "role",
            "invited_by",
            "status",
            "email_sent_at",
            "accepted_at",
        )
