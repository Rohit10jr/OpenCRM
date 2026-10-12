"""Write the salutations and genders every site has (docs/FINDINGS.md 66).

The framework's setup wizard creates them when a site is made
(``frappe/desk/page/setup_wizard/install_fixtures.py:20-49``), so upstream code can rely
on ``Mr`` and ``Male`` existing. They have to exist here for the same reason: a Link to
either is validated on save (``frappe_core/links.py``), and a database without the rows
would refuse every contact, lead and deal that carries one. A migration rather than only
``seed_defaults``, so a fresh database, the test database included, has them from the
start. Rows that are already there are left alone. Nothing to undo backwards.

Live models rather than historical ones, as in ``crm_app`` 0008 and 0010: the two tables
are created by 0012 and have not changed since, and the rows go in through
``BaseDocument.save`` so they are named and stamped like every other document.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    from frappe_platform.reference_data import add_genders, add_salutations

    add_genders()
    add_salutations()


class Migration(migrations.Migration):
    dependencies = [
        ("frappe_platform", "0013_contact_labels_and_status"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
