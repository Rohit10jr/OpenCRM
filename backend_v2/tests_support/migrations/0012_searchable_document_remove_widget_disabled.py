import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tests_support", "0011_widget_disabled"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SearchableDocument",
            fields=[
                (
                    "name",
                    models.CharField(
                        editable=False,
                        max_length=140,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("creation", models.DateTimeField(blank=True, editable=False, null=True)),
                (
                    "modified",
                    models.DateTimeField(
                        blank=True, db_index=True, editable=False, null=True
                    ),
                ),
                ("idx", models.IntegerField(default=0)),
                ("docstatus", models.SmallIntegerField(default=0)),
                (
                    "_assign",
                    models.JSONField(blank=True, db_column="_assign", default=list),
                ),
                (
                    "_liked_by",
                    models.JSONField(blank=True, db_column="_liked_by", default=list),
                ),
                (
                    "_comments",
                    models.JSONField(blank=True, db_column="_comments", default=list),
                ),
                (
                    "_user_tags",
                    models.CharField(
                        blank=True,
                        db_column="_user_tags",
                        default="",
                        max_length=500,
                    ),
                ),
                ("title", models.CharField(blank=True, default="", max_length=140)),
                ("disabled", models.BooleanField(default=False)),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="modified_by",
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        db_column="owner",
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-modified"]},
        ),
        migrations.RemoveField(model_name="widget", name="disabled"),
    ]
