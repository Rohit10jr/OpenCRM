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
from frappe_core.exceptions import LinkValidationError, MandatoryError


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


#: Columns every child row carries that are never "mandatory" in Frappe's sense: the
#: BaseDocument stamps, the caches, and the parent pointers this module fills in.
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
    """The field's label for a message: Django's automatic ``verbose_name`` is the
    fieldname with spaces, lowercased, so it is title-cased back; an explicit one is
    used as written. (``rate`` -> "Rate", ``product_name`` -> "Product Name".)"""
    label = str(field.verbose_name)
    return label.title() if label == field.name.replace("_", " ") else label


def _is_mandatory(field) -> bool:
    """Frappe's ``reqd`` as the models encode it: a writable column that allows neither
    NULL nor blank and has no default."""
    if field.name in _STAMPS or field.primary_key or not field.editable:
        return False
    if field.null or field.blank:
        return False
    return not field.has_default()


def _is_link(field) -> bool:
    return field.is_relation and (field.many_to_one or field.one_to_one)


def prepare_rows(
    child_model, rows: list[dict], *, fieldname: str, parent_field: str | None = None
) -> list[dict]:
    """Validate ``rows`` the way upstream validates a document's child rows, and return
    the payloads to write.

    Two checks, in upstream's order (``document.py:_validate_links`` runs before
    ``_validate_mandatory``), each collecting every row's problems before raising:

    * A Link given **by name**, as every form sends it (``{"contact": "Ada Lovelace"}``),
      is moved to the column Django writes (``contact_id``) after confirming the target
      exists; a missing target is ``LinkValidationError`` with upstream's wording,
      ``Could not find Row #1: Contact: ZZ Nobody`` (base_document.py:790-796). Before
      this the dict reached ``create()`` untouched and Django raised a 500 (FINDINGS.md 9).
    * A mandatory column with no value is ``MandatoryError`` with upstream's wording for
      a child row, ``Error: <strong>CRM Products</strong> Row #1: Value missing for:
      Rate`` (base_document.py:747-756), one message per missing value. Before this the
      NOT NULL constraint fired and answered 409 "Duplicate" (FINDINGS.md 7).

    A caller may still pass an instance or the raw key under the attname, as the models
    do when they build the status-change log.
    """
    doctype = child_model.get_doctype()
    fields = [f for f in child_model._meta.get_fields() if getattr(f, "concrete", False)]
    accepted = {f.name for f in fields} | {f.attname for f in fields}
    missing_links: list[str] = []
    missing_values: list[str] = []
    payloads: list[dict] = []

    for index, row in enumerate(rows or [], start=1):
        payload = {k: v for k, v in (row or {}).items() if k in accepted and k != "name"}
        for field in fields:
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
                missing_links.append(f"Row #{index}: {_label(field)}: {value}")
        for field in fields:
            if field.name == parent_field or not _is_mandatory(field):
                continue
            value = payload.get(field.attname if _is_link(field) else field.name)
            if value is None or value == "":
                missing_values.append(
                    f"Error: <strong>{doctype}</strong> Row #{index}: "
                    f"Value missing for: {_label(field)}"
                )
        payload["idx"] = index
        payload.setdefault("parentfield", fieldname)
        payloads.append(payload)

    if missing_links:
        raise LinkValidationError("Could not find " + ", ".join(missing_links))
    if missing_values:
        raise MandatoryError(messages=missing_values)
    return payloads


@transaction.atomic
def replace_children(instance, fieldname: str, spec: dict, rows: list[dict]) -> None:
    """Delete the parent's existing rows and recreate them from ``rows``.

    Wholesale replacement, not a merge - Frappe's semantics. ``idx`` is assigned from
    list position, which is what orders a child table in the UI. The rows are validated
    by :func:`prepare_rows` before anything is deleted.
    """
    child_model = spec["model"]
    parent_doctype = type(instance).get_doctype()

    if spec["polymorphic"]:
        base_filter = {"parenttype": parent_doctype, "parent": str(instance.pk)}
    else:
        base_filter = {spec["fk"]: instance}

    payloads = prepare_rows(child_model, rows, fieldname=fieldname, parent_field=spec["fk"])

    child_model._default_manager.filter(**base_filter).delete()

    for payload in payloads:
        payload.update(base_filter)
        payload.setdefault("parenttype", parent_doctype)
        child_model._default_manager.create(**payload)


def delete_polymorphic_children(instance) -> int:
    """C8 - delete a parent's polymorphic child rows.

    Port of ``frappe/model/delete_doc.py:207-227``, which deletes every child table's
    rows by ``{parenttype, parent}`` when a document is deleted.

    Child tables with a real foreign key are already handled by Django's ``CASCADE``.
    The three polymorphic ones (``CRM Products``, ``CRM Status Change Log``,
    ``CRM Rolling Response Time``) cannot have one - each is embedded by *both* CRM Lead
    and CRM Deal - so ``parent`` is a plain string and nothing cascades. Deleting a lead
    left its product and status-log rows behind, keyed to an id that no longer resolves.

    Returns the number of rows removed.
    """
    parent_doctype = type(instance).get_doctype()
    removed = 0

    for spec in discover_child_tables(type(instance)).values():
        if not spec["polymorphic"]:
            continue
        count, _ = (
            spec["model"]
            ._default_manager.filter(parenttype=parent_doctype, parent=str(instance.pk))
            .delete()
        )
        removed += count

    return removed


def _on_parent_delete(sender, instance, **kwargs):
    delete_polymorphic_children(instance)


def connect_cascade(model) -> None:
    """Wire :func:`delete_polymorphic_children` to a parent model's ``post_delete``."""
    from django.db.models.signals import post_delete

    post_delete.connect(
        _on_parent_delete,
        sender=model,
        dispatch_uid=f"frappe_core.children.cascade.{model._meta.label}",
    )
