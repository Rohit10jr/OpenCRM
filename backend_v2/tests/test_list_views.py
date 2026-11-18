"""List-view definitions (specs/CONFIGURATION.md 4.8; temp A-40).

FOUNDATION Q6: a class in each app's `list_views.py`, named by the ViewSet's
`list_view_class`. A `parse` twin of ``backend/tests/test_list_definitions.py`` (its
other cases are the SALES, ACTIVITIES and CONTACTS definitions). `list_definition_for`
reads the production routes, so the test resources' definitions are read off their
ViewSets.
"""

import pytest

from configuration.list_views import ListView, list_definition_for
from tests_support.list_views import WidgetListView
from tests_support.views import SearchableDocumentViewSet, WidgetViewSet


def test_the_base_is_the_old_fallback():
    assert ListView.default_columns() == [
        {"label": "Name", "type": "Data", "key": "name", "width": "16rem"},
        {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
    ]
    assert ListView.default_rows() == ["name"]
    assert ListView.default_kanban_settings() == {}
    assert ListView.hidden_fields == ()
    assert ListView.has_list_data() is False
    assert ListView.parse([{"name": "x"}]) == [{"name": "x"}]


def test_a_definition_sets_every_hook():
    assert WidgetViewSet.list_view_class is WidgetListView
    assert WidgetListView.has_list_data() is True
    assert WidgetListView.default_rows() == ["name", "widget_name", "status", "notes", "modified"]
    assert WidgetListView.default_kanban_settings()["title_field"] == "widget_name"
    assert WidgetListView.hidden_fields == ("notes",)


def test_a_resource_without_a_definition_names_none():
    assert getattr(SearchableDocumentViewSet, "list_view_class", None) is None


def test_the_answers_are_copies():
    columns = WidgetListView.default_columns()
    columns[0]["width"] = "1rem"
    assert WidgetListView.default_columns()[0]["width"] == "12rem"
    settings = WidgetListView.default_kanban_settings()
    settings["title_field"] = "changed"
    assert WidgetListView.default_kanban_settings()["title_field"] == "widget_name"


def test_parse_runs_the_definitions_hook():
    """Twin of the old `parse_list_data` cases: the definition rewrites the rows it is
    given."""
    assert WidgetListView.parse([{"name": "a"}]) == [{"name": "a", "parsed": True}]


@pytest.mark.parametrize(
    ("doctype", "expected"),
    [
        ("CRM View Settings", ListView),
        ("FCRM Settings", ListView),
        ("No Such Doctype", None),
        ("Version", None),
        ("CRM Dropdown Item", None),
        ("", None),
    ],
)
def test_list_definition_for_a_doctype(doctype, expected):
    assert list_definition_for(doctype) is expected
