"""``crm.api.doc.*`` - Group A. Ported from ``crm/api/doc.py``.

``get_data`` is deliberately absent: phase 0 built it in ``frappe_core/api/doc.py`` and
registered the same dotted path. Re-registering it here would silently shadow the
tested implementation.

Field metadata comes from ``frappe_core.metadata``; this module wraps it rather than
re-deriving allowlists, because phase 4 owns fixing them to key on the Frappe fieldtype
(C7) and a second copy would have to be found and fixed twice.
"""

from __future__ import annotations

import json

from django.core.exceptions import FieldDoesNotExist
from django.db import transaction
from django.db.models.fields.related import ForeignKey, OneToOneField

from frappe_core import assignment, metadata, permissions, registry
from frappe_core.exceptions import DoesNotExistError
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.exceptions import ValidationError, throw
from frappe_core.metadata import _frappe_fieldtype, _link_target
from frappe_core.query import by_name, parse_json_param
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

#: ``crm/api/doc.py:38-44`` - appended to every ``sort_options`` response.
SORT_STANDARD_FIELDS = [
    {"label": "Name", "fieldname": "name"},
    {"label": "Created On", "fieldname": "creation"},
    {"label": "Last Modified", "fieldname": "modified"},
    {"label": "Modified By", "fieldname": "modified_by"},
    {"label": "Owner", "fieldname": "owner"},
]


def _concrete_fields(model):
    return [f for f in model._meta.get_fields() if getattr(f, "concrete", False)]


def _field_descriptor(field) -> dict:
    return {
        "label": str(getattr(field, "verbose_name", field.name)),
        "fieldname": field.name,
        "fieldtype": _resolved_fieldtype(field),
        "options": _link_target(field) or _select_options_string(field),
    }


def _resolved_fieldtype(field) -> str:
    """``_frappe_fieldtype`` cannot see a Select; a ``CharField`` with ``choices`` is one.

    Phase 0's mapping keys on the **Django internal type**, so ``Select`` and ``Data``
    are the same thing to it - that is C7, and it is phase 4's to fix properly. Until
    then this narrow correction is needed here, because ``get_quick_filters`` branches
    on the fieldtype to decide whether to expand ``options`` into a list: without it the
    frontend receives a raw newline-separated string and renders its first character.
    """
    if getattr(field, "choices", None) and _frappe_fieldtype(field) == "Data":
        return "Select"
    return _frappe_fieldtype(field)


def _select_options_string(field):
    """Frappe stores Select options as one newline-separated string."""
    choices = getattr(field, "choices", None)
    if not choices:
        return None
    return "\n".join(str(c[0]) for c in choices)


@whitelist("crm.api.doc.sort_options")
def sort_options(doctype: str):
    """``crm/api/doc.py:24-51``.

    Upstream drops ``no_value_fields`` (layout types, Table, Button). Those were never
    materialised as columns in this port (PHASE_1_MODELS.md section 2), so every
    concrete field qualifies.
    """
    entry = registry.get_entry(doctype)
    fields = [
        {
            "label": str(getattr(field, "verbose_name", field.name)),
            "value": field.name,
            "fieldname": field.name,
        }
        for field in _concrete_fields(entry.model)
    ]
    for standard in SORT_STANDARD_FIELDS:
        fields.append({**standard, "value": standard["fieldname"]})
    return fields


@whitelist("crm.api.doc.get_filterable_fields")
def get_filterable_fields(doctype: str):
    """``crm/api/doc.py:54-109``. Delegates to the phase-0 implementation."""
    return metadata.get_filterable_fields(doctype)


@whitelist("crm.api.doc.get_group_by_fields")
def get_group_by_fields(doctype: str):
    """``crm/api/doc.py:112-160``. Delegates to the phase-0 implementation."""
    return metadata.get_group_by_fields(doctype)


