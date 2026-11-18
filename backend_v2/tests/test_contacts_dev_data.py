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


def test_clear_removes_only_what_the_seed_made(administrator):
    Gender.objects.filter(pk="Other").delete()
    CRMIndustry(industry="Handmade").save(user=administrator)
    dev_data.add_reference_rows(administrator)
    dev_data.write_industries(administrator)

    assert dev_data.clear_reference_rows(administrator) == 1
    assert dev_data.clear_industries(administrator) == 51
    assert not Gender.objects.filter(pk="Other").exists()
    assert set(Gender.objects.values_list("pk", flat=True)) == set(reference_rows.GENDERS) - {"Other"}
    assert list(CRMIndustry.objects.values_list("pk", flat=True)) == ["Handmade"]
