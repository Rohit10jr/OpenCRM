# Port only: KNOWN_ISSUES §6 — revoking access tokens that have already been issued.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('frappe_platform', '0020_todo_assignment_rule_assignmentrule_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='token_version',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
