"""Shared list-query validation and row projection."""

from __future__ import annotations

import json
import re
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext as _

from core.exceptions import ValidationError
from core.field_access import hidden_from, is_hidden
from core.filters import apply_filters

DEFAULT_PAGE_LENGTH = 20
MAX_PAGE_LENGTH = 500
JSON_TEXT_FIELDS = ("_assign", "_liked_by", "_comments")


def by_name(model, name):
    try:
        key = model._meta.pk.to_python(name)
    except (DjangoValidationError, ValueError, TypeError):
        return model._default_manager.none()
    return model._default_manager.filter(pk=key)


def parse_json_param(value: Any, default=None):
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


def concrete_field_names(model) -> set[str]:
    names = set()
    for field in model._meta.get_fields():
        if getattr(field, "concrete", False):
            names.add(field.name)
            if getattr(field, "attname", None):
                names.add(field.attname)
    return names


def resolve_fields(model, fields, *, user, selectable=None) -> list[str]:
    blocked = hidden_from(model, user)
    concrete = [field.name for field in model._meta.get_fields() if getattr(field, "concrete", False)]
    allowed_by_view = set(selectable) if selectable is not None else None
    default = [
        name
        for name in concrete
        if name not in blocked
        and (allowed_by_view is None or name in allowed_by_view)
    ]
    fields = parse_json_param(fields)
    if not fields or fields == "*" or "*" in fields:
        return default
    if isinstance(fields, str):
        fields = [fields]
    resolved = []
    for raw in fields:
        field = str(raw).strip()
        if field in blocked or (allowed_by_view is not None and field not in allowed_by_view):
            raise ValidationError(_("Field {0!r} is not readable").format(field))
        if field not in concrete_field_names(model):
            raise ValidationError(
                _("Unknown field {0!r} for this document type").format(field)
            )
        if field not in resolved:
            resolved.append(field)
    return resolved


_ORDER_CLAUSE = re.compile(
    r"""^\s*(?:(?:`(?P<qtable>[^`]+)`|(?P<utable>\w+))\s*\.\s*)?
    [`"]?(?P<field>\w+)[`"]?(?:\s+(?P<direction>asc|desc))?\s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def resolve_order_by(model, order_by, *, user, sortable=None) -> list[str]:
    if not order_by:
        return []
    if isinstance(order_by, (list, tuple)):
        order_by = ",".join(str(item) for item in order_by)
    allowed_by_view = set(sortable) if sortable is not None else None
    concrete = concrete_field_names(model)
    resolved = []
    for clause in str(order_by).split(","):
        clause = clause.strip()
        if not clause:
            continue
        match = _ORDER_CLAUSE.match(clause)
        if match is None:
            raise ValidationError(
                _("Cannot parse sort clause {0!r}").format(clause)
            )
        field = match.group("field")
        direction = (match.group("direction") or "asc").lower()
        if is_hidden(model, field, user) or (allowed_by_view is not None and field not in allowed_by_view):
            raise ValidationError(_("Cannot order by {0!r}").format(field))
        if field not in concrete:
            raise ValidationError(
                _("Cannot order by unknown field {0!r}").format(field)
            )
        resolved.append(f"-{field}" if direction == "desc" else field)
    return resolved


def resolve_group_by(model, group_by, *, user, sortable=None):
    if not group_by:
        return None
    field = str(group_by).strip()
    if "." in field:
        field = field.rsplit(".", 1)[-1].strip("`\"")
    allowed_by_view = set(sortable) if sortable is not None else None
    if is_hidden(model, field, user) or (allowed_by_view is not None and field not in allowed_by_view):
        raise ValidationError(_("Cannot group by {0!r}").format(field))
    if field not in concrete_field_names(model):
        raise ValidationError(
            _("Cannot group by unknown field {0!r}").format(field)
        )
    return field


def coerce_page_length(value, default=DEFAULT_PAGE_LENGTH):
    if value in (None, ""):
        return default
    try:
        page_length = int(value)
    except (TypeError, ValueError):
        raise ValidationError(_("Invalid page length {0!r}").format(value)) from None
    if page_length < 0:
        raise ValidationError(_("Page length cannot be negative"))
    return min(page_length, MAX_PAGE_LENGTH)


def coerce_offset(value):
    if value in (None, ""):
        return 0
    try:
        offset = int(value)
    except (TypeError, ValueError):
        raise ValidationError(_("Invalid offset {0!r}").format(value)) from None
    return max(offset, 0)


def build_list_queryset(
    queryset,
    *,
    user,
    filters=None,
    or_filters=None,
    order_by=None,
    group_by=None,
    filterable=None,
    sortable=None,
):
    """Apply client clauses to an already row-rule-narrowed queryset."""
    queryset = apply_filters(
        queryset,
        filters=parse_json_param(filters),
        or_filters=parse_json_param(or_filters),
        user=user,
        filterable=filterable,
    )
    ordering = resolve_order_by(queryset.model, order_by, user=user, sortable=sortable)
    resolve_group_by(queryset.model, group_by, user=user, sortable=sortable)
    return queryset.order_by(*ordering) if ordering else queryset


def wire_json_text(row):
    for key in JSON_TEXT_FIELDS:
        if key in row and not isinstance(row[key], str):
            row[key] = json.dumps(row[key] if row[key] is not None else [])
    return row


def fetch_rows(
    queryset,
    *,
    user,
    fields=None,
    filters=None,
    or_filters=None,
    order_by=None,
    group_by=None,
    limit_start=0,
    limit_page_length=DEFAULT_PAGE_LENGTH,
    selectable=None,
    filterable=None,
    sortable=None,
):
    queryset = build_list_queryset(
        queryset,
        user=user,
        filters=filters,
        or_filters=or_filters,
        order_by=order_by,
        group_by=group_by,
        filterable=filterable,
        sortable=sortable,
    )
    selected = resolve_fields(queryset.model, fields, user=user, selectable=selectable)
    start = coerce_offset(limit_start)
    length = coerce_page_length(limit_page_length)
    queryset = queryset[start:] if length == 0 else queryset[start : start + length]
    return [wire_json_text(row) for row in queryset.values(*selected)]


def count_rows(queryset, *, user, filters=None, or_filters=None, filterable=None):
    return build_list_queryset(
        queryset,
        user=user,
        filters=filters,
        or_filters=or_filters,
        filterable=filterable,
    ).count()
