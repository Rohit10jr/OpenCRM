"""Encrypt telephony credentials that were stored in plain text.

A4, and the same shape as ``frappe_platform/0005`` for the mail password. Upstream keeps
these out of the document table entirely - they are ``Password`` fieldtypes, written to
the encrypted ``__Auth`` table - so this closes a gap the port introduced by modelling
them as ordinary columns.

**Data-only.** No schema change; only the contents change.

Safe to deploy ahead of running, and skipped when no ``FIELD_ENCRYPTION_KEY`` is set -
see the sibling migration for why failing here would be the wrong behaviour.
"""

from django.conf import settings
from django.db import migrations

#: model name -> the fields on it that hold credentials.
TARGETS = {
    "CRMTwilioSettings": ("api_secret", "auth_token"),
    "CRMExotelSettings": ("api_token",),
}


def _rewrite(apps, transform, predicate):
    for model_name, fields in TARGETS.items():
        model = apps.get_model("crm_app", model_name)
        for row in model.objects.all().iterator():
            changed = []
            for fieldname in fields:
                value = getattr(row, fieldname, "")
                if value and predicate(value):
                    setattr(row, fieldname, transform(value))
                    changed.append(fieldname)
            if changed:
                # `update_fields` keeps `modified` (auto_now) from being rewritten, which
                # would otherwise make every settings record look edited on deploy day.
                row.save(update_fields=changed)


def encrypt_existing(apps, schema_editor):
    if not getattr(settings, "FIELD_ENCRYPTION_KEY", ""):
        return
    from frappe_core.secrets import encrypt, is_encrypted

    _rewrite(apps, encrypt, lambda v: not is_encrypted(v))


def decrypt_existing(apps, schema_editor):
    """Reverse, so a rollback leaves readable data rather than stranded ciphertext."""
    if not getattr(settings, "FIELD_ENCRYPTION_KEY", ""):
        return
    from frappe_core.secrets import decrypt, is_encrypted

    _rewrite(apps, decrypt, is_encrypted)


class Migration(migrations.Migration):
    dependencies = [
        ("crm_app", "0002_alter_crmdealstatus_color_alter_crmfieldslayout_type_and_more"),
    ]

    operations = [
        migrations.RunPython(encrypt_existing, decrypt_existing),
    ]
