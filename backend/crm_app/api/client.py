"""Frappe's generic client API - ``frappe.client.*`` and two ``frappe.desk.*`` calls.

**Not in `PHASE_3_ENDPOINTS.md` section 2's group list, but required by the frontend.**
`PORT_PLAN.md` section 3 names them explicitly: *"Frontend also calls these Frappe
built-ins directly - they must exist"*, with call counts. Grepping the shipped frontend
confirms it: `frappe.client.delete`, `set_value`, `insert`, `get`, `get_list`,
`rename_doc`, `get_doc_permissions`, plus `frappe.desk.form.assign_to.add`,
`frappe.desk.like.toggle_like` and `frappe.desk.search.search_link`.

The frontend contract is a hard external contract, and the phase's first acceptance
criterion is "every dotted path resolves at its original URL" - so these are in scope
even though the group list omits them. Recorded as added scope in PROGRESS_PHASE_3.md.

Every one of these routes through the phase-2 permission layer. They are the widest
attack surface in the port: a generic "set any field on any document" endpoint that
skipped permission checks would undo phase 2 entirely.
"""

from __future__ import annotations

from django.db import transaction

from frappe_core import permissions, registry
from frappe_core.exceptions import DoesNotExistError
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.exceptions import throw
from frappe_core.views import _candidate_instance, check_destination
from frappe_core.naming import validate_name
from frappe_core.query import fetch_rows, parse_json_param
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist


def _entry_or_404(doctype: str):
    if not registry.has_doctype(doctype):
        raise DoesNotExistError(f"DocType {doctype} not found")
    entry = registry.get_entry(doctype)
    if entry.is_child_table:
        raise DoesNotExistError(f"DocType {doctype} not found")
    return entry


def _get_checked(doctype: str, name: str, ptype: str):
    entry = _entry_or_404(doctype)
    instance = entry.model._default_manager.filter(pk=name).first()
    if instance is None:
        raise DoesNotExistError(f"{doctype} {name} not found")
    if not permissions.check_object_permission(instance, ptype, get_current_user()):
        raise FrappePermissionError(f"No permission for {doctype} {name}", title="Not Permitted")
    return entry, instance


@whitelist("frappe.client.get")
def client_get(doctype: str, name: str | None = None, filters=None, parent=None):
    """``frappe/client.py:get`` - fetch one document by name, or by filters."""
    entry = _entry_or_404(doctype)

    if name is None:
        parsed = parse_json_param(filters, None)
        if not parsed:
            throw("name or filters is required")
        rows = fetch_rows(doctype, fields=["name"], filters=parsed, limit_page_length=1)
        if not rows:
            raise DoesNotExistError(f"{doctype} not found")
        name = rows[0]["name"]

    _entry, instance = _get_checked(doctype, name, "read")
    return entry.get_serializer_class()(instance).data


@whitelist("frappe.client.get_list")
def client_get_list(
    doctype: str,
    fields=None,
    filters=None,
    or_filters=None,
    order_by: str | None = None,
    limit_start: int = 0,
    limit_page_length: int = 20,
    parent=None,
    **extra,
):
    """``frappe/client.py:get_list``. Permission-filtered via ``fetch_rows``."""
    _entry_or_404(doctype)
    return fetch_rows(
        doctype,
        fields=parse_json_param(fields),
        filters=parse_json_param(filters),
        or_filters=parse_json_param(or_filters),
        order_by=order_by,
        limit_start=limit_start,
        limit_page_length=limit_page_length,
    )


@whitelist("frappe.client.get_single_value")
def client_get_single_value(doctype: str, field: str):
    """``frappe/client.py:get_single_value`` - one field off a singleton."""
    entry = _entry_or_404(doctype)
    if not entry.is_single:
        throw(f"{doctype} is not a single DocType")
    instance = entry.model._default_manager.first()
    if instance is None:
        return None
    from frappe_core.field_security import sensitive_fields

    if field in sensitive_fields(entry.model):
        raise FrappePermissionError(f"Field {field!r} is not readable")
    return getattr(instance, field, None)


