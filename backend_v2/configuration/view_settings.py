"""Saved views: CRM View Settings' rules (specs/CONFIGURATION.md section 4.7).

The resource and the dedicated calls share these two rules, so every way in has the
same lock (old `crm_app/permissions/metadata_docs.py:61-91`,
`crm_app/api/view_settings.py:37-48`):

- **read:** the caller's own views, ownerless views and public views; Administrator and
  System Manager read every view;
- **write** (and delete): the owner; Sales Manager on a public view; Administrator and
  System Manager.
"""

from __future__ import annotations

import json

from django.db.models import Q

from accounts.roles import ADMINISTRATOR, ROLE_SALES_MANAGER, ROLE_SYSTEM_MANAGER
from configuration import field_meta
from configuration.list_views import list_definition_for
from configuration.models import CRMViewSettings
from configuration.serializers import CRMViewSettingsSerializer
from core.doctypes import declared_doctypes
from core.exceptions import DoesNotExistError, PermissionError, ValidationError
from core.inputs import parse_json_param
from core.query import wire_json_text
from core.resources import rules_for

VIEW_SETTINGS = "CRM View Settings"
NOT_PERMITTED = "Not permitted"
JSON_KEYS = ("filters", "columns", "rows", "kanban_columns", "kanban_fields")
STANDARD_LABELS = {"group_by": "Group By", "kanban": "Kanban"}


def sees_every_view(user) -> bool:
    return user.name == ADMINISTRATOR or user.has_role(ROLE_SYSTEM_MANAGER)


def read_rule(user):
    """The list rule: `None` for every view, else a filter."""
    if sees_every_view(user):
        return None
    return Q(user=user) | Q(user__isnull=True) | Q(public=True)


def can_read(user, view) -> bool:
    if sees_every_view(user):
        return True
    return view.user_id == user.name or view.user_id is None or bool(view.public)


def can_write(user, view) -> bool:
    """Write and delete, the old `check_permission`."""
    if sees_every_view(user):
        return True
    if view.public and user.has_role(ROLE_SALES_MANAGER):
        return True
    return bool(view.user_id) and view.user_id == user.name


def require_write(user, view) -> None:
    if not can_write(user, view):
        raise PermissionError(NOT_PERMITTED)


def not_found(name):
    return DoesNotExistError(f"{VIEW_SETTINGS} {name} not found")


def serialised(view, user) -> dict:
    return CRMViewSettingsSerializer(view, context={"user": user}).data


# --- the doctype's defaults (old `view_settings.py:56-106`) ------------------------------


def get_route_name(doctype: str) -> str:
    """`"CRM Lead"` -> `"Leads"`."""
    if doctype.startswith("CRM "):
        doctype = doctype[4:]
    if not doctype.endswith("s"):
        doctype += "s"
    return doctype


def default_rows(doctype) -> list:
    definition = list_definition_for(doctype)
    return definition.default_rows() if definition else []


def kanban_link_columns(target: str, user) -> list[dict]:
    """A Link column field's values: the target's rows the caller may list, oldest
    modified first; none when the target has no row rules."""
    model = declared_doctypes().get(target)
    rules = rules_for(model) if model is not None else None
    if rules is None:
        return []
    queryset = model._default_manager.all()
    rule = rules.list_rule(user)
    if rule is not None:
        queryset = queryset.filter(rule)
    return [{"name": pk} for pk in queryset.order_by("modified").values_list("pk", flat=True)]


def default_columns(view: dict, user) -> list:
    """The doctype's default columns, or for a kanban with a `column_field` its columns
    from the metadata file: a Link's target rows, a Select's options."""
    doctype = view.get("dt") or view.get("doctype")
    definition = list_definition_for(doctype)
    if definition is None:
        return []
    if view.get("type") == "kanban" and view.get("column_field"):
        field = field_meta.get_field(doctype, view["column_field"])
        if not field:
            return []
        if field.get("fieldtype") == "Link" and field.get("options"):
            return kanban_link_columns(field["options"], user)
        if field.get("fieldtype") == "Select":
            return [{"name": option} for option in field_meta.select_options(field)]
        return []
    return definition.default_columns()


# --- shared steps (old `view_settings.py:109-143`) ---------------------------------------


def _normalise(view) -> dict:
    """The five JSON-ish fields, parsed; blank becomes `{}` for filters, else `[]`."""
    parsed = dict(parse_json_param(view, {}) or {})
    for key in JSON_KEYS:
        value = parse_json_param(parsed.get(key), None)
        if value in (None, ""):
            value = {} if key == "filters" else []
        parsed[key] = value
    return parsed


def _apply(doc, view: dict, *, doctype: str) -> None:
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


def _merge_default_rows(view: dict, doctype) -> None:
    """`rows + default_rows`, duplicates removed in order."""
    extra = default_rows(doctype)
    if extra:
        view["rows"] = list(view["rows"]) + extra
    view["rows"] = list(dict.fromkeys(view["rows"]))


def _fill_default_columns(view: dict, user) -> None:
    if not view["kanban_columns"] and view.get("type") == "kanban":
        view["kanban_columns"] = default_columns(view, user)
    elif not view["columns"]:
        view["columns"] = default_columns(view, user)


def _require_doctype(doctype) -> None:
    """PE-12d: the route name is built from it."""
    if not doctype:
        raise ValidationError("DocType is required")


# --- the calls ---------------------------------------------------------------------------


