"""Run version-15 Data Imports through the port's normal document write path."""

from __future__ import annotations

import json
import logging
import traceback
from datetime import timedelta

from celery import shared_task
from billiard.exceptions import SoftTimeLimitExceeded
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError as DRFValidationError

from frappe_core import permissions
from frappe_core.exceptions import FrappeError, PermissionError as FrappePermissionError
from frappe_core.exceptions import _flatten_drf_detail
from frappe_core.session import session_user
from frappe_platform.models import DataImport, DataImportLog

from crm_app.api.client import client_insert
from crm_app.realtime import publish

from .documents import build_import_file, get_data_import


logger = logging.getLogger(__name__)
CLAIM_TTL = timedelta(hours=3)


def get_import_logs(data_import: str) -> list[dict]:
    return list(
        DataImportLog._default_manager.filter(data_import=str(data_import))
        .order_by("log_index")
        .values("success", "docname", "messages", "exception", "row_indexes")[:5000]
    )


def claim_import(data_import: str) -> timezone.datetime | None:
    """Claim an import once, while allowing a lost queue message to expire."""
    claimed_at = timezone.now()
    stale_before = claimed_at - CLAIM_TTL
    # Upstream: ``is_job_enqueued`` is checked separately from enqueueing.
    # Port only: one conditional UPDATE makes that check-and-claim indivisible, and a
    # three-hour lease recovers a job whose queue message was lost (UPSTREAM_BUGS.md 78).
    updated = DataImport._default_manager.filter(pk=str(data_import)).filter(
        Q(job_claimed_at__isnull=True) | Q(job_claimed_at__lt=stale_before)
    ).update(job_claimed_at=claimed_at)
    return claimed_at if updated else None


def release_import(data_import: str, claimed_at=None) -> None:
    queryset = DataImport._default_manager.filter(pk=str(data_import))
    if claimed_at is not None:
        queryset = queryset.filter(job_claimed_at=claimed_at)
    queryset.update(job_claimed_at=None)


def _save_job_field(document: DataImport, field: str, value) -> None:
    setattr(document, field, value)
    document.save(update_fields=[field, "modified", "modified_by"])


def _row_indexes(payload) -> list[int]:
    return [row.row_number for row in payload.rows]


def _plain_value(value):
    """Remove ``frappe._dict``-style attribute access before DRF sees nested rows."""
    if isinstance(value, dict):
        return {key: _plain_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain_value(item) for item in value]
    return value


def _messages_for_exception(exc: Exception) -> str:
    if isinstance(exc, FrappeError):
        messages = list(exc.messages)
    elif isinstance(exc, DRFValidationError):
        messages = _flatten_drf_detail(exc.detail)
    else:
        messages = []
    return json.dumps([{"message": message} for message in messages])


def _create_log(data_import: str, log_index: int, **details) -> DataImportLog:
    return DataImportLog._default_manager.create(
        data_import=str(data_import),
        log_index=log_index,
        success=details.get("success", False),
        row_indexes=json.dumps(details.get("row_indexes") or []),
        docname=details.get("docname") or "",
        messages=details.get("messages"),
        exception=details.get("exception") or "",
    )


def run_import(document: DataImport) -> list[dict] | None:
    """``Importer.import_data`` (version-15 ``importer.py:78-230``)."""
    _save_job_field(document, "template_warnings", "")
    imported_file = build_import_file(document)
    payloads = imported_file.get_payloads_for_import()

    warnings = [warning for warning in imported_file.get_warnings() if warning.get("type") != "info"]
    if warnings:
        _save_job_field(document, "template_warnings", json.dumps(warnings))
        return None

    import_log = list(
        DataImportLog._default_manager.filter(data_import=str(document.pk))
        .order_by("log_index")
        .values("row_indexes", "success", "log_index")
    )
    log_index = 0

    if document.status in ("Partial Success", "Error") and len(import_log) >= document.payload_count:
        import_log = [log for log in import_log if log["success"]]
        DataImportLog._default_manager.filter(
            data_import=str(document.pk), success=False
        ).delete()

    imported_rows: list[int] = []
    for log in import_log:
        if log["success"] or len(import_log) < document.payload_count:
            imported_rows.extend(json.loads(log["row_indexes"]))
        log_index = log["log_index"]

    total_payload_count = len(payloads)
    for payload in payloads:
        row_indexes = _row_indexes(payload)
        if set(row_indexes).intersection(imported_rows):
            # Upstream publishes ``data_import_progress`` here and after each row.
            # Nothing in this port's screens listens for it, so only the terminal
            # refresh is emitted (UPSTREAM_BUGS.md 80).
            continue

        try:
            if payload.doc is None:
                raise TypeError("Import payload has no parent document")
            values = _plain_value(payload.doc)
            values["doctype"] = document.reference_doctype
            with transaction.atomic():
                created = client_insert(doc=values)
                _create_log(
                    str(document.pk),
                    log_index,
                    success=True,
                    docname=created["name"],
                    row_indexes=row_indexes,
                    messages=None,
                )
                if document.status != "Partial Success":
                    _save_job_field(document, "status", "Partial Success")
        # Upstream: the row-level ``except Exception`` also catches rq's
        # ``JobTimeoutException``, so its outer ``Timed Out`` handler is not reached.
        # Port only: let the task handler record the timeout without creating a failed
        # row log; the atomic block rolls back that row (UPSTREAM_BUGS.md 81).
        except SoftTimeLimitExceeded:
            raise
        except Exception as exc:
            _create_log(
                str(document.pk),
                log_index,
                success=False,
                exception=traceback.format_exc(),
                messages=_messages_for_exception(exc),
                row_indexes=row_indexes,
            )
        log_index += 1

    import_log = list(
        DataImportLog._default_manager.filter(data_import=str(document.pk))
        .order_by("log_index")
        .values("row_indexes", "success", "log_index")
    )
    successes = [log for log in import_log if log["success"]]
    failures = [log for log in import_log if not log["success"]]
    if len(failures) >= total_payload_count and not successes:
        status = "Error"
    elif failures and successes:
        status = "Partial Success"
    elif len(successes) == total_payload_count:
        status = "Success"
    else:
        status = "Pending"
    _save_job_field(document, "status", status)
    return import_log


def _try_import_lock(data_import: str) -> bool:
    # Port only: a session advisory lock prevents Redis late redelivery from running the
    # same import concurrently (UPSTREAM_BUGS.md 79).
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s))", [str(data_import)])
        return bool(cursor.fetchone()[0])


def _release_import_lock(data_import: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [str(data_import)])


@shared_task(name="crm.data_import.start", soft_time_limit=10000)
def start_data_import_task(data_import: str, user: str) -> None:
    """``data_import.py:start_import`` with worker-side authorization and locking."""
    with session_user(user):
        if not _try_import_lock(data_import):
            return
        handled = False
        try:
            document = get_data_import(data_import)
            if document.job_claimed_at is None:
                return
            handled = True
            claimed_at = document.job_claimed_at
            if not permissions.check_object_permission(document, "write", user):
                _save_job_field(document, "status", "Error")
                return
            run_import(document)
        except SoftTimeLimitExceeded:
            document = get_data_import(data_import)
            _save_job_field(document, "status", "Timed Out")
        except Exception:
            logger.exception("Data import failed: %s", data_import)
            document = get_data_import(data_import)
            _save_job_field(document, "status", "Error")
        finally:
            if handled:
                release_import(data_import, claimed_at)
                publish("data_import_refresh", {"data_import": str(data_import)})
            _release_import_lock(data_import)
