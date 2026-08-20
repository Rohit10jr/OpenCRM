"""``crm.fcrm.doctype.crm_view_settings.crm_view_settings.*`` — saved views.

Ported from ``crm/fcrm/doctype/crm_view_settings/crm_view_settings.py``. These are
controller methods rather than ``crm/api/`` endpoints, but the frontend calls them by
their full dotted path, so they are part of the same contract.

The permission model here is its own thing and is worth stating plainly, because it is
not the phase-2 row rule (``check_permission``, source :150-160):

* Administrator and System Manager may edit any view
* a **public** view may be edited by a Sales Manager
* a **private** view may be edited only by its owner

Everything routes through :func:`check_permission`, so there is one definition of it.
"""

from __future__ import annotations

import json

from frappe_core import registry
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.query import parse_json_param
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

VIEW_SETTINGS = "CRM View Settings"


def _roles(user: str) -> set[str]:
    from frappe_platform.models import User

    obj = User._default_manager.filter(pk=user).first()
    return obj.get_roles() if obj else set()


def check_permission(doc) -> None:
    """``crm_view_settings.py:150-160``. Message ``"Not permitted"`` verbatim."""
    user = get_current_user()
    roles = _roles(user)

    if user == "Administrator" or "System Manager" in roles:
        return
    if doc.public and "Sales Manager" in roles:
        return
    if doc.user_id and doc.user_id == user:
        return
    raise FrappePermissionError("Not permitted")


def remove_duplicates(values: list) -> list:
    """``crm_view_settings.py:163-164`` — order-preserving."""
    return list(dict.fromkeys(values))


def get_route_name(doctype: str) -> str:
    """``crm_view_settings.py:318-328``. ``"CRM Lead"`` -> ``"Leads"``."""
    if doctype.startswith("CRM "):
        doctype = doctype[4:]
    if not doctype.endswith("s"):
        doctype += "s"
    return doctype


def sync_default_rows(doctype: str, type: str = "list") -> list:
    """``crm_view_settings.py:167-174``."""
    if not registry.has_doctype(doctype):
        return []
    entry = registry.get_entry(doctype)
    return list(entry.default_list_data().get("rows") or [])


def sync_default_columns(view: dict) -> list:
    """``crm_view_settings.py:177-194``.

    For a kanban with a ``column_field`` the columns come from the Link target's rows or
    the Select's options — the same resolution ``get_data``'s kanban branch does, and it
    goes through the permission layer for the same reason.
    """
    from frappe_core import field_meta
    from frappe_core.query import base_queryset

    doctype = view.get("dt") or view.get("doctype")
    if not doctype or not registry.has_doctype(doctype):
        return []

    if view.get("type") == "kanban" and view.get("column_field"):
        field = field_meta.get_field(doctype, view["column_field"])
        if not field:
            return []
        if field.get("fieldtype") == "Link" and field.get("options"):
            target = field["options"]
            if not registry.has_doctype(target):
                return []
            return [
                {"name": pk}
                for pk in base_queryset(target, get_current_user())
                .order_by("modified")
                .values_list("pk", flat=True)
            ]
        if field.get("fieldtype") == "Select":
            return [{"name": option} for option in field_meta.select_options(field)]
        return []

    entry = registry.get_entry(doctype)
    return list(entry.default_list_data().get("columns") or [])


def _normalise(view: dict) -> dict:
    """Parse the five JSON-ish fields the frontend may send as strings or natives."""
    parsed = dict(view)
    for key in ("filters", "columns", "rows", "kanban_columns", "kanban_fields"):
        value = parse_json_param(parsed.get(key), None)
        if value in (None, ""):
            value = {} if key == "filters" else []
        parsed[key] = value
    return parsed


def _apply(doc, view: dict, *, doctype: str) -> None:
    """The field assignment shared by create/update/standard-view."""
    doc.label = view.get("label") or doc.label
    doc.type = view.get("type") or "list"
    doc.icon = view.get("icon") or ""
    doc.route_name = view.get("route_name") or get_route_name(doctype)
    doc.load_default_columns = bool(view.get("load_default_columns") or False)
    doc.filters = json.dumps(view["filters"])
    doc.order_by = view.get("order_by") or ""
    doc.group_by_field = view.get("group_by_field") or ""
    doc.column_field = view.get("column_field") or ""
    doc.title_field = view.get("title_field") or ""
    doc.kanban_columns = json.dumps(view["kanban_columns"])
    doc.kanban_fields = json.dumps(view["kanban_fields"])
    doc.columns = json.dumps(view["columns"])
    doc.rows = json.dumps(view["rows"])


