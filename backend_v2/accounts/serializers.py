"""Serializers for the accounts resources."""

from rest_framework import serializers

from core.exceptions import PermissionError, ValidationError
from core.models import validate_email_address
from core.serializers import DocumentSerializer

from .invitations import INVITABLE_ROLES, new_invitation_key
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
            "user_emails",
        )

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None and "name" in fields:
            # PE-7 (proposed): a name sent on update is ignored, never a second row.
            fields["name"].read_only = True
        return fields

    #: The send-from accounts, CONFIGURATION's User Email rows (named by label, so this
    #: app does not import configuration). Written by System Manager only
    #: (`User.PRIVILEGED_WRITE_FIELDS`).
    CHILD_TABLES = {"user_emails": ("configuration.UserEmail", "parent_user")}

    #: Child-table keys the old User document always carries (its serializer emits every
    #: reverse FK it discovers, backend/frappe_core/children.py:38-51), empty here until
    #: their unit builds them: Assignment Rule User (ASSIGNMENTS, PE-9). Never written
    #: through User.
    EMPTY_CHILD_KEYS = ("assignmentruleuser_set",)

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
    """`key` is sensitive on the model and never on the wire, even for a manager.

    PE-8: through the resource, `email` and `role` are written on create and then set once
    (upstream's `set_only_once`, `frappe/model/document.py:697-721`); `key`, `status` and
    `invited_by` are set by the server on create, as upstream's `before_insert`
    (`crm_invitation.py`)."""

    #: (fieldname, label) for upstream's "Value cannot be changed for <label>".
    SET_ONCE_FIELDS = (("email", "Email"), ("role", "Role"))

    def get_fields(self):
        fields = super().get_fields()
        if "role" in fields and not fields["role"].read_only:
            # Upstream's validate_can_invite runs before its Select check, so any text
            # reaches create's 403; a change is the set-once refusal.
            fields["role"] = serializers.CharField(
                required=False, allow_blank=True, allow_null=True
            )
        return fields

    def create(self, validated_data):
        # Upstream's order: before_insert checks the address, then validate the role
        # (crm_invitation.py, before_insert and validate_can_invite).
        validate_email_address(validated_data.get("email") or "")
        if validated_data.get("role") not in INVITABLE_ROLES:
            raise PermissionError("Cannot invite for this role")
        validated_data["key"] = new_invitation_key()
        validated_data["status"] = "Pending"
        validated_data["invited_by"] = self.user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        for fieldname, label in self.SET_ONCE_FIELDS:
            if fieldname in validated_data and validated_data[fieldname] != getattr(
                instance, fieldname
            ):
                raise ValidationError(f"Value cannot be changed for <strong>{label}</strong>")
        return super().update(instance, validated_data)

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