#: ``in_standard_filter`` per doctype, transcribed from the DocType JSON.
#:
#: Kept in one table rather than as a ``get_standard_filter_fields`` staticmethod per
#: model (the pattern ``get_hidden_fields`` uses) for one reason: **phase 4 owns field
#: metadata** (C7) and will fold this into the real field-meta layer, so scattering it
#: across five model files now means finding it in five places later.
#:
#: ``test_standard_filter_fields_match_the_json`` reads every DocType JSON and asserts
#: this mapping is exactly right, so its location does not affect its correctness. A
#: per-model override is still honoured, so phase 4 can migrate incrementally.
STANDARD_FILTER_FIELDS: dict[str, list[str]] = {
    "CRM Call Log": ["from", "status", "type", "to", "telephony_medium"],
    "CRM Deal": ["organization", "email", "status"],
    "CRM Fields Layout": ["dt", "type"],
    "CRM Lead": ["status", "email", "lead_name", "organization", "converted"],
    "CRM Organization": ["organization_name", "no_of_employees", "industry", "territory"],
    "CRM Service Level Agreement": ["sla_name"],
    "CRM Task": ["title", "priority", "assigned_to", "status", "due_date"],
    "CRM Telephony Agent": ["user", "mobile_no", "user_name"],
    "CRM View Settings": ["label", "dt"],
    "FCRM Note": ["title", "content"],
}


def _standard_filter_fields(entry) -> list[str]:
    """Fieldnames the doctype marks ``in_standard_filter`` in its JSON.

    Upstream reads it off ``DocField`` and lets a Property Setter override it at
    runtime; this port has no Property Setter, so the CRM Global Settings row is the
    only runtime override - and that is the branch ``get_quick_filters`` checks first
    anyway, so the observable behaviour matches.
    """
    provider = getattr(entry.model, "get_standard_filter_fields", None)
    if callable(provider):
        return list(provider() or [])
    return list(STANDARD_FILTER_FIELDS.get(entry.doctype, []))


@whitelist("crm.api.doc.get_quick_filters")
def get_quick_filters(doctype: str, cached: bool = True):
    """``crm/api/doc.py:163-204``.

    ``cached`` is accepted and ignored - it selects Frappe's meta cache upstream, which
    has no analogue here. Dropping the parameter would 500 the frontend, which sends it.
    """
    from crm_app.models import CRMGlobalSettings

    entry = registry.get_entry(doctype)
    by_name = {f.name: f for f in _concrete_fields(entry.model)}

    row = CRMGlobalSettings._default_manager.filter(dt=doctype, type="Quick Filters").first()
    fields: list[dict] = []

    if row is not None:
        selected = row.json or []
        if isinstance(selected, str):
            selected = json.loads(selected or "[]")
        for fieldname in selected:
            if fieldname == "name":
                fields.append({"label": "Name", "fieldname": "name", "fieldtype": "Data"})
            elif fieldname in by_name:
                fields.append(_field_descriptor(by_name[fieldname]))
    else:
        fields = [
            _field_descriptor(by_name[name])
            for name in _standard_filter_fields(entry)
            if name in by_name
        ]

    quick_filters = []
    for field in fields:
        options = field.get("options")
        if field.get("fieldtype") == "Select" and options and isinstance(options, str):
            parsed = [{"label": o, "value": o} for o in options.split("\n")]
            # Upstream prepends a blank choice unless one is already present.
            if not any(not o.get("value") for o in parsed):
                parsed.insert(0, {"label": "", "value": ""})
            options = parsed
        quick_filters.append(
            {
                "label": field.get("label"),
                "fieldname": field.get("fieldname"),
                "fieldtype": field.get("fieldtype"),
                "options": options,
            }
        )

    if doctype == "CRM Lead":
        # crm/api/doc.py:201-202
        quick_filters = [f for f in quick_filters if f.get("fieldname") != "converted"]

    return quick_filters


@whitelist("crm.api.doc.update_quick_filters")
def update_quick_filters(quick_filters: str | list, old_filters: str | list, doctype: str):
    """``crm/api/doc.py:207-224``.

    Upstream does two things: writes the CRM Global Settings row, and flips
    ``in_standard_filter`` on each added/removed field via a Property Setter. Only the
    first is ported - ``Property Setter`` is a framework doctype this port does not
    model. The effect is the same, because once the Global Settings row exists
    ``get_quick_filters`` reads it and never consults ``in_standard_filter`` again
    (``crm/api/doc.py:168``).
    """
    from crm_app.models import CRMGlobalSettings

    registry.get_entry(doctype)  # 404 for an unknown doctype, as upstream would
    selected = parse_json_param(quick_filters, []) or []
    parse_json_param(old_filters, [])  # accepted for signature fidelity

    row = CRMGlobalSettings._default_manager.filter(dt=doctype, type="Quick Filters").first()
    if row is None:
        CRMGlobalSettings._default_manager.create(
            dt=doctype, type="Quick Filters", json=list(selected)
        )
    else:
        row.json = list(selected)
        row.save()


