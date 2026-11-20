"""Export's field-info provider, filled from the field metadata
(specs/CONFIGURATION.md section 4.5; temp A-35).

Ported from `backend/crm_app/api/reportview.py:36-84` (`get_field_info`).
`core.mixins.export.ListExportMixin` calls `provider(fields)` with no doctype, so this is
a factory bound to a model: a resource's ViewSet assigns
`export_field_info = staticmethod(export_field_info_for(Model))`, and `core` never imports
`configuration`. No CONFIGURATION resource exports a list; SALES', CONTACTS' and
ACTIVITIES' resources opt in when they are built.
"""

from __future__ import annotations

from configuration import field_meta
from configuration.field_helpers import STANDARD_FILTER_FIELDS
from core.doctypes import doctype_of

#: The standard columns' labels: the same table every filterable-field list appends.
STANDARD_LABELS = {f["fieldname"]: f["label"] for f in STANDARD_FILTER_FIELDS}

#: `frappe/model/meta.py:get_default_df`: the standard columns' types.
STANDARD_TYPES = {
    "creation": "Datetime",
    "modified": "Datetime",
    "idx": "Int",
    "docstatus": "Int",
    "owner": "Link",
    "modified_by": "Link",
}


def export_field_info_for(model, get_field=None):
    """A provider of label and type per exported column for `model`'s doctype.

    `name` is labelled `ID`, type `Data`; a metadata field gives its label (or the
    fieldname) and fieldtype (or `Data`); anything else takes the standard label and type.
    `get_field` is the metadata lookup, `field_meta.get_field` unless a test overlays one.
    """
    doctype = doctype_of(model)
    lookup = get_field or field_meta.get_field

    def export_field_info(fields: list[str]) -> list[dict]:
        info = []
        for fieldname in fields:
            if fieldname == "name":
                info.append({"fieldname": "name", "label": "ID", "fieldtype": "Data"})
                continue
            meta = lookup(doctype, fieldname)
            if meta:
                info.append(
                    {
                        "fieldname": fieldname,
                        "label": meta.get("label") or fieldname,
                        "fieldtype": meta.get("fieldtype") or "Data",
                    }
                )
                continue
            info.append(
                {
                    "fieldname": fieldname,
                    "label": STANDARD_LABELS.get(fieldname, fieldname),
                    "fieldtype": STANDARD_TYPES.get(fieldname, "Data"),
                }
            )
        return info

    return export_field_info
