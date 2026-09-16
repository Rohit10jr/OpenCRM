"""``frappe.desk.form.load.getdoctype`` - a doctype's field definitions for the form
store (``stores/meta.js``).

Ported from ``frappe/desk/form/load.py:getdoctype`` and ``get_meta_bundle``. One call
returns the doctype's own meta *and* the meta of every child table it embeds, because a
form that renders a grid needs the child's fields before it can draw a single column.

**What a "meta document" is here.** Upstream returns ``frappe.desk.form.meta.get_meta``,
a ``FormMeta``: the DocType row, its DocFields, and the client-side assets bolted on by
``load_assets`` - ``__js``, ``__list_js``, ``__print_formats``, ``__dashboard`` and the
rest of ``ASSET_KEYS``. None of those exist in this port: a DocType's client script is a
Frappe-desk concept, and the CRM frontend is a Vue app that never looks at them
(``stores/meta.js`` reads ``name``, ``fields``, ``translated_doctype`` and the grid
properties, nothing else). So a meta document here is the DocType's *properties* plus
its field list - the part that has a meaning in this port - and the asset keys are
absent rather than present-and-null, which is the same thing to every reader in
``frontend/src``.

The field list is ``field_meta.get_fields`` verbatim, **layout breaks included**:
upstream's meta carries every DocField row in ``idx`` order, ``Section Break`` and
``Column Break`` among them, and ``FieldLayout`` on the client depends on that.

Permission: authenticated, and nothing more - which is what upstream does. ``getdoctype``
checks nothing, because metadata is not a document: it describes the shape of a doctype,
not the contents of anybody's records. (Contrast ``getdoc``, two functions up, which
checks ``read`` on the named document.)
"""

from __future__ import annotations

from crm_app.api.user_settings import get_user_settings
from frappe_core import field_meta, registry
from frappe_core.exceptions import DoesNotExistError
from frappe_core.renderers import WithResponseKeys
from frappe_core.whitelist import whitelist

#: ``frappe/model/__init__.py:table_fields`` - the two fieldtypes whose ``options`` names
#: a child doctype.
TABLE_FIELDTYPES = ("Table", "Table MultiSelect")

#: DocType properties every meta document carries, with the value a DocType row has when
#: the property is unset. The generator drops empty and zero values from the JSON
#: (``scripts/generate_field_meta.py``), so "absent" has to be turned back into "0" here
#: rather than left for the client to guess.
#:
#: ``sort_field``/``sort_order`` are the exception: ``frappe/core/doctype/doctype.json``
#: declares no default for ``sort_field``, and every consumer in the framework spells the
#: fallback ``meta.sort_field or "modified"`` (``db_query.py``). All 39 CRM doctypes set
#: it explicitly to ``modified``/``DESC``; the default only ever applies to the platform
#: doctypes, which ship no JSON, and it is the same answer the framework would reach.
#:
#: ``is_submittable`` is hard-coded 0: it is not in the generated JSON because no doctype
#: in this port declares it - the CRM has no submittable doctype, and the port models no
#: docstatus workflow. The key is emitted anyway because it is the one DocType property
#: a Frappe-shaped client is entitled to branch on.
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


def _meta_document(doctype: str) -> dict:
    """One entry of the bundle: the DocType's properties plus its fields.

    ``idx`` is added to each field here rather than in the generated file. Upstream's
    DocField rows carry it because they are rows in a child table and every child row
    has one; it is the 1-based position in declaration order, so it is *derivable* and
    committing 1,400 copies of a counter would be noise. Each descriptor is copied on
    the way out, so the parsed-JSON memo behind ``field_meta`` is never mutated.
    """
    meta = dict(DOCTYPE_PROPERTY_DEFAULTS)
    if registry.has_doctype(doctype):
        # The platform doctypes ship no JSON, so the registry is the only place that
        # knows `Contact Email` is a child table and `FCRM Settings` is a single.
        entry = registry.get_entry(doctype)
        meta["istable"] = 1 if entry.is_child_table else 0
        meta["issingle"] = 1 if entry.is_single else 0
    meta.update(field_meta.get_doctype_properties(doctype))
    meta["name"] = doctype
    meta["fields"] = [
        dict(field, idx=i) for i, field in enumerate(field_meta.get_fields(doctype), start=1)
    ]
    return meta


def get_meta_bundle(doctype: str) -> list[dict]:
    """``frappe/desk/form/load.py:get_meta_bundle`` - the doctype, then one meta per
    table field, in field order.

    Line for line: ``[meta] + [meta(df.options) for df in fields if df.fieldtype in
    table_fields]``. A doctype that embedded the same child table twice would send that
    child's meta twice, as upstream does; none of the generated doctypes does, and
    ``stores/meta.js`` folds the list into a dict keyed by ``name`` anyway.
    """
    bundle = [_meta_document(doctype)]
    for field in bundle[0]["fields"]:
        if field.get("fieldtype") in TABLE_FIELDTYPES and field.get("options"):
            bundle.append(_meta_document(field["options"]))
    return bundle


