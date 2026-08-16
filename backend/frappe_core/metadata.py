"""Field metadata — filterable, group-by and list columns.

**C7 is closed here.** Phase 0 keyed both allowlists on the *Django internal type*,
which is lossy: `Long Text`/`Small Text`/`Text Editor` all collapse to `TextField`, and
`Duration`/`Rating` are indistinguishable from `IntegerField`/`FloatField`. So `Duration`
was group-by-able only by accident and `Rating` was filterable only by accident.

Phase 4 keys them on the **Frappe fieldtype**, read from
:mod:`frappe_core.field_meta`, which is generated from the DocType JSON. The lists below
are now transcriptions of the source rather than translations of it, so
`test_allowlists_match_the_source` can compare them to `crm/api/doc.py` directly.

The phase-0 extension points (`registry.register_metadata_hooks`) are unchanged; phase 4
registers providers through them rather than editing the call sites.
"""

from __future__ import annotations

from django.db.models.fields.related import ForeignKey, OneToOneField

from frappe_core import field_meta, registry
from frappe_core.session import get_current_user

#: ``crm/api/doc.py:get_filterable_fields:56-73`` — verbatim, as Frappe fieldtypes.
FILTERABLE_FIELDTYPES = {
    "Check",
    "Data",
    "Float",
    "Int",
    "Currency",
    "Dynamic Link",
    "Link",
    "Long Text",
    "Select",
    "Small Text",
    "Text Editor",
    "Text",
    "Duration",
    "Rating",
    "Date",
    "Datetime",
}

#: ``crm/api/doc.py:get_group_by_fields:114-126`` — narrower; no free text.
GROUP_BY_FIELDTYPES = {
    "Check",
    "Data",
    "Float",
    "Int",
    "Currency",
    "Dynamic Link",
    "Link",
    "Select",
    "Duration",
    "Date",
    "Datetime",
}

#: Appended by upstream to every filterable-field list, in this order.
STANDARD_FILTER_FIELDS = [
    {"fieldname": "name", "fieldtype": "Link", "label": "Name"},
    {"fieldname": "owner", "fieldtype": "Link", "label": "Created By", "options": "User"},
    {
        "fieldname": "modified_by",
        "fieldtype": "Link",
        "label": "Last Updated By",
        "options": "User",
    },
    {"fieldname": "_user_tags", "fieldtype": "Data", "label": "Tags"},
    {"fieldname": "_liked_by", "fieldtype": "Data", "label": "Like"},
    {"fieldname": "_comments", "fieldtype": "Text", "label": "Comments"},
    {"fieldname": "_assign", "fieldtype": "Text", "label": "Assigned To"},
    {"fieldname": "creation", "fieldtype": "Datetime", "label": "Created On"},
    {"fieldname": "modified", "fieldtype": "Datetime", "label": "Last Updated On"},
]

#: ``crm/api/doc.py:143-154`` — appended to every group-by list. Upstream lists
#: ``Created On`` and ``Modified On`` twice over; the duplicates are dropped here
#: because a repeated entry in a dropdown is a rendering bug nothing depends on.
GROUP_BY_STANDARD_FIELDS = [
    {"fieldname": "name", "label": "Name"},
    {"fieldname": "creation", "label": "Created On"},
    {"fieldname": "modified", "label": "Last Modified"},
    {"fieldname": "modified_by", "label": "Modified By"},
    {"fieldname": "owner", "label": "Owner"},
    {"fieldname": "_liked_by", "label": "Like"},
    {"fieldname": "_assign", "label": "Assigned To"},
    {"fieldname": "_comments", "label": "Comments"},
]


def get_list_columns(doctype: str, user: str | None = None, view_type: str = "list") -> list:
    """Saved-view columns for ``doctype``, or the controller default.

    Phase 0 has no view-settings persistence (spec section 9), so this returns the
    controller default. Phase 4 registers a provider that consults CRM View Settings
    first - the merge order lives in ``api/doc.py:get_data``.
    """
    user = user or get_current_user()
    entry = registry.get_entry(doctype)
    if entry.list_columns_provider is not None:
        provided = entry.list_columns_provider(doctype, user, view_type)
        # `None` is the provider's fall-through signal - the same contract `get_data`
        # uses. Returning it here would hand the caller "no columns" where upstream's
        # `elif` would have used the controller default.
        if provided is not None:
            return provided
    return entry.default_list_data().get("columns", [])


def get_filterable_fields(doctype: str) -> list:
    """Fields the client may filter on. ``crm/api/doc.py:54-109``.

    Honours ``get_non_filterable_fields()`` on the controller, as upstream does
    (``crm/api/doc.py:75-78``).
    """
    entry = registry.get_entry(doctype)
    if entry.filterable_fields_provider is not None:
        return entry.filterable_fields_provider(doctype)

    restricted = set(entry.non_filterable_fields())
    fields = []
    for descriptor in STANDARD_FILTER_FIELDS:
        if descriptor["fieldname"] not in restricted:
            fields.append({**descriptor, "value": descriptor["fieldname"]})

    for field in field_meta.get_fields(doctype):
        fieldname = field.get("fieldname")
        if not fieldname or fieldname in restricted or fieldname == "name":
            continue
        if any(f["fieldname"] == fieldname for f in fields):
            continue
        if field.get("fieldtype") not in FILTERABLE_FIELDTYPES:
            continue
        fields.append(
            {
                "fieldname": fieldname,
                "label": field.get("label") or fieldname,
                "fieldtype": field.get("fieldtype"),
                "options": field.get("options"),
                "value": fieldname,
            }
        )
    return fields


def get_group_by_fields(doctype: str) -> list:
    """``crm/api/doc.py:112-160``.

    Upstream appends its own standard fields after the doctype's own, including
    ``_liked_by`` / ``_assign`` / ``_comments``, which are not group-by-able by
    fieldtype but are listed anyway (lines 143-158).
    """
    entry = registry.get_entry(doctype)
    restricted = set(entry.non_filterable_fields())

    fields = []
    for field in field_meta.get_fields(doctype):
        fieldname = field.get("fieldname")
        if not fieldname or fieldname in restricted:
            continue
        if field.get("fieldtype") not in GROUP_BY_FIELDTYPES:
            continue
        fields.append({"fieldname": fieldname, "label": field.get("label") or fieldname})

    for descriptor in GROUP_BY_STANDARD_FIELDS:
        if descriptor["fieldname"] in restricted:
            continue
        if any(f["fieldname"] == descriptor["fieldname"] for f in fields):
            continue
        fields.append(dict(descriptor))
    return fields


def _frappe_fieldtype(field) -> str:
    """Best-effort Django -> Frappe fieldtype, for the metadata payload."""
    internal = field.get_internal_type()
    return {
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
    }.get(internal, "Data")


def _link_target(field) -> str | None:
    if isinstance(field, (ForeignKey, OneToOneField)):
        related = field.related_model
        return getattr(related, "get_doctype", lambda: None)() or related.__name__
    return None
