"""Acceptance criteria 2 and 3 - the six naming strategies, and series atomicity.

PHASE_0_FOUNDATION.md section 2.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from django.db import connection, connections

from frappe_core.models import NamingSeriesCounter
from frappe_core.naming import Format, Hash, NameError_, NamingSeries, next_series_value
from tests_support.models import (
    CounterDoc,
    FieldDoc,
    FormatDoc,
    HashDoc,
    PromptDoc,
    SeriesDoc,
    Widget,
)

pytestmark = pytest.mark.django_db


# --- strategy 1: naming_series ------------------------------------------------


def test_naming_series_produces_prefixed_padded_name():
    doc = SeriesDoc.objects.create(label="first")
    year = datetime.now(timezone.utc).year
    assert doc.name == f"PZS-{year}-00001"


def test_naming_series_increments():
    names = [SeriesDoc.objects.create(label=str(i)).name for i in range(3)]
    year = datetime.now(timezone.utc).year
    assert names == [
        f"PZS-{year}-00001",
        f"PZS-{year}-00002",
        f"PZS-{year}-00003",
    ]


def test_naming_series_counters_are_per_prefix():
    SeriesDoc.objects.create(label="s")
    Widget.objects.create(widget_name="w")
    year = datetime.now(timezone.utc).year
    assert NamingSeriesCounter.objects.get(prefix=f"PZS-{year}-").current == 1
    assert NamingSeriesCounter.objects.get(prefix=f"PZW-{year}-").current == 1


@pytest.mark.parametrize(
    "pattern,expected_prefix,expected_digits",
    [
        ("CRM-LEAD-.YYYY.-", "CRM-LEAD-{year}-", 5),
        ("CRM-DEAL-.YYYY.-", "CRM-DEAL-{year}-", 5),
        ("ABC-.YY.-.MM.-", "ABC-{yy}-{mm}-", 5),
        ("PLAIN-", "PLAIN-", 5),
        ("X-.####", "X-", 4),
    ],
)
def test_naming_series_prefix_resolution(pattern, expected_prefix, expected_digits):
    now = datetime(2026, 8, 14, tzinfo=timezone.utc)
    prefix, digits = NamingSeries(pattern).resolve_prefix(None, now=now)
    assert prefix == expected_prefix.format(year=2026, yy=26, mm="08")
    assert digits == expected_digits


def test_naming_series_matches_the_spec_example():
    """PHASE_0_FOUNDATION.md section 2: ``CRM-LEAD-.YYYY.-`` -> ``CRM-LEAD-2026-00001``."""
    strategy = NamingSeries("CRM-LEAD-.YYYY.-")
    prefix, digits = strategy.resolve_prefix(None, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert f"{prefix}{1:0{digits}d}" == "CRM-LEAD-2026-00001"


# --- strategy 2: field:<name> -------------------------------------------------


def test_field_value_uses_the_field_verbatim():
    """Not slugified.

    ``crm_lead.py:244-262`` round-trips a lead's free-text ``organization`` through the
    organization's PK and back into ``organization_name``; slugifying would corrupt the
    display name on the next lead referencing the same organization.
    """
    doc = FieldDoc.objects.create(organization_name="Acme Corp")
    assert doc.name == "Acme Corp"


def test_field_value_strips_whitespace():
    doc = FieldDoc.objects.create(organization_name="  Acme Corp  ")
    assert doc.name == "Acme Corp"


def test_field_value_rejects_empty():
    with pytest.raises(NameError_):
        FieldDoc.objects.create(organization_name="   ")


def test_field_value_collision_raises():
    from django.db import IntegrityError, transaction

    FieldDoc.objects.create(organization_name="Acme Corp")
    with pytest.raises(IntegrityError), transaction.atomic():
        FieldDoc.objects.create(organization_name="Acme Corp")


# --- strategy 3: autoincrement ------------------------------------------------


def test_autoincrement_gives_integer_pks():
    first = CounterDoc.objects.create(label="a")
    second = CounterDoc.objects.create(label="b")
    assert isinstance(first.pk, int)
    assert second.pk == first.pk + 1


def test_autoincrement_doctypes_do_not_touch_the_series_table():
    CounterDoc.objects.create(label="a")
    assert NamingSeriesCounter.objects.count() == 0


# --- strategy 4: hash ---------------------------------------------------------


def test_hash_is_ten_hex_chars():
    doc = HashDoc.objects.create(label="x")
    assert re.fullmatch(r"[0-9a-f]{10}", doc.name)


def test_hash_names_are_unique():
    names = {HashDoc.objects.create(label=str(i)).name for i in range(25)}
    assert len(names) == 25


def test_hash_length_is_configurable():
    assert len(Hash(6).generate(None)) == 6


# --- strategy 5: format:{...} -------------------------------------------------


def test_format_interpolates_field_values():
    doc = FormatDoc.objects.create(dt="CRM Lead", type="Quick Entry")
    assert doc.name == "CRM Lead-Quick Entry"


def test_format_rejects_an_empty_result():
    with pytest.raises(NameError_):
        Format("{missing}").generate(FormatDoc(dt="", type=""))


# --- strategy 6: prompt -------------------------------------------------------


def test_prompt_accepts_a_client_supplied_name():
    doc = PromptDoc(name="my-script", label="x")
    doc.save()
    assert doc.name == "my-script"
    assert PromptDoc.objects.filter(pk="my-script").exists()


def test_prompt_rejects_a_missing_name():
    with pytest.raises(NameError_):
        PromptDoc(label="x").save()


def test_prompt_declares_it_needs_a_client_name():
    assert PromptDoc.get_name_strategy().requires_client_name is True


# --- criterion 3: atomicity ---------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_naming_series_is_atomic_under_50_concurrent_creates():
    """50 real threads, 50 real connections, one shared prefix.

    ``select_for_update()`` must serialise them; a ``max(id)+1`` implementation
    collapses here into duplicate names.
    """
    prefix = "CONCURRENT-TEST-"
    errors: list[Exception] = []

    def claim():
        try:
            return next_series_value(prefix)
        except Exception as exc:  # pragma: no cover - surfaced via the assert below
            errors.append(exc)
            return None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(lambda _: claim(), range(50)))

    assert not errors, f"concurrent naming raised: {errors!r}"
    values = sorted(v for v in results if v is not None)
    assert len(values) == 50
    assert values == list(range(1, 51)), "counter handed out a duplicate or skipped one"
    assert NamingSeriesCounter.objects.get(prefix=prefix).current == 50


@pytest.mark.django_db(transaction=True)
def test_concurrent_document_creates_get_unique_names():
    """The same race, through the model layer rather than the counter directly."""
    errors: list[Exception] = []

    def create(i):
        try:
            return SeriesDoc.objects.create(label=str(i)).name
        except Exception as exc:  # pragma: no cover
            errors.append(exc)
            return None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=25) as pool:
        names = list(pool.map(create, range(25)))

    assert not errors, f"concurrent create raised: {errors!r}"
    assert len(set(names)) == 25
    assert SeriesDoc.objects.count() == 25


def test_postgres_is_the_backend_under_test():
    """The like/ilike and select_for_update criteria are Postgres-specific."""
    assert connection.vendor == "postgresql"
