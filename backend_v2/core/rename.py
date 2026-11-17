"""Rename a document in place while preserving every followed reference."""

from __future__ import annotations

from django.apps import apps
from django.db import transaction
from django.db.models.fields.reverse_related import ForeignObjectRel

from core import children
from core.delete import _dynamic_link_declarations
from core.doctypes import doctype_of


def _copy_under(original, new_name: str):
    model = type(original)
    values = {
        field.attname: getattr(original, field.attname)
        for field in model._meta.concrete_fields
    }
    values[model._meta.pk.attname] = new_name
    return model(**values)


def _repoint_foreign_keys(model, old: str, new: str) -> None:
    for relation in model._meta.get_fields(include_hidden=True):
        if not isinstance(relation, ForeignObjectRel):
            continue
        field = relation.field
        if not (field.many_to_one or field.one_to_one):
            continue
        relation.related_model._default_manager.filter(
            **{field.attname: old}
        ).update(**{field.attname: new})


def _repoint_child_parents(model, old: str, new: str) -> None:
    doctype = doctype_of(model)
    for spec in children.child_table_specs(model).values():
        if not spec["polymorphic"]:
            continue
        spec["model"]._default_manager.filter(
            parenttype=doctype, parent=old
        ).update(parent=new)


def _repoint_dynamic_links(doctype: str, old: str, new: str) -> None:
    for other_model in apps.get_models():
        for doctype_field, name_field in _dynamic_link_declarations(other_model):
            other_model._default_manager.filter(
                **{doctype_field: doctype, name_field: old}
            ).update(**{name_field: new})


def _repoint_text_links(model, old: str, new: str) -> None:
    # PE-5 (approved 17 Nov 2026): the old backend left these dangling.
    for other_model in apps.get_models():
        text_links = getattr(other_model, "TEXT_LINK_FIELDS", None) or {}
        for fieldname, (target_label, _) in text_links.items():
            # Resolved as core.links resolves it, so the label's case does not matter.
            if apps.get_model(target_label) is not model:
                continue
            other_model._default_manager.filter(**{fieldname: old}).update(
                **{fieldname: new}
            )


def _unique_columns(model) -> list:
    fields = []
    by_name = {field.name: field for field in model._meta.concrete_fields}
    for field in model._meta.concrete_fields:
        if field.unique and not field.primary_key:
            fields.append(field)
    for constraint in model._meta.constraints:
        for fieldname in getattr(constraint, "fields", ()) or ():
            if fieldname in by_name:
                fields.append(by_name[fieldname])
    for group in model._meta.unique_together:
        for fieldname in group:
            if fieldname in by_name:
                fields.append(by_name[fieldname])
    return list(dict.fromkeys(field for field in fields if not field.primary_key))


def _blank_for(field):
    if field.null:
        return None
    if getattr(field, "empty_strings_allowed", False) and not field.is_relation:
        return ""
    raise ValueError(field.name)


def rename_document(model, old: str, new: str) -> str:
    """Copy ``old`` under ``new``, repoint references, then remove ``old``."""

    doctype = doctype_of(model)
    with transaction.atomic():
        original = model._default_manager.select_for_update().get(pk=old)
        copy = _copy_under(original, new)
        parked = {}
        for field in _unique_columns(model):
            value = getattr(copy, field.attname)
            if value in (None, ""):
                continue
            try:
                setattr(copy, field.attname, _blank_for(field))
            except ValueError:
                continue
            parked[field.attname] = value

        model._default_manager.bulk_create([copy])
        _repoint_foreign_keys(model, old, new)
        _repoint_child_parents(model, old, new)
        _repoint_dynamic_links(doctype, old, new)
        _repoint_text_links(model, old, new)
        model._default_manager.filter(pk=old).delete()
        if parked:
            model._default_manager.filter(pk=new).update(**parked)
    return new
