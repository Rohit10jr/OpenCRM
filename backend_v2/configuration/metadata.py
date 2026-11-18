"""Field metadata answers: `getdoctype` and what a doctype is for them
(specs/CONFIGURATION.md section 4.5; temp A-35).

Ported from `backend/crm_app/api/form_load.py`. A doctype exists here when a model
declares `DOCTYPE` and is served by a resource (a singleton counts), or is a child table
of one: the existing derived lookups, no registry. A withheld doctype is not found
(PE-14); a child table answers `getdoctype` only (PE-15); every answer lists only the
fields the caller may read (PE-16).
"""

from __future__ import annotations

import functools

from django.apps import apps

from configuration import field_meta
from core.doctypes import declared_doctypes, is_child_table, is_single
from core.exceptions import DoesNotExistError
from core.field_access import hidden_from
from core.resources import PRODUCTION_URLCONF, routed_rule_map, routed_viewsets

TABLE_FIELDTYPES = ("Table", "Table MultiSelect")

#: DocType properties every meta document carries, with a DocType row's value when unset
#: (old `form_load.py:41-66`): the generator drops empty and zero values from the file.
DOCTYPE_PROPERTY_DEFAULTS = {
    "istable": 0,
    "issingle": 0,
    "autoname": None,
    "title_field": None,
    "editable_grid": 0,
    "translated_doctype": 0,
    "sort_field": "modified",
    "sort_order": "DESC",
    "is_submittable": 0,
}


@functools.lru_cache(maxsize=1)
def _served_children() -> frozenset:
    """The child models of every served resource's serializer `CHILD_TABLES`."""
    children = set()
    for viewset in routed_viewsets(PRODUCTION_URLCONF):
        serializer = getattr(viewset, "serializer_class", None)
        for model_label, _fk in (getattr(serializer, "CHILD_TABLES", {}) or {}).values():
            children.add(apps.get_model(model_label))
    return frozenset(children)


def served_model(doctype):
    """The model for `doctype` when it is served or a served child, else `None`."""
    model = declared_doctypes().get(str(doctype))
    if model is None:
        return None
    if model in routed_rule_map() or model in _served_children():
        return model
    return None


def model_or_404(doctype, *, child_allowed: bool):
    """The served model, or 404 "DocType X not found": for an unknown or withheld doctype
    (PE-14), and for a child table where `child_allowed` is false (PE-15)."""
    model = served_model(doctype)
    if model is None or (is_child_table(model) and not child_allowed):
        raise DoesNotExistError(f"DocType {doctype} not found")
    return model


def readable_fields(model, fields: list[dict], user) -> list[dict]:
    """PE-16: the fields the caller may read, each a copy; `idx` is left as it was."""
    hidden = hidden_from(model, user)
    return [dict(field) for field in fields if field.get("fieldname") not in hidden]


def _meta_document(doctype: str, model, user) -> dict:
    """One bundle entry: the DocType's properties, then its readable fields with their
    1-based `idx` in declaration order (old `form_load.py:69-90`)."""
    meta = dict(DOCTYPE_PROPERTY_DEFAULTS)
    meta["istable"] = 1 if is_child_table(model) else 0
    meta["issingle"] = 1 if is_single(model) else 0
    meta.update(field_meta.get_doctype_properties(doctype))
    meta["name"] = doctype
    numbered = [
        dict(field, idx=i) for i, field in enumerate(field_meta.get_fields(doctype), start=1)
    ]
    meta["fields"] = readable_fields(model, numbered, user)
    return meta


def get_meta_bundle(doctype: str, model, user) -> list[dict]:
    """`get_meta_bundle`: the doctype, then one meta per table field in field order;
    a child that does not exist here is left out (A-35)."""
    bundle = [_meta_document(doctype, model, user)]
    for field in bundle[0]["fields"]:
        if field.get("fieldtype") in TABLE_FIELDTYPES and field.get("options"):
            child = served_model(field["options"])
            if child is not None:
                bundle.append(_meta_document(field["options"], child, user))
    return bundle


def get_parent_dt(doctype: str, model) -> str | None:
    """`get_parent_dt`: the existing doctype embedding this child table, over the doctypes
    in sorted order so a child of two parents resolves the same way every time (old
    `form_load.py:109-141`); `None` for anything that is not a child table."""
    if not is_child_table(model):
        return None
    for candidate in sorted(declared_doctypes()):
        if candidate == doctype or served_model(candidate) is None:
            continue
        for field in field_meta.get_fields(candidate):
            if field.get("fieldtype") in TABLE_FIELDTYPES and field.get("options") == doctype:
                return candidate
    return None


def getdoctype(doctype, *, with_parent=False, user):
    """`frappe.desk.form.load.getdoctype` (old `form_load.py:151-196`). Answers
    `(docs, user_settings, parent_dt or None)`. `with_parent` on a child table answers the
    parent's bundle when the parent exists, else the child's own; `cached_timestamp` is
    the caller's to send and is ignored."""
    from configuration.user_settings import get_user_settings

    model = model_or_404(doctype, child_allowed=True)
    docs: list[dict] = []
    parent_dt = None
    if with_parent:
        parent_dt = get_parent_dt(doctype, model)
        if parent_dt:
            docs = get_meta_bundle(parent_dt, served_model(parent_dt), user)
    if not docs:
        docs = get_meta_bundle(doctype, model, user)
    return docs, get_user_settings(parent_dt or doctype, user=user), parent_dt
