"""Form layouts: `get_fields_layout`, `get_sidepanel_sections`, `save_fields_layout`
(specs/CONFIGURATION.md section 4.6; temp A-37).

Ported from `backend/crm_app/api/fields_layout.py` (upstream `crm_fields_layout.py`). The
layout rows of the metadata file (Tab, Section and Column Breaks, in declaration order)
are the default layout. Every call validates the doctype (PE-14; a child table answers
the layout and its save, PE-15) and leaves out the fields the caller may not read
(PE-16); a layout's field lists hold fieldnames (PE-18).
"""

from __future__ import annotations

import json
import secrets

from configuration import field_meta
from configuration.layouts import (
    check_fieldnames_only,
    keep_fieldnames_only,
    parse_layout,
)
from configuration.metadata import model_or_404
from configuration.models import CRMFieldsLayout
from core.exceptions import PermissionError
from core.field_access import hidden_from

#: `crm_fields_layout.py:124-128`: left out of the side panel's field pool.
SIDEPANEL_EXCLUDED_FIELDTYPES = ("Tab Break", "Section Break", "Column Break")

#: The roles that save a layout through this call (`fields_layout.py:256`); roles only,
#: as backend/ (the resource also passes the literal Administrator).
SAVE_ROLES = {"System Manager", "Sales Manager"}


