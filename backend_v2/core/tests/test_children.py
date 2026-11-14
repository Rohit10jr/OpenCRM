import pytest
from django.db import models

from core import children
from core.children import child_table_specs, prepare_rows
from core.exceptions import MandatoryError
from tests_support.models import Widget, WidgetNote, WidgetRow


pytestmark = pytest.mark.django_db


class DoubleWidgetRow(models.Model):
    parent = models.ForeignKey(Widget, on_delete=models.CASCADE, related_name="+")
    related_widget = models.ForeignKey(
        Widget, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        app_label = "tests_support"


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


def test_multiple_parent_links_require_a_named_parent_field(monkeypatch):
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
