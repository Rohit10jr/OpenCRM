"""Declared child tables, read inline and replaced wholesale on write."""

from __future__ import annotations

import contextvars
from collections import Counter
from contextlib import contextmanager

from django.apps import apps
from django.db import models, transaction
from django.db.models.signals import post_delete
from core.doctypes import doctype_of, is_child_table, model_for_doctype
from core.exceptions import LinkValidationError, MandatoryError
from core.field_access import hidden_from, readonly_fields, unwritable_by
from core.translate import _


def _model(label: str):
    try:
        model = apps.get_model(label)
    except (LookupError, ValueError):
        model = None
    if model is None:
        raise TypeError(_("Unknown child model {0}").format(label))
    if not is_child_table(model):
        raise TypeError(_("{0} is not declared as a child table").format(label))
    return model


def child_fields(child_model) -> tuple[str, ...]:
    """Return the child row's explicit wire/write field policy."""
    declared = getattr(child_model, "CHILD_FIELDS", None)
    if declared is None:
        raise TypeError(
            _("Child table {0} must declare CHILD_FIELDS").format(
                child_model._meta.label
            )
        )
    fields = tuple(declared)
    concrete = {
        field.name
        for field in child_model._meta.get_fields()
        if getattr(field, "concrete", False)
    }
    unknown = [fieldname for fieldname in fields if fieldname not in concrete]
    if unknown:
        raise TypeError(
            _("Child table {0} declares unknown CHILD_FIELDS: {1}").format(
                child_model._meta.label, ", ".join(unknown)
            )
        )
    return fields


def child_table_specs(
    parent_model, declared: dict[str, str | tuple[str, str]] | None = None
) -> dict:
    """Resolve the serializer's FK children and the model's polymorphic children."""
    specs = {}
    for fieldname, declaration in (declared or {}).items():
        if isinstance(declaration, tuple):
            label, parent_link = declaration
        else:
            label, parent_link = declaration, None
        child_model = _model(label)
        child_fields(child_model)
        links = [
            field
            for field in child_model._meta.get_fields()
            if isinstance(field, models.ForeignKey)
            and field.related_model is parent_model
        ]
        if parent_link is not None:
            matching_links = [field for field in links if field.name == parent_link]
            if len(matching_links) != 1:
                raise TypeError(
                    _("{0}.{1} is not a link to {2}").format(
                        label, parent_link, parent_model._meta.label
                    )
                )
            links = matching_links
        elif len(links) > 1:
            choices = ", ".join(field.name for field in links)
            raise TypeError(
                _(
                    "Child table {0} has multiple links to {1}: {2}. "
                    "Declare one as (\"{0}\", \"<field_name>\") in CHILD_TABLES."
                ).format(label, parent_model._meta.label, choices)
            )
        if len(links) != 1:
            raise TypeError(
                _("Child table {0} must have exactly one link to {1}").format(
                    label, parent_model._meta.label
                )
            )
        specs[fieldname] = {
            "model": child_model,
            "fk": links[0].name,
            "polymorphic": False,
        }

    polymorphic = getattr(parent_model, "POLYMORPHIC_CHILD_TABLES", {}) or {}
    for fieldname, label in polymorphic.items():
        child_model = _model(label)
        child_fields(child_model)
        specs[fieldname] = {
            "model": child_model,
            "fk": None,
            "polymorphic": True,
        }

    counts = Counter(spec["model"] for spec in specs.values())
    for fieldname, spec in specs.items():
        if counts[spec["model"]] > 1:
            spec["distinguish_parentfield"] = True
            spec["fieldname"] = fieldname
    return specs


def read_children(instance, spec: dict) -> list:
    if spec["polymorphic"]:
        filters = {
            "parent": str(instance.pk),
            "parenttype": doctype_of(type(instance)),
        }
        if spec.get("distinguish_parentfield"):
            filters["parentfield"] = spec["fieldname"]
    else:
        filters = {spec["fk"]: instance}
    return list(spec["model"]._default_manager.filter(**filters).order_by("idx"))


_STAMPS = frozenset(
    {
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
        "parent",
        "parenttype",
        "parentfield",
    }
)


def _label(field) -> str:
    label = str(field.verbose_name)
    return label.title() if label == field.name.replace("_", " ") else label


def _is_mandatory(field) -> bool:
    return not (
        field.name in _STAMPS
        or field.primary_key
        or not field.editable
        or field.null
        or field.blank
        or field.has_default()
    )


def _is_link(field) -> bool:
    return field.is_relation and (field.many_to_one or field.one_to_one)


