"""PE-16's blind side: no metadata property or expression names a hidden field
(specs/CONFIGURATION.md section 4.5; temp A-36 finding 7).

PE-16 leaves field rows a caller may not read out of every metadata answer, but the
doctype's properties (`title_field`, `sort_field`, ...) and the other fields'
expressions (`depends_on`, `mandatory_depends_on`, `read_only_depends_on`, `fetch_from`)
pass through as they are. Nothing names a sensitive or restricted field today; this
guard keeps it so for every served doctype.
"""

from __future__ import annotations

import re

from configuration import field_meta
from configuration.metadata import served_model
from core.doctypes import declared_doctypes
from core.field_access import restricted_fields, sensitive_fields

PROPERTY_KEYS = ("title_field", "sort_field", "search_fields", "image_field")
EXPRESSION_KEYS = ("depends_on", "mandatory_depends_on", "read_only_depends_on", "fetch_from")


def _mentions(text: str, fieldname: str) -> bool:
    return bool(re.search(rf"(?<![\w]){re.escape(fieldname)}(?![\w])", str(text)))


def test_no_property_or_expression_names_a_hidden_field():
    found = []
    checked = 0
    for doctype in sorted(declared_doctypes()):
        model = served_model(doctype)
        if model is None:
            continue
        hidden = sensitive_fields(model) | restricted_fields(model)
        if not hidden:
            continue
        checked += 1
        properties = field_meta.get_doctype_properties(doctype)
        for key in PROPERTY_KEYS:
            for fieldname in hidden:
                if properties.get(key) and _mentions(properties[key], fieldname):
                    found.append((doctype, key, fieldname))
        for field in field_meta.get_fields(doctype):
            for key in EXPRESSION_KEYS:
                for fieldname in hidden:
                    if field.get(key) and _mentions(field[key], fieldname):
                        found.append((doctype, f"{field.get('fieldname')}.{key}", fieldname))
    assert checked, "no served doctype declares hidden fields; the guard would be vacuous"
    assert not found, f"Metadata naming a field the caller may not read: {found}"