def get_parent_dt(doctype: str) -> str | None:
    """``frappe/model/meta.py:get_parent_dt`` - the doctype embedding this child table.

    Upstream asks the DocField table for the first row whose ``fieldtype`` is a table
    type and whose ``options`` is this doctype, and returns its ``parent``. There is no
    DocField table here, so the same question is asked of the generated metadata: scan
    the registered doctypes for a ``Table``/``Table MultiSelect`` field pointing here.

    ``registry.all_doctypes()`` is sorted, so a child embedded by more than one parent
    (``CRM Products`` is in both ``CRM Deal`` and ``CRM Lead``) resolves the same way on
    every call. Upstream's answer in that case is whichever row the database hands back
    first, which is not defined either; determinism is strictly the better of the two.

    That ambiguity is real and upstream's: asked about ``CRM Products`` the answer is
    ``CRM Deal``, even when it was the lead form asking, so the bundle and the
    ``user_settings`` come back in the deal's context. It cannot reach a grid, because
    ``Grid.vue`` looks its saved columns up under the parent it was rendered with
    (``getGridViewSettings(parentDoctype)``), and that entry is filled by the parent's own
    ``getMeta`` call - not by this one. Reproduced rather than corrected: the caller does
    not say which parent it meant, so there is nothing here to correct it with.

    Returns ``None`` for anything that is not a child table, as upstream's
    ``frappe.is_table`` guard does.
    """
    if not _is_table(doctype):
        return None
    for candidate in registry.all_doctypes():
        if candidate == doctype:
            continue
        for field in field_meta.get_fields(candidate):
            if field.get("fieldtype") in TABLE_FIELDTYPES and field.get("options") == doctype:
                return candidate
    return None


def _is_table(doctype: str) -> bool:
    properties = field_meta.get_doctype_properties(doctype)
    if properties:
        return bool(properties.get("istable"))
    return registry.has_doctype(doctype) and registry.get_entry(doctype).is_child_table


@whitelist("frappe.desk.form.load.getdoctype")
def getdoctype(doctype: str, with_parent=False, cached_timestamp: str | None = None):
    """``frappe/desk/form/load.py:getdoctype`` - load a doctype.

    Answers ``{"message": null, "docs": [...], "user_settings": "..."}``: upstream writes
    ``docs`` and ``user_settings`` into ``frappe.response`` beside ``message`` rather than
    returning them, and ``frappe-ui`` hands the caller the whole body whenever ``docs`` is
    present (``frappe-ui/src/utils/frappeRequest.ts:92``), so the shape is load-bearing.

    ``with_parent`` is how the report builder - and this CRM's ``stores/meta.js``, which
    passes it on every call - asks for a child table *in context*: the answer is the
    parent's bundle, which contains the child anyway, plus a ``parent_dt`` key naming it.
    A doctype that is not a child table has no parent, so the flag does nothing, which is
    the common case here. When a child table has no locatable parent the child's own
    bundle is returned instead, exactly as upstream's ``if not docs`` fallback does.

    ``cached_timestamp`` is **accepted and ignored**. Upstream compares it against
    ``docs[0].modified`` and returns the string ``"use_cache"`` when they match, telling
    the client its cached copy is still good. That needs a modification timestamp for the
    doctype definition itself, which the port does not have: metadata here comes from a
    committed JSON file generated at build time, not from DocType rows with a ``modified``
    column, so there is no stamp to compare and no value that could ever match. Answering
    with the bundle is always correct - it is what upstream does whenever the stamps
    differ - and the frontend sends ``cached_timestamp: null`` on every call
    (``stores/meta.js``), so the branch is dead on this client regardless.
    """
    if not registry.has_doctype(doctype):
        raise DoesNotExistError(f"DocType {doctype} not found")

    docs: list[dict] = []
    parent_dt = None

    # `with_parent and (parent_dt := get_parent_dt(doctype))`, upstream's line for line.
    if with_parent:
        parent_dt = get_parent_dt(doctype)
        if parent_dt:
            docs = get_meta_bundle(parent_dt)

    if not docs:
        docs = get_meta_bundle(doctype)

    keys = {"docs": docs, "user_settings": get_user_settings(parent_dt or doctype)}
    if parent_dt:
        # Upstream sets `frappe.response["parent_dt"]` only when it found one.
        keys["parent_dt"] = parent_dt
    return WithResponseKeys(None, **keys)
