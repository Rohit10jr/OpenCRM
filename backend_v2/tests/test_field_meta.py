"""The field metadata file and its reader (specs/CONFIGURATION.md section 4.5).

Ported from ``backend/tests/test_phase4_metadata.py:37-87`` (internal, rewritten for
`configuration.field_meta`): the staleness check, the layout rows, the value fields, and
the platform fallback on User (`:82`). The allowlist and non-filterable cases (`:94`,
`:103`, `:152`) come with the helpers (CF5d). The rest is new.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

from configuration import field_meta
from tests.upstream_source import CRM_DOCTYPE_DIR

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"


def test_generated_field_meta_is_current():
    """Regenerate from the DocType JSON and compare with the committed file. CI checks
    frappe/crm out at the port's commit and sets CRM_UPSTREAM_DIR, so this runs there."""
    if not CRM_DOCTYPE_DIR.exists():
        # CI sets CRM_UPSTREAM_DIR; a wrong one must fail, since -rfE does not list skips
        # and the check would vanish silently (A-36 finding 8). Unset, it is a local run
        # without the owner's checkout.
        if os.environ.get("CRM_UPSTREAM_DIR"):
            pytest.fail(f"CRM_UPSTREAM_DIR is set but {CRM_DOCTYPE_DIR} does not exist")
        pytest.skip("CRM source not available")

    sys.path.insert(0, str(SCRIPTS))
    try:
        import generate_field_meta

        regenerated = generate_field_meta.build()
    finally:
        sys.path.remove(str(SCRIPTS))

    committed = json.loads(field_meta._DATA_FILE.read_text(encoding="utf-8"))
    assert committed == regenerated, (
        "doctype_meta.json is stale - run: python scripts/generate_field_meta.py"
    )


def test_the_file_holds_the_39_crm_doctypes():
    assert len(field_meta._raw()) == 39
    assert field_meta.has_meta("FCRM Settings") and field_meta.has_meta("CRM Dropdown Item")


def test_field_meta_keeps_the_layout_breaks():
    fieldtypes = {f["fieldtype"] for f in field_meta.get_fields("CRM Lead")}
    assert "Section Break" in fieldtypes
    assert "Tab Break" in fieldtypes or "Column Break" in fieldtypes


def test_value_fields_exclude_the_layout_breaks():
    fieldtypes = {f["fieldtype"] for f in field_meta.get_value_fields("CRM Lead")}
    assert not (fieldtypes & field_meta.NO_VALUE_FIELDTYPES)


@pytest.mark.django_db
def test_field_meta_falls_back_for_platform_doctypes():
    assert not field_meta.has_meta("User")
    fields = field_meta.get_fields("User")
    assert {f["fieldname"] for f in fields} >= {"name", "full_name", "enabled"}


# --- new: the fallback on backend_v2's declarations (A-35 point 6) -------------------------


@pytest.mark.django_db
def test_a_text_link_falls_back_to_link_and_its_target():
    """`test_system_settings.py:70`: System Settings' currency is Link / Currency."""
    currency = field_meta.get_field("System Settings", "currency")
    assert (currency["fieldtype"], currency["options"]) == ("Link", "Currency")


@pytest.mark.django_db
def test_choices_fall_back_to_select_with_their_options():
    date_format = field_meta.get_field("System Settings", "date_format")
    assert date_format["fieldtype"] == "Select"
    assert date_format["options"].split("\n")[0] == "yyyy-mm-dd"


@pytest.mark.django_db
def test_an_attach_field_falls_back_to_attach_image():
    assert field_meta.get_fieldtype("User", "user_image") == "Attach Image"


@pytest.mark.django_db
def test_a_dynamic_link_falls_back_to_dynamic_link():
    field = field_meta.get_field("Foundation Dynamic Reference", "reference_name")
    assert (field["fieldtype"], field["options"]) == ("Dynamic Link", "reference_doctype")


@pytest.mark.django_db
def test_no_table_row_is_made_up_for_a_child_table():
    """The old User has no TABLE_FIELD_LABELS, so no Table row for user_emails."""
    assert field_meta.get_field("User", "user_emails") is None


def test_an_unknown_doctype_has_no_fields():
    assert field_meta.get_fields("No Such Doctype") == []


def test_properties_are_a_fresh_dict():
    first = field_meta.get_doctype_properties("CRM Lead")
    first["istable"] = 99
    assert field_meta.get_doctype_properties("CRM Lead").get("istable") != 99
