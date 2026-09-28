"""Name every single-row doctype's document after its doctype, as upstream does.

Phase 1 named the one row of FCRM Settings, CRM Twilio Settings, CRM Exotel Settings and
ERPNext CRM Settings ``Settings``. Upstream names a single's document after its doctype
(``frappe.get_single("FCRM Settings")`` loads ``FCRM Settings``), and the frontend
hardcodes that name, so every settings screen answered 404 (docs/FINDINGS.md 37).

``rename_document`` is used rather than a bare UPDATE because CRM Dropdown Item rows
hold a foreign key to the FCRM Settings row, and the helper repoints those, along with
any link or dynamic link that names the document. No schema changes, so the live models
the helper uses match this migration's state.
"""

from django.db import migrations

SINGLETONS = (
    "FCRM Settings",
    "CRM Twilio Settings",
    "CRM Exotel Settings",
    "ERPNext CRM Settings",
)

OLD = "Settings"


def _rename(old: str, new_for) -> None:
    from frappe_core import registry
    from frappe_core.rename import rename_document

    for doctype in SINGLETONS:
        model = registry.get_model(doctype)
        new = new_for(doctype)
        if model._default_manager.filter(pk=old).exists() and not (
            model._default_manager.filter(pk=new).exists()
        ):
            rename_document(doctype, old, new)


def forwards(apps, schema_editor):
    _rename(OLD, lambda doctype: doctype)


def backwards(apps, schema_editor):
    from frappe_core import registry
    from frappe_core.rename import rename_document

    for doctype in SINGLETONS:
        model = registry.get_model(doctype)
        if model._default_manager.filter(pk=doctype).exists() and not (
            model._default_manager.filter(pk=OLD).exists()
        ):
            rename_document(doctype, doctype, OLD)


class Migration(migrations.Migration):
    dependencies = [
        ("crm_app", "0007_crmlead_unique_facebook_lead_per_form"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
