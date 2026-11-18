"""Frappe field metadata: the port's `frappe.get_meta(doctype).fields`
(specs/CONFIGURATION.md section 4.5).

Ported from `backend/frappe_core/field_meta.py`. The data comes from the DocType JSON,
generated into `configuration/data/doctype_meta.json` by `scripts/generate_field_meta.py`
and committed; `tests/test_field_meta.py` regenerates and compares. It carries what the
models dropped: the Frappe fieldtypes (`Long Text`, `Duration`, `Rating`, ...) and the
layout rows (`Section Break`, `Column Break`, `Tab Break`) in declaration order.

A doctype with no entry in the file (a platform model: User, System Settings, ...) falls
back to its Django model, read through backend_v2's declarations (`TEXT_LINK_FIELDS`,
`DYNAMIC_LINK_FIELDS`, `ATTACH_FIELDS`). Nothing here filters by caller: the answers
that reach a client leave out what the caller may not read (PE-16) at their own routes.
"""

from __future__ import annotations

import functools
import json
import pathlib

from django.apps import apps
from django.db.models import ForeignKey, OneToOneField

from core.doctypes import doctype_of, model_for_doctype

_DATA_FILE = pathlib.Path(__file__).resolve().parent / "data" / "doctype_meta.json"

#: Frappe fieldtypes that carry no value: layout, and the two table types
#: (`frappe/model/__init__.py:no_value_fields`).
NO_VALUE_FIELDTYPES = frozenset(
    {
        "Section Break",
        "Column Break",
        "Tab Break",
        "HTML",
        "Table",
        "Table MultiSelect",
        "Button",
        "Image",
        "Fold",
        "Heading",
    }
)

#: The three that structure a form layout, in the order a default layout nests them.
LAYOUT_FIELDTYPES = ("Tab Break", "Section Break", "Column Break")

#: Best-effort Django -> Frappe fieldtype, for a model with no file entry (old
#: `frappe_core/metadata.py:175-194`).
_DJANGO_TO_FRAPPE = {
    "BooleanField": "Check",
    "CharField": "Data",
    "TextField": "Small Text",
    "EmailField": "Data",
    "IntegerField": "Int",
    "BigIntegerField": "Int",
    "SmallIntegerField": "Int",
    "PositiveIntegerField": "Int",
    "FloatField": "Float",
    "DecimalField": "Currency",
    "DateField": "Date",
    "DateTimeField": "Datetime",
    "ForeignKey": "Link",
    "OneToOneField": "Link",
    "JSONField": "JSON",
}


@functools.lru_cache(maxsize=1)
def _raw() -> dict:
    if not _DATA_FILE.exists():  # pragma: no cover - the file is committed
        return {}
    return json.loads(_DATA_FILE.read_text(encoding="utf-8"))


def has_meta(doctype: str) -> bool:
    return doctype in _raw()


def get_fields(doctype: str) -> list[dict]:
    """Every field the DocType declares, in declaration order, layout rows included;
    the model's fields for a doctype with no file entry. The file's lists are the memo:
    a caller that changes a field copies it first."""
    meta = _raw().get(doctype)
    if meta is not None:
        return meta["fields"]
    return _derive_from_model(doctype)


def get_doctype_properties(doctype: str) -> dict:
    """The doctype-level keys the generator kept, as a fresh dict; `{}` with no entry."""
    meta = _raw().get(doctype)
    if meta is None:
        return {}
    return {key: value for key, value in meta.items() if key != "fields"}


def get_value_fields(doctype: str) -> list[dict]:
    """`get_fields` minus the layout and table types: what upstream calls a value field."""
    return [f for f in get_fields(doctype) if f.get("fieldtype") not in NO_VALUE_FIELDTYPES]


def get_field(doctype: str, fieldname: str) -> dict | None:
    for field in get_fields(doctype):
        if field.get("fieldname") == fieldname:
            return field
    return None


def get_fieldtype(doctype: str, fieldname: str) -> str | None:
    field = get_field(doctype, fieldname)
    return field.get("fieldtype") if field else None


def get_title_field(doctype: str) -> str | None:
    meta = _raw().get(doctype)
    return meta.get("title_field") if meta else None


def select_options(field: dict) -> list[str]:
    """Frappe stores Select options as one newline-separated string."""
    if field.get("fieldtype") != "Select":
        return []
    return [o for o in (field.get("options") or "").split("\n")]


def frappe_fieldtype(field) -> str:
    """A Django field's Frappe fieldtype, best effort; a CharField with choices is a
    Select."""
    fieldtype = _DJANGO_TO_FRAPPE.get(field.get_internal_type(), "Data")
    if getattr(field, "choices", None) and fieldtype == "Data":
        return "Select"
    return fieldtype


def link_target(field) -> str | None:
    if isinstance(field, (ForeignKey, OneToOneField)):
        return doctype_of(field.related_model)
    return None


def _text_link_targets(model) -> dict[str, str]:
    """`TEXT_LINK_FIELDS` as {fieldname: target doctype} (old `LINK_FIELDS`)."""
    targets = {}
    for fieldname, (model_label, _label) in (getattr(model, "TEXT_LINK_FIELDS", {}) or {}).items():
        targets[fieldname] = doctype_of(apps.get_model(model_label))
    return targets


def _dynamic_link_targets(model) -> dict[str, str]:
    """`DYNAMIC_LINK_FIELDS` pairs (doctype column, name column) as {name column: doctype
    column} (old `DYNAMIC_LINK_FIELDS` dict)."""
    return {
        name_field: doctype_field
        for doctype_field, name_field in (getattr(model, "DYNAMIC_LINK_FIELDS", ()) or ())
    }


def _derive_from_model(doctype: str) -> list[dict]:
    """Best effort for a doctype with no file entry (old `field_meta.py:124-196`). No
    Table rows are made up from child tables: the old fallback added them only where a
    model declared `TABLE_FIELD_LABELS`, which none of this backend's models does."""
    model = model_for_doctype(doctype)
    if model is None:
        return []
    link_fields = _text_link_targets(model)
    dynamic_link_fields = _dynamic_link_targets(model)
    attach_fields = getattr(model, "ATTACH_FIELDS", ()) or ()
    fields = []
    for field in model._meta.get_fields():
        if not getattr(field, "concrete", False):
            continue
        fieldtype = frappe_fieldtype(field)
        if field.name in link_fields:
            fieldtype = "Link"
        elif field.name in dynamic_link_fields:
            fieldtype = "Dynamic Link"
        elif field.name in attach_fields:
            fieldtype = "Attach Image"
        entry = {
            "fieldname": field.name,
            "fieldtype": fieldtype,
            "label": str(getattr(field, "verbose_name", field.name)),
        }
        options = (
            link_fields.get(field.name)
            or dynamic_link_fields.get(field.name)
            or link_target(field)
        )
        if options:
            entry["options"] = options
        elif fieldtype == "Select" and getattr(field, "choices", None):
            entry["options"] = "\n".join(str(c[0]) for c in field.choices)
        fields.append(entry)
    return fields


def clear_cache() -> None:
    """Test-only: drop the parsed-file memo."""
    _raw.cache_clear()
