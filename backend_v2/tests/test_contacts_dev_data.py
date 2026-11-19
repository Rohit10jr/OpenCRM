"""CONTACTS' development data (specs/CONTACTS.md §4 "Reference rows"; milestone 1).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_salutation_gender.py:35-47`` (the
lists exist, and the install step puts a deleted row back) and
``backend/tests/test_seed_defaults.py:122-123``, `:253` (the 51 industries). The old
`seed_defaults` is `seed_dev_data`'s two CONTACTS steps. New: the clear step removes only
what the seed made.
"""

import pytest

from contacts import dev_data, reference_rows
from contacts.models import CRMIndustry, Gender, Salutation

pytestmark = pytest.mark.django_db


def test_the_migration_wrote_the_lists_so_the_step_adds_none(administrator):
    assert dev_data.add_reference_rows(administrator) == 0


def test_a_deleted_row_is_put_back_by_the_seed_step(administrator):
    Salutation.objects.filter(pk="Prof").delete()
    assert dev_data.add_reference_rows(administrator) == 1
    assert Salutation.objects.filter(pk="Prof").exists()


def test_the_51_industries_are_written_once(administrator):
    assert len(reference_rows.INDUSTRIES) == 51
    assert dev_data.write_industries(administrator) == 51
    assert set(CRMIndustry.objects.values_list("pk", flat=True)) == set(reference_rows.INDUSTRIES)
    assert dev_data.write_industries(administrator) == 0


def test_clear_removes_the_seeded_industries_and_keeps_a_restored_reference_row(administrator):
    """A restored salutation or gender is promised to every database: never cleared."""
    Gender.objects.filter(pk="Other").delete()
    CRMIndustry(industry="Handmade").save(user=administrator)
    dev_data.add_reference_rows(administrator)
    dev_data.write_industries(administrator)

    assert dev_data.clear_reference_rows(administrator) == 0
    assert dev_data.clear_industries(administrator) == 51
    assert set(Gender.objects.values_list("pk", flat=True)) == set(reference_rows.GENDERS)
    assert list(CRMIndustry.objects.values_list("pk", flat=True)) == ["Handmade"]


def test_both_steps_are_registered_after_configurations():
    from core.dev_data import STEPS

    assert [step.key for step in STEPS][4:] == ["reference_rows", "industries"]


def test_seed_dev_data_puts_a_deleted_salutation_back(monkeypatch):
    import io

    from django.core.management import call_command

    from tests.test_dev_data_commands import PASSWORDS

    for variable, value in PASSWORDS.items():
        monkeypatch.setenv(variable, value)
    Salutation.objects.filter(pk="Prof").delete()
    call_command("seed_dev_data", stdout=io.StringIO())
    assert Salutation.objects.filter(pk="Prof").exists()
    call_command("clear_dev_data", stdout=io.StringIO())
    assert Salutation.objects.filter(pk="Prof").exists()
