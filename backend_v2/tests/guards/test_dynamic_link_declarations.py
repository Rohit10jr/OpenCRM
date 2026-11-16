"""Require every doctype/name column pair to declare its rename behavior."""

from django.apps import apps
from django.db import models
from django.test.utils import isolate_apps

from core.delete import IGNORE_LINKS_ON_DELETE, _dynamic_link_declarations
from core.doctypes import doctype_of
from core.models import BaseDocument, Version


OLD_DYNAMIC_LINK_PAIRS = (
    ("reference_doctype", "reference_name"),
    ("reference_doctype", "reference_docname"),
    ("reference_type", "reference_name"),
    ("attached_to_doctype", "attached_to_name"),
    ("ref_doctype", "docname"),
    ("link_doctype", "link_name"),
    ("notification_type_doctype", "notification_type_doc"),
)


def _expected_dynamic_link_pairs(model):
    columns = {field.name for field in model._meta.concrete_fields}
    expected = {
        pair
        for pair in OLD_DYNAMIC_LINK_PAIRS
        if pair[0] in columns and pair[1] in columns
    }
    for doctype_field in columns:
        if not doctype_field.endswith("_doctype"):
            continue
        stem = doctype_field[: -len("_doctype")]
        for suffix in ("_name", "_docname", "_doc"):
            name_field = stem + suffix
            if name_field in columns:
                expected.add((doctype_field, name_field))
    return expected


def _missing_dynamic_link_declarations(installed_models):
    failures = []
    for model in installed_models:
        if not isinstance(model, type) or not issubclass(model, BaseDocument):
            continue
        expected = _expected_dynamic_link_pairs(model)
        declared = set(_dynamic_link_declarations(model))
        for pair in sorted(expected - declared):
            failures.append((model._meta.label, pair))
    return sorted(failures)


def test_every_doctype_name_pair_is_declared_for_rename():
    missing = _missing_dynamic_link_declarations(apps.get_models())

    assert not missing, "Undeclared doctype/name pairs: " + repr(missing)


def test_version_declares_rename_pair_but_delete_still_ignores_it():
    assert set(_dynamic_link_declarations(Version)) == {
        ("ref_doctype", "docname")
    }
    assert doctype_of(Version) in IGNORE_LINKS_ON_DELETE


@isolate_apps("core")
def test_guard_rejects_an_undeclared_pair():
    class UndeclaredReference(BaseDocument):
        DOCTYPE = "Guard Undeclared Reference"
        reference_doctype = models.CharField(max_length=140)
        reference_name = models.CharField(max_length=140)

        class Meta:
            app_label = "core"

    assert _missing_dynamic_link_declarations([UndeclaredReference]) == [
        (
            "core.UndeclaredReference",
            ("reference_doctype", "reference_name"),
        )
    ]