def _merge_default_rows(view: dict, doctype: str) -> None:
    """``rows + default_rows``, deduplicated — source :57-59, :96-98, :224-226."""
    default_rows = sync_default_rows(doctype, view.get("type") or "list")
    if default_rows:
        view["rows"] = list(view["rows"]) + default_rows
    view["rows"] = remove_duplicates(view["rows"])


def _serialise(doc) -> dict:
    return registry.get_entry(VIEW_SETTINGS).get_serializer_class()(doc).data


@whitelist("crm.fcrm.doctype.crm_view_settings.crm_view_settings.create", methods=("POST",))
def create(view: str | dict):
    """``crm_view_settings.py:45-81``."""
    from crm_app.models import CRMViewSettings

    parsed = _normalise(parse_json_param(view, {}) or {})
    doctype = parsed.get("doctype")
    _merge_default_rows(parsed, doctype)

    if not parsed["kanban_columns"] and parsed.get("type") == "kanban":
        parsed["kanban_columns"] = sync_default_columns(parsed)
    elif not parsed["columns"]:
        parsed["columns"] = sync_default_columns(parsed)

    doc = CRMViewSettings(dt=doctype, user_id=get_current_user(), label=parsed.get("label"))
    _apply(doc, parsed, doctype=doctype)
    doc.save()
    return _serialise(doc)


@whitelist("crm.fcrm.doctype.crm_view_settings.crm_view_settings.update", methods=("POST", "PUT"))
def update(view: str | dict):
    """``crm_view_settings.py:84-116``."""
    from crm_app.models import CRMViewSettings

    parsed = _normalise(parse_json_param(view, {}) or {})
    doc = CRMViewSettings._default_manager.filter(pk=parsed.get("name")).first()
    if doc is None:
        from frappe_core.exceptions import DoesNotExistError

        raise DoesNotExistError(f"{VIEW_SETTINGS} {parsed.get('name')} not found")
    check_permission(doc)

    doctype = parsed.get("doctype") or doc.dt
    _merge_default_rows(parsed, doctype)
    _apply(doc, parsed, doctype=doctype)
    doc.save()
    return _serialise(doc)


@whitelist(
    "crm.fcrm.doctype.crm_view_settings.crm_view_settings.delete", methods=("POST", "DELETE")
)
def delete(name: str | int):
    """``crm_view_settings.py:119-123``. Silent when the view is already gone."""
    from crm_app.models import CRMViewSettings

    doc = CRMViewSettings._default_manager.filter(pk=name).first()
    if doc is None:
        return
    check_permission(doc)
    doc.delete()


@whitelist("crm.fcrm.doctype.crm_view_settings.crm_view_settings.public", methods=("POST",))
def public(name: str | int, value: bool | int):
    """``crm_view_settings.py:126-135``.

    Note this one does **not** use ``check_permission``: making a view public is a
    stronger act than editing it, and upstream gates it on Administrator or Sales
    Manager only. Message verbatim.
    """
    from crm_app.models import CRMViewSettings
    from frappe_core.exceptions import DoesNotExistError

    user = get_current_user()
    if user != "Administrator" and "Sales Manager" not in _roles(user):
        raise FrappePermissionError("Not permitted")

    doc = CRMViewSettings._default_manager.filter(pk=name).first()
    if doc is None:
        raise DoesNotExistError(f"{VIEW_SETTINGS} {name} not found")

    wants_public = bool(value)
    if doc.pinned:
        doc.pinned = False
    doc.public = wants_public
    # A public view has no owner; a private one reverts to the caller (source :134).
    doc.user_id = None if wants_public else user
    doc.save()


