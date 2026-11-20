"""The contacts resources (specs/CONTACTS.md)."""

from django.db.models import Q

from accounts.roles import (
    ADMINISTRATOR,
    ROLE_SALES_MANAGER,
    ROLE_SALES_USER,
    ROLE_SYSTEM_MANAGER,
)
from contacts.models import Address
from contacts.serializers import (
    ADDRESS_FIELDS,
    DOCUMENT_FIELDS,
    AddressSerializer,
    CRMIndustrySerializer,
    GenderSerializer,
    SalutationSerializer,
)
from core.access import Access
from core.mixins import LinkSearchMixin
from core.views import DocumentViewSet


def _is_system_admin(user) -> bool:
    return user.name == ADMINISTRATOR or user.has_role(ROLE_SYSTEM_MANAGER)


CRM_ROLES = frozenset({ROLE_SALES_USER, ROLE_SALES_MANAGER, ROLE_SYSTEM_MANAGER})


def _has_crm_role(user) -> bool:
    """PE-29: Sales User, Sales Manager, System Manager or Administrator."""
    return user.name == ADMINISTRATOR or bool(user.get_roles() & CRM_ROLES)


def _crm_list_rule(user):
    """PE-29: a caller with no CRM role lists nothing."""
    return None if _has_crm_role(user) else Q(pk__in=[])


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


LINK_KEYS = ("link_doctype", "link_name")


def address_query_filters(filters):
    """The old `address_query` (`crm_app/api/client.py:64-81`): `link_doctype` and
    `link_name` select the addresses linked to that document through their Dynamic Link
    rows; every other key filters as a field. List-shaped filters get the same rule, as
    ACCOUNTS' User search does (the old code fails on them)."""
    if isinstance(filters, dict):
        result = dict(filters)
        wanted = {key: result.pop(key, None) for key in LINK_KEYS}
    elif isinstance(filters, list):
        wanted = {}
        result = []
        for condition in filters:
            if (
                isinstance(condition, (list, tuple))
                and len(condition) >= 3
                and condition[-3] in LINK_KEYS
                and condition[-2] == "="
            ):
                wanted[condition[-3]] = condition[-1]
            else:
                result.append(condition)
    else:
        return filters
    if not any(wanted.values()):
        return result
    names = Address.linked_to(wanted.get("link_doctype"), wanted.get("link_name"))
    if isinstance(result, dict):
        result["name"] = ["in", names]
    else:
        result.append(["name", "in", names])
    return result


class AddressViewSet(LinkSearchMixin, DocumentViewSet):
    """A caller with a CRM role reads, writes and creates an address (PE-29); System
    Manager or Administrator deletes one (old `platform_docs.py:424-434`). Every column
    readable, filterable and sortable; search matches the name, hides disabled addresses
    and reads the link filters."""

    access = Access.ruled()
    serializer_class = AddressSerializer
    readable_fields = AddressSerializer.Meta.fields
    filterable_fields = (*DOCUMENT_FIELDS, *ADDRESS_FIELDS)
    sortable_fields = (*DOCUMENT_FIELDS, *ADDRESS_FIELDS)
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        return _crm_list_rule(user)

    @staticmethod
    def has_object_rule(user, document, ptype):
        if ptype == "delete":
            return _is_system_admin(user)
        return _has_crm_role(user)

    def search_filters(self, filters, flags, user):
        filters = address_query_filters(filters)
        if isinstance(filters, list) and not flags["include_disabled"]:
            # The base hook hides disabled rows for dict filters only; list filters get
            # the same condition, as ACCOUNTS' User search does.
            if not any(
                isinstance(condition, (list, tuple)) and len(condition) >= 3 and condition[-3] == "disabled"
                for condition in filters
            ):
                filters = [*filters, ["disabled", "!=", 1]]
            return filters
        return super().search_filters(filters, flags, user)


class CRMIndustryViewSet(LinkSearchMixin, DocumentViewSet):
    """Every caller with a CRM role reads, writes, creates and deletes (PE-29; `backend/`
    registers no rule, DECISIONS 58). Every column readable, filterable and sortable."""

    access = Access.ruled()
    serializer_class = CRMIndustrySerializer
    readable_fields = CRMIndustrySerializer.Meta.fields
    filterable_fields = CRMIndustrySerializer.Meta.fields
    sortable_fields = CRMIndustrySerializer.Meta.fields
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        return _crm_list_rule(user)

    @staticmethod
    def has_object_rule(user, document, ptype):
        return _has_crm_role(user)
