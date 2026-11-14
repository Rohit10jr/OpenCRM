from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("tests_support", "0005_dynamicreference")]

    operations = [
        migrations.AddField(
            model_name="widgetrow",
            name="related_widget",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="linked_rows",
                to="tests_support.widget",
            ),
        ),
    ]
