"""Discover and unlink documents that point at a resource record."""

from collections import defaultdict

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.response import Response

from core.delete import (
    IGNORE_LINKS_ON_DELETE,
    _dynamic_link_declarations,
    check_dynamic_links,
)
from core.doctypes import doctype_of, is_child_table, model_for_doctype
from core.exceptions import LinkExistsError
from core.inputs import build_payload
from core.query import parse_json_param
from core.renderers import Envelope
from core.resources import rules_for


def _parent_fk(model):
    try:
        parentfield = model._meta.get_field("parentfield").default
    except models.FieldDoesNotExist:
        return None
    for field in model._meta.concrete_fields:
        if (
            isinstance(field, (models.ForeignKey, models.OneToOneField))
            and field.remote_field.related_name == parentfield
        ):
            return field
    return None


def _rules_or_raise(model):
    rules = rules_for(model)
    if rules is None:
        raise ImproperlyConfigured(
            f"{model._meta.label} is reachable by the linked-document scan "
            "but has no routed or declared row rules"
        )
    return rules


def _source_spec(model, target_model):
    child_table = is_child_table(model)
    parent_fk = _parent_fk(model) if child_table else None
    foreign_keys = [
        field
        for field in model._meta.get_fields()
        if isinstance(field, (models.ForeignKey, models.OneToOneField))
        and field is not parent_fk
        and field.related_model is target_model
    ]
    dynamic_pairs = []
    concrete = {field.name for field in model._meta.concrete_fields}
    if child_table:
        for doctype_field, name_field in _dynamic_link_declarations(model):
            if doctype_field in concrete and name_field in concrete:
                dynamic_pairs.append((doctype_field, name_field))
        field_order = {
            field.name: index for index, field in enumerate(model._meta.get_fields())
        }
        dynamic_pairs.sort(key=lambda pair: field_order[pair[1]])
    elif "reference_doctype" in concrete:
        for name_field in ("reference_name", "reference_docname"):
            if name_field in concrete:
                dynamic_pairs.append(("reference_doctype", name_field))
                break
    return parent_fk, foreign_keys, dynamic_pairs


def linked_documents(target_model, names, user):
    """Return visible ``(doctype, instance)`` links to any target name.

    Each source model is queried once with all names and all of its reference shapes.
    Child rows bypass their own list rule, then resolve and check their actual parent.
    """

    target_doctype = doctype_of(target_model)
    target_names = {str(name) for name in names}
    if not target_names:
        return []

    tagged = []
    polymorphic = defaultdict(set)
    polymorphic_candidates = []
    source_models = sorted(
        (
            model
            for model in apps.get_models()
            if getattr(model, "DOCTYPE", None)
        ),
        key=doctype_of,
    )
    for model in source_models:
        source_doctype = doctype_of(model)
        if source_doctype in IGNORE_LINKS_ON_DELETE:
            continue
        parent_fk, foreign_keys, dynamic_pairs = _source_spec(model, target_model)
        condition = Q()
        for field in foreign_keys:
            condition |= Q(**{f"{field.name}__in": target_names})
        for doctype_field, name_field in dynamic_pairs:
            condition |= Q(
                **{
                    doctype_field: target_doctype,
                    f"{name_field}__in": target_names,
                }
            )
        if not condition.children:
            continue

        child_table = is_child_table(model)
        rows = model._default_manager.filter(condition)
        if child_table:
            if parent_fk is not None:
                rows = rows.select_related(parent_fk.name)
        else:
            rules = _rules_or_raise(model)
            list_rule = rules.list_rule(user)
            if list_rule is not None:
                rows = rows.filter(list_rule)
        rows = list(rows)

        def collect_child(sort_key, row):
            if parent_fk is not None:
                parent = getattr(row, parent_fk.name, None)
                if parent is not None:
                    tagged.append(
                        (sort_key, doctype_of(type(parent)), parent, True)
                    )
                return
            parent_doctype = str(getattr(row, "parenttype", "") or "")
            parent_name = str(getattr(row, "parent", "") or "")
            parent_model = model_for_doctype(parent_doctype)
            if parent_model is not None and parent_name:
                polymorphic[parent_model].add(parent_name)
                polymorphic_candidates.append(
                    (sort_key, parent_model, parent_name)
                )

        # Phase 1: FK fields, in doctype and model-field order. Deliberately do
        # not impose row ordering: the old queries did not have order_by().
        for field_index, field in enumerate(foreign_keys):
            matching = [
                row
                for row in rows
                if str(getattr(row, field.attname, "")) in target_names
            ]
            for row_position, row in enumerate(matching):
                sort_key = (1, source_doctype, field_index, row_position)
                if child_table:
                    collect_child(sort_key, row)
                else:
                    tagged.append((sort_key, source_doctype, row, False))

        if not child_table:
            # Phase 2: the one conventional parent reference pair (SA2b).
            for field_index, (doctype_field, name_field) in enumerate(
                dynamic_pairs
            ):
                matching = [
                    row
                    for row in rows
                    if str(getattr(row, doctype_field, "")) == target_doctype
                    and str(getattr(row, name_field, "")) in target_names
                ]
                for row_position, row in enumerate(matching):
                    sort_key = (
                        2,
                        source_doctype,
                        field_index,
                        row_position,
                    )
                    tagged.append((sort_key, source_doctype, row, False))
            continue

        # Phase 3: child Dynamic Link fields. The old query explicitly orders
        # each field's rows by primary key.
        concrete = {field.name for field in model._meta.concrete_fields}
        for field_index, (doctype_field, name_field) in enumerate(dynamic_pairs):
            matching = [
                row
                for row in rows
                if str(getattr(row, doctype_field, "")) == target_doctype
                and str(getattr(row, name_field, "")) in target_names
                and not ("docstatus" in concrete and row.docstatus == 2)
                and str(getattr(row, "parenttype", "") or "")
                not in IGNORE_LINKS_ON_DELETE
            ]
            for row_position, row in enumerate(
                sorted(matching, key=lambda item: item.pk)
            ):
                collect_child(
                    (3, source_doctype, field_index, row_position), row
                )

    polymorphic_parents = {}
    for parent_model, parent_names in polymorphic.items():
        polymorphic_parents[parent_model] = {
            str(parent.pk): parent
            for parent in parent_model._default_manager.filter(pk__in=parent_names)
        }
    for sort_key, parent_model, parent_name in polymorphic_candidates:
        parent = polymorphic_parents[parent_model].get(parent_name)
        if parent is not None:
            tagged.append((sort_key, doctype_of(parent_model), parent, True))

    visible = []
    for sort_key, parent_doctype, parent, via_child in tagged:
        parent_model = type(parent)
        if (
            via_child
            and parent_model is target_model
            and str(parent.pk) in target_names
        ):
            continue
        if via_child:
            rules = _rules_or_raise(parent_model)
            if rules.has_object_rule(user, parent, "read") is False:
                continue
        visible.append((sort_key, parent_doctype, parent))

    visible.sort(key=lambda candidate: candidate[0])
    seen = set()
    found = []
    for _, source_doctype, instance in visible:
        key = (source_doctype, str(instance.pk))
        if key not in seen:
            seen.add(key)
            found.append((source_doctype, instance))
    return found


