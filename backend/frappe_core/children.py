"""Child tables, serialised inline and replaced on write.

PHASE_1_MODELS.md section 3: "Serialise nested inside the parent; the frontend expects
them inline" and "Writing a parent replaces its child rows wholesale (Frappe semantics)
- not a merge."

Two shapes exist in this port, because the source has two:

* **Single-parent** children carry a real FK (``CRM Contacts`` -> ``CRM Deal``,
  ``CRM Holiday`` -> ``CRM Holiday List``, ...). Discovered automatically from the
  reverse relation.
* **Multi-parent** children cannot (``CRM Products``, ``CRM Status Change Log`` and
  ``CRM Rolling Response Time`` are each embedded by *both* ``CRM Lead`` and
  ``CRM Deal``). Frappe models these with a ``parent`` string plus ``parenttype``; a
  parent declares them explicitly::

      class CRMLead(BaseDocument):
          POLYMORPHIC_CHILD_TABLES = {"products": "CRM Products"}

Both shapes serialise identically on the wire, which is what matters to the frontend.
"""

from __future__ import annotations

from django.db import transaction

from frappe_core import registry


def discover_child_tables(model) -> dict[str, dict]:
    """``{parent_fieldname: {"doctype", "model", "fk", "polymorphic"}}``."""
    found: dict[str, dict] = {}

    # 1. Reverse FK relations whose target is a registered child table.
    for relation in model._meta.related_objects:
        related_model = relation.related_model
        doctype = getattr(related_model, "get_doctype", lambda: None)()
        if not doctype or not registry.has_doctype(doctype):
            continue
        if not registry.get_entry(doctype).is_child_table:
            continue
        fieldname = relation.get_accessor_name()
        found[fieldname] = {
            "doctype": doctype,
            "model": related_model,
            "fk": relation.field.name,
            "polymorphic": False,
        }

    # 2. Explicitly declared multi-parent children.
    for fieldname, doctype in (getattr(model, "POLYMORPHIC_CHILD_TABLES", {}) or {}).items():
        if not registry.has_doctype(doctype):
            continue
        found[fieldname] = {
            "doctype": doctype,
            "model": registry.get_model(doctype),
            "fk": None,
            "polymorphic": True,
        }

    return found


def read_children(instance, spec: dict) -> list:
    child_model = spec["model"]
    if spec["polymorphic"]:
        queryset = child_model._default_manager.filter(
            parenttype=type(instance).get_doctype(), parent=str(instance.pk)
        )
    else:
        queryset = child_model._default_manager.filter(**{spec["fk"]: instance})
    return list(queryset.order_by("idx"))


@transaction.atomic
def replace_children(instance, fieldname: str, spec: dict, rows: list[dict]) -> None:
    """Delete the parent's existing rows and recreate them from ``rows``.

    Wholesale replacement, not a merge - Frappe's semantics. ``idx`` is assigned from
    list position, which is what orders a child table in the UI.
    """
    child_model = spec["model"]
    parent_doctype = type(instance).get_doctype()

    if spec["polymorphic"]:
        base_filter = {"parenttype": parent_doctype, "parent": str(instance.pk)}
    else:
        base_filter = {spec["fk"]: instance}

    child_model._default_manager.filter(**base_filter).delete()

    # Both the field name and its attname, so a caller may pass either ``log_owner``
    # (an instance) or ``log_owner_id`` (a raw PK). Without the attname, FK values
    # supplied by PK were silently dropped and the column came back NULL.
    concrete = set()
    for f in child_model._meta.get_fields():
        if getattr(f, "concrete", False):
            concrete.add(f.name)
            concrete.add(getattr(f, "attname", f.name))
    for index, row in enumerate(rows or [], start=1):
        payload = {k: v for k, v in (row or {}).items() if k in concrete and k != "name"}
        payload.update(base_filter)
        payload.setdefault("parenttype", parent_doctype)
        payload.setdefault("parentfield", fieldname)
        payload["idx"] = index
        child_model._default_manager.create(**payload)