@whitelist("frappe.client.set_value", methods=("POST", "PUT"))
def client_set_value(doctype: str, name: str, fieldname, value=None):
    """``frappe/client.py:set_value``.

    ``fieldname`` is either a field name plus ``value``, or a dict of field->value -
    both spellings are used by the frontend. Writes go through the serializer so that
    validation, ``fetch_from`` and the read-only rules on underscore fields all apply;
    a bare ``update()`` here would bypass every one of them.
    """
    entry, instance = _get_checked(doctype, name, "write")

    parsed = parse_json_param(fieldname, fieldname)
    payload = parsed if isinstance(parsed, dict) else {str(parsed): value}

    serializer_class = entry.get_serializer_class()
    serializer = serializer_class(instance, data=payload, partial=True)
    serializer.is_valid(raise_exception=True)
    # Same guard as `/api/resource/` PUT: a row that names its own parent can be *moved*
    # onto a document the caller cannot write, and the check on the way in only saw where
    # it used to live.
    check_destination(entry, instance, serializer.validated_data)
    with transaction.atomic():
        instance = serializer.save()
    return serializer_class(instance).data


@whitelist("frappe.client.insert", methods=("POST",))
def client_insert(doc=None, **extra):
    """``frappe/client.py:insert``.

    Enforces create permission, which is what makes ``CRM Notification`` uncreatable by
    an ordinary user through this path as well as through ``/api/resource/``.
    """
    payload = parse_json_param(doc, doc) or {}
    if not isinstance(payload, dict):
        throw("doc must be an object")

    doctype = payload.get("doctype")
    if not doctype:
        throw("doctype is required")
    entry = _entry_or_404(doctype)

    data = {k: v for k, v in payload.items() if k != "doctype"}

    # The candidate carries the payload's fields, so a rule that defers to a referenced
    # document can see which document. `/api/resource/` has the same check for the same
    # reason - the two create doors must agree, or the stricter one is decoration.
    if not permissions.check_object_permission(
        _candidate_instance(entry, data), "create", get_current_user()
    ):
        raise FrappePermissionError(f"Not permitted to create {doctype}", title="Not Permitted")
    serializer_class = entry.get_serializer_class()
    serializer = serializer_class(data=data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        instance = serializer.save()
    return serializer_class(instance).data


@whitelist("frappe.client.delete", methods=("DELETE", "POST"))
def client_delete(doctype: str, name: str):
    """``frappe/client.py:delete``."""
    _entry, instance = _get_checked(doctype, name, "delete")
    with transaction.atomic():
        instance.delete()
    return None


@whitelist("frappe.client.rename_doc", methods=("POST",))
def client_rename_doc(doctype: str, old_name: str, new_name: str, merge: bool = False):
    """``frappe/rename_doc.py:rename_doc``.

    Renaming a string PK is a real operation in Frappe - the frontend uses it to rename
    an Email Template. ``merge`` is **not** supported: merging two documents means
    repointing every inbound reference, which needs the framework's link map. It raises
    rather than silently ignoring the flag and losing data.
    """
    entry, instance = _get_checked(doctype, old_name, "write")

    if merge:
        throw("Merging documents is not supported")

    new_name = validate_name(doctype, str(new_name))
    if new_name == old_name:
        return old_name
    if entry.model._default_manager.filter(pk=new_name).exists():
        throw(f"{doctype} {new_name} already exists")

    with transaction.atomic():
        # A string PK change is an insert + delete in Django, not an UPDATE.
        instance.pk = new_name
        instance._state.adding = True
        instance.save(force_insert=True)
        entry.model._default_manager.filter(pk=old_name).delete()

    return new_name


@whitelist("frappe.client.get_doc_permissions")
def client_get_doc_permissions(doctype: str, docname: str):
    """``frappe/client.py:get_doc_permissions``.

    Returns the permission map the frontend uses to grey out buttons. Unlike the other
    calls here this must **not** raise on a denied document - the caller is asking
    "what may I do", and the honest answer for an invisible row is "nothing".
    """
    entry = _entry_or_404(doctype)
    instance = entry.model._default_manager.filter(pk=docname).first()
    if instance is None:
        return {"permissions": {}}

    user = get_current_user()
    return {
        "permissions": {
            ptype: permissions.check_object_permission(instance, ptype, user)
            for ptype in ("read", "write", "delete", "create", "share", "print", "email")
        }
    }


@whitelist("frappe.desk.form.assign_to.add", methods=("POST",))
def assign_to_add(doctype: str, name: str, assign_to=None, description: str = "", **extra):
    """``frappe/desk/form/assign_to.py:add``.

    Creates the ToDo rows that *are* the assignment, so this is access-granting: a user
    who can assign a document to someone grants that someone read access to it. Write
    permission on the document is therefore required.
    """
    from frappe_core import assignment

    _entry, instance = _get_checked(doctype, name, "write")

    users = parse_json_param(assign_to, []) or []
    if isinstance(users, str):
        users = [users]

    added = []
    for user in users:
        if assignment.assign_to_user(doctype, name, user, description=description):
            added.append(user)
    return assignment.get_assigned_users(doctype, name)


@whitelist("frappe.desk.like.toggle_like", methods=("POST",))
def toggle_like(doctype: str, name: str, add: str = "No"):
    """``frappe/desk/like.py:toggle_like``.

    ``_liked_by`` is one of the four denormalised caches. It is written with a bare
    ``update()`` because a like must not bump ``modified`` - that would reorder every
    list view sorted by last-modified, which is the default sort
    (``AS_BUILT.md`` section 4).
    """
    _entry, instance = _get_checked(doctype, name, "read")

    user = get_current_user()
    liked = list(instance._liked_by or [])
    wants_like = str(add).lower() in ("yes", "1", "true")

    if wants_like and user not in liked:
        liked.append(user)
    elif not wants_like and user in liked:
        liked.remove(user)
    else:
        return liked

    type(instance)._default_manager.filter(pk=instance.pk).update(_liked_by=liked)
    return liked


@whitelist("frappe.desk.search.search_link")
def search_link(
    doctype: str,
    txt: str = "",
    query: str | None = None,
    filters=None,
    page_length: int = 10,
    reference_doctype: str | None = None,
    ignore_user_permissions: bool = False,
    **extra,
):
    """``frappe/desk/search.py:search_link``.

    Backs every Link field's autocomplete. Returns ``[{"value", "description"}]``, which
    is the shape ``frappe-ui``'s Link control reads.

    ``ignore_user_permissions`` is accepted and **ignored** - honouring it would let the
    autocomplete enumerate rows the caller cannot see, which is precisely the leak the
    phase-2 layer exists to prevent. Logged as a deliberate divergence.
    """
    entry = _entry_or_404(doctype)

    parsed_filters = parse_json_param(filters, None)
    or_filters = None
    if txt:
        or_filters = {"name": ["like", f"%{txt}%"]}
        title_field = getattr(entry.model, "SEARCH_FIELD", None)
        if title_field:
            or_filters[title_field] = ["like", f"%{txt}%"]

    fields = ["name"]
    title_field = getattr(entry.model, "SEARCH_FIELD", None)
    if title_field:
        fields.append(title_field)

    rows = fetch_rows(
        doctype,
        fields=fields,
        filters=parsed_filters,
        or_filters=or_filters,
        order_by="modified desc",
        limit_page_length=int(page_length or 10),
    )
    return [
        {
            "value": row["name"],
            "description": str(row.get(title_field) or "") if title_field else "",
        }
        for row in rows
    ]