@whitelist("crm.fcrm.doctype.crm_view_settings.crm_view_settings.pin", methods=("POST",))
def pin(name: str | int, value: bool | int):
    """``crm_view_settings.py:138-143``."""
    from crm_app.models import CRMViewSettings
    from frappe_core.exceptions import DoesNotExistError

    doc = CRMViewSettings._default_manager.filter(pk=name).first()
    if doc is None:
        raise DoesNotExistError(f"{VIEW_SETTINGS} {name} not found")
    check_permission(doc)
    doc.pinned = bool(value)
    doc.save()


@whitelist(
    "crm.fcrm.doctype.crm_view_settings.crm_view_settings.set_as_default", methods=("POST",)
)
def set_as_default(
    name: str | int | None = None, type: str | None = None, doctype: str | None = None
):
    """``crm_view_settings.py:197-211``.

    Exactly one view per user may be default, so the others are cleared afterwards —
    scoped to *this user's* views, which is what stops one user's choice resetting
    everybody else's.
    """
    from crm_app.models import CRMViewSettings

    if name:
        CRMViewSettings._default_manager.filter(pk=name).update(is_default=True)
    else:
        doc = create_or_update_standard_view(
            {"type": type, "doctype": doctype, "is_default": 1}
        )
        name = doc["name"]

    CRMViewSettings._default_manager.filter(
        user=get_current_user(), is_default=True
    ).exclude(pk=name).update(is_default=False)


@whitelist(
    "crm.fcrm.doctype.crm_view_settings.crm_view_settings.create_or_update_standard_view",
    methods=("POST",),
)
def create_or_update_standard_view(view: str | dict):
    """``crm_view_settings.py:214-291``.

    The standard view is the per-user default for a doctype+type, and it is what
    ``get_data``'s step 3 looks up — the key is
    ``{dt, type, is_standard: 1, user}`` (``crm/api/doc.py:324-331``).
    """
    from crm_app.models import CRMViewSettings

    parsed = _normalise(parse_json_param(view, {}) or {})
    doctype = parsed.get("doctype")
    parsed["column_field"] = parsed.get("column_field") or "status"
    _merge_default_rows(parsed, doctype)

    if not parsed["kanban_columns"] and parsed.get("type") == "kanban":
        parsed["kanban_columns"] = sync_default_columns(parsed)
    elif not parsed["columns"]:
        parsed["columns"] = sync_default_columns(parsed)

    view_type = parsed.get("type") or "list"
    user = get_current_user()

    doc = CRMViewSettings._default_manager.filter(
        dt=doctype, type=view_type, is_standard=True, user=user
    ).first()

    if doc is None:
        label = {"group_by": "Group By", "kanban": "Kanban"}.get(view_type, "List")
        doc = CRMViewSettings(
            dt=doctype, user_id=user, is_standard=True, label=parsed.get("label") or label
        )
        parsed.setdefault("label", label)

    parsed["order_by"] = parsed.get("order_by") or "modified desc"
    parsed["group_by_field"] = parsed.get("group_by_field") or "owner"
    _apply(doc, parsed, doctype=doctype)
    doc.is_default = bool(parsed.get("is_default") or False)
    doc.save()
    return _serialise(doc)


@whitelist(
    "crm.fcrm.doctype.crm_view_settings.crm_view_settings.fetch_and_update_kanban_columns",
    methods=("POST",),
)
def fetch_and_update_kanban_columns(name: str | int):
    """``crm_view_settings.py:294-308``.

    A column that has appeared since the view was saved is appended with
    ``delete: True`` rather than shown — that flag is how ``get_data`` knows to render
    the column empty (``crm/api/doc.py:405``). It marks *new* columns, which reads
    backwards until you see that the frontend treats it as "hidden by default".
    """
    from crm_app.models import CRMViewSettings

    doc = CRMViewSettings._default_manager.filter(pk=name).first()
    if doc is None or doc.type != "kanban":
        return None

    new_columns = sync_default_columns(
        {"dt": doc.dt, "type": doc.type, "column_field": doc.column_field}
    )
    existing = parse_json_param(doc.kanban_columns, []) or []
    existing_names = [c.get("name") for c in existing]
    for column in new_columns:
        if column.get("name") not in existing_names:
            existing.append({"name": column.get("name"), "delete": True})

    doc.kanban_columns = json.dumps(existing)
    doc.save()
    return doc.kanban_columns
