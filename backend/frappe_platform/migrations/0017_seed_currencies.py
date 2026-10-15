"""Write the currencies every site has, nine of them enabled (docs/FINDINGS.md 63).

The framework writes them when a site is set up, before any app installs
(``frappe/geo/doctype/country/country.py:import_country_and_currency``), so upstream code
can rely on ``USD`` existing. They have to exist here for the same reason as the
salutations in 0014: ``currency`` on a deal, an organization and FCRM Settings is a Link,
validated on save (``frappe_core/links.py``), and a database without the rows would refuse
the ``USD`` already stored on organizations. A migration rather than only
``seed_defaults``, so a fresh database, the test database included, has them from the
start. Rows that are already there are left alone. Nothing to undo backwards.

The historical model, so a column added to Currency later cannot break this step of a
fresh ``migrate``.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    from frappe_platform.reference_data import add_currencies

    add_currencies(apps.get_model("frappe_platform", "Currency"))


class Migration(migrations.Migration):
    dependencies = [
        ("frappe_platform", "0016_currency"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