def _require_readable(doctype: str, name: str):
    """Read permission on the named document, or 403.

    Upstream omits this on several of the endpoints below - it reads ToDo and link rows
    without checking the *subject* document first. That is a leak with no upside
    (assignee emails, the titles of related records), and it is invisible to an honest
    client, which only ever asks about documents it can already see. Diverging closes it;
    `PHASE_3_ENDPOINTS.md` criterion 9 requires it either way.
    """
    if not registry.has_doctype(doctype):
        raise DoesNotExistError(f"DocType {doctype} not found")
    instance = by_name(registry.get_model(doctype), name).first()
    if instance is None:
        raise DoesNotExistError(f"{doctype} {name} not found")
    if not permissions.check_object_permission(instance, "read", get_current_user()):
        raise FrappePermissionError(f"No permission for {doctype} {name}", title="Not Permitted")
    return instance


@whitelist("crm.api.doc.get_assigned_users")
def get_assigned_users(doctype: str, name: str, default_assigned_to: str | None = None):
    """``crm/api/doc.py:607-625``.

    Uses the phase-0 helper, whose default status filter excludes ``Closed`` *and*
    ``Cancelled`` - which is what this endpoint wants. The permission view is a
    different filter; see ``AS_BUILT.md`` section 4.
    """
    _require_readable(doctype, name)
    users = assignment.get_assigned_users(doctype, name)
    if not users and default_assigned_to:
        users = [default_assigned_to]
    return users


@whitelist("crm.api.doc.remove_assignments")
def remove_assignments(
    doctype: str, name: str, assignees: str | list, ignore_permissions: bool = False
):
    """``crm/api/doc.py:589-604``.

    Upstream cancels the ToDo rather than deleting it, via
    ``frappe.desk.form.assign_to.set_status(..., status="Cancelled")``. Cancelling is
    load-bearing: a cancelled ToDo grants no access (PHASE_2_PERMISSIONS.md section 2),
    whereas deleting the row would lose the audit trail upstream keeps.
    """
    parsed = parse_json_param(assignees, []) or []
    if isinstance(parsed, str):
        parsed = [parsed]
    if not parsed:
        return

    # `ignore_permissions` is accepted for signature fidelity and **deliberately not
    # honoured**. Upstream is whitelisted with the same parameter and passes it straight
    # to `set_status` (`crm/api/doc.py:597-604`), which means any authenticated caller
    # can send `ignore_permissions=True` and cancel assignments on a document they
    # cannot write. That is a privilege escalation reachable from the public API, and
    # no honest client sends the flag - so ignoring it is invisible to the frontend and
    # closes the hole. Recorded in UPSTREAM_BUGS.md.
    entry = registry.get_entry(doctype)
    instance = by_name(entry.model, name).first()
    if instance is None:
        throw(f"{doctype} {name} not found")
    if not permissions.check_object_permission(instance, "write", get_current_user()):
        raise FrappePermissionError(f"No permission for {doctype} {name}")

    assignment.cancel_assignment(doctype, name, parsed)


#: The DocField flags a row always carries, as 0 when the JSON leaves them out.
#: ``EditValueModal.vue:78`` keeps a field only when ``hidden == 0 && read_only == 0``,
#: so a missing key (``undefined == 0`` is false) empties the bulk-edit dropdown
#: (FINDINGS.md 52); the generator drops zero-valued keys, so they are restored here.
DOCFIELD_FLAG_DEFAULTS = {
    "hidden": 0,
    "read_only": 0,
    "reqd": 0,
    "permlevel": 0,
    "in_list_view": 0,
    "in_standard_filter": 0,
}


