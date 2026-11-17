from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tests_support", "0009_linked_document_fixtures")]

    operations = [
        migrations.AddField(
            model_name="widget",
            name="external_id",
            field=models.CharField(
                blank=True, max_length=140, null=True, unique=True
            ),
        ),
    ]
