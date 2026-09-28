"""Seed the standard user-menu items on an FCRM Settings row that has none (docs/FINDINGS.md 42).

Upstream writes the six ``standard_dropdown_items`` from ``crm/hooks.py`` into FCRM
Settings at install (``crm/install.py:530``) and re-syncs them after every migrate. The
port's row was created without them, so ``UserDropdown.vue``, which builds the menu at
the top of the sidebar from those rows, had nothing to show: no Settings, no About, no
Log out. ``FCRMSettings.load`` now seeds a row it creates; this migration covers the
rows that already exist. A row that has items of its own is left alone, as upstream's
install leaves it. Nothing to undo backwards.

Live models rather than historical ones, as in 0008: no schema has changed since, and
the child rows go in through ``BaseDocument.save`` so they are named and stamped like
every other document.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    from crm_app.models.metadata import FCRMSettings, add_standard_dropdown_items

    settings = FCRMSettings._default_manager.filter(pk=FCRMSettings.singleton_name()).first()
    if settings is not None:
        add_standard_dropdown_items(settings)


class Migration(migrations.Migration):
    dependencies = [
        ("crm_app", "0009_dashboard_tiles_carry_a_layout"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