def create_view(view, *, user) -> dict:
    """`create` (old `:150-167`): no check; the view belongs to the caller."""
    parsed = _normalise(view)
    doctype = parsed.get("doctype")
    _require_doctype(doctype)
    _merge_default_rows(parsed, doctype)
    _fill_default_columns(parsed, user)
    doc = CRMViewSettings(dt=doctype, user=user, label=parsed.get("label"))
    _apply(doc, parsed, doctype=doctype)
    doc.save(user=user)
    return serialised(doc, user)


def update_view(view, *, user) -> dict:
    """`update` (old `:170-187`): 404, then the write rule."""
    parsed = _normalise(view)
    doc = CRMViewSettings.named(parsed.get("name"))
    if doc is None:
        raise not_found(parsed.get("name"))
    require_write(user, doc)
    doctype = parsed.get("doctype") or doc.dt
    _merge_default_rows(parsed, doctype)
    _apply(doc, parsed, doctype=doctype)
    doc.save(user=user)
    return serialised(doc, user)


def delete_view(name, *, user) -> None:
    """`delete` (old `:193-201`): nothing for a missing view; else the write rule."""
    doc = CRMViewSettings.named(name)
    if doc is None:
        return None
    require_write(user, doc)
    doc.delete()
    return None


def create_or_update_standard_view(view, *, user) -> dict:
    """`create_or_update_standard_view` (old `:277-315`): the caller's own standard row
    for the doctype and type, created when missing."""
    parsed = _normalise(view)
    doctype = parsed.get("doctype")
    _require_doctype(doctype)
    parsed["column_field"] = parsed.get("column_field") or "status"
    _merge_default_rows(parsed, doctype)
    _fill_default_columns(parsed, user)

    view_type = parsed.get("type") or "list"
    doc = CRMViewSettings.own_standard_view(doctype, view_type, user)
    if doc is None:
        label = STANDARD_LABELS.get(view_type, "List")
        doc = CRMViewSettings(
            dt=doctype, user=user, is_standard=True, label=parsed.get("label") or label
        )
        parsed.setdefault("label", label)

    parsed["order_by"] = parsed.get("order_by") or "modified desc"
    parsed["group_by_field"] = parsed.get("group_by_field") or "owner"
    _apply(doc, parsed, doctype=doctype)
    doc.is_default = bool(parsed.get("is_default") or False)
    doc.save(user=user)
    return serialised(doc, user)


def get_views(doctype, *, user) -> list[dict]:
    """`crm.api.views.get_views` (old `crm_app/api/views.py:12-36`): the read rule, then
    ownerless views and the caller's own, of `doctype` when it is truthy (the store sends
    `""` for every doctype). No `doctype` at all is 417 (PE-12d)."""
    if doctype is None:
        raise ValidationError("DocType is required")
    rows = CRMViewSettings.listed_for(user, read_rule(user), doctype)
    return [wire_json_text(row) for row in rows]


def _named_or_404(name):
    doc = CRMViewSettings.named(name)
    if doc is None:
        raise not_found(name)
    return doc


def set_public(name, value, *, user) -> None:
    """`public` (old `:204-229`): Administrator or Sales Manager (System Manager is not
    enough, as `backend/`), then 404, then the read rule (PE-20). Publishing clears the
    owner and unpins; unpublishing gives the view to the caller."""
    if user.name != ADMINISTRATOR and not user.has_role(ROLE_SALES_MANAGER):
        raise PermissionError(NOT_PERMITTED)
    doc = _named_or_404(name)
    if not can_read(user, doc):
        raise PermissionError(NOT_PERMITTED)
    wants_public = bool(value)
    if doc.pinned:
        doc.pinned = False
    doc.public = wants_public
    doc.user = None if wants_public else user
    doc.save(user=user)


def pin(name, value, *, user) -> None:
    """`pin` (old `:232-243`): 404, then the write rule. A Sales Manager pinning a public
    view pins it for everyone, as `backend/`."""
    doc = _named_or_404(name)
    require_write(user, doc)
    doc.pinned = bool(value)
    doc.save(user=user)


def set_as_default(name=None, type=None, doctype=None, *, user) -> None:
    """`set_as_default` (old `:246-270`). With a name, the caller's own view (PE-21);
    without one, the caller's standard view. Then the caller's other defaults clear."""
    if name:
        doc = _named_or_404(name)
        if doc.user_id != user.name:
            raise PermissionError(NOT_PERMITTED)
        CRMViewSettings.mark_default(doc.pk)
        keep = doc.pk
    else:
        standard = create_or_update_standard_view(
            {"type": type, "doctype": doctype, "is_default": 1}, user=user
        )
        keep = standard["name"]
    CRMViewSettings.clear_other_defaults(user, keep)


def fetch_and_update_kanban_columns(name, *, user):
    """`fetch_and_update_kanban_columns` (old `:318-347`): the kanban's columns as a JSON
    string, a column that has appeared since flagged `delete: True`; `None` for a missing
    view or one that is not a kanban. The read rule applies, and the columns are saved
    only where the caller may write the view (PE-21)."""
    doc = CRMViewSettings.named(name)
    if doc is None:
        return None
    if not can_read(user, doc):
        raise PermissionError(NOT_PERMITTED)
    if doc.type != "kanban":
        return None
    current = default_columns(
        {"dt": doc.dt, "type": doc.type, "column_field": doc.column_field}, user
    )
    existing = parse_json_param(doc.kanban_columns, []) or []
    existing_names = [column.get("name") for column in existing]
    for column in current:
        if column.get("name") not in existing_names:
            existing.append({"name": column.get("name"), "delete": True})
    text = json.dumps(existing)
    if can_write(user, doc):
        doc.kanban_columns = text
        doc.save(user=user)
    return text
