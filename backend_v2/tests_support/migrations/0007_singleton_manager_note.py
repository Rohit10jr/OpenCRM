from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tests_support", "0006_widgetrow_related_widget")]

    operations = [
        migrations.AddField(
            model_name="singletondocument",
            name="manager_note",
            field=models.CharField(blank=True, default="", max_length=140),
        )
    ]
