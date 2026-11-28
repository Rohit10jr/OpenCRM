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
    """The base definition, upstream's fallback when a controller defines none.

    A subclass sets what the old model hooks answered (`frappe_core/registry.py:94-137`,
    `api/doc.py:145-155`): `columns` and `rows` (`default_list_data`),
    `kanban_settings` (`default_kanban_settings`), `hidden_fields` (`get_hidden_fields`)
    and `parse` (`parse_list_data`). `get_non_filterable_fields` stays on the model
    (milestone 5); the old `get_standard_filter_fields` is defined by no model and is not
    ported.
    """

    columns = (
        {"label": "Name", "type": "Data", "key": "name", "width": "16rem"},
        {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
    )
    rows = ("name",)
    kanban_settings = None
    hidden_fields = ()

    @classmethod
    def default_columns(cls) -> list[dict]:
        return copy.deepcopy(list(cls.columns))

    @classmethod
    def default_rows(cls) -> list[str]:
        return list(cls.rows)

    @classmethod
    def has_list_data(cls) -> bool:
        """The old `has_default_list_data`: a definition that sets its own columns or rows."""
        return any(
            "columns" in klass.__dict__ or "rows" in klass.__dict__
            for klass in cls.__mro__
            if klass is not ListView and issubclass(klass, ListView)
        )

    @classmethod
    def default_kanban_settings(cls) -> dict:
        return copy.deepcopy(dict(cls.kanban_settings or {}))

    @classmethod
    def parse(cls, data: list[dict]) -> list[dict]:
        return data


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
