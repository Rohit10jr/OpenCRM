"""Model-to-row-rule resolution and its startup check."""

from types import ModuleType

import pytest
from django.test import override_settings
from django.test.utils import isolate_apps
from django.urls import path

from core.checks import check_resource_rule_viewsets
from core.models import BaseDocument
from core.resources import clear_rules_cache, rules_for
from core.views import DocumentViewSet
from tests_support.models import SecuredDocument, SingletonDocument, Widget
from tests_support.views import (
    SecuredDocumentViewSet,
    SingletonDocumentViewSet,
    WidgetViewSet,
)


class DeclaredRules:
    @staticmethod
    def list_rule(user):
        return None

    @staticmethod
    def has_object_rule(user, document, ptype):
        return None


@pytest.fixture(autouse=True)
def _fresh_rule_map():
    clear_rules_cache()
    yield
    clear_rules_cache()


def _viewset(model, name):
    serializer = type(
        f"{name}Serializer",
        (),
        {"Meta": type("Meta", (), {"model": model})},
    )
    return type(name, (DocumentViewSet,), {"serializer_class": serializer})


def _urlconf(*routes):
    urlconf = ModuleType("test_resource_urlconf")
    urlconf.urlpatterns = list(routes)
    return urlconf


def _route(prefix, viewset):
    return path(prefix, viewset.as_view({"get": "list"}))


def test_rules_for_finds_test_resource_viewsets():
    assert rules_for(Widget) is WidgetViewSet
    assert rules_for(SecuredDocument) is SecuredDocumentViewSet
    assert rules_for(SingletonDocument) is SingletonDocumentViewSet


@isolate_apps("core")
def test_rules_for_returns_none_for_unrouted_model_without_declaration():
    class UnroutedDocument(BaseDocument):
        DOCTYPE = "Unrouted Rule Fixture"

        class Meta:
            app_label = "core"

    assert rules_for(UnroutedDocument) is None


@isolate_apps("core")
def test_rules_for_resolves_declared_rules_on_unrouted_model():
    class UnroutedDocument(BaseDocument):
        DOCTYPE = "Declared Rule Fixture"
        ROW_RULES = "core.tests.test_resources.DeclaredRules"

        class Meta:
            app_label = "core"

    assert rules_for(UnroutedDocument) is DeclaredRules


@isolate_apps("core")
def test_rules_for_refreshes_after_urlconf_changes():
    class RoutedDocument(BaseDocument):
        DOCTYPE = "Changing URLconf Fixture"

        class Meta:
            app_label = "core"

    viewset = _viewset(RoutedDocument, "ChangingViewSet")
    urlconf = _urlconf(_route("one/", viewset))
    with override_settings(ROOT_URLCONF=urlconf):
        assert rules_for(RoutedDocument) is viewset
        urlconf.urlpatterns = []
        assert rules_for(RoutedDocument) is viewset
        clear_rules_cache()
        assert rules_for(RoutedDocument) is None


@isolate_apps("core")
def test_system_check_reports_two_viewsets_for_one_model():
    class RoutedDocument(BaseDocument):
        DOCTYPE = "Conflicting ViewSet Fixture"

        class Meta:
            app_label = "core"

    first = _viewset(RoutedDocument, "FirstViewSet")
    second = _viewset(RoutedDocument, "SecondViewSet")
    urlconf = _urlconf(_route("one/", first), _route("two/", second))

    with override_settings(ROOT_URLCONF=urlconf):
        errors = check_resource_rule_viewsets(None)

    assert [error.id for error in errors] == ["core.E001"]
    assert "FirstViewSet, SecondViewSet" in errors[0].msg


@isolate_apps("core")
def test_system_check_allows_one_viewset_at_two_prefixes():
    class RoutedDocument(BaseDocument):
        DOCTYPE = "Repeated ViewSet Fixture"

        class Meta:
            app_label = "core"

    viewset = _viewset(RoutedDocument, "RepeatedViewSet")
    urlconf = _urlconf(_route("one/", viewset), _route("two/", viewset))

    with override_settings(ROOT_URLCONF=urlconf):
        assert check_resource_rule_viewsets(None) == []
