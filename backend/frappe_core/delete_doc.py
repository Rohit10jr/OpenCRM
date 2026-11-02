"""The link check a delete runs before it removes anything: ``frappe/model/delete_doc.py``
(version-15) for the Dynamic Link half, FINDINGS.md 76.

Upstream's ``delete_doc`` refuses with ``LinkExistsError`` while another document still
names the record, through a Link field (``check_if_doc_is_linked``) or a Dynamic Link
field (``check_if_doc_is_dynamically_linked``), lines 141-153. The port's Link fields are
foreign keys, and ``on_delete=PROTECT`` refuses those at the database
(``exceptions.link_exists_error``). The Dynamic Link pairs - a task's
``reference_doctype`` / ``reference_docname`` - are plain columns nothing protected, so a
deal with a task was deleted and the task left naming nothing.

Every delete a caller asks for runs :func:`check_dynamic_links` first: ``DELETE
/api/resource/``, ``frappe.client.delete``, the delete dialog's linked-document delete
and the bulk delete. The query reads every row, not the caller's: upstream's does, so a
reference the caller cannot see (a notification addressed to someone else) still blocks
the delete, and the message names that document's doctype and name and no more, as
upstream's does.

The fields come from the port's field metadata (``field_meta``), the way upstream reads
them off DocField in ``dynamic_links.py:get_dynamic_links``.
"""

from __future__ import annotations

from frappe_core import field_meta, registry
from frappe_core.exceptions import (
    LinkExistsError,
    _child_parent_name,
    link_exists_message,
    throw,
)

#: Doctypes whose rows go with the document instead of standing in the way of its
#: deletion: the framework's ``ignore_links_on_delete`` hook (``frappe/hooks.py:433-454``)
#: plus the CRM's own (``crm/hooks.py:260``). A comment, a file or an assignment is
#: deleted with its document (``frappe_core/children.py:delete_references``); listing it
#: as a "linked document" asked the user to unlink it first, and unlinking orphaned it
#: (FINDINGS.md 75). Only the names this port registers matter.
IGNORE_LINKS_ON_DELETE = frozenset(
    {
        "Activity Log",
        "Comment",
        "Communication",
        "DocShare",
        "Document Follow",
        "Email Unsubscribe",
        "Failed Lead Sync Log",
        "File",
        "Notification Log",
        "Tag Link",
        "ToDo",
        "Version",
        "View Log",
    }
)

#: ``frappe.model.docstatus.DocStatus.cancelled()``.
_CANCELLED = 2


def get_dynamic_links() -> list[tuple[str, str, str]]:
    """``dynamic_links.py:get_dynamic_links``: every Dynamic Link field, as
    ``(parent doctype, fieldname, options)``.

    Upstream orders them by the parent DocType's ``read_only`` and ``in_create`` so a
    user-facing doctype is named first; no doctype the port registers sets either, so
    registry order stands in.
    """
    found = []
    for doctype in registry.all_doctypes():
        for field in field_meta.get_fields(doctype):
            if field.get("fieldtype") == "Dynamic Link" and field.get("options"):
                found.append((doctype, field["fieldname"], field["options"]))
    return found


def get_dynamic_linked_docs(doctype: str, names, child_tables_only: bool = False) -> list[dict]:
    """``delete_doc.py:355-430`` (``get_dynamic_linked_docs``, ``method="Delete"``), over
    a batch of names: one query per Dynamic Link field, whatever the batch size.

    Upstream first narrows the fields to those whose stored doctypes include this one
    (``get_dynamic_link_map``, a cached ``select distinct``); filtering on the doctype
    column directly gives the same rows.

    Port only: ``child_tables_only`` reads just the Dynamic Link fields of child tables,
    for the delete dialog, which finds the reference pairs on its own,
    permission-filtered (``crm_app/api/doc.py``, FINDINGS.md 93).
    """
    names = [str(name) for name in names]
    if not names:
        return []

    linked: list[dict] = []
    for parent, fieldname, options in get_dynamic_links():
        if parent in IGNORE_LINKS_ON_DELETE:
            # don't check for communication and todo!
            continue

        entry = registry.get_entry(parent)
        if child_tables_only and not entry.is_child_table:
            continue
        if entry.is_single:
            # Upstream: a Single's dynamic link is read with get_singles_dict
            # (delete_doc.py:371-391). Port only: no Single the port registers declares
            # a Dynamic Link field, and Singles are not stored that way here.
            continue

        model = entry.model
        columns = {f.name for f in model._meta.concrete_fields}
        if fieldname not in columns or options not in columns:
            # Port only: a field the DocType JSON declares and the model does not carry.
            continue

        rows = model._default_manager.filter(**{options: doctype, f"{fieldname}__in": names})
        if "docstatus" in columns:
            # linked to an non-cancelled doc when deleting
            rows = rows.exclude(docstatus=_CANCELLED)
        # Port only: by name, so the document named in the refusal is the same on every
        # run (upstream's is the database's first row).
        for row in rows.order_by("pk"):
            if entry.is_child_table:
                reference_doctype = str(getattr(row, "parenttype", "") or "")
                reference_docname = _child_parent_name(row)
            else:
                reference_doctype = parent
                reference_docname = str(row.pk)

            if reference_doctype in IGNORE_LINKS_ON_DELETE:
                # don't check for communication and todo!
                continue

            linked.append(
                {
                    "doc": str(getattr(row, fieldname)),
                    "reference_doctype": reference_doctype,
                    "reference_docname": reference_docname,
                    "at_position": f"at Row: {row.idx}" if entry.is_child_table else "",
                }
            )
    return linked


def check_if_doc_is_dynamically_linked(doctype: str, names) -> None:
    """``delete_doc.py:433-440``: raise ``LinkExistsError`` for the first reference."""
    links = get_dynamic_linked_docs(doctype, names)
    if links:
        link = links[0]
        reference_doctype = link["reference_doctype"]
        # hack to display Single doctype only once in message (delete_doc.py:447-449)
        if reference_doctype == link["reference_docname"]:
            reference_doctype = ""
        throw(
            link_exists_message(
                doctype,
                link["doc"],
                reference_doctype,
                link["reference_docname"],
                link["at_position"],
            ),
            LinkExistsError,
        )


def check_dynamic_links(doctype: str, names) -> None:
    """``delete_doc.py:141-153``, run before the delete.

    A doctype with an ``enabled`` or ``disabled`` field is told to disable the record
    instead, as upstream tells it.
    """
    try:
        # Upstream: check_if_doc_is_linked(doc)
        # Port: the Link half is the foreign keys' on_delete=PROTECT, refused when the
        # row is deleted and rendered by exceptions.link_exists_error - so a document
        # with both kinds of reference is refused for its Dynamic Link first, where
        # upstream names the Link first. The disable message is not given for those.
        check_if_doc_is_dynamically_linked(doctype, names)
    except LinkExistsError:
        if field_meta.get_field(doctype, "enabled") or field_meta.get_field(doctype, "disabled"):
            throw(f"You can disable this {doctype} instead of deleting it.", LinkExistsError)
        raise
