"""Write the FCRM Settings row and its six standard dropdown items (spec section 4.3).

A row the application cannot run without (decision 13): the sidebar's user menu is built
from these items and shows nothing without them. Written as Administrator, each item
named with `core.naming`'s hash, `idx` 1-6. An existing row is left alone, items and
all. The items are a frozen copy of `configuration.models.STANDARD_DROPDOWN_ITEMS`
(`crm/hooks.py:314-357`), so a later change there cannot rewrite history.
"""

from django.db import migrations
from django.utils import timezone

from core.naming import Hash

NAME = "FCRM Settings"
ITEMS = (
    {"name1": "app_selector", "label": "Apps", "type": "Route", "route": "#"},
    {"name1": "settings", "label": "Settings", "type": "Route", "icon": "settings", "route": "#"},
    {"name1": "login_to_fc", "label": "Login to Frappe Cloud", "type": "Route", "route": "#"},
    {"name1": "about", "label": "About", "type": "Route", "icon": "info", "route": "#"},
    {"name1": "separator", "label": "", "type": "Separator"},
    {"name1": "logout", "label": "Log out", "type": "Route", "icon": "log-out", "route": "#"},
)


def write_row(apps, schema_editor):
    FCRMSettings = apps.get_model("configuration", "FCRMSettings")
    CRMDropdownItem = apps.get_model("configuration", "CRMDropdownItem")
    if FCRMSettings.objects.filter(pk=NAME).exists():
        return
    now = timezone.now()
    stamp = {
        "owner_id": "Administrator",
        "modified_by_id": "Administrator",
        "creation": now,
        "modified": now,
    }
    settings = FCRMSettings.objects.create(name=NAME, **stamp)
    naming = Hash()
    CRMDropdownItem.objects.bulk_create(
        [
            CRMDropdownItem(
                name=naming.generate(None),
                parent_settings=settings,
                parenttype=NAME,
                parentfield="dropdown_items",
                idx=idx,
                is_standard=True,
                **item,
                **stamp,
            )
            for idx, item in enumerate(ITEMS, start=1)
        ]
    )


class Migration(migrations.Migration):
    dependencies = [
        ("configuration", "0005_fcrmsettings_crmdropdownitem"),
        ("accounts", "0002_seed_roles_and_users"),
    ]

    operations = [migrations.RunPython(write_row, migrations.RunPython.noop)]