def docfield(field: dict) -> dict:
    """A DocField row as ``frappe.get_meta(doctype).fields`` hands it out: the JSON's
    keys plus the zero flags, and ``options`` / ``description`` / ``default`` present
    even when empty, since the frontend destructures them."""
    row = {"options": None, "description": None, "default": None}
    row.update(DOCFIELD_FLAG_DEFAULTS)
    row.update(field)
    return row


@whitelist("crm.api.doc.get_fields")
def get_fields(doctype: str, allow_all_fieldtypes: bool = False):
    """``crm/api/doc.py:639-651``: the doctype's DocFields in declaration order, minus
    the value-less types (``frappe.model.no_value_fields``) and ``Read Only``, unless
    ``allow_all_fieldtypes`` asks for every one of them.

    Two screens read it. The bulk-edit dialog (``EditValueModal.vue``) offers the fields
    that are neither hidden nor read-only, then renders an input by ``fieldtype`` with
    ``options`` for a Select or a Link. The settings page (``SettingsPage.vue``) asks
    with ``allow_all_fieldtypes`` and lays the form out from the Tab, Section and Column
    Breaks, so those must come through too. Both need the DocType's own field list -
    labels, order and layout - not the Django model's columns, which is what this served
    before and why the dropdown was empty (FINDINGS.md 52).
    """
    from frappe_core import field_meta
    from frappe_core.field_meta import NO_VALUE_FIELDTYPES

    registry.get_entry(doctype)  # 404 for a doctype the port does not have
    if str(allow_all_fieldtypes).strip().lower() in ("1", "true"):
        not_allowed = frozenset()
    else:
        not_allowed = NO_VALUE_FIELDTYPES | {"Read Only"}
    return [
        docfield(field)
        for field in field_meta.get_fields(doctype)
        if field.get("fieldname") and field.get("fieldtype") not in not_allowed
    ]


#: Doctypes whose rows go with the document instead of standing in the way of its
#: deletion: the framework's ``ignore_links_on_delete`` hook (``frappe/hooks.py:455-470``)
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


def _parent_fk_name(model) -> str | None:
    """The FK a child row reaches its parent through: the one whose reverse name is the
    row's ``parentfield`` (``crm_app/api/client.py:_child_row_and_parent`` walks the
    same way). A polymorphic child (``CRM Products``, ``Dynamic Link``) has none; its
    parent is a name in the ``parent`` column."""
    try:
        parentfield = model._meta.get_field("parentfield").default
    except FieldDoesNotExist:
        return None
    for field in model._meta.concrete_fields:
        if field.is_relation and field.remote_field.related_name == parentfield:
            return field.name
    return None


def _parent_of(row):
    """The document a child row belongs to, or ``None``."""
    fk_name = _parent_fk_name(type(row))
    if fk_name:
        return getattr(row, fk_name, None)
    parenttype, parent = getattr(row, "parenttype", ""), getattr(row, "parent", "")
    if parenttype and parent and registry.has_doctype(parenttype):
        return by_name(registry.get_model(parenttype), parent).first()
    return None


def _link_sources(target_doctype: str):
    """Every ``(doctype, entry, fieldname, via_child)`` whose FK points at
    ``target_doctype``.

    A child table's own parent FK is not a link: the row belongs to the document and
    goes with it. Upstream never sees it, because the ``parent`` column is not a Link
    field (``delete_doc.py:313-319``). Listed as a linked document, a deal's own
    contact row could not be unlinked, so after "Unlink All" it was still there and the
    Delete button never appeared (FINDINGS.md 75). A child table's *other* FKs are
    links, and for those upstream lists the parent document (``delete_doc.py:352-384``):
    ``via_child`` tells the caller to resolve each row to its parent.
    """
    for doctype in registry.all_doctypes():
        if doctype in IGNORE_LINKS_ON_DELETE:
            continue
        entry = registry.get_entry(doctype)
        parent_fk = _parent_fk_name(entry.model) if entry.is_child_table else None
        for field in entry.model._meta.get_fields():
            if not isinstance(field, (ForeignKey, OneToOneField)) or field.name == parent_fk:
                continue
            related = field.related_model
            if getattr(related, "get_doctype", lambda: None)() == target_doctype:
                yield doctype, entry, field.name, entry.is_child_table


