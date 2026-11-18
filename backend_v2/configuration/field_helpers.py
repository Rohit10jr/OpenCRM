"""The four field helpers: `get_fields`, `sort_options`, `get_filterable_fields`,
`get_group_by_fields` (specs/CONFIGURATION.md section 4.5; temp A-35).

Each is ported as the old backend has it, not merged into one function:
`backend/crm_app/api/doc.py:38-101,309-355` and `backend/frappe_core/metadata.py:30-172`.
A child table answers none of them (PE-15); every answer leaves out the fields the caller
may not read (PE-16). A model may subtract from the filter and group-by lists with a
`get_non_filterable_fields()` staticmethod, as the old controllers did.
"""

from __future__ import annotations

from configuration import field_meta
from configuration.field_meta import NO_VALUE_FIELDTYPES
from configuration.metadata import readable_fields
from core.field_access import hidden_from

#: `crm/api/doc.py:56-73`, the fieldtypes a list may filter on.
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

#: `crm/api/doc.py:114-126`, narrower: no free text.
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

#: `crm/api/doc.py:143-154`, appended to every group-by list without duplicates.
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

#: `crm/api/doc.py:38-44`, appended to every `sort_options` answer, so `name`, `creation`,
#: `modified`, `modified_by` and `owner` appear twice, as in `backend/`.
SORT_STANDARD_FIELDS = [
    {"label": "Name", "fieldname": "name"},
    {"label": "Created On", "fieldname": "creation"},
    {"label": "Last Modified", "fieldname": "modified"},
    {"label": "Modified By", "fieldname": "modified_by"},
    {"label": "Owner", "fieldname": "owner"},
]

#: The DocField flags a row always carries, as 0 when the file leaves them out
#: (`EditValueModal.vue:78` keeps a field only when `hidden == 0 && read_only == 0`).
DOCFIELD_FLAG_DEFAULTS = {
    "hidden": 0,
    "read_only": 0,
    "reqd": 0,
    "permlevel": 0,
    "in_list_view": 0,
    "in_standard_filter": 0,
}


def _non_filterable(model) -> set[str]:
    provider = getattr(model, "get_non_filterable_fields", None)
    return set(provider()) if callable(provider) else set()


def docfield(field: dict) -> dict:
    """A DocField row as `frappe.get_meta(doctype).fields` hands it out: the file's keys
    plus the zero flags, and `options` / `description` / `default` always present."""
    row = {"options": None, "description": None, "default": None}
    row.update(DOCFIELD_FLAG_DEFAULTS)
    row.update(field)
    return row


def get_fields(doctype: str, model, user, allow_all_fieldtypes=False) -> list[dict]:
    """`crm/api/doc.py:329-355`: the doctype's DocFields in declaration order, minus the
    value-less types and `Read Only` unless `allow_all_fieldtypes` is 1 or true."""
    if str(allow_all_fieldtypes).strip().lower() in ("1", "true"):
        not_allowed = frozenset()
    else:
        not_allowed = NO_VALUE_FIELDTYPES | {"Read Only"}
    rows = [
        docfield(field)
        for field in field_meta.get_fields(doctype)
        if field.get("fieldname") and field.get("fieldtype") not in not_allowed
    ]
    return readable_fields(model, rows, user)


def sort_options(doctype: str, model, user) -> list[dict]:
    """`crm/api/doc.py:82-101`: the model's concrete fields, labels from `verbose_name`,
    then the five standard fields."""
    hidden = hidden_from(model, user)
    fields = [
        {
            "label": str(getattr(field, "verbose_name", field.name)),
            "value": field.name,
            "fieldname": field.name,
        }
        for field in model._meta.get_fields()
        if getattr(field, "concrete", False) and field.name not in hidden
    ]
    for standard in SORT_STANDARD_FIELDS:
        fields.append({**standard, "value": standard["fieldname"]})
    return fields


def get_filterable_fields(doctype: str, model, user) -> list[dict]:
    """`frappe_core/metadata.py:111-144`: the nine standard fields first, then the value
    fields of the allowed types; `name`, duplicates and non-filterable fields dropped."""
    restricted = _non_filterable(model) | hidden_from(model, user)
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


def get_group_by_fields(doctype: str, model, user) -> list[dict]:
    """`frappe_core/metadata.py:147-172`: the doctype's fields of the allowed types, then
    the eight standard fields without duplicates."""
    restricted = _non_filterable(model) | hidden_from(model, user)
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
