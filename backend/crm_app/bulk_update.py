"""``frappe/desk/doctype/bulk_update/bulk_update.py:82-124`` - ``_bulk_action``.

The per-document half of ``submit_cancel_or_update_docs`` and the Celery task that runs
it in the background, kept **out of** ``crm_app/api/`` deliberately: an api module may not
touch a model manager (``tests/test_phase3_endpoints.py::
test_no_endpoint_bypasses_the_permission_layer``), and this one has to load, permission-
check and save documents one at a time.

``crm_app/api/bulk_update.py`` imports this module at load, and ``CrmAppConfig.ready``
imports ``crm_app.api`` - so importing the app registers :func:`bulk_update_docs_task`
with Celery without ``crm_app/tasks.py`` having to know about it.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.db import transaction

from frappe_core import permissions, registry
from frappe_core.query import by_name, parse_json_param
from frappe_core.views import check_destination

logger = logging.getLogger(__name__)

#: Below this many documents the batch runs in the request (``bulk_update.py:67``).
BULK_UPDATE_INLINE_THRESHOLD = 20

#: Above this many it is refused outright (``bulk_update.py:78``).
BULK_UPDATE_MAX_DOCUMENTS = 500


def bulk_action(
    doctype: str,
    docnames: list,
    action: str = "submit",
    data=None,
    user: str | None = None,
) -> list:
    """``_bulk_action`` - apply ``action`` to each document, collecting the failures.

    Returns the list of names that did not go through. **Never raises for one document**:
    upstream wraps each iteration in ``try/except``, logs, rolls that document back and
    carries on, and the return value is the only report the caller gets. The one thing
    that does raise is an unknown ``doctype``, which is resolved once up front - upstream
    would fail on every name in turn and hand back a ``failed`` list as long as the input,
    which reads like "all of your documents are broken" rather than "there is no such
    doctype".

    **"submit" and "cancel" fail every document.** Nothing in this port is submittable -
    there is no ``docstatus`` - so there is no document these two can apply to. Upstream
    behaves the same way with a non-submittable doctype: ``doc.submit()`` raises,
    the handler catches it and the name lands in ``failed``.

    ``user`` is passed explicitly rather than read from the session so that the Celery
    task checks permission against the user who asked for the batch, not against the
    worker's ambient ``Guest``.
    """
    entry = registry.get_entry(doctype)
    if data:
        data = parse_json_param(data, None)
    failed = []

    for docname in docnames:
        try:
            # `by_name`, not `get(pk=)`: a name the key cannot hold is "not found", the
            # way `frappe.get_doc` has it (`frappe_core/query.py:32`).
            instance = by_name(entry.model, docname).first()
            if instance is None:
                # Upstream's `frappe.get_doc` raises `DoesNotExistError` here. **It does
                # so outside the try block** in version-15 (`bulk_update.py:88-89`), so
                # one missing name aborts the whole batch and the caller loses the report
                # for every other document - including the ones already committed. Making
                # it an ordinary per-document failure is the same answer the surrounding
                # code gives for every other error, and the frontend renders the `failed`
                # list either way.
                failed.append(docname)
                continue

            if action == "update":
                # Upstream reaches the same refusal one step later, inside `doc.save()`,
                # which raises `PermissionError` and is caught below. Checking first is
                # the port's convention and keeps a denied write out of the transaction.
                if not permissions.check_object_permission(instance, "write", user):
                    failed.append(docname)
                    continue

                serializer_class = entry.get_serializer_class()
                serializer = serializer_class(instance, data=data or {}, partial=True)
                serializer.is_valid(raise_exception=True)
                # The resource PUT's own destination re-check (`frappe_core/views.py:227`):
                # a row that names its own parent must not be repointed at a parent the
                # caller cannot write.
                check_destination(entry, instance, serializer.validated_data)
                # One transaction per document, matching upstream's commit-per-document /
                # rollback-on-failure. A failure must not undo the documents already done.
                with transaction.atomic():
                    serializer.save()
            else:
                # "submit" / "cancel" / anything else. See the docstring.
                failed.append(docname)
        except Exception:
            # `frappe.log_error("Bulk action failed")` (`bulk_update.py:121`).
            logger.exception("Bulk action failed: %s %s", doctype, docname)
            failed.append(docname)

    return failed


@shared_task(name="crm.bulk_update_docs")
def bulk_update_docs_task(
    doctype: str,
    docnames: list,
    action: str = "submit",
    data=None,
    user: str | None = None,
) -> list:
    """The enqueued half of ``submit_cancel_or_update_docs`` (``bulk_update.py:69-77``).

    **Permission is re-checked in the worker**, against ``user`` - the same rule
    ``crm.delete_bulk_docs`` follows (`PHASE_5_ASYNC.md` §5). A queued message is an
    argument list like any other: replayed, hand-crafted or delayed past a permission
    change, it still may not write more than ``user`` may write right now.

    ``session_user`` as well as the explicit argument, because the write itself stamps
    ``modified_by`` from the ambient session, which in a worker is ``Guest``.
    """
    from frappe_core.session import get_current_user, session_user

    with session_user(user):
        # Read the bound user back rather than passing `user` down: a task enqueued with
        # no user is then checked as Guest and denied, not left unchecked.
        return bulk_action(doctype, docnames, action, data, get_current_user())