def _parents_of_rows(rows, doctype: str, names: set[str], user):
    """The parent documents of linking child rows, as upstream lists them: the document
    being deleted is skipped (``delete_doc.py:370-372``), and so is a parent the caller
    cannot read, the rule the rest of this endpoint keeps."""
    for row in rows:
        parent = _parent_of(row)
        if parent is None:
            continue
        parent_doctype = type(parent).get_doctype()
        if parent_doctype == doctype and str(parent.pk) in names:
            continue
        if not permissions.check_object_permission(parent, "read", user):
            continue
        yield parent_doctype, parent


def _dynamic_link_sources(target_doctype: str):
    """Doctypes using Frappe's ``reference_doctype`` / ``reference_name`` convention.

    Upstream calls ``get_dynamic_linked_docs``; this reproduces it over the two spellings
    the CRM actually uses (``reference_name`` and ``reference_docname``).
    """
    for doctype in registry.all_doctypes():
        if doctype in IGNORE_LINKS_ON_DELETE:
            continue
        entry = registry.get_entry(doctype)
        names = {f.name for f in entry.model._meta.get_fields() if getattr(f, "concrete", False)}
        if "reference_doctype" not in names:
            continue
        for name_field in ("reference_name", "reference_docname"):
            if name_field in names:
                yield doctype, entry, name_field
                break


def _linked_doc_title(doctype: str, instance) -> str:
    """``crm/api/doc.py:700-708`` - three doctypes get a bespoke title."""
    if doctype == "CRM Call Log":
        return f"Call from {getattr(instance, 'from')} to {getattr(instance, 'to')}"
    if doctype == "CRM Deal":
        return getattr(instance, "organization_id", None) or str(instance.pk)
    if doctype == "CRM Notification":
        return instance.message or str(instance.pk)
    return getattr(instance, "title", None) or str(instance.pk)


@whitelist("crm.api.doc.get_linked_docs_of_document")
def get_linked_docs_of_document(doctype: str, docname: str):
    """``crm/api/doc.py:677-718``.

    Upstream leans on the framework's link map. Here the equivalent is derived from the
    registry: every FK pointing at this doctype, plus the dynamic
    ``reference_doctype``/``reference_name`` convention.

    Results are permission-filtered. Upstream is not - it uses ``frappe.get_doc``
    directly - but returning the titles of documents the caller cannot open would be a
    leak with no upside, and this endpoint feeds a "delete will also affect these" UI.
    """
    _require_readable(doctype, docname)

    from frappe_core.query import base_queryset

    user = get_current_user()
    seen: set[tuple[str, str]] = set()
    results: list[dict] = []

    def collect(linked_doctype: str, linked_entry, queryset):
        for instance in queryset:
            key = (linked_doctype, str(instance.pk))
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "doc": linked_doctype,
                    "title": _linked_doc_title(linked_doctype, instance),
                    "reference_docname": str(instance.pk),
                    "reference_doctype": linked_doctype,
                }
            )

    for linked_doctype, linked_entry, fieldname, via_child in _link_sources(doctype):
        queryset = base_queryset(linked_doctype, user).filter(**{fieldname: docname})
        if via_child:
            for parent_doctype, parent in _parents_of_rows(queryset, doctype, {str(docname)}, user):
                collect(parent_doctype, None, [parent])
        else:
            collect(linked_doctype, linked_entry, queryset)

    for linked_doctype, linked_entry, name_field in _dynamic_link_sources(doctype):
        queryset = base_queryset(linked_doctype, user).filter(
            reference_doctype=doctype, **{name_field: docname}
        )
        collect(linked_doctype, linked_entry, queryset)

    return results


def _clear_reference(instance) -> None:
    """``crm/api/doc.py:721-749`` - blank the reference rather than delete the row."""
    doctype = type(instance).get_doctype()
    updates: dict = {}
    names = {f.name for f in type(instance)._meta.get_fields() if getattr(f, "concrete", False)}

    if doctype == "CRM Notification":
        updates = {"reference_doctype": "", "reference_name": ""}
        # Upstream only clears the notification-type pair when it matches the reference.
        if instance.notification_type_doctype == instance.reference_doctype:
            updates.update({"notification_type_doctype": "", "notification_type_doc": ""})
    else:
        if "reference_doctype" in names:
            updates["reference_doctype"] = ""
        if "reference_docname" in names:
            updates["reference_docname"] = ""
        if "reference_name" in names:
            updates["reference_name"] = ""

    if updates:
        type(instance)._default_manager.filter(pk=instance.pk).update(**updates)


