from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("tests_support", "0008_tracked_document")]

    operations = [
        migrations.AlterField(
            model_name="pointingdocument",
            name="widget",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pointers",
                to="tests_support.widget",
            ),
        ),
    ]
