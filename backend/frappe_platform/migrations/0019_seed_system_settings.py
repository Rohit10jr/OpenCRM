"""Write the System Settings row from the formats the site already uses (docs/FINDINGS.md 64).

Until now the seven format defaults came from ``settings.FRAPPE_SYSDEFAULTS``, which a
deployment can set from its ``.env`` (``FRAPPE_DATE_FORMAT`` and the rest). The row is
written from that same setting, so nothing a user sees changes on the day this lands; from
then on the Defaults page edits the row and the boot call reads it. A row that is already
there is left alone. Nothing to undo backwards.

Live model, as in 0014 and 0017: the table is created by 0018.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    from frappe_platform.models import SystemSettings

    SystemSettings.load()


class Migration(migrations.Migration):
    dependencies = [
        ("frappe_platform", "0018_system_settings"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
