"""Apply the DocType JSON's Open communication-status default to existing sales rows."""

from django.db import migrations


def forwards(apps, schema_editor):
    communication_status = apps.get_model("crm_app", "CRMCommunicationStatus")
    if not communication_status.objects.filter(pk="Open").exists():
        return

    for model_name in ("CRMLead", "CRMDeal"):
        model = apps.get_model("crm_app", model_name)
        model.objects.filter(communication_status__isnull=True).update(
            communication_status_id="Open"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("crm_app", "0011_kanban_fields_reset"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
