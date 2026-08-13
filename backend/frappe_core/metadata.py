"""Phase-4 extension points, with working phase-0 defaults.

PHASE_0_FOUNDATION.md section 8. Phase 4 replaces the bodies by registering providers
through :func:`frappe_core.registry.register_metadata_hooks`; the call sites here and in
``api/doc.py`` stay put.

The defaults below are deliberately derived from the model rather than stubbed to
``None``, so ``get_data`` returns a correct payload before phase 4 lands - the response
*shape* is final now (spec section 6b).
"""

from __future__ import annotations

from django.db.models.fields.related import ForeignKey, OneToOneField

from frappe_core import registry
from frappe_core.session import get_current_user

#: Fieldtype allowlist from ``crm/api/doc.py:get_filterable_fields:56-73``, expressed as
#: Django internal types. Phase 4 owns the Frappe-fieldtype version of this list.
FILTERABLE_INTERNAL_TYPES = {
    "BooleanField",
    "CharField",
    "TextField",
    "EmailField",
    "URLField",
    "SlugField",
    "IntegerField",
    "BigIntegerField",
    "SmallIntegerField",
    "PositiveIntegerField",
    "FloatField",
    "DecimalField",
    "DateField",
    "DateTimeField",
    "ForeignKey",
    "OneToOneField",
}

#: ``crm/api/doc.py:get_group_by_fields:114-126`` - narrower than the filter list; no
#: free-text types.
GROUP_BY_INTERNAL_TYPES = {
    "BooleanField",
    "CharField",
    "IntegerField",
    "BigIntegerField",
    "SmallIntegerField",
    "PositiveIntegerField",
    "FloatField",
    "DecimalField",
    "DateField",
    "DateTimeField",
    "ForeignKey",
    "OneToOneField",
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


def get_list_columns(doctype: str, user: str | None = None, view_type: str = "list") -> list:
    """Saved-view columns for ``doctype``, or the controller default.

    Phase 0 has no view-settings persistence (spec section 9), so this returns the
    controller default. Phase 4 registers a provider that consults CRM View Settings
    first - the merge order lives in ``api/doc.py:get_data``.
    """
    user = user or get_current_user()
    entry = registry.get_entry(doctype)
    if entry.list_columns_provider is not None:
        return entry.list_columns_provider(doctype, user, view_type)
    return entry.default_list_data().get("columns", [])


def get_filterable_fields(doctype: str) -> list:
    """Fields the client may filter on.

    Honours ``get_non_filterable_fields()`` on the controller, as upstream does at
    ``crm/api/doc.py:75-78``.
    """
    entry = registry.get_entry(doctype)
    if entry.filterable_fields_provider is not None:
        return entry.filterable_fields_provider(doctype)

    restricted = set(entry.non_filterable_fields())
    fields = []
    for descriptor in STANDARD_FILTER_FIELDS:
        if descriptor["fieldname"] not in restricted:
            fields.append({**descriptor, "value": descriptor["fieldname"]})

    for field in entry.model._meta.get_fields():
        if not getattr(field, "concrete", False):
            continue
        fieldname = field.name
        if fieldname in restricted or fieldname == "name":
            continue
        if any(f["fieldname"] == fieldname for f in fields):
            continue
        if field.get_internal_type() not in FILTERABLE_INTERNAL_TYPES:
            continue
        fields.append(
            {
                "fieldname": fieldname,
                "label": getattr(field, "verbose_name", fieldname),
                "fieldtype": _frappe_fieldtype(field),
                "options": _link_target(field),
                "value": fieldname,
            }
        )
    return fields


def get_group_by_fields(doctype: str) -> list:
    entry = registry.get_entry(doctype)
    restricted = set(entry.non_filterable_fields())
    fields = []
    for field in entry.model._meta.get_fields():
        if not getattr(field, "concrete", False):
            continue
        if field.name in restricted:
            continue
        if field.get_internal_type() not in GROUP_BY_INTERNAL_TYPES:
            continue
        fields.append({"fieldname": field.name, "label": getattr(field, "verbose_name", field.name)})
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
