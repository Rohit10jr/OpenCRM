"""Frappe field metadata — the port's ``frappe.get_meta(doctype).fields``.

Phase 4. This is what closes **C7**: phase 0's ``_frappe_fieldtype`` guessed the Frappe
fieldtype from the Django internal type, which is lossy in both directions —
``Long Text``/``Small Text``/``Text Editor`` all collapse to ``TextField``, and
``Duration``/``Rating`` are indistinguishable from ``IntegerField``/``FloatField``. The
allowlists in ``metadata.py`` are *defined* in terms of Frappe fieldtypes, so guessing
made them approximately right and impossible to verify.

The data comes from the DocType JSON, generated into
``crm_app/data/doctype_meta.json`` by ``scripts/generate_field_meta.py`` and committed.
``test_generated_field_meta_is_current`` regenerates and diffs, so it cannot drift.

**Layout fieldtypes are present here and only here.** ``Section Break``, ``Column Break``
and ``Tab Break`` are excluded from the models by design (PHASE_1_MODELS.md §2) but are
exactly what ``get_default_layout`` walks to build tabs and sections — they are layout
*data*, which is what PHASE_4_METADATA.md §2 said all along.

Doctypes with no JSON (the nine platform models — ``User``, ``Contact``, ``ToDo`` …)
fall back to deriving metadata from the Django model, which is all that was ever
available for them.
"""

from __future__ import annotations

import functools
import json
import pathlib

from frappe_core import registry

_DATA_FILE = (
    pathlib.Path(__file__).resolve().parent.parent / "crm_app" / "data" / "doctype_meta.json"
)

#: Frappe fieldtypes that carry no value — layout, and the two table types.
#: ``frappe/model/__init__.py:no_value_fields``.
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

#: The three that structure a form layout, in the order ``get_default_layout`` nests them.
LAYOUT_FIELDTYPES = ("Tab Break", "Section Break", "Column Break")


@functools.lru_cache(maxsize=1)
def _raw() -> dict:
    if not _DATA_FILE.exists():  # pragma: no cover - the file is committed
        return {}
    return json.loads(_DATA_FILE.read_text(encoding="utf-8"))


def has_meta(doctype: str) -> bool:
    return doctype in _raw()


def get_fields(doctype: str) -> list[dict]:
    """Every field the DocType declares, **in declaration order, layout breaks included**.

    Falls back to model introspection for the platform doctypes, which ship no JSON.
    """
    meta = _raw().get(doctype)
    if meta is not None:
        return meta["fields"]
    return _derive_from_model(doctype)


def get_doctype_properties(doctype: str) -> dict:
    """The doctype-level keys the generator kept - everything in the entry but ``fields``.

    ``istable``, ``issingle``, ``autoname``, ``title_field`` and whichever of
    ``editable_grid`` / ``sort_field`` / ``sort_order`` / ``naming_rule`` / ... the
    DocType JSON actually declares. ``{}`` for a doctype with no JSON.

    A fresh dict every call: ``getdoctype`` merges defaults into the result, and the
    value behind :func:`_raw` is a process-lifetime memo that must not be written to.
    """
    meta = _raw().get(doctype)
    if meta is None:
        return {}
    return {key: value for key, value in meta.items() if key != "fields"}


def get_value_fields(doctype: str) -> list[dict]:
    """``get_fields`` minus the layout and table types — what upstream calls a value field."""
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


def _derive_from_model(doctype: str) -> list[dict]:
    """Best effort for a doctype with no JSON — the nine platform models.

    This is phase 0's old guess, kept **only** where there is genuinely nothing better.
    It is not used for any CRM doctype.
    """
    if not registry.has_doctype(doctype):
        return []
    from frappe_core.metadata import _frappe_fieldtype, _link_target

    model = registry.get_model(doctype)
    # A text column that upstream declares as a Link (``Contact.salutation`` ->
    # ``Salutation``): the model names the target in ``LINK_FIELDS`` and the metadata
    # says Link, which is the shape the CRM doctypes already have for the same two
    # fields - a text column in the model, a Link in the JSON (FINDINGS.md 66).
    link_fields = getattr(model, "LINK_FIELDS", None) or {}
    fields = []
    for field in model._meta.get_fields():
        if not getattr(field, "concrete", False):
            continue
        fieldtype = _frappe_fieldtype(field)
        if getattr(field, "choices", None) and fieldtype == "Data":
            fieldtype = "Select"
        if field.name in link_fields:
            fieldtype = "Link"
        entry = {
            "fieldname": field.name,
            "fieldtype": fieldtype,
            "label": str(getattr(field, "verbose_name", field.name)),
        }
        options = link_fields.get(field.name) or _link_target(field)
        if options:
            entry["options"] = options
        elif fieldtype == "Select" and getattr(field, "choices", None):
            entry["options"] = "\n".join(str(c[0]) for c in field.choices)
        fields.append(entry)
    return fields


def clear_cache() -> None:
    """Test-only — drop the parsed-JSON memo."""
    _raw.cache_clear()
