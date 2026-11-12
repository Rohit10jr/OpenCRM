"""Seed the four roles and Frappe's two built-in users."""

from django.db import migrations


ROLES = ["Administrator", "System Manager", "Sales Manager", "Sales User"]
BUILTIN_USERS = ["Administrator", "Guest"]


def seed(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("accounts", "User")

    groups = {}
    for role in ROLES:
        groups[role], _ = Group.objects.get_or_create(name=role)

    administrator, created = User.objects.get_or_create(
        name="Administrator",
        defaults={
            "email": "admin@example.com",
            "first_name": "Administrator",
            "full_name": "Administrator",
            "enabled": True,
            "user_type": "System User",
            "is_staff": True,
            "is_superuser": True,
            "password": "!",
        },
    )
    if created:
        administrator.groups.add(
            groups["Administrator"], groups["System Manager"]
        )

    User.objects.get_or_create(
        name="Guest",
        defaults={
            "email": "guest@example.com",
            "first_name": "Guest",
            "full_name": "Guest",
            "enabled": True,
            "user_type": "Website User",
            "password": "!",
        },
    )


def unseed(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("accounts", "User")
    User.objects.filter(name__in=BUILTIN_USERS).delete()
    Group.objects.filter(name__in=ROLES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
