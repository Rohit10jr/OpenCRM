"""Guard row-rule classification for project models reachable by link scans."""

from types import ModuleType

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.test.utils import isolate_apps

from core.delete import IGNORE_LINKS_ON_DELETE
from core.doctypes import doctype_of, is_child_table
from core.mixins.linked import is_link_source
from core.models import BaseDocument
from core.resources import _declared_rules, rules_for
from tests.guards.test_resource_access import TEST_MODEL_EXCLUSIONS


class DeclaredRules:
    @staticmethod
    def list_rule(user):
        return None

    @staticmethod
    def has_object_rule(user, document, ptype):
        return None


class InstanceMethodRules:
    def list_rule(self, user):
        return None

    def has_object_rule(self, user, document, ptype):
        return None


def _invalid_declared_rule_providers(installed_models):
    failures = []
    for model in sorted(installed_models, key=lambda item: item._meta.label):
        if "ROW_RULES" not in model.__dict__:
            continue
        try:
            _declared_rules(model)
        except ImproperlyConfigured as exc:
            failures.append(str(exc))
    return failures


def _unclassifiable_link_models(installed_models):
    failures = []
    for model in installed_models:
        if not issubclass(model, BaseDocument):
            continue
        if model._meta.app_label in TEST_MODEL_EXCLUSIONS or not is_link_source(model):
            continue
        if is_child_table(model) or doctype_of(model) in IGNORE_LINKS_ON_DELETE:
            continue
        if rules_for(model) is None:
            failures.append(model._meta.label)
    return sorted(failures)


def test_every_link_scan_model_has_a_row_rule_classification():
    failures = _unclassifiable_link_models(apps.get_models())

    assert not failures, "Link-scan models without a row-rule classification: " + repr(
        failures
    )


def test_every_declared_row_rule_provider_is_valid():
    failures = _invalid_declared_rule_providers(apps.get_models())

    assert not failures, "Invalid declared row-rule providers: " + repr(failures)


@isolate_apps("core")
def test_declared_rule_guard_rejects_instance_methods():
    class UnroutedDocument(BaseDocument):
        DOCTYPE = "Guard Instance Rule Fixture"
        ROW_RULES = "tests.guards.test_link_scan_rules.InstanceMethodRules"

        class Meta:
            app_label = "core"

    assert _invalid_declared_rule_providers([UnroutedDocument]) == [
        "core.UnroutedDocument.ROW_RULES "
        "'tests.guards.test_link_scan_rules.InstanceMethodRules' method list_rule "
        "must be a staticmethod"
    ]


@isolate_apps("core")
def test_declared_rule_guard_allows_module_provider(monkeypatch):
    provider = ModuleType("module_rule_provider")
    provider.list_rule = lambda user: None
    provider.has_object_rule = lambda user, document, ptype: None

    class UnroutedDocument(BaseDocument):
        DOCTYPE = "Guard Module Rule Fixture"
        ROW_RULES = "tests.guards.module_rule_provider"

        class Meta:
            app_label = "core"

    monkeypatch.setattr("core.resources.import_string", lambda path: provider)

    assert _invalid_declared_rule_providers([UnroutedDocument]) == []


@isolate_apps("core")
def test_link_scan_guard_requires_and_resolves_declared_rules():
    class TargetDocument(BaseDocument):
        DOCTYPE = "Link Guard Target"

        class Meta:
            app_label = "core"

    class LinkingDocument(BaseDocument):
        DOCTYPE = "Link Guard Source"
        target = models.ForeignKey(TargetDocument, on_delete=models.PROTECT)

        class Meta:
            app_label = "core"

    models_to_check = [TargetDocument, LinkingDocument]
    assert _unclassifiable_link_models(models_to_check) == ["core.LinkingDocument"]

    LinkingDocument.ROW_RULES = "tests.guards.test_link_scan_rules.DeclaredRules"
    assert _unclassifiable_link_models(models_to_check) == []


@isolate_apps("core")
def test_link_scan_guard_classifies_conventional_reference_pairs():
    class ReferencingDocument(BaseDocument):
        DOCTYPE = "Link Guard Conventional Source"
        reference_doctype = models.CharField(max_length=140)
        reference_name = models.CharField(max_length=140)

        class Meta:
            app_label = "core"

    assert _unclassifiable_link_models([ReferencingDocument]) == [
        "core.ReferencingDocument"
    ]

    ReferencingDocument.ROW_RULES = (
        "tests.guards.test_link_scan_rules.DeclaredRules"
    )
    assert _unclassifiable_link_models([ReferencingDocument]) == []
