"""List-view definitions stay where a list can be served, and name readable fields only
(specs/CONFIGURATION.md 4.8; temp A-40).

A child table, a withheld doctype and a settings record have no list view (PE-22): a
withheld doctype has no ViewSet at all, so the check is on child and singleton
ViewSets. The engine reads a definition's columns, rows and kanban defaults, so each
names only fields its resource lets the caller read, and every resource opting in to
`list-view/` has the seven standard fields the engine adds readable.
"""

import json

from core.doctypes import is_child_table
from core.resources import routed_viewsets
from core.views import SingletonViewSet

URLCONFS = (None, "config.test_urls")


def _viewsets():
    seen = set()
    for urlconf in URLCONFS:
        seen |= routed_viewsets(urlconf)
    return sorted(seen, key=lambda viewset: viewset.__qualname__)


def misplaced(viewsets) -> list[str]:
    return [
        viewset.__qualname__
        for viewset in viewsets
        if getattr(viewset, "list_view_class", None) is not None
        and (
            issubclass(viewset, SingletonViewSet)
            or is_child_table(viewset.serializer_class.Meta.model)
        )
    ]


def unreadable(viewsets) -> list[str]:
    problems = []
    for viewset in viewsets:
        definition = getattr(viewset, "list_view_class", None)
        if definition is None:
            continue
        named = {column.get("key") for column in definition.default_columns()}
        named |= set(definition.default_rows())
        settings = definition.default_kanban_settings()
        if settings.get("title_field"):
            named.add(settings["title_field"])
        fields = settings.get("kanban_fields") or []
        named |= set(json.loads(fields) if isinstance(fields, str) else fields)
        extra = sorted(named - set(viewset.readable_fields) - {None})
        if extra:
            problems.append(f"{viewset.__qualname__}: {extra}")
    return problems


def lacking_standard_fields(viewsets) -> list[str]:
    """The engine adds the seven standard fields to every answer's rows."""
    from configuration.list_engine import STANDARD_FIELDS
    from configuration.mixins import ListViewMixin

    standard = {descriptor["fieldname"] for descriptor in STANDARD_FIELDS}
    return [
        f"{viewset.__qualname__}: {sorted(standard - set(viewset.readable_fields))}"
        for viewset in viewsets
        if issubclass(viewset, ListViewMixin) and not standard <= set(viewset.readable_fields)
    ]


def test_every_list_view_resource_reads_the_standard_fields():
    assert lacking_standard_fields(_viewsets()) == []


def test_no_child_or_singleton_resource_names_a_list_view():
    assert misplaced(_viewsets()) == []


def test_every_definition_names_readable_fields_only():
    assert unreadable(_viewsets()) == []


def test_the_checks_catch_a_broken_definition():
    from configuration.list_views import ListView
    from tests_support.views import SingletonDocumentViewSet, WidgetViewSet

    class Unreadable(ListView):
        rows = ("name", "no_such_field")

    class BrokenWidgetViewSet(WidgetViewSet):
        list_view_class = Unreadable

    class ListedSingletonViewSet(SingletonDocumentViewSet):
        list_view_class = ListView

    class NarrowWidgetViewSet(WidgetViewSet):
        readable_fields = ("name", "widget_name")

    [problem] = unreadable([BrokenWidgetViewSet])
    assert problem.endswith("BrokenWidgetViewSet: ['no_such_field']")
    assert len(misplaced([ListedSingletonViewSet])) == 1
    assert len(lacking_standard_fields([NarrowWidgetViewSet])) == 1
