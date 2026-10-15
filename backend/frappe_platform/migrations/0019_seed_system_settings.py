"""Write the System Settings row from the formats the site already uses (docs/FINDINGS.md 64).

Until now the seven format defaults came from ``settings.FRAPPE_SYSDEFAULTS``, which a
deployment can set from its ``.env`` (``FRAPPE_DATE_FORMAT`` and the rest). The row is
written from that same setting, so nothing a user sees changes on the day this lands; from
then on the Defaults page edits the row and the boot call reads it. A row that is already
there is left alone. Nothing to undo backwards.

The historical model and a plain insert, with the seven fields named here: a column added
to System Settings later (``language``, for finding 59) cannot break this step of a fresh
``migrate``, and a ``FRAPPE_CURRENCY`` the Currency table does not hold is copied as it
was accepted before, not refused mid-deploy.
"""

from django.conf import settings
from django.db import migrations
from django.utils import timezone

FIELDS = (
    "date_format",
    "time_format",
    "number_format",
    "float_precision",
    "currency_precision",
    "currency",
    "rounding_method",
)


def forwards(apps, schema_editor):
    model = apps.get_model("frappe_platform", "SystemSettings")
    if model._default_manager.filter(pk="System Settings").exists():
        return
    configured = getattr(settings, "FRAPPE_SYSDEFAULTS", {}) or {}
    now = timezone.now()
    model._default_manager.create(
        name="System Settings",
        owner_id="Administrator",
        modified_by_id="Administrator",
        creation=now,
        modified=now,
        **{field: configured[field] for field in FIELDS if field in configured},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("frappe_platform", "0018_system_settings"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
