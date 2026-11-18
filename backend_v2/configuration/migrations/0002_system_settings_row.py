"""Write the System Settings row from `FRAPPE_SYSDEFAULTS` (spec section 4.2, decision 13).

A row the application cannot run without, as accounts' 0002 writes roles and built-in
users; not dev data, so `DEV_DATA_ALLOWED` does not gate it. In `backend/` this is
migration 0019. An existing row is left alone.
"""

from django.conf import settings
from django.db import migrations
from django.utils import timezone

NAME = "System Settings"
FIELDS = (
    "date_format",
    "time_format",
    "number_format",
    "float_precision",
    "currency_precision",
    "currency",
    "rounding_method",
)


def write_row(apps, schema_editor):
    SystemSettings = apps.get_model("configuration", "SystemSettings")
    if SystemSettings.objects.filter(pk=NAME).exists():
        return
    configured = getattr(settings, "FRAPPE_SYSDEFAULTS", {}) or {}
    now = timezone.now()
    SystemSettings.objects.create(
        name=NAME,
        owner_id="Administrator",
        modified_by_id="Administrator",
        creation=now,
        modified=now,
        **{field: configured[field] for field in FIELDS if field in configured},
    )


def remove_row(apps, schema_editor):
    apps.get_model("configuration", "SystemSettings").objects.filter(pk=NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("configuration", "0001_initial"),
        ("accounts", "0002_seed_roles_and_users"),
    ]

    operations = [migrations.RunPython(write_row, remove_row)]
