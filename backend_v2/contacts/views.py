"""The contacts resources (specs/CONTACTS.md)."""

from accounts.roles import ADMINISTRATOR, ROLE_SYSTEM_MANAGER
from contacts.serializers import CRMIndustrySerializer, GenderSerializer, SalutationSerializer
from core.access import Access
from core.mixins import LinkSearchMixin
from core.views import DocumentViewSet


def _is_system_admin(user) -> bool:
    return user.name == ADMINISTRATOR or user.has_role(ROLE_SYSTEM_MANAGER)


def _read_all_write_admin(user, ptype) -> bool:
    """Everyone reads; System Manager or Administrator writes, creates and deletes (old
    `crm_app/permissions/platform_docs.py:472-484`)."""
    if ptype == "read":
        return True
    return _is_system_admin(user)


class SalutationViewSet(LinkSearchMixin, DocumentViewSet):
    """Every column readable, filterable and sortable; search matches `name`."""

    access = Access.ruled()
    serializer_class = SalutationSerializer
    readable_fields = SalutationSerializer.Meta.fields
    filterable_fields = SalutationSerializer.Meta.fields
    sortable_fields = SalutationSerializer.Meta.fields
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        return None

    @staticmethod
    def has_object_rule(user, document, ptype):
        return _read_all_write_admin(user, ptype)


class GenderViewSet(LinkSearchMixin, DocumentViewSet):
    """As Salutation."""

    access = Access.ruled()
    serializer_class = GenderSerializer
    readable_fields = GenderSerializer.Meta.fields
    filterable_fields = GenderSerializer.Meta.fields
    sortable_fields = GenderSerializer.Meta.fields
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        return None

    @staticmethod
    def has_object_rule(user, document, ptype):
        return _read_all_write_admin(user, ptype)


class CRMIndustryViewSet(LinkSearchMixin, DocumentViewSet):
    """Open to every signed-in user, as `backend/` (no rule registered; DECISIONS 58).
    Every column readable, filterable and sortable."""

    access = Access.open(
        reason="Reference data: the industry vocabulary shown on organisation forms; "
        "no confidential rows or fields (PORT_MAP's reviewed-open entry)."
    )
    serializer_class = CRMIndustrySerializer
    readable_fields = CRMIndustrySerializer.Meta.fields
    filterable_fields = CRMIndustrySerializer.Meta.fields
    sortable_fields = CRMIndustrySerializer.Meta.fields
    searchable_fields = ()
