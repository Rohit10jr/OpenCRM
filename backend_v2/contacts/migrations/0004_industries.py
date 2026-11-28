"""Write the 51 industries (specs/CONFIGURATION.md §10.1-10.2, CONTACTS §4 "Reference
rows"; owner, temp A-48 group 4).

No longer a `seed_dev_data` step: a database has them from its first migrate. The list
is the shared data constant `contacts.reference_rows.INDUSTRIES`; the writing code is
frozen here, on the historical model, `create` with every column, as `contacts/0002`.
An existing row is left alone.
"""

from datetime import timedelta

from django.db import migrations
from django.utils import timezone

from contacts.reference_rows import INDUSTRIES


def write_industries(apps, schema_editor):
    CRMIndustry = apps.get_model("contacts", "CRMIndustry")
    existing = set(CRMIndustry._default_manager.values_list("pk", flat=True))
    now = timezone.now()
    for offset, value in enumerate(INDUSTRIES):
        if value in existing:
            continue
        stamp = now + timedelta(microseconds=offset)
        CRMIndustry._default_manager.create(
            name=value,
            industry=value,
            owner_id="Administrator",
            modified_by_id="Administrator",
            creation=stamp,
            modified=stamp,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("contacts", "0003_dynamic_link_address"),
        ("accounts", "0002_seed_roles_and_users"),
    ]

    operations = [migrations.RunPython(write_industries, migrations.RunPython.noop)]
