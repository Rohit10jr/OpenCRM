"""``crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.*`` — form layouts.

Ported from ``crm/fcrm/doctype/crm_fields_layout/crm_fields_layout.py``.

**This is where the layout fieldtypes come back.** `PHASE_1_MODELS.md` §2 dropped
`Section Break` / `Column Break` / `Tab Break` from the models because they carry no
data — and `PHASE_4_METADATA.md` §2 said they would return here as layout *data*. They
do, via :mod:`frappe_core.field_meta`, which keeps the DocType JSON's field order.

Not ported: **permlevel restrictions** (`handle_perm_level_restrictions`, source
:146-170). Frappe's per-field permission levels come from the DocType's `permissions`
table, which this port does not model.

**Correcting the reason originally given here.** This docstring used to say "no CRM
doctype sets a non-zero `permlevel` (checked across all 39 JSONs), so the function would
be a no-op". That is false. `CRM Twilio Settings` sets `permlevel: 1` on `api_key`,
`api_secret` and `twiml_sid` — the credential fields, which is exactly what the feature
exists for.

The effect is covered, by a different mechanism: `RESTRICTED_FIELDS` on the models
concerned (`frappe_core.field_security`), applied in the serializer, the list-field
resolver and the filter guard. So the *fields* upstream protects with permlevel are
protected here; what is absent is a general reading of the permlevel column, which stays
absent because the `permissions` table it lives on is not modelled at all.

The gap that matters is therefore **not** "permlevel is unhandled" but "a new permlevel
field upstream will not be noticed here" — someone has to add it to `RESTRICTED_FIELDS`
by hand. Recorded in specs/SECURITY_MODEL.md.
"""

from __future__ import annotations

import json
import secrets

from frappe_core import field_meta
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

LAYOUT_DOCTYPE = "CRM Fields Layout"

#: ``crm_fields_layout.py:124-128`` — excluded from the side panel's field pool.
SIDEPANEL_EXCLUDED_FIELDTYPES = ("Tab Break", "Section Break", "Column Break")


def random_string(length: int = 4) -> str:
    """``frappe.utils.random_string`` — only ever used for element ids here."""
    return secrets.token_hex((length + 1) // 2)[:length]


def _layout_row(doctype: str, type: str):
    """Through base_queryset for the same reason as ``form_script`` - no row rule on
    CRM Fields Layout today, but the invariant stays uniform."""
    from frappe_core.query import base_queryset

    return base_queryset(LAYOUT_DOCTYPE, get_current_user()).filter(dt=doctype, type=type).first()


def get_default_layout(doctype: str) -> list:
    """``crm_fields_layout.py:213-259``.

    Walks the fields **in declaration order**, opening a new tab at each ``Tab Break``,
    a new section at each ``Section Break`` and a new column at each ``Column Break``.
    That ordering *is* the layout, which is why `field_meta` keeps the breaks.
    """
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


@whitelist("crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout")
def get_fields_layout(doctype: str, type: str, parent_doctype: str | None = None):
    """``crm_fields_layout.py:29-107``.

    Returns tabs -> sections -> columns -> **expanded field objects**. The stored layout
    holds fieldnames; each is swapped for its metadata on the way out, and a fieldname
    the doctype no longer has simply drops.
    """
    row = _layout_row(doctype, type)
    tabs = []
    if row is not None and row.layout:
        tabs = json.loads(row.layout)

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

    by_name = {f.get("fieldname"): f for f in field_meta.get_fields(doctype)}

    required_fields = []
    if type == "Required Fields":
        # Source :63-68 - required, and with no default to fall back on.
        required_fields = [
            dict(f)
            for f in field_meta.get_fields(doctype)
            if f.get("reqd") and not f.get("default")
        ]

    for tab in tabs:
        for section in tab.get("sections") or []:
            if section.get("columns"):
                section["columns"] = [c for c in section["columns"] if c]
            for column in section.get("columns") or []:
                column["fields"] = [f for f in (column.get("fields") or []) if f]
                expanded = []
                for fieldname in column["fields"]:
                    if isinstance(fieldname, dict):
                        expanded.append(fieldname)
                        continue
                    field = by_name.get(fieldname)
                    if field is None:
                        continue
                    expanded.append(dict(field))
                    if type == "Required Fields" and field.get("reqd"):
                        required_fields = [
                            f
                            for f in required_fields
                            if f.get("fieldname") != field.get("fieldname")
                        ]
                column["fields"] = expanded

    if type == "Required Fields" and required_fields and tabs:
        # Source :92-106 - anything still required but not placed gets its own section.
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
    """``crm_fields_layout.py:173-186`` — placeholders and Select option expansion."""
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


@whitelist("crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections")
def get_sidepanel_sections(doctype: str):
    """``crm_fields_layout.py:110-143``. Returns ``[]`` when nothing is configured."""
    row = _layout_row(doctype, "Side Panel")
    if row is None or not row.layout:
        return []

    layout = json.loads(row.layout)
    by_name = {
        f.get("fieldname"): f
        for f in field_meta.get_fields(doctype)
        if f.get("fieldtype") not in SIDEPANEL_EXCLUDED_FIELDTYPES
    }

    for section in layout:
        section["name"] = section.get("name") or section.get("label")
        for column in section.get("columns") or []:
            expanded = []
            for fieldname in column.get("fields") or []:
                if isinstance(fieldname, dict):
                    expanded.append(fieldname)
                    continue
                field = by_name.get(fieldname)
                if field is not None:
                    expanded.append(get_field_obj(field))
            column["fields"] = expanded

    return layout


@whitelist(
    "crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.save_fields_layout", methods=("POST",)
)
def save_fields_layout(doctype: str, type: str, layout: str):
    """``crm_fields_layout.py:189-210``. Message verbatim.

    Upstream guards with ``frappe.has_permission("CRM Fields Layout", "write")``, which
    resolves to the doctype's role permissions — System Manager in a default install.
    A layout is site-wide configuration, so a Sales User must not rewrite it.
    """
    from crm_app.models import CRMFieldsLayout
    from crm_app.api.user import _roles_of

    if not _roles_of(get_current_user()) & {"System Manager", "Sales Manager"}:
        raise FrappePermissionError("Not permitted to modify fields layout")

    row = _layout_row(doctype, type)
    if row is None:
        row = CRMFieldsLayout(dt=doctype, type=type)
    row.layout = layout if isinstance(layout, str) else json.dumps(layout)
    row.save()
    return row.layout
