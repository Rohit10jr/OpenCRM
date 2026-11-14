from django.db import migrations, models

import core.fields


class Migration(migrations.Migration):
    dependencies = [("tests_support", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="secureddocument",
            name="audit_value",
            field=models.CharField(blank=True, default="", max_length=140),
        ),
        migrations.AddField(
            model_name="secureddocument",
            name="encrypted_secret",
            field=core.fields.EncryptedCharField(
                blank=True, default="", max_length=255
            ),
        ),
        migrations.AddField(
            model_name="secureddocument",
            name="manager_value",
            field=models.CharField(blank=True, default="", max_length=140),
        ),
    ]
