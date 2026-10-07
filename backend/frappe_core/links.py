"""Link validation for the Link fields this port stores as text.

A Link whose target doctype was modelled when the column was written is a foreign key,
and the database and the serializer already refuse a value that names nothing. A few
Links are plain text columns instead, because their target did not exist here at the
time: ``salutation`` and ``gender`` on a contact, a lead and a deal. Once the target is
modelled, upstream's rule applies to them as it does to every Link.

``Document._validate_links`` (``frappe/model/document.py``) runs on each save and
refuses one whose Link names no document: ``Could not find <Label>: <value>``, or
``Could not find Row #<idx>: <Label>: <value>`` for a child row
(``base_document.py:1040-1054``), as ``LinkValidationError``. On MariaDB the lookup is
case-insensitive and the value is rewritten to the stored spelling, so ``mr`` is saved
as ``Mr``; that is reproduced here, since the same typed value must not be accepted on
one database and refused on the other.

Which fields: whatever the doctype's metadata calls a Link, whose target is a registered
doctype, and whose column on the model is not a relation. Nothing is listed by hand, so
a text Link becomes validated the day its target is ported (docs/FINDINGS.md 66).
"""

from __future__ import annotations

from frappe_core.exceptions import LinkValidationError


def text_link_fields(model) -> list[tuple[str, str, str]]:
    """``(fieldname, target doctype, label)`` for each text column that is a Link."""
    from frappe_core import field_meta, registry

    doctype = getattr(model, "get_doctype", lambda: None)()
    if not doctype or not registry.has_doctype(doctype):
        return []
    found = []
    for field in field_meta.get_fields(doctype):
        if field.get("fieldtype") != "Link":
            continue
        target, fieldname = field.get("options"), field.get("fieldname")
        if not target or not fieldname or not registry.has_doctype(target):
            continue
        try:
            column = model._meta.get_field(fieldname)
        except Exception:  # noqa: BLE001 - metadata may name a field the model lacks
            continue
        if column.is_relation or not getattr(column, "concrete", False):
            continue
        found.append((fieldname, target, str(field.get("label") or fieldname)))
    return found


def validate_text_links(instance) -> None:
    """Refuse a save whose text Link names nothing; normalise a case-only difference."""
    from frappe_core import registry

    missing: list[str] = []
    for fieldname, target, label in text_link_fields(type(instance)):
        value = getattr(instance, fieldname, None)
        if value in (None, ""):
            continue
        manager = registry.get_model(target)._default_manager
        if manager.filter(pk=value).exists():
            continue
        spellings = list(manager.filter(pk__iexact=str(value)).values_list("pk", flat=True)[:2])
        if len(spellings) == 1:
            setattr(instance, fieldname, spellings[0])
            continue
        if getattr(instance, "parentfield", None):
            missing.append(f"Row #{getattr(instance, 'idx', 0)}: {label}: {value}")
        else:
            missing.append(f"{label}: {value}")
    if missing:
        raise LinkValidationError("Could not find " + ", ".join(missing))
