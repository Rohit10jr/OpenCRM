"""List definitions: what a list view shows by default (specs/CONFIGURATION.md 4.7, 4.8).

FOUNDATION Q6 (`specs/FOUNDATION.md:349`): a class in each app's `list_views.py`, named
by the ViewSet's `list_view_class`. Milestone 7 builds the seam the saved-view calls
read; milestone 8 adds the rest of the definition and the first classes. Until a
ViewSet names one, every served doctype answers the base: the Name and Last Modified
columns and the rows `["name"]` (old `frappe_core/registry.py:94-114`).
"""

from __future__ import annotations

import copy

from configuration.metadata import served_model
from core.doctypes import is_child_table
from core.resources import routed_rule_map


class ListView:
    """The base definition, upstream's fallback when a controller defines none."""

    columns = (
        {"label": "Name", "type": "Data", "key": "name", "width": "16rem"},
        {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
    )
    rows = ("name",)

    @classmethod
    def default_columns(cls) -> list[dict]:
        return copy.deepcopy(list(cls.columns))

    @classmethod
    def default_rows(cls) -> list[str]:
        return list(cls.rows)


def list_definition_for(doctype):
    """The list definition of a served doctype that is not a child table, else `None`
    (an unknown, withheld or child doctype: PE-14, PE-15)."""
    if not doctype:
        return None
    model = served_model(doctype)
    if model is None or is_child_table(model):
        return None
    viewset = routed_rule_map().get(model)
    return getattr(viewset, "list_view_class", None) or ListView