def _clear_contact(instance) -> None:
    """``crm/api/doc.py:752-766`` - used when the deleted document is a Contact."""
    model = type(instance)
    names = {f.name for f in model._meta.get_fields() if getattr(f, "concrete", False)}
    if "contact" in names:
        model._default_manager.filter(pk=instance.pk).update(contact=None)
    if hasattr(instance, "contacts"):
        instance.contacts.all().delete()


@whitelist("crm.api.doc.remove_linked_doc_reference")
def remove_linked_doc_reference(
    items: str | list, remove_contact: bool = False, delete: bool = False
):
    """``crm/api/doc.py:769-792``. Returns the literal string ``"success"``, as upstream does."""
    parsed = parse_json_param(items, []) or []
    user = get_current_user()

    for item in parsed:
        if not isinstance(item, dict):
            continue
        item_doctype, item_name = item.get("doctype"), item.get("docname")
        if not item_doctype or not item_name:
            continue
        if not registry.has_doctype(item_doctype):
            continue

        instance = registry.get_model(item_doctype)._default_manager.filter(pk=item_name).first()
        if instance is None:
            continue
        # Upstream checks write permission and skips silently on failure (line 778).
        if not permissions.check_object_permission(instance, "write", user):
            continue

        if remove_contact:
            _clear_contact(instance)
        else:
            _clear_reference(instance)

        if delete:
            instance.delete()

    return "success"


#: Above this many items upstream enqueues the delete instead of running it inline
#: (``crm/api/doc.py:833``). Phase 5 turns this into a real Celery task.
BULK_DELETE_ENQUEUE_THRESHOLD = 10


def authorize_bulk_delete(doctype: str, names: list[str], user: str) -> list[str]:
    """Resolve ``names`` to the rows ``user`` may delete, or refuse the whole batch.

    Split out of :func:`delete_bulk_docs` in phase 5 so the Celery task can run the same
    check itself rather than trusting the caller (`PHASE_5_ASYNC.md` §5).

    C9: the *visibility* half is batched into a single permission-filtered query rather
    than N calls to ``has_permission``.

    That batched query is a pre-filter, not the whole check. It is the **list** rule, and
    for the two metadata doctypes the list rule is deliberately weaker than the write
    rule — anyone may read a public ``CRM View Settings`` row, only its owner or an admin
    may delete one (``permissions/metadata_docs.py``). Checking visibility alone would
    have made this endpoint delete what ``DELETE /api/resource/<dt>/<name>`` refuses
    (``frappe_core/views.py:133``), which is upstream's behaviour too: ``delete_bulk``
    goes through ``frappe.delete_doc``, and that runs ``check_permission("delete")`` per
    document. So the surviving rows get the object hook as well, on instances already
    loaded — no extra query per item.
    """
    from frappe_core.query import base_queryset

    entry = registry.get_entry(doctype)

    permitted = set(
        str(pk)
        for pk in base_queryset(doctype, user).filter(pk__in=names).values_list("pk", flat=True)
    )
    instances = {
        str(obj.pk): obj for obj in entry.model._default_manager.filter(pk__in=names)
    }
    existing = set(instances)

    denied = sorted((existing - permitted))
    # The object rule can be stricter than the list rule, so visibility alone is not
    # enough. Batched (C9): one query for the whole batch, not one per item.
    survivors = permissions.filter_object_permitted(
        doctype, [instances[n] for n in sorted(existing & permitted)], "delete", user
    )
    denied += sorted((existing & permitted) - {str(doc.pk) for doc in survivors})
    if denied:
        raise FrappePermissionError(
            f"No permission to delete {doctype} {denied[0]}", title="Not Permitted"
        )

    # Names that no longer exist are dropped, not an error: that is what makes a retried
    # delivery of the Celery task a no-op instead of a failure.
    return [n for n in names if n in existing]