def prepare_rows(
    child_model,
    rows: list[dict],
    *,
    fieldname: str,
    parent_field: str | None = None,
    user=None,
) -> list[dict]:
    """Validate links and mandatory values, then return model-ready row payloads."""
    allowed = set(child_fields(child_model))
    fields = [
        field
        for field in child_model._meta.get_fields()
        if getattr(field, "concrete", False) and field.name in allowed
    ]
    blocked = (
        hidden_from(child_model, user)
        | readonly_fields(child_model)
        | unwritable_by(child_model, user)
        | {
            "name",
            "owner",
            "modified_by",
            "creation",
            "modified",
            "_assign",
            "_liked_by",
            "_comments",
            "_user_tags",
        }
    )
    writable_fields = [field for field in fields if field.name not in blocked]
    accepted = {field.name for field in writable_fields} | {
        field.attname for field in writable_fields
    }
    missing_links = []
    missing_values = []
    payloads = []

    for index, row in enumerate(rows or [], start=1):
        payload = {
            key: value
            for key, value in (row or {}).items()
            if key in accepted and key != "name"
        }
        if parent_field:
            payload.pop(parent_field, None)
            payload.pop(f"{parent_field}_id", None)

        for field in writable_fields:
            if not _is_link(field) or field.name not in payload:
                continue
            value = payload.pop(field.name)
            if value is None or value == "":
                payload[field.attname] = None
            elif hasattr(value, "pk"):
                payload[field.attname] = value.pk
            elif field.related_model._default_manager.filter(pk=value).exists():
                payload[field.attname] = value
            else:
                missing_links.append(
                    _("Row #{0}: {1}: {2}").format(index, _label(field), value)
                )

        for field in writable_fields:
            if field.name == parent_field or not _is_mandatory(field):
                continue
            value = payload.get(field.attname if _is_link(field) else field.name)
            if value is None or value == "":
                missing_values.append(
                    _(
                        "Error: <strong>{0}</strong> Row #{1}: "
                        "Value missing for: {2}"
                    ).format(doctype_of(child_model), index, _label(field))
                )
        payload["idx"] = index
        payload.setdefault("parentfield", fieldname)
        payloads.append(payload)

    if missing_links:
        raise LinkValidationError(
            _("Could not find {0}").format(", ".join(missing_links))
        )
    if missing_values:
        raise MandatoryError(messages=missing_values)
    return payloads


_REPLACING = contextvars.ContextVar("core.children.replacing", default=False)


def replacing_children() -> bool:
    return _REPLACING.get()


@transaction.atomic
def replace_children(
    instance, fieldname: str, spec: dict, rows: list[dict], *, user
) -> None:
    child_model = spec["model"]
    parent_doctype = doctype_of(type(instance))
    if spec["polymorphic"]:
        base_filter = {"parent": str(instance.pk), "parenttype": parent_doctype}
    else:
        base_filter = {spec["fk"]: instance}
    if spec.get("distinguish_parentfield"):
        base_filter["parentfield"] = fieldname

    payloads = prepare_rows(
        child_model,
        rows,
        fieldname=fieldname,
        parent_field=spec["fk"],
        user=user,
    )
    token = _REPLACING.set(True)
    try:
        child_model._default_manager.filter(**base_filter).delete()
        for payload in payloads:
            payload.update(base_filter)
            payload.setdefault("parenttype", parent_doctype)
            row = child_model(**payload)
            row.save(user=user)
    finally:
        _REPLACING.reset(token)


def delete_polymorphic_children(instance) -> int:
    removed = 0
    declarations = getattr(type(instance), "POLYMORPHIC_CHILD_TABLES", {}) or {}
    for child_model in {_model(label) for label in declarations.values()}:
        count, _ = child_model._default_manager.filter(
            parent=str(instance.pk), parenttype=doctype_of(type(instance))
        ).delete()
        removed += count
    return removed


def delete_polymorphic_children_batch(model, names: list[str]) -> int:
    """Delete each declared polymorphic child table once for a parent batch."""
    removed = 0
    declarations = getattr(model, "POLYMORPHIC_CHILD_TABLES", {}) or {}
    for child_model in {_model(label) for label in declarations.values()}:
        count, _ = child_model._default_manager.filter(
            parent__in=names, parenttype=doctype_of(model)
        ).delete()
        removed += count
    return removed


# ACTIVITIES extends this table with ToDo, Comment, File, and Communication when those
# models exist. Communication uses ``clear``; the other reference rows use ``delete``.
_REFERENCE_CLEANUP: tuple[tuple[str, str, str, str], ...] = (
    ("Version", "ref_doctype", "docname", "delete"),
)

REFERENCE_DOCTYPES = frozenset(row[0] for row in _REFERENCE_CLEANUP)
_REFERENCES_HANDLED = contextvars.ContextVar(
    "core.children.references_handled", default=False
)


def delete_references_batch(doctype: str, names: list[str]) -> int:
    """Remove reference rows for all supplied document names in one batch per type."""
    if not names:
        return 0
    touched = 0
    for reference_doctype, doctype_column, name_column, action in _REFERENCE_CLEANUP:
        reference_model = model_for_doctype(reference_doctype)
        if reference_model is None:
            continue
        rows = reference_model._default_manager.filter(
            **{doctype_column: doctype, f"{name_column}__in": names}
        )
        if action == "delete":
            count, _ = rows.delete()
        else:
            count = rows.update(**{doctype_column: "", name_column: ""})
        touched += count
    return touched


def delete_references(instance) -> int:
    return delete_references_batch(
        doctype_of(type(instance)), [str(instance.pk)]
    )


@contextmanager
def references_handled():
    """Stand down per-row cleanup when a caller already cleaned a whole batch."""
    token = _REFERENCES_HANDLED.set(True)
    try:
        yield
    finally:
        _REFERENCES_HANDLED.reset(token)


def _on_parent_delete(sender, instance, **kwargs):
    if _REFERENCES_HANDLED.get():
        return
    delete_polymorphic_children(instance)
    delete_references(instance)


def connect_cascades() -> None:
    """Wire document cleanup without wiring the reference doctypes themselves."""
    from core.models import BaseDocument

    for model in apps.get_models():
        if (
            isinstance(model, type)
            and issubclass(model, BaseDocument)
            and not model._meta.abstract
            and not is_child_table(model)
            and doctype_of(model) not in REFERENCE_DOCTYPES
        ):
            post_delete.connect(
                _on_parent_delete,
                sender=model,
                dispatch_uid=f"core.children.cascade.{model._meta.label}",
            )
