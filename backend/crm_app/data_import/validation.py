"""Data Import's version-15 save validation."""

from __future__ import annotations

from django.db.models.signals import pre_save

from frappe_core.exceptions import throw
from frappe_platform.models import DataImport

from .documents import IMPORTABLE_DOCTYPES, build_import_file
from .importer import INSERT


_JOB_UPDATE_FIELDS = frozenset(
    {"status", "template_warnings", "job_claimed_at", "modified", "modified_by"}
)


def validate_data_import(sender, instance, raw=False, update_fields=None, **kwargs) -> None:
    if raw:
        return
    # Upstream's background job uses ``db_set``, which does not run ``validate``.
    # Port only: partial saves of the job-owned fields have the same behavior, so a
    # status update cannot be blocked by re-reading or re-parsing the upload.
    if update_fields and set(update_fields) <= _JOB_UPDATE_FIELDS:
        return

    previous_file = None
    if not instance._state.adding:
        previous_file = sender._default_manager.filter(pk=instance.pk).values_list(
            "import_file", flat=True
        ).first()
    if not instance.import_file or (
        not instance._state.adding and previous_file != instance.import_file
    ):
        instance.template_options = ""
        instance.template_warnings = ""

    if instance.reference_doctype not in IMPORTABLE_DOCTYPES:
        throw(
            "Data Import is not allowed for {0}. Enable 'Allow Import' in DocType settings.".format(
                instance.reference_doctype
            )
        )

    # Upstream accepts both sources and both import modes.
    # Port only: this port deliberately supports uploaded CSV inserts only
    # (``UPSTREAM_BUGS.md`` 76).
    if (instance.google_sheets_url or "").strip():
        throw("Google Sheets imports are not supported")
    if instance.import_type == "Update Existing Records":
        throw("Updating existing records is not supported")
    if not instance.import_type:
        instance.import_type = INSERT

    if instance.import_file:
        imported = build_import_file(instance)
        # Warnings are intentionally not a save refusal. Upstream checks them only
        # when the import job starts.
        instance.payload_count = len(imported.get_payloads_for_import())


def connect_signals() -> None:
    pre_save.connect(
        validate_data_import,
        sender=DataImport,
        weak=False,
        dispatch_uid="crm.data_import.validate",
    )
