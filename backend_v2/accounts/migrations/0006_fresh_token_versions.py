"""Every existing account gets a fresh random `token_version`, once (owner, 21 Nov 2026;
ACCOUNTS §10.5 "Existing rows", PE-32), the built-ins included. It signs everyone out
once.

The historical model only, one `update()` per row, and its own frozen copy of the
expression: the migration imports no live code (temp proposal C-1).
"""

import secrets

from django.db import migrations


def _fresh_version() -> int:
    # Frozen copy of accounts.authentication.new_token_version as of this migration.
    return secrets.randbelow(2**62) + 1


def fresh_token_versions(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for name in User.objects.values_list("pk", flat=True):
        User.objects.filter(pk=name).update(token_version=_fresh_version())


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_token_version_bigint'),
    ]

    operations = [
        migrations.RunPython(fresh_token_versions, migrations.RunPython.noop),
    ]
