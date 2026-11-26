"""The contacts resources (specs/CONTACTS.md)."""

from django.db.models import Q

from accounts.roles import (
    ADMINISTRATOR,
    ROLE_SALES_MANAGER,
    ROLE_SALES_USER,
    ROLE_SYSTEM_MANAGER,
)
from accounts.directory import session_role_flags
from configuration.export_fields import export_field_info_for
from configuration.mixins import ListViewMixin
from contacts.list_views import ContactListView, OrganizationListView
from contacts.models import Address, Contact, CRMOrganization
from contacts.serializers import (
    ADDRESS_FIELDS,
    CONTACT_FIELDS,
    DOCUMENT_FIELDS,
    AddressSerializer,
    ContactSerializer,
    CRMIndustrySerializer,
    CRMOrganizationSerializer,
    CRMTerritorySerializer,
    GenderSerializer,
    SalutationSerializer,
)
from rest_framework.decorators import action
from rest_framework.response import Response

from contacts import actions as contact_actions
from contacts import child_rows
from core.access import Access
from core.inputs import build_payload
from core.query import fetch_rows
from core.mixins import (
    BulkDeleteMixin,
    BulkUpdateMixin,
    LinkedDocumentsMixin,
    LinkSearchMixin,
    ListExportMixin,
    RenameMixin,
)
from core.renderers import Envelope
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


class SalutationViewSet(RenameMixin, LinkSearchMixin, DocumentViewSet):
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


class AddressViewSet(RenameMixin, LinkSearchMixin, DocumentViewSet):
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


class ContactViewSet(
    ListViewMixin,
    BulkDeleteMixin,
    BulkUpdateMixin,
    LinkedDocumentsMixin,
    LinkSearchMixin,
    ListExportMixin,
    RenameMixin,
    DocumentViewSet,
):
    """Contact (specs/CONTACTS.md §4, §8, §11.5): a CRM role reads, writes and creates
    (PE-29); delete is the owner's, a System Manager's or Administrator's, and only with
    a CRM role (old `platform_docs.py:437-455`, `contact.json`'s role table). Every column
    readable, filterable and sortable; search matches `name`. The shared actions
    (milestone 6a) take the same rules; the bulk delete clears each linked document's
    `contact` and `contacts` (PE-25), as the old `remove_contact=(doctype == "Contact")`."""

    bulk_delete_remove_contact = True
    export_field_info = staticmethod(export_field_info_for(Contact))
    list_view_class = ContactListView
    access = Access.ruled()
    serializer_class = ContactSerializer
    readable_fields = ContactSerializer.Meta.fields
    filterable_fields = (*DOCUMENT_FIELDS, *CONTACT_FIELDS)
    sortable_fields = (*DOCUMENT_FIELDS, *CONTACT_FIELDS)
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        return _crm_list_rule(user)

    @staticmethod
    def has_object_rule(user, document, ptype):
        if not _has_crm_role(user):
            return False
        if ptype != "delete":
            return True
        if _is_system_admin(user):
            return True
        owner = getattr(document, "owner_id", None)
        return bool(owner) and str(owner) == str(user.name)

    # The contact calls take the contact from the URL but never load it through
    # get_object(): a missing or refused contact is 403, not the base 404 (§4).
    @action(detail=True, methods=("post",), url_path="create-new-email-or-phone")
    def create_new_email_or_phone(self, request, **kwargs):
        """`crm.api.contact.create_new` (§11.4: the route's name)."""
        inputs = build_payload(request)
        result = contact_actions.create_new(
            type(self), request.user, self._url_name(), inputs.get("field"), inputs.get("value")
        )
        return Response(Envelope(result, "message"))

    @action(detail=True, methods=("post",), url_path="set-as-primary")
    def set_as_primary(self, request, **kwargs):
        """`crm.api.contact.set_as_primary`."""
        inputs = build_payload(request)
        result = contact_actions.set_as_primary(
            type(self), request.user, self._url_name(), inputs.get("field"), inputs.get("value")
        )
        return Response(Envelope(result, "message"))

    @action(detail=False, methods=("get",), url_path="search-emails")
    def search_emails(self, request):
        """`crm.api.contact.search_emails`; the frontend's POST is the generator's (§1)."""
        inputs = build_payload(request)
        result = contact_actions.search_emails(self.get_queryset(), request.user, inputs.get("txt"))
        return Response(Envelope(result, "message"))

    # The row routes (§4, DECISIONS 60): the row in the URL, the values in the body.
    @action(detail=True, methods=("patch", "delete"), url_path=r"email-ids/(?P<row>[^/]+)")
    def email_row(self, request, row=None, **kwargs):
        return self._row_route(request, "email_ids", row)

    @action(detail=True, methods=("patch", "delete"), url_path=r"phone-nos/(?P<row>[^/]+)")
    def phone_row(self, request, row=None, **kwargs):
        return self._row_route(request, "phone_nos", row)

    def _row_route(self, request, table, row):
        if request.method == "DELETE":
            child_rows.delete_row(type(self), request.user, self._url_name(), table, row)
            return Response(Envelope(None, "message"))
        contact = child_rows.edit_row(
            type(self), request.user, self._url_name(), table, row, request.data
        )  # the body only, as the document PATCH: a query parameter is not a value
        data = self.get_serializer(contact).data
        return Response(Envelope(data, "message"))

    def _url_name(self):
        return self.kwargs[self.lookup_url_kwarg or self.lookup_field]


