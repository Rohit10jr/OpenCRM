import re
from datetime import datetime, timezone

import pytest
from django.db import IntegrityError, transaction

from core.exceptions import NameError as FrappeNameError
from core.exceptions import ValidationError
from core.models import NamingSeriesCounter
from core.naming import NamingSeries, append_number_if_name_exists, validate_name
from tests_support.models import (
    AutoIncrementDocumentFixture,
    DataImportDocument,
    FieldDocument,
    FormatDocument,
    HashDocument,
    PromptDocument,
    SeriesDocument,
)

pytestmark = pytest.mark.django_db


def save(document, user):
    document.save(user=user)
    return document


def test_naming_series_produces_five_digit_numbers(administrator):
    first = save(SeriesDocument(label="first"), administrator)
    second = save(SeriesDocument(label="second"), administrator)
    year = datetime.now(timezone.utc).year
    assert [first.name, second.name] == [
        f"FOUNDATION-{year}-00001",
        f"FOUNDATION-{year}-00002",
    ]


def test_series_counter_is_selected_for_update_and_numbers_stay_distinct(
    administrator, monkeypatch
):
    manager = NamingSeriesCounter.objects
    original = manager.select_for_update
    calls = []

    def locked(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(manager, "select_for_update", locked)
    first = save(SeriesDocument(label="first"), administrator)
    second = save(SeriesDocument(label="second"), administrator)
    assert first.name != second.name
    assert len(calls) == 2


@pytest.mark.parametrize(
    "pattern,prefix,digits",
    [
        ("CRM-LEAD-.YYYY.-", "CRM-LEAD-2026-", 5),
        ("ABC-.YY.-.MM.-", "ABC-26-08-", 5),
        ("X-.####", "X-", 4),
    ],
)
def test_series_prefix_resolution(pattern, prefix, digits):
    assert NamingSeries(pattern).resolve_prefix(
        now=datetime(2026, 8, 14, tzinfo=timezone.utc)
    ) == (prefix, digits)


def test_field_value_is_not_slugified(administrator):
    document = save(FieldDocument(title="Acme Corp"), administrator)
    assert document.name == "Acme Corp"


def test_append_number_uses_the_next_existing_suffix(administrator):
    for name in ("Acme", "Acme-1", "Acme-2"):
        save(PromptDocument(name=name), administrator)
    assert append_number_if_name_exists(PromptDocument, "Acme") == "Acme-3"


def test_field_value_requires_its_label(administrator):
    with pytest.raises(ValidationError, match="^Title is required$"):
        save(FieldDocument(title=""), administrator)


def test_hash_has_ten_hex_characters(administrator):
    document = save(HashDocument(label="x"), administrator)
    assert re.fullmatch(r"[0-9a-f]{10}", document.name)


def test_format_interpolates_fields(administrator):
    document = save(
        FormatDocument(document_type="CRM Lead", layout_type="Quick Entry"),
        administrator,
    )
    assert document.name == "CRM Lead-Quick Entry"


def test_prompt_requires_and_accepts_a_name(administrator):
    with pytest.raises(ValidationError, match="^Please set the document name$"):
        save(PromptDocument(label="missing"), administrator)
    assert save(PromptDocument(name="my-script", label="ok"), administrator).name == "my-script"


def test_autoincrement_is_an_integer(administrator):
    first = save(AutoIncrementDocumentFixture(label="a"), administrator)
    second = save(AutoIncrementDocumentFixture(label="b"), administrator)
    assert isinstance(first.pk, int)
    assert second.pk == first.pk + 1


def test_data_import_timestamp(administrator):
    document = save(DataImportDocument(reference_doctype="CRM Lead"), administrator)
    assert re.fullmatch(
        r"CRM Lead Import on \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{6}",
        document.name,
    )


@pytest.mark.parametrize("name", ["<script>", "a>b"])
def test_angle_brackets_are_rejected(name):
    with pytest.raises(FrappeNameError) as caught:
        validate_name("Widget", name)
    assert str(caught.value) == "Name cannot contain special characters like '<', '>'"


def test_new_doctype_marker_is_rejected():
    with pytest.raises(FrappeNameError) as caught:
        validate_name("Widget", "New Widget 1")
    assert str(caught.value) == (
        "There were some errors setting the name, please contact the administrator"
    )


def test_doctype_name_is_rejected_except_for_singletons():
    with pytest.raises(FrappeNameError, match="Name of Widget cannot be Widget"):
        validate_name("Widget", "Widget")
    assert validate_name("Widget", "Widget", is_single=True) == "Widget"


def test_empty_name_is_rejected():
    with pytest.raises(ValidationError, match="^No Name Specified for Widget$"):
        validate_name("Widget", "")


def test_force_insert_refuses_a_taken_name(administrator):
    save(PromptDocument(name="taken", label="original"), administrator)
    with pytest.raises(IntegrityError), transaction.atomic():
        save(PromptDocument(name="taken", label="replacement"), administrator)
    assert PromptDocument.objects.get(pk="taken").label == "original"
