"""Rename a document in place: ``frappe/model/rename_doc.py`` for a CRM install.

Upstream changes the primary key and then repoints everything that named the old
value: every Link field in every doctype (``update_link_field_values``), every Dynamic
Link (``rename_dynamic_links``: Comment, Communication, ToDo, Notification and the
rest, matched on their doctype column), the ``parent`` of child rows
(``rename_parent_and_child``), attachments (``update_attachments``) and the version
history (``rename_versions``). The document keeps its rows, its timeline and its place
on every other document.

Django cannot change a primary key with ``save()``; the row has to be inserted under
the new name and the old one deleted. Done in that order with every reference
repointed in between, inside one transaction, that is the same operation. The copy is
written with ``bulk_create`` so no save hook, naming strategy or version capture runs
for what is not a new document. (An earlier port saved the copy and deleted the
original without repointing anything: a document any row protected could not be
renamed, and one whose rows cascaded lost them - FINDINGS.md 13.)
"""

from __future__ import annotations

from django.db import transaction
from django.db.models.fields.reverse_related import ForeignObjectRel

from frappe_core import children, registry

#: The column pairs the port's models use for a Dynamic Link - a doctype column and
#: the name column beside it. Upstream reads these off the DocType JSON
#: (``get_dynamic_link_map``); here they are the spellings the models declare.
DYNAMIC_LINK_PAIRS: tuple[tuple[str, str], ...] = (
    ("reference_doctype", "reference_name"),
    ("reference_doctype", "reference_docname"),
    ("reference_type", "reference_name"),
    ("attached_to_doctype", "attached_to_name"),
    ("ref_doctype", "docname"),
    ("link_doctype", "link_name"),
)


def _copy_under(original, new_name: str):
    model = type(original)
    values = {f.attname: getattr(original, f.attname) for f in model._meta.concrete_fields}
    values[model._meta.pk.attname] = new_name
    return model(**values)


def _repoint_foreign_keys(model, old: str, new: str) -> None:
    """Every foreign key in the schema that points at ``model`` - including the hidden
    ones on many-to-many through tables - moves from ``old`` to ``new``. PROTECT and
    CASCADE alike: nothing is deleted while they still point at the old row."""
    for rel in model._meta.get_fields(include_hidden=True):
        if not isinstance(rel, ForeignObjectRel):
            continue
        field = rel.field
        if not (field.many_to_one or field.one_to_one):
            continue
        rel.related_model._default_manager.filter(**{field.attname: old}).update(
            **{field.attname: new}
        )


def _repoint_child_parents(model, doctype: str, old: str, new: str) -> None:
    """Multi-parent child rows carry the parent's name as a string."""
    for spec in children.discover_child_tables(model).values():
        if spec["polymorphic"]:
            spec["model"]._default_manager.filter(parenttype=doctype, parent=old).update(
                parent=new
            )


def _repoint_dynamic_links(doctype: str, old: str, new: str) -> None:
    for other in registry.all_doctypes():
        other_model = registry.get_model(other)
        columns = {f.name for f in other_model._meta.concrete_fields}
        for doctype_column, name_column in DYNAMIC_LINK_PAIRS:
            if doctype_column in columns and name_column in columns:
                other_model._default_manager.filter(
                    **{doctype_column: doctype, name_column: old}
                ).update(**{name_column: new})


def rename_document(doctype: str, old: str, new: str) -> str:
    """Rename ``old`` to ``new`` and repoint every reference. The caller has already
    validated the names and the permission, as ``validate_rename`` does upstream."""
    model = registry.get_model(doctype)
    with transaction.atomic():
        original = model._default_manager.select_for_update().get(pk=old)
        model._default_manager.bulk_create([_copy_under(original, new)])
        _repoint_foreign_keys(model, old, new)
        _repoint_child_parents(model, doctype, old, new)
        _repoint_dynamic_links(doctype, old, new)
        model._default_manager.filter(pk=old).delete()
    return new