class CRMIndustryViewSet(RenameMixin, LinkSearchMixin, DocumentViewSet):
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


class CRMTerritoryViewSet(RenameMixin, LinkSearchMixin, DocumentViewSet):
    """The territory tree (specs/CONTACTS.md §11.1): PE-29's rule, as CRM Industry's (a CRM
    role for every action; `backend/` registers no rule, owner A-74). Every column
    readable, filterable and sortable; rename sets `territory_name` (PE-24, PE-31). A
    territory with children is refused on delete by the PROTECT parent link (PE-34)."""

    access = Access.ruled()
    serializer_class = CRMTerritorySerializer
    readable_fields = CRMTerritorySerializer.Meta.fields
    filterable_fields = CRMTerritorySerializer.Meta.fields
    sortable_fields = CRMTerritorySerializer.Meta.fields
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        return _crm_list_rule(user)

    @staticmethod
    def has_object_rule(user, document, ptype):
        return _has_crm_role(user)


class CRMOrganizationViewSet(
    ListViewMixin,
    BulkDeleteMixin,
    BulkUpdateMixin,
    LinkedDocumentsMixin,
    LinkSearchMixin,
    ListExportMixin,
    RenameMixin,
    DocumentViewSet,
):
    """CRM Organization (specs/CONTACTS.md §4, §8): PE-29's rule, as CRM Industry's (a CRM
    role for every action). Every column readable, filterable and sortable; search matches
    `name` (§8). The shared actions (milestone 6b) take the same rule; rename sets
    `organization_name` (PE-24, PE-31). Its list view (milestone 7) is
    `OrganizationListView`."""

    export_field_info = staticmethod(export_field_info_for(CRMOrganization))
    list_view_class = OrganizationListView
    access = Access.ruled()
    serializer_class = CRMOrganizationSerializer
    readable_fields = CRMOrganizationSerializer.Meta.fields
    filterable_fields = CRMOrganizationSerializer.Meta.fields
    sortable_fields = CRMOrganizationSerializer.Meta.fields
    searchable_fields = ()

    @staticmethod
    def list_rule(user):
        return _crm_list_rule(user)

    @staticmethod
    def has_object_rule(user, document, ptype):
        return _has_crm_role(user)

    @action(detail=False, methods=("get",), url_path="directory")
    def directory(self, request):
        """`crm.api.session.get_organizations` (old `session.py:158-170`): a CRM role,
        else 403 "You are not permitted to access CRM resources."; every column of every
        organization the list rule shows, ordered by name, no limit, in the list shape."""
        session_role_flags(request.user)
        rows = fetch_rows(
            self.get_queryset(),
            user=request.user,
            fields=["*"],
            order_by="name asc",
            limit_page_length=0,
            selectable=self.readable_fields,
        )
        return Response(Envelope(rows, "message"))
