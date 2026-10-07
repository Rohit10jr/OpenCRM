"""Frappe's generic client API - ``frappe.client.*`` and two ``frappe.desk.*`` calls.

**Not in `PHASE_3_ENDPOINTS.md` section 2's group list, but required by the frontend.**
`PORT_PLAN.md` section 3 names them explicitly: *"Frontend also calls these Frappe
built-ins directly - they must exist"*, with call counts. Grepping the shipped frontend
confirms it: `frappe.client.delete`, `set_value`, `insert`, `get`, `get_list`,
`rename_doc`, `get_doc_permissions`, plus `frappe.desk.form.assign_to.add`,
`frappe.desk.like.toggle_like` and `frappe.desk.search.search_link`.

The frontend contract is a hard external contract, and the phase's first acceptance
criterion is "every dotted path resolves at its original URL" - so these are in scope
even though the group list omits them. Recorded as added scope in docs/internal/PROGRESS_PHASE_3.md.

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
from frappe_core.query import by_name, fetch_rows, parse_json_param
from frappe_core.rename import rename_document
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist


def _entry_or_404(doctype: str):
    if not registry.has_doctype(doctype):
        raise DoesNotExistError(f"DocType {doctype} not found")
    entry = registry.get_entry(doctype)
    if entry.is_child_table:
        raise DoesNotExistError(f"DocType {doctype} not found")
    return entry


def _user_query_filters(filters, ignore_user_type: bool) -> dict:
    """``frappe/core/doctype/user/user.py:user_query``, the standard query every User
    Link goes through: enabled accounts only, and no Website Users unless the caller,
    a System User, asked with ``ignore_user_type``, which the CRM's Link fields do
    (FINDINGS.md 46)."""
    from frappe_platform.models import User

    result = dict(filters or {})
    result.setdefault("enabled", 1)
    caller_type = (
        User._default_manager.filter(pk=get_current_user())
        .values_list("user_type", flat=True)
        .first()
    )
    if not (ignore_user_type and caller_type == "System User"):
        result["user_type"] = ["!=", "Website User"]
    return result


def _address_query_filters(filters: dict) -> dict:
    """``address.py:address_query``, the standard query behind every Address Link:
    ``link_doctype`` and ``link_name`` select the addresses linked to that document
    through their Dynamic Link rows; every other key filters as a field."""
    from frappe_platform.models import DynamicLink

    result = dict(filters)
    link_doctype = result.pop("link_doctype", None)
    link_name = result.pop("link_name", None)
    if link_doctype or link_name:
        rows = DynamicLink._default_manager.filter(parenttype="Address")
        if link_doctype:
            rows = rows.filter(link_doctype=link_doctype)
        if link_name:
            rows = rows.filter(link_name=link_name)
        result["name"] = ["in", list(rows.values_list("parent", flat=True).distinct())]
    return result


def _without_disabled(model, filters) -> dict | None:
    """``search.py:244-248``: a doctype with an ``enabled`` or ``disabled`` check hides
    its switched-off rows from the autocomplete unless ``include_disabled`` was sent."""
    names = {f.name for f in model._meta.get_fields()}
    if "enabled" not in names and "disabled" not in names:
        return filters
    result = dict(filters or {})
    if "enabled" in names:
        result.setdefault("enabled", 1)
    if "disabled" in names:
        result.setdefault("disabled", ["!=", 1])
    return result


def _get_checked(doctype: str, name: str, ptype: str):
    entry = _entry_or_404(doctype)
    instance = by_name(entry.model, name).first()
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
    """``frappe/client.py:get_single_value`` - one field off a singleton.

    **Three checks, and it shipped with one.** Found by the phase-7 review.

    The original only rejected `SENSITIVE_FIELDS`, which left this endpoint as a way around
    both of the other mechanisms:

    * no **row rule** was applied, so a doctype whose whole point is being manager-only —
      `CRM Twilio Settings`, `CRM Exotel Settings`, `ERPNext CRM Settings` — answered to any
      authenticated caller;
    * no **`RESTRICTED_FIELDS`** check, so the manager-only *fields* on those rows came back
      too.

    Concretely, before this fix, any Sales User could read
    `CRM Exotel Settings.webhook_verify_token` — the shared secret that is the entire
    authentication on a public webhook — and `ERPNext CRM Settings.api_key`. The hole
    predates phase 7 (`frappe.client.*` landed in phase 3), and phase 7 is what made it
    serious by putting credentials behind restricted fields.

    It is the same lesson as every other finding in this project, one layer along: *a
    doctype's endpoints are not its attack surface.* Here it was not even the generic
    route — it was a second, older method endpoint doing the same job unguarded.
    """
    from frappe_core.field_security import is_hidden

    entry = _entry_or_404(doctype)
    if not entry.is_single:
        throw(f"{doctype} is not a single DocType")

    instance = entry.model._default_manager.first()
    if instance is None:
        return None

    user = get_current_user()
    if not permissions.check_object_permission(instance, "read", user):
        raise FrappePermissionError(f"Not permitted to read {doctype}")

    # `is_hidden` answers for sensitive *and* restricted, and only consults roles for the
    # latter - the same entry point the four field-naming routes use.
    if is_hidden(entry.model, field, user):
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
    """``frappe/model/rename_doc.py:rename_doc``.

    Renames in place - every Link, Dynamic Link, child ``parent`` and version that named
    the document is repointed (:mod:`frappe_core.rename`); the frontend uses it on
    organizations, email templates, email accounts, assignment rules and SLA policies.
    The refusals are ``validate_rename``'s, in its order and with its wording, and all
    of them are a plain ``frappe.throw`` - 417, the permission one included.

    ``merge`` is **not** supported: merging two documents means folding one's references
    into the other's and deleting it, which nothing in the CRM asks for. It raises
    rather than silently ignoring the flag and losing data.
    """
    entry = _entry_or_404(doctype)

    if merge:
        throw("Merging documents is not supported")

    old_name = str(old_name)
    new_name = str(new_name)
    instance = entry.model._default_manager.filter(pk=old_name).first()
    if instance is None:
        throw(f"Can't rename {old_name} to {new_name} because {old_name} doesn't exist.")
    if old_name == new_name:
        throw("No changes made because old and new name are the same.")
    if entry.model._default_manager.filter(pk=new_name).exists():
        throw(f"Another {doctype} with name {new_name} exists, select another name")
    if not permissions.check_object_permission(instance, "write", get_current_user()):
        throw(f"You need write permission on {doctype} {old_name} to rename")
    # "validate naming like it's done in doc.py" - validate_rename's last step.
    new_name = validate_name(doctype, new_name)

    return rename_document(doctype, old_name, new_name)


@whitelist("frappe.client.get_doc_permissions")
def client_get_doc_permissions(doctype: str, docname: str):
    """``frappe/client.py:get_doc_permissions``.

    Returns the permission map the frontend uses to grey out buttons. Unlike the other
    calls here this must **not** raise on a denied document - the caller is asking
    "what may I do", and the honest answer for an invisible row is "nothing".
    """
    entry = _entry_or_404(doctype)
    instance = by_name(entry.model, docname).first()
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


@whitelist("frappe.desk.form.assign_to.add_multiple", methods=("POST",))
def assign_to_add_multiple(doctype: str, name=None, assign_to=None, description: str = "", **extra):
    """``frappe/desk/form/assign_to.py:148-156`` - ``add_multiple``.

    Upstream is ``json.loads(args["name"])`` and then :func:`add` per document, so this
    runs exactly what :func:`assign_to_add` runs for each name, write check included.
    ``name`` is the *list*, not a document - that odd shape is upstream's and the
    frontend sends it (``AssignmentModal.vue:160``, ``name: JSON.stringify(list)``).

    **Returns ``None``.** Upstream's ``add_multiple`` has no ``return`` statement; only
    the single-document ``add`` returns the assignee list. ``AssignmentModal.vue`` ignores
    the body and reloads the list, so the empty answer is what the frontend expects.

    ``bulk_assign`` / ``re_assign`` arrive from that same call and are **swallowed by
    ``**extra``**: upstream ignores them too - ``add`` reads neither out of ``args``, and
    nothing downstream of it does either. They are frontend-side analytics flags that
    happen to be sent along with the payload.

    **Divergence: the whole batch is one transaction.** Upstream loops with no
    transaction around it, so a document that refuses half way through leaves the earlier
    ones assigned and reports an error - the caller cannot tell which half applied. The
    port's other bulk paths (``crm.api.doc.delete_bulk_docs``) refuse the whole batch
    instead, and this follows them: a 403 on the third document unassigns the first two.
    """
    from frappe_core import assignment

    names = parse_json_param(name, []) or []
    if not isinstance(names, list):
        names = [names]

    users = parse_json_param(assign_to, []) or []
    if isinstance(users, str):
        users = [users]

    with transaction.atomic():
        for docname in names:
            # Same check `add` makes, per document: assigning grants the assignee read
            # access, so it takes write permission on the document being given away.
            _get_checked(doctype, docname, "write")
            for user in users:
                assignment.assign_to_user(doctype, docname, user, description=description)


@whitelist("frappe.desk.form.assign_to.remove_multiple", methods=("POST",))
def assign_to_remove_multiple(doctype: str, names=None, **extra):
    """``frappe/desk/form/assign_to.py:191-201`` - ``remove_multiple``.

    Upstream loops ``get()`` (the open assignments - status not in Cancelled/Closed) and
    calls ``remove()`` on each, which is ``set_status(..., status="Cancelled")``. Here
    that is :func:`assignment.get_assigned_users` (the same status filter - it is the
    display filter, ``INACTIVE_FOR_DISPLAY``) followed by
    :func:`assignment.cancel_assignment`, which cancels rather than deletes and fires the
    ToDo signal, so the assignee is notified exactly as upstream's ``notify_assignment``
    does.

    **``ignore_permissions`` is swallowed.** ``ListBulkActions.vue:154`` sends it, but
    upstream's ``remove_multiple`` takes only ``doctype`` and ``names`` - the framework
    drops the surplus argument before the function sees it, so it has no effect there
    either. This is *not* the ``crm.api.doc.remove_assignments`` case, where upstream
    really does accept the flag and honour it (see that function's note).

    Write permission per document, and the same one-transaction divergence
    :func:`assign_to_add_multiple` documents. Returns ``None``, as upstream does.

    One more divergence, deliberate: upstream's ``get()`` carries ``limit=5`` - it feeds
    the form sidebar, which shows five - so ``remove_multiple`` on a document with six
    assignees cancels five and leaves one. The button says "clear assignment"; here every
    open assignment goes.
    """
    from frappe_core import assignment

    parsed = parse_json_param(names, []) or []
    if not isinstance(parsed, list):
        parsed = [parsed]

    with transaction.atomic():
        for docname in parsed:
            _get_checked(doctype, docname, "write")
            assigned = assignment.get_assigned_users(doctype, docname)
            if assigned:
                assignment.cancel_assignment(doctype, docname, assigned)


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
    # Two keys the frontend sends inside `filters` that are not fields: upstream's
    # search_widget pops `include_disabled` (search.py:204-208) and User's standard
    # query pops `ignore_user_type` (user.py:user_query); the port read both as fields
    # and answered 400 to every User Link in the app (FINDINGS.md 46).
    include_disabled = False
    ignore_user_type = False
    if isinstance(parsed_filters, dict):
        include_disabled = _truthy(parsed_filters.pop("include_disabled", False))
        ignore_user_type = _truthy(parsed_filters.pop("ignore_user_type", False))
    if doctype == "User":
        parsed_filters = _user_query_filters(parsed_filters, ignore_user_type)
    else:
        if doctype == "Address" and isinstance(parsed_filters, dict):
            parsed_filters = _address_query_filters(parsed_filters)
        if not include_disabled and isinstance(parsed_filters, (dict, type(None))):
            parsed_filters = _without_disabled(entry.model, parsed_filters)

