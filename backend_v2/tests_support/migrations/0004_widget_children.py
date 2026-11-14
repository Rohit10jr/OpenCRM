from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_seed_roles_and_users"),
        ("tests_support", "0003_testtree_treeitem"),
    ]

    operations = [
        migrations.AddField(
            model_name="widgetrow",
            name="value",
            field=models.CharField(default="", max_length=140),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name="WidgetNote",
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
                        blank=True, db_column="_user_tags", default="", max_length=500
                    ),
                ),
                ("parent", models.CharField(max_length=140)),
                ("parenttype", models.CharField(max_length=140)),
                ("parentfield", models.CharField(max_length=140)),
                ("value", models.CharField(max_length=140)),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="modified_by",
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="accounts.user",
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
                        to="accounts.user",
                    ),
                ),
            ],
            options={"ordering": ["-modified"]},
        ),
    ]
