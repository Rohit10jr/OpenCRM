"""Transactional bulk deletion through an opted-in resource's policy."""

from django.db import transaction
from rest_framework.decorators import action
from rest_framework.response import Response

from core.children import (
    delete_polymorphic_children_batch,
    delete_references_batch,
    references_handled,
)
from core.delete import check_dynamic_links, check_dynamic_links_batch
from core.doctypes import doctype_of
from core.exceptions import LinkExistsError, PermissionError, throw
from core.inputs import build_payload
from core.mixins.bulk_update import viewset_path
from core.mixins.linked import (
    _clear_contact,
    _clear_link_fields,
    _clear_reference,
    linked_documents,
)
from core.query import parse_json_param
from core.renderers import Envelope
from core.resources import rules_for
from core.translate import _

BULK_DELETE_ENQUEUE_THRESHOLD = 10


def _permission_refusal(viewset_class, name):
    raise PermissionError(
        _("No permission to delete {0} {1}").format(
            doctype_of(viewset_class.serializer_class.Meta.model), name
        ),
        title=_("Not Permitted"),
    )


def authorize_bulk_delete(viewset_class, names, user):
    """Return existing authorized names, or refuse the complete batch."""

    model = viewset_class.serializer_class.Meta.model
    instances = {
        str(instance.pk): instance
        for instance in model._default_manager.filter(pk__in=names)
    }
    existing = set(instances)
    if not existing:
        return []
    if user is None or not getattr(user, "is_authenticated", False):
        _permission_refusal(viewset_class, sorted(existing)[0])

    visible_rows = model._default_manager.filter(pk__in=existing)
    list_rule = viewset_class.list_rule(user)
    if list_rule is not None:
        visible_rows = visible_rows.filter(list_rule)
    visible = {str(pk) for pk in visible_rows.values_list("pk", flat=True)}

    invisible = sorted(existing - visible)
    if invisible:
        _permission_refusal(viewset_class, invisible[0])
    object_denied = sorted(
        name
        for name in existing & visible
        if viewset_class.has_object_rule(user, instances[name], "delete") is False
    )
    if object_denied:
        _permission_refusal(viewset_class, object_denied[0])
    return [name for name in names if name in existing]


def perform_bulk_delete(viewset_class, targets, user, delete_linked=False):
    """Clear writable links and delete all targets in one transaction."""

    model = viewset_class.serializer_class.Meta.model
    with transaction.atomic():
        for _source_doctype, instance in linked_documents(model, targets, user):
            rules = rules_for(type(instance))
            if (
                rules is None
                or rules.has_object_rule(user, instance, "write") is False
            ):
                continue
            if viewset_class.bulk_delete_remove_contact:
                _clear_contact(instance)
            else:
                _clear_reference(instance)
                for target in targets:
                    _clear_link_fields(instance, model, target)
            if delete_linked:
                try:
                    check_dynamic_links(instance)
                except LinkExistsError:
                    continue
                instance.delete()

        target_instances = list(model._default_manager.filter(pk__in=targets))
        check_dynamic_links_batch(target_instances)
        delete_polymorphic_children_batch(model, targets)
        delete_references_batch(doctype_of(model), targets)
        with references_handled():
            model._default_manager.filter(pk__in=targets).delete()


class BulkDeleteMixin:
    """Add the collection ``bulk-delete`` action to a document resource."""

    bulk_delete_remove_contact = False

    @action(detail=False, methods=("post",), url_path="bulk-delete")
    def bulk_delete(self, request):
        inputs = build_payload(request)
        parsed = parse_json_param(inputs.get("items"), []) or []
        if not parsed:
            throw(_("Items are required"))
        if not isinstance(parsed, list):
            throw(_("Items must be a list"))

        names = [str(item) for item in parsed]
        targets = authorize_bulk_delete(type(self), names, request.user)
        delete_linked = bool(inputs.get("delete_linked", False))
        if len(targets) > BULK_DELETE_ENQUEUE_THRESHOLD:
            from core.tasks import delete_bulk_docs

            delete_bulk_docs.delay(
                viewset_path(type(self)), targets, delete_linked, request.user.name
            )
        else:
            perform_bulk_delete(type(self), targets, request.user, delete_linked)
        return Response(Envelope("success", "message"))
