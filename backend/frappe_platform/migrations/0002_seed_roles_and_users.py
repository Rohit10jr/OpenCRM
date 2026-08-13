"""Seed the four roles and Frappe's two built-in users.

PHASE_0_FOUNDATION.md section 7 ("Roles to seed") and PHASE_2_PERMISSIONS.md section 5.

``Administrator`` and ``Guest`` are real User rows in Frappe, not sentinels. They have
to exist here too, because ``BaseDocument.save`` stamps ``owner`` with the ambient
session user and that FK has to resolve - including for documents created outside a
request, where the ambient user is ``Guest``.
"""

from django.db import migrations

ROLES = ["Administrator", "System Manager", "Sales Manager", "Sales User"]


def seed(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("frappe_platform", "User")

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
            "password": "!",  # unusable until someone sets one
        },
    )
    if created:
        administrator.groups.add(groups["Administrator"], groups["System Manager"])

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
    User = apps.get_model("frappe_platform", "User")
    User.objects.filter(name__in=["Administrator", "Guest"]).delete()
    Group.objects.filter(name__in=ROLES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("frappe_platform", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
