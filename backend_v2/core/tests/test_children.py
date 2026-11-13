import pytest

from core.children import child_table_specs, prepare_rows
from core.exceptions import MandatoryError
from tests_support.models import Widget, WidgetNote, WidgetRow


pytestmark = pytest.mark.django_db


def test_declared_child_specs_resolve_fk_and_polymorphic_shapes():
    specs = child_table_specs(
        Widget, {"rows": "tests_support.WidgetRow"}
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


def test_prepare_rows_reports_the_old_mandatory_child_message():
    with pytest.raises(MandatoryError) as caught:
        prepare_rows(WidgetRow, [{}], fieldname="rows", parent_field="parent")

    assert caught.value.messages == [
        "Error: <strong>Foundation Widget Row</strong> Row #1: "
        "Value missing for: Value"
    ]
