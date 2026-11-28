"""CONTACTS' default rows (specs/CONFIGURATION.md §10, CONTACTS §4 "Reference rows").

Salutations and genders come from `contacts/0002`, industries from `contacts/0004`; no
`seed_dev_data` step writes or clears them any more (owner, temp A-48 group 4). Ported
(REBUILD_PLAN S14) from ``backend/tests/test_salutation_gender.py:35-47`` and
``backend/tests/test_seed_defaults.py:122-123``, `:253`, against the migrations: the
restore cases (a deleted row put back) come with `restore_defaults` (§10.8 step 3).
"""

import importlib
import io

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from contacts import reference_rows
from contacts.models import CRMIndustry, Gender, Salutation

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _dev_data_allowed(settings):
    """Two tests run seed_dev_data / clear_dev_data; the test settings leave the flag off."""
    settings.DEV_DATA_ALLOWED = True


def test_the_migrations_wrote_the_reference_lists():
    assert set(Salutation.objects.values_list("pk", flat=True)) >= set(reference_rows.SALUTATIONS)
    assert set(Gender.objects.values_list("pk", flat=True)) >= set(reference_rows.GENDERS)


def test_the_migration_wrote_the_51_industries():
    assert len(reference_rows.INDUSTRIES) == 51
    assert set(CRMIndustry.objects.values_list("pk", flat=True)) == set(reference_rows.INDUSTRIES)
    row = CRMIndustry.objects.get(pk=reference_rows.INDUSTRIES[0])
    assert (row.industry, row.owner_id, row.modified_by_id) == (
        reference_rows.INDUSTRIES[0], "Administrator", "Administrator"
    )


def test_the_industries_migration_on_its_own_apps_writes_what_is_missing(administrator):
    """§10.6 "New": the function on historical apps, after deleting rows."""
    CRMIndustry.objects.filter(pk__in=reference_rows.INDUSTRIES[:3]).delete()
    CRMIndustry(industry="Handmade").save(user=administrator)
    apps = MigrationLoader(connection).project_state(("contacts", "0004_industries")).apps
    module = importlib.import_module("contacts.migrations.0004_industries")

    module.write_industries(apps, None)

    names = set(CRMIndustry.objects.values_list("pk", flat=True))
    assert names == set(reference_rows.INDUSTRIES) | {"Handmade"}
    # Every column §10.2 lists, on a row the function itself wrote (A-78 finding 4).
    for name in reference_rows.INDUSTRIES[:3]:
        row = CRMIndustry.objects.get(pk=name)
        assert row.industry == name
        assert row.owner_id == row.modified_by_id == "Administrator"
        assert row.creation == row.modified
        assert (row.idx, row.docstatus) == (0, 0)
        assert (row._assign, row._liked_by, row._comments, row._user_tags) == ([], [], [], "")


def test_only_the_users_step_is_left():
    from core.dev_data import STEPS

    assert [step.key for step in STEPS] == ["users"]


def test_clear_dev_data_leaves_every_industry_salutation_and_gender(administrator, monkeypatch):
    from tests.test_dev_data_commands import PASSWORDS

    for variable, value in PASSWORDS.items():
        monkeypatch.setenv(variable, value)
    CRMIndustry(industry="Handmade").save(user=administrator)
    before = (
        set(CRMIndustry.objects.values_list("pk", flat=True)),
        set(Salutation.objects.values_list("pk", flat=True)),
        set(Gender.objects.values_list("pk", flat=True)),
    )
    call_command("seed_dev_data", stdout=io.StringIO())
    call_command("clear_dev_data", stdout=io.StringIO())
    after = (
        set(CRMIndustry.objects.values_list("pk", flat=True)),
        set(Salutation.objects.values_list("pk", flat=True)),
        set(Gender.objects.values_list("pk", flat=True)),
    )
    assert after == before


def test_seed_dev_data_no_longer_puts_a_salutation_back(monkeypatch):
    """The reference step is retired; `restore_defaults` puts it back (step 3)."""
    from tests.test_dev_data_commands import PASSWORDS

    for variable, value in PASSWORDS.items():
        monkeypatch.setenv(variable, value)
    Salutation.objects.filter(pk="Prof").delete()
    call_command("seed_dev_data", stdout=io.StringIO())
    assert not Salutation.objects.filter(pk="Prof").exists()