def _linked_title(instance):
    hook = getattr(type(instance), "linked_document_title", None)
    if callable(hook):
        return str(hook(instance))
    return str(getattr(instance, "title", None) or instance.pk)


def _clear_reference(instance):
    hook = getattr(type(instance), "clear_linked_document_reference", None)
    if callable(hook):
        hook(instance)
        return
    concrete = {field.name for field in type(instance)._meta.concrete_fields}
    updates = {
        fieldname: ""
        for fieldname in (
            "reference_doctype",
            "reference_docname",
            "reference_name",
        )
        if fieldname in concrete
    }
    if updates:
        type(instance)._default_manager.filter(pk=instance.pk).update(**updates)


def _clear_link_fields(instance, target_model, target_name):
    updates = {}
    parent_fk = _parent_fk(type(instance)) if is_child_table(type(instance)) else None
    for field in type(instance)._meta.concrete_fields:
        if (
            isinstance(field, (models.ForeignKey, models.OneToOneField))
            and field is not parent_fk
            and field.related_model is target_model
            and str(getattr(instance, field.attname, "")) == str(target_name)
        ):
            updates[field.name] = None
    if updates:
        type(instance)._default_manager.filter(pk=instance.pk).update(**updates)


def _clear_contact(instance):
    concrete = {field.name for field in type(instance)._meta.concrete_fields}
    if "contact" in concrete:
        type(instance)._default_manager.filter(pk=instance.pk).update(contact=None)
    contacts = getattr(instance, "contacts", None)
    if contacts is not None:
        contacts.all().delete()


class LinkedDocumentsMixin:
    """Add the delete-dialog list and unlink action to a document resource."""

    @action(detail=True, methods=("get", "post"), url_path="linked-documents")
    def linked_documents(self, request, *args, **kwargs):
        if request.method == "GET":
            source = self._object_by_name("read")
            results = {}
            for source_doctype, instance in linked_documents(
                self.document_model, [source.pk], request.user
            ):
                name = str(instance.pk)
                results[name] = {
                    "doc": source_doctype,
                    "title": _linked_title(instance),
                    "reference_docname": name,
                    "reference_doctype": source_doctype,
                }
            return Response(Envelope(list(results.values()), "message"))

        inputs = build_payload(request)
        items = parse_json_param(inputs.get("items"), []) or []
        remove_contact = bool(inputs.get("remove_contact", False))
        delete = bool(inputs.get("delete", False))
        target_name = self.kwargs[self.lookup_url_kwarg or self.lookup_field]

        for item in items:
            if not isinstance(item, dict):
                continue
            item_doctype = item.get("doctype")
            item_name = item.get("docname")
            if not item_doctype or not item_name:
                continue
            model = model_for_doctype(item_doctype)
            rules = rules_for(model) if model is not None else None
            if model is None or rules is None:
                continue
            instance = model._default_manager.filter(pk=item_name).first()
            if instance is None:
                continue
            if rules.has_object_rule(request.user, instance, "write") is False:
                continue

            if remove_contact:
                _clear_contact(instance)
            else:
                _clear_reference(instance)
                _clear_link_fields(instance, self.document_model, target_name)
            if delete:
                try:
                    check_dynamic_links(instance)
                except LinkExistsError:
                    continue
                instance.delete()

        return Response(Envelope("success", "message"))
