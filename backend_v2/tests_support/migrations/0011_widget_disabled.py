from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tests_support", "0010_widget_external_id")]

    operations = [
        migrations.AddField(
            model_name="widget",
            name="disabled",
            field=models.BooleanField(default=False),
        ),
    ]
