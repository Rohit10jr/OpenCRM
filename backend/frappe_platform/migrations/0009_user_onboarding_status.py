"""``User.onboarding_status``: the per-app onboarding steps frappe-ui's ``useOnboarding``
stores through ``frappe.onboarding.update_user_onboarding_status`` (FINDINGS.md 39)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("frappe_platform", "0008_communication_email_headers"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="onboarding_status",
            field=models.TextField(blank=True, default=""),
        ),
    ]
