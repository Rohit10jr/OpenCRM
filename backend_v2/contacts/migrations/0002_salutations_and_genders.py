"""Write the salutations and genders (specs/CONTACTS.md §4 "Reference rows"; decision H).

Rows the application cannot run without, as `backend/` writes them by migration
(`frappe_platform/migrations/0014_seed_salutations_and_genders.py`): a Link to either is
checked on save, so a database without them would refuse a contact that carries one.
Existing rows are left alone; the owner is Administrator, the install user.
"""

from datetime import timedelta

from django.db import migrations
from django.utils import timezone

from contacts.reference_rows import GENDERS, SALUTATIONS


def _write(model, fieldname, values):
    existing = set(model._default_manager.values_list("pk", flat=True))
    now = timezone.now()
    for offset, value in enumerate(values):
        if value in existing:
            continue
        stamp = now + timedelta(microseconds=offset)
        model._default_manager.create(
            name=value,
            owner_id="Administrator",
            modified_by_id="Administrator",
            creation=stamp,
            modified=stamp,
            **{fieldname: value},
        )


def write_rows(apps, schema_editor):
    _write(apps.get_model("contacts", "Salutation"), "salutation", SALUTATIONS)
    _write(apps.get_model("contacts", "Gender"), "gender", GENDERS)


class Migration(migrations.Migration):
    dependencies = [
        ("contacts", "0001_initial"),
        ("accounts", "0002_seed_roles_and_users"),
    ]

    operations = [migrations.RunPython(write_rows, migrations.RunPython.noop)]
