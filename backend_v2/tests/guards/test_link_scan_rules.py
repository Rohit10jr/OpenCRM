"""Guard row-rule classification for project models reachable by link scans."""

from django.apps import apps
from django.db import models
from django.test.utils import isolate_apps

from core.delete import IGNORE_LINKS_ON_DELETE
from core.doctypes import doctype_of, is_child_table
from core.models import BaseDocument
from core.resources import rules_for
from tests.guards.test_resource_access import TEST_MODEL_EXCLUSIONS


class DeclaredRules:
    @staticmethod
    def list_rule(user):
        return None

    @staticmethod
    def has_object_rule(user, document, ptype):
        return None


def _is_reachable(model):
    if getattr(model, "DYNAMIC_LINK_FIELDS", ()):
        return True
    return any(
        isinstance(field, (models.ForeignKey, models.OneToOneField))
        and getattr(field.remote_field.model, "DOCTYPE", None)
        for field in model._meta.concrete_fields
    )


def _unclassifiable_link_models(installed_models):
    failures = []
    for model in installed_models:
        if not issubclass(model, BaseDocument):
            continue
        if model._meta.app_label in TEST_MODEL_EXCLUSIONS or not _is_reachable(model):
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
