"""Encrypt Email Account credentials that were stored in plain text.

Stage 3 of A3. Rows written before this hold the SMTP password as readable text in
``tabEmail Account``; this rewrites them as ciphertext (``frappe_core.secrets``).

**Data-only** - no schema change. The column stays; only its contents change, which is
what makes this cheap to apply and possible to reverse.

Safe to deploy ahead of running: :func:`frappe_core.secrets.decrypt` passes an unprefixed
value straight through, so mail keeps working on un-migrated rows in the window between
the code landing and the migration being applied.

**Skipped when no key is configured.** A deployment with no ``FIELD_ENCRYPTION_KEY``
should not have its migration fail - it should keep running exactly as before, and start
encrypting when a key is set. Failing here would block every unrelated migration behind
it, on a box where nothing is broken yet. The check that a key *ought* to be set belongs
in deployment, not in a migration.
"""

from django.conf import settings
from django.db import migrations

FIELDS = ("password", "api_secret")


def encrypt_existing(apps, schema_editor):
    if not getattr(settings, "FIELD_ENCRYPTION_KEY", ""):
        return

    from frappe_core.secrets import encrypt, is_encrypted

    # The historical model, per Django's rules for data migrations - so this keeps
    # working if the real model gains or loses fields later. It has no `save()` override
    # and therefore no mixin, which is why the encryption is applied explicitly here.
    EmailAccount = apps.get_model("frappe_platform", "EmailAccount")

    for account in EmailAccount.objects.all().iterator():
        changed = []
        for fieldname in FIELDS:
            value = getattr(account, fieldname, "")
            if value and not is_encrypted(value):
                setattr(account, fieldname, encrypt(value))
                changed.append(fieldname)
        if changed:
            # `update_fields` keeps this to the columns that changed; `modified` is
            # `auto_now` and would otherwise be rewritten, making it look as though every
            # account was edited on the day of the deploy.
            account.save(update_fields=changed)


def decrypt_existing(apps, schema_editor):
    """Reverse: restore plaintext, so the migration can be rolled back with the data
    intact rather than stranding unreadable rows behind a downgrade."""
    if not getattr(settings, "FIELD_ENCRYPTION_KEY", ""):
        return

    from frappe_core.secrets import decrypt, is_encrypted

    EmailAccount = apps.get_model("frappe_platform", "EmailAccount")

    for account in EmailAccount.objects.all().iterator():
        changed = []
        for fieldname in FIELDS:
            value = getattr(account, fieldname, "")
            if value and is_encrypted(value):
                setattr(account, fieldname, decrypt(value))
                changed.append(fieldname)
        if changed:
            account.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [
        ("frappe_platform", "0004_emailaccount_add_signature_and_more"),
    ]

    operations = [
        migrations.RunPython(encrypt_existing, decrypt_existing),
    ]
