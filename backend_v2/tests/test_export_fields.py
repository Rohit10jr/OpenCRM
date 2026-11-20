"""Export's field-info provider (specs/CONFIGURATION.md 4.5; temp A-35).

New: no old test calls `get_field_info` directly (`backend/crm_app/api/reportview.py`'s
callers are the export tests of SALES, CONTACTS and ACTIVITIES, which port with them).
None of this unit's doctypes has a Duration, Text Editor, Long Text or Rating field, so
those types are tested through a metadata overlay on a `tests_support` model.
"""

import pytest

from configuration.export_fields import export_field_info_for
from configuration.models import FCRMSettings
from core.mixins.export import ListExportMixin
from tests_support.models import Widget

pytestmark = pytest.mark.django_db

OVERLAY = {
    ("Foundation Widget", "duration"): {"fieldname": "duration", "label": "Duration", "fieldtype": "Duration"},
    ("Foundation Widget", "notes"): {"fieldname": "notes", "label": "Notes", "fieldtype": "Text Editor"},
    ("Foundation Widget", "story"): {"fieldname": "story", "label": "", "fieldtype": "Long Text"},
    ("Foundation Widget", "stars"): {"fieldname": "stars", "label": "Stars", "fieldtype": "Rating"},
}


def overlay(doctype, fieldname):
    return OVERLAY.get((doctype, fieldname))


def test_name_is_labelled_id():
    info = export_field_info_for(FCRMSettings)(["name"])
    assert info == [{"fieldname": "name", "label": "ID", "fieldtype": "Data"}]


def test_a_metadata_field_gives_its_label_and_type():
    """Expected values read from the file itself (upstream labels brand_name "Name")."""
    from configuration import field_meta

    fields = ["brand_name", "enable_forecasting"]
    info = export_field_info_for(FCRMSettings)(fields)
    expected = [
        (field_meta.get_field("FCRM Settings", f)["label"], field_meta.get_fieldtype("FCRM Settings", f))
        for f in fields
    ]
    assert [(row["label"], row["fieldtype"]) for row in info] == expected
    assert expected[1][1] == "Check"


def test_a_standard_column_takes_the_standard_label_and_type():
    info = export_field_info_for(FCRMSettings)(["creation", "owner", "idx", "unknown_col"])
    assert [(row["label"], row["fieldtype"]) for row in info] == [
        ("Created On", "Datetime"),
        ("Created By", "Link"),
        ("idx", "Int"),
        ("unknown_col", "Data"),
    ]


def test_the_rich_types_come_through_an_overlay():
    info = export_field_info_for(Widget, get_field=overlay)(["duration", "notes", "story", "stars"])
    assert [(row["label"], row["fieldtype"]) for row in info] == [
        ("Duration", "Duration"),
        ("Notes", "Text Editor"),
        ("story", "Long Text"),
        ("Stars", "Rating"),
    ]


def test_a_viewset_assigns_the_factorys_provider():
    class ExportingViewSet(ListExportMixin):
        export_field_info = staticmethod(export_field_info_for(FCRMSettings))

    assert ExportingViewSet().get_export_field_info(["name"])[0]["label"] == "ID"
