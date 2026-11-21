"""Forget the dev-data records of the four retired steps (specs/CONFIGURATION.md §10.2).

Tidy-up, not safety: `clear_dev_data` reads only the steps in `core.dev_data.STEPS`, and
the default rows those steps wrote are now promised to every database. The step names
are frozen here.
"""

from django.db import migrations

RETIRED_STEPS = ("fields_layouts", "quick_filters", "form_scripts", "industries")


def forget_retired_steps(apps, schema_editor):
    DevDataRecord = apps.get_model("core", "DevDataRecord")
    DevDataRecord.objects.filter(step__in=RETIRED_STEPS).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0003_dev_data_record")]

    operations = [migrations.RunPython(forget_retired_steps, migrations.RunPython.noop)]
