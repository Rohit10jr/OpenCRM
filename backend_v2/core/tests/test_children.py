import pytest
from django.db import models
from django.test.utils import isolate_apps

from core import children
from core.children import child_table_specs, prepare_rows
from core.exceptions import MandatoryError
from core.models import BaseDocument
from tests_support.models import Widget, WidgetNote, WidgetRow
from tests_support.serializers import WidgetSerializer


pytestmark = pytest.mark.django_db
_document_user_model = Widget._meta.get_field("owner").remote_field.model


def _explicit_field_child_model():
    class ExplicitFieldChild(BaseDocument):
        DOCTYPE = "Foundation Explicit Field Child"
        IS_CHILD_TABLE = True
        CHILD_FIELDS = (
            "name",
            "owner",
            "modified_by",
            "creation",
            "modified",
            "idx",
            "docstatus",
            "_assign",
            "_liked_by",
            "_comments",
            "_user_tags",
            "listed_value",
        )
        listed_value = models.CharField(max_length=140, blank=True, default="")
        unlisted_value = models.CharField(max_length=140, blank=True, default="")

        class Meta:
            app_label = "tests_support"
            managed = False

    for field_name in ("owner", "modified_by"):
        field = ExplicitFieldChild._meta.get_field(field_name)
        field.remote_field.model = _document_user_model

    return ExplicitFieldChild


def test_declared_child_specs_resolve_fk_and_polymorphic_shapes():
    specs = child_table_specs(
        Widget, {"rows": ("tests_support.WidgetRow", "parent")}
    )

    assert specs["rows"] == {
        "model": WidgetRow,
        "fk": "parent",
        "polymorphic": False,
    }
    assert specs["poly_rows"] == {
        "model": WidgetNote,
        "fk": None,
        "polymorphic": True,
    }


@isolate_apps("tests_support")
def test_multiple_parent_links_require_a_named_parent_field(monkeypatch):
    class DoubleWidgetRow(models.Model):
        CHILD_FIELDS = ("parent", "related_widget")
        parent = models.ForeignKey(Widget, on_delete=models.CASCADE, related_name="+")
        related_widget = models.ForeignKey(
            Widget, on_delete=models.PROTECT, related_name="+"
        )

        class Meta:
            app_label = "tests_support"

    real_model = children._model
    monkeypatch.setattr(
        children,
        "_model",
        lambda label: (
            DoubleWidgetRow
            if label == "tests_support.DoubleWidgetRow"
            else real_model(label)
        ),
    )

    with pytest.raises(TypeError) as caught:
        child_table_specs(Widget, {"rows": "tests_support.DoubleWidgetRow"})

    assert str(caught.value) == (
        "Child table tests_support.DoubleWidgetRow has multiple links to "
        "tests_support.Widget: parent, related_widget. Declare one as "
        '("tests_support.DoubleWidgetRow", "<field_name>") in CHILD_TABLES.'
    )

    specs = child_table_specs(
        Widget,
        {"rows": ("tests_support.DoubleWidgetRow", "parent")},
    )
    assert specs["rows"] == {
        "model": DoubleWidgetRow,
        "fk": "parent",
        "polymorphic": False,
    }


def test_prepare_rows_reports_the_old_mandatory_child_message():
    with pytest.raises(MandatoryError) as caught:
        prepare_rows(WidgetRow, [{}], fieldname="rows", parent_field="parent")

    assert caught.value.messages == [
        "Error: <strong>Foundation Widget Row</strong> Row #1: "
        "Value missing for: Value"
    ]


@isolate_apps("tests_support")
def test_unlisted_child_column_is_not_rendered(alice):
    ExplicitFieldChild = _explicit_field_child_model()
    child = ExplicitFieldChild(
        listed_value="shown",
        unlisted_value="withheld",
    )
    serializer = WidgetSerializer(context={"user": alice})

    data = serializer._represent_child(child)

    assert data["listed_value"] == "shown"
    assert "unlisted_value" not in data


@isolate_apps("tests_support")
def test_unlisted_child_column_is_not_written():
    ExplicitFieldChild = _explicit_field_child_model()
    payload = prepare_rows(
        ExplicitFieldChild,
        [{"listed_value": "kept", "unlisted_value": "dropped"}],
        fieldname="rows",
    )[0]

    assert payload["listed_value"] == "kept"
    assert "unlisted_value" not in payload


@isolate_apps("tests_support")
def test_child_model_without_an_explicit_field_list_raises(monkeypatch):
    ExplicitFieldChild = _explicit_field_child_model()
    monkeypatch.delattr(ExplicitFieldChild, "CHILD_FIELDS")

    with pytest.raises(TypeError) as caught:
        prepare_rows(ExplicitFieldChild, [], fieldname="rows")

    assert str(caught.value) == (
        "Child table tests_support.ExplicitFieldChild must declare CHILD_FIELDS"
    )
