"""Every value field the metadata file lists for a served doctype is a model column
(specs/CONFIGURATION.md section 4.5; A-35).

Field metadata describes what a form shows and a list filters on; a field the file
lists but the model lacks would be offered to the client and then fail at the query.
Entries for doctypes with no backend_v2 model yet are inert and not checked.
"""

from __future__ import annotations

from configuration import field_meta
from core.doctypes import declared_doctypes
from core.resources import routed_rule_map

#: (doctype, fieldname) the file lists that the model deliberately lacks, with the reason.
REVIEWED_MISSING_COLUMNS: dict[tuple[str, str], str] = {}


def _served_doctypes():
    served = {model for model in routed_rule_map()}
    for doctype, model in declared_doctypes().items():
        if model in served or getattr(model, "IS_CHILD_TABLE", False):
            yield doctype, model


def test_every_value_field_of_a_served_doctype_is_a_column():
    missing = []
    checked = set()
    for doctype, model in _served_doctypes():
        if not field_meta.has_meta(doctype):
            continue
        checked.add(doctype)
        columns = {
            name
            for field in model._meta.get_fields()
            if getattr(field, "concrete", False)
            for name in (field.name, getattr(field, "attname", field.name))
        }
        for field in field_meta.get_value_fields(doctype):
            name = field.get("fieldname")
            if name and name not in columns and (doctype, name) not in REVIEWED_MISSING_COLUMNS:
                missing.append((doctype, name))
    assert not missing, f"Metadata fields with no model column: {missing}"
    assert {"FCRM Settings", "CRM Dropdown Item"} <= checked, checked


def test_reviewed_exceptions_still_apply():
    for doctype, fieldname in REVIEWED_MISSING_COLUMNS:
        assert field_meta.get_field(doctype, fieldname), (doctype, fieldname)