def random_string(length: int = 4) -> str:
    """`frappe.utils.random_string`, only ever used for element ids here."""
    return secrets.token_hex((length + 1) // 2)[:length]


def _readable_fields(doctype: str, model, user) -> list[dict]:
    hidden = hidden_from(model, user)
    return [f for f in field_meta.get_fields(doctype) if f.get("fieldname") not in hidden]


def get_default_layout(doctype: str) -> list:
    """`crm_fields_layout.py:213-259`: the fields in declaration order, a new tab at each
    Tab Break, a section at each Section Break, a column at each Column Break."""
    fields = field_meta.get_fields(doctype)
    tabs: list = []

    if fields and fields[0].get("fieldtype") != "Tab Break":
        sections = []
        if fields[0].get("fieldtype") != "Section Break":
            sections.append(
                {
                    "name": "section_" + random_string(),
                    "columns": [{"name": "column_" + random_string(), "fields": []}],
                }
            )
        tabs.append({"name": "tab_" + random_string(), "sections": sections})

    for field in fields:
        fieldtype = field.get("fieldtype")
        if fieldtype == "Tab Break":
            tabs.append(
                {
                    "name": "tab_" + random_string(),
                    "sections": [
                        {
                            "name": "section_" + random_string(),
                            "columns": [{"name": "column_" + random_string(), "fields": []}],
                        }
                    ],
                }
            )
        elif fieldtype == "Section Break":
            tabs[-1]["sections"].append(
                {
                    "name": "section_" + random_string(),
                    "columns": [{"name": "column_" + random_string(), "fields": []}],
                }
            )
        elif fieldtype == "Column Break":
            tabs[-1]["sections"][-1]["columns"].append(
                {"name": "column_" + random_string(), "fields": []}
            )
        else:
            tabs[-1]["sections"][-1]["columns"][-1]["fields"].append(field.get("fieldname"))

    return tabs


def get_fields_layout(doctype, type, *, user, parent_doctype=None) -> list:
    """`crm_fields_layout.py:29-107`: tabs, sections, columns of expanded field objects.
    A fieldname the doctype no longer has, or the caller may not read, is left out;
    `parent_doctype` is accepted and ignored."""
    model = model_or_404(doctype, child_allowed=True)
    row = CRMFieldsLayout.row_for(doctype, type)
    tabs = []
    if row is not None and row.layout:
        tabs = keep_fieldnames_only(parse_layout(row.layout))

    if not tabs and type != "Required Fields":
        tabs = get_default_layout(doctype)

    has_tabs = (
        isinstance(tabs, list)
        and tabs
        and isinstance(tabs[0], dict)
        and any("sections" in tab for tab in tabs)
    )
    if not has_tabs:
        tabs = [{"name": "first_tab", "sections": tabs}]

    readable = _readable_fields(doctype, model, user)
    by_name = {f.get("fieldname"): f for f in readable}

    required_fields = []
    if type == "Required Fields":
        # Required, and with no default to fall back on (source :63-68).
        required_fields = [dict(f) for f in readable if f.get("reqd") and not f.get("default")]

    for tab in tabs:
        for section in tab.get("sections") or []:
            if section.get("columns"):
                section["columns"] = [c for c in section["columns"] if c]
            for column in section.get("columns") or []:
                expanded = []
                for fieldname in [f for f in (column.get("fields") or []) if f]:
                    field = by_name.get(fieldname)
                    if field is None:
                        continue
                    expanded.append(dict(field))
                    if type == "Required Fields" and field.get("reqd"):
                        required_fields = [
                            f for f in required_fields if f.get("fieldname") != fieldname
                        ]
                column["fields"] = expanded

    if type == "Required Fields" and required_fields and tabs:
        # Anything still required but not placed gets its own section (source :92-106).
        tabs[-1]["sections"].append(
            {
                "label": "Required Fields",
                "name": "required_fields_section_" + random_string(),
                "opened": True,
                "hideLabel": True,
                "columns": [
                    {
                        "name": "required_fields_column_" + random_string(),
                        "fields": required_fields,
                    }
                ],
            }
        )

    return tabs or []


def get_field_obj(field: dict) -> dict:
    """`crm_fields_layout.py:173-186`: placeholders and Select option expansion."""
    obj = dict(field)
    label = obj.get("label") or obj.get("fieldname") or ""
    fieldtype = obj.get("fieldtype")

    if fieldtype in ("Link", "Select"):
        obj.setdefault("placeholder", f"Select {label}...")
    else:
        obj.setdefault("placeholder", f"Add {label}...")

    if fieldtype == "Select" and obj.get("options"):
        obj["options"] = [
            {"label": option, "value": option} for option in field_meta.select_options(field)
        ]

    if obj.get("read_only"):
        obj["tooltip"] = "This field is read only and cannot be edited."

    return obj


def get_sidepanel_sections(doctype, *, user) -> list:
    """`crm_fields_layout.py:110-143`: the side panel's sections, each field expanded;
    `[]` when nothing is configured. Not for a child table (PE-15)."""
    model = model_or_404(doctype, child_allowed=False)
    row = CRMFieldsLayout.row_for(doctype, "Side Panel")
    if row is None or not row.layout:
        return []

    layout = keep_fieldnames_only(parse_layout(row.layout))
    by_name = {
        f.get("fieldname"): f
        for f in _readable_fields(doctype, model, user)
        if f.get("fieldtype") not in SIDEPANEL_EXCLUDED_FIELDTYPES
    }

    for section in layout:
        section["name"] = section.get("name") or section.get("label")
        for column in section.get("columns") or []:
            column["fields"] = [
                get_field_obj(by_name[fieldname])
                for fieldname in column.get("fields") or []
                if fieldname in by_name
            ]

    return layout


def save_fields_layout(doctype, type, layout, *, user) -> str:
    """`crm_fields_layout.py:189-210`: answers the stored string (a list input is
    JSON-dumped). System Manager or Sales Manager only, message verbatim. The layout must
    be valid JSON (PE-12c) whose field lists hold fieldnames (PE-18); `type` is stored as
    given."""
    if not user.get_roles() & SAVE_ROLES:
        raise PermissionError("Not permitted to modify fields layout")
    model_or_404(doctype, child_allowed=True)
    parsed = parse_layout(layout)
    check_fieldnames_only(parsed)

    row = CRMFieldsLayout.row_for(doctype, type)
    if row is None:
        row = CRMFieldsLayout(dt=doctype, type=type)
    row.layout = layout if isinstance(layout, str) else json.dumps(layout)
    row.save(user=user)
    return row.layout
