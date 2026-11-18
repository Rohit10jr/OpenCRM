"""Quick filters: `get_quick_filters`, `update_quick_filters` (specs/CONFIGURATION.md
section 4.6; temp A-37).

Ported from `backend/crm_app/api/doc.py:116-234` (upstream `crm/api/doc.py:163-224`).
A list's quick filters are the JSON list of fieldnames on the CRM Global Settings row
for (dt, "Quick Filters"); without one, the doctype's standard filter fields. Each entry
is built from the model's concrete fields. Both calls check the doctype, child tables
excluded (PE-14, PE-15), and leave out the fields the caller may not read (PE-16).
"""

from __future__ import annotations

from configuration.field_meta import frappe_fieldtype, link_target
from configuration.metadata import model_or_404
from configuration.models import CRMGlobalSettings
from core.field_access import hidden_from

QUICK_FILTERS = "Quick Filters"

#: The fields each doctype marks `in_standard_filter` in its upstream JSON (old
#: `doc.py:126-137`), the fallback without a stored row. Named apart from
#: `field_helpers.STANDARD_FILTER_FIELDS`, the standard columns offered as filters.
QUICK_FILTER_FALLBACK: dict[str, list[str]] = {
    "CRM Call Log": ["from", "status", "type", "to", "telephony_medium"],
    "CRM Deal": ["organization", "email", "status"],
    "CRM Fields Layout": ["dt", "type"],
    "CRM Lead": ["status", "email", "lead_name", "organization", "converted"],
    "CRM Organization": ["organization_name", "no_of_employees", "industry", "territory"],
    "CRM Service Level Agreement": ["sla_name"],
    "CRM Task": ["title", "priority", "assigned_to", "status", "due_date"],
    "CRM Telephony Agent": ["user", "mobile_no", "user_name"],
    "CRM View Settings": ["label", "dt"],
    "FCRM Note": ["title", "content"],
}


def _concrete_fields(model) -> dict:
    return {f.name: f for f in model._meta.get_fields() if getattr(f, "concrete", False)}


def _field_descriptor(field) -> dict:
    """Old `doc.py:51-57`: label from `verbose_name`, options a link target or the Select
    choices as one newline-separated string."""
    options = link_target(field)
    if options is None and getattr(field, "choices", None):
        options = "\n".join(str(choice[0]) for choice in field.choices)
    return {
        "label": str(getattr(field, "verbose_name", field.name)),
        "fieldname": field.name,
        "fieldtype": frappe_fieldtype(field),
        "options": options,
    }


def _stored_row(doctype: str):
    return CRMGlobalSettings.first_row(doctype, QUICK_FILTERS)


def get_quick_filters(doctype, *, user, cached=True) -> list[dict]:
    """Old `doc.py:154-207`: `{label, fieldname, fieldtype, options}` per filter; Select
    options become `{label, value}` with a blank first option unless one exists;
    `converted` dropped for CRM Lead. `cached` is accepted and ignored. A stored entry
    that is not a string is skipped (PE-12c); a stored name is matched against the
    model's fields, never queried as it is."""
    model = model_or_404(doctype, child_allowed=False)
    hidden = hidden_from(model, user)
    by_name = {
        name: field for name, field in _concrete_fields(model).items() if name not in hidden
    }

    row = _stored_row(doctype)
    fields: list[dict] = []
    if row is not None:
        selected = row.json if isinstance(row.json, list) else []
        for fieldname in selected:
            if not isinstance(fieldname, str):
                continue
            if fieldname == "name":
                fields.append({"label": "Name", "fieldname": "name", "fieldtype": "Data"})
            elif fieldname in by_name:
                fields.append(_field_descriptor(by_name[fieldname]))
    else:
        fields = [
            _field_descriptor(by_name[name])
            for name in QUICK_FILTER_FALLBACK.get(doctype, [])
            if name in by_name
        ]

    quick_filters = []
    for field in fields:
        options = field.get("options")
        if field.get("fieldtype") == "Select" and options and isinstance(options, str):
            parsed = [{"label": o, "value": o} for o in options.split("\n")]
            if not any(not o.get("value") for o in parsed):
                parsed.insert(0, {"label": "", "value": ""})
            options = parsed
        quick_filters.append(
            {
                "label": field.get("label"),
                "fieldname": field.get("fieldname"),
                "fieldtype": field.get("fieldtype"),
                "options": options,
            }
        )

    if doctype == "CRM Lead":
        quick_filters = [f for f in quick_filters if f.get("fieldname") != "converted"]

    return quick_filters


def update_quick_filters(quick_filters, old_filters, doctype, *, user) -> None:
    """Old `doc.py:210-234`: writes the row's list and answers `None`. `old_filters` is
    accepted and ignored (upstream's Property Setter half is not ported)."""
    model_or_404(doctype, child_allowed=False)
    selected = list(quick_filters or [])
    row = _stored_row(doctype)
    if row is None:
        row = CRMGlobalSettings(dt=doctype, type=QUICK_FILTERS)
    row.json = selected
    row.save(user=user)
