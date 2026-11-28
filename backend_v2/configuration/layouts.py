"""Field layouts: what a stored layout may hold (specs/CONFIGURATION.md section 4.6).

A layout is JSON text: a list of tabs or sections, each with columns whose `fields`
lists hold fieldnames. These helpers are shared by the CRM Fields Layout resource and
the layout calls, so both doors keep the same rule: a layout must be valid JSON
(PE-12c), and its field lists hold fieldnames only (PE-18), refused on save and left out
on read.
"""

from __future__ import annotations

import json

from core.exceptions import ValidationError

INVALID_JSON = "Layout must be valid JSON"
FIELDNAMES_ONLY = "A layout's field lists hold fieldnames only"


def parse_layout(text):
    """The layout as Python data; 417 when it is not valid JSON (PE-12c). A list or a
    dict passes through, as the old save JSON-dumps a list input."""
    if isinstance(text, (list, dict)):
        return text
    if text in (None, ""):
        return []
    try:
        return json.loads(text)
    except (TypeError, ValueError, RecursionError):
        raise ValidationError(INVALID_JSON) from None


def _all_field_lists(layout) -> list[list]:
    """Every `fields` list; a layout nested too deep to walk is 417 like invalid JSON
    (PE-12c), not a 500."""
    try:
        return list(_field_lists(layout))
    except RecursionError:
        raise ValidationError(INVALID_JSON) from None


def _field_lists(node):
    """Every `fields` list anywhere in the layout."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "fields" and isinstance(value, list):
                yield value
            else:
                yield from _field_lists(value)
    elif isinstance(node, list):
        for item in node:
            yield from _field_lists(item)


def check_fieldnames_only(layout) -> None:
    """PE-18 on save: every entry of every `fields` list is a string, else 417."""
    for fields in _all_field_lists(layout):
        if any(not isinstance(entry, str) for entry in fields):
            raise ValidationError(FIELDNAMES_ONLY)


def keep_fieldnames_only(layout):
    """PE-18 on read: each `fields` list keeps its string entries only (in place on a
    parsed copy)."""
    for fields in _all_field_lists(layout):
        fields[:] = [entry for entry in fields if isinstance(entry, str)]
    return layout


def validated_layout_text(value) -> str:
    """The text to store: valid JSON whose field lists hold fieldnames only."""
    layout = parse_layout(value)
    check_fieldnames_only(layout)
    return value if isinstance(value, str) else json.dumps(layout)