def perform_bulk_delete(doctype: str, targets: list[str], delete_linked: bool = False) -> None:
    """The delete itself. Assumes :func:`authorize_bulk_delete` has already passed."""
    entry = registry.get_entry(doctype)

    with transaction.atomic():
        # The link scan is batched the same way the permission check is: one query per
        # *link source* for the whole batch, rather than one per source per item. Doing
        # it per item made the query count grow ~14x per row, which is the same N+1 C9
        # is about - just in the other half of the function.
        for link in _linked_docs_for_batch(doctype, targets):
            _clear_or_delete_link(link, remove_contact=(doctype == "Contact"), delete=delete_linked)

        # The reference cleanup delete_doc.py does per document (ToDo, Version, Comment,
        # File, Communication) is batched the same way: one query per reference doctype
        # for the whole batch, and the per-row hook stands down.
        from frappe_core import children

        children.delete_references_batch(doctype, targets)
        with children.references_handled():
            entry.model._default_manager.filter(pk__in=targets).delete()


@whitelist("crm.api.doc.delete_bulk_docs")
def delete_bulk_docs(doctype: str, items: str | list, delete_linked: bool = False):
    """``crm/api/doc.py:795-837``.

    Two things upstream leaves loose and this does not:

    * **Permission is checked per item** (spec acceptance criterion). Upstream relies on
      ``frappe.desk.reportview.delete_bulk`` to do it; we check explicitly and refuse the
      whole batch if any item is denied, rather than half-deleting.
    * **The batch is one transaction.** Upstream deletes row by row and logs failures.
      A partially-applied bulk delete is worse than a rejected one.

    Over :data:`BULK_DELETE_ENQUEUE_THRESHOLD` items it goes to Celery, matching
    ``crm/api/doc.py:833``. The authorization runs here *and* again in the worker: here so
    the caller gets a refusal instead of a silent background failure, and there because a
    task must not trust its own arguments (`PHASE_5_ASYNC.md` §5).
    """
    if not doctype:
        throw("Doctype is required")
    parsed = parse_json_param(items, []) or []
    if not parsed:
        throw("Items are required")
    if not isinstance(parsed, list):
        throw("Items must be a list")

    user = get_current_user()
    names = [str(i) for i in parsed]
    targets = authorize_bulk_delete(doctype, names, user)

    if len(targets) > BULK_DELETE_ENQUEUE_THRESHOLD:
        from crm_app.tasks import delete_bulk_docs_task

        delete_bulk_docs_task.delay(doctype, targets, delete_linked, user)
        return "success"

    perform_bulk_delete(doctype, targets, delete_linked)
    return "success"


def _linked_docs_for_batch(doctype: str, names: list[str]):
    """Every document linking to *any* of ``names``, in a bounded number of queries."""
    from frappe_core.query import base_queryset

    if not names:
        return []

    user = get_current_user()
    seen: set[tuple[str, str]] = set()
    found = []

    def collect(linked_doctype, queryset):
        for instance in queryset:
            key = (linked_doctype, str(instance.pk))
            if key not in seen:
                seen.add(key)
                found.append((linked_doctype, instance))

    for linked_doctype, _entry, fieldname, via_child in _link_sources(doctype):
        rows = base_queryset(linked_doctype, user).filter(**{f"{fieldname}__in": names})
        if via_child:
            for parent_doctype, parent in _parents_of_rows(rows, doctype, set(names), user):
                collect(parent_doctype, [parent])
        else:
            collect(linked_doctype, rows)
    for linked_doctype, _entry, name_field in _dynamic_link_sources(doctype):
        collect(
            linked_doctype,
            base_queryset(linked_doctype, user).filter(
                reference_doctype=doctype, **{f"{name_field}__in": names}
            ),
        )
    return found


def _clear_or_delete_link(link, *, remove_contact: bool, delete: bool) -> None:
    _linked_doctype, instance = link
    if not permissions.check_object_permission(instance, "write", get_current_user()):
        return
    if remove_contact:
        _clear_contact(instance)
    else:
        _clear_reference(instance)
    if delete:
        instance.delete()
