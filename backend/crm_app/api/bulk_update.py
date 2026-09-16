"""``frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs`` - bulk
edit from the list view (``EditValueModal.vue``).

Only the dispatch lives here - the size bands and the refusal. The per-document work and
the Celery task are in ``crm_app/bulk_update.py``, because an api module may not reach a
model manager (``tests/test_phase3_endpoints.py::
test_no_endpoint_bypasses_the_permission_layer``).

Importing this module imports ``crm_app.bulk_update``, and ``CrmAppConfig.ready`` imports
``crm_app.api`` - which is what registers ``crm.bulk_update_docs`` with Celery.
"""

from __future__ import annotations

from crm_app.bulk_update import (
    BULK_UPDATE_INLINE_THRESHOLD,
    BULK_UPDATE_MAX_DOCUMENTS,
    bulk_action,
    bulk_update_docs_task,
)
from frappe_core.exceptions import throw
from frappe_core.query import parse_json_param
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist


@whitelist(
    "frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs",
    methods=("POST",),
)
def submit_cancel_or_update_docs(
    doctype: str,
    docnames=None,
    action: str = "submit",
    data=None,
    task_id: str | None = None,
):
    """``frappe/desk/doctype/bulk_update/bulk_update.py:54-79``.

    Three size bands, upstream's:

    * under 20 - run it in the request and return the ``failed`` list;
    * 20 to 500 - hand it to Celery and return ``None``;
    * over 500 - refuse, with upstream's sentence and title.

    **Upstream also shows an alert on the enqueue path** -
    ``frappe.msgprint(_("Bulk operation is enqueued in background."), alert=True)``. This
    port has no ``msgprint``: a *success* response carries no message channel
    (``frappe_core/exceptions.py`` builds ``_server_messages`` only for errors), so that
    sentence cannot be delivered and is not faked. ``EditValueModal.vue`` ignores the
    response body either way - it closes the dialog and reloads the list.

    ``task_id`` is accepted for signature fidelity and unused. Upstream threads it into
    ``publish_progress`` so a progress bar can follow the batch; nothing in the CRM
    frontend subscribes to that event, so no progress is published here.
    """
    parsed = parse_json_param(docnames, []) or []
    if not isinstance(parsed, list):
        parsed = [parsed]
    names = [str(n) for n in parsed]

    # `data` may arrive as a JSON string (a query-string caller) or as the object
    # `EditValueModal.vue:113` sends. `bulk_action` parses it too; doing it here as well
    # keeps what goes onto the queue a plain dict rather than a string to re-parse.
    payload = parse_json_param(data, None)

    if len(names) < BULK_UPDATE_INLINE_THRESHOLD:
        return bulk_action(doctype, names, action, payload, get_current_user())

    if len(names) <= BULK_UPDATE_MAX_DOCUMENTS:
        bulk_update_docs_task.delay(doctype, names, action, payload, get_current_user())
        return None

    throw(
        "Bulk operations only support up to 500 documents.",
        title="Too Many Documents",
    )
