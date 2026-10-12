"""Shared list-query construction.

Both ``/api/resource/`` and ``crm.api.doc.get_data`` build their querysets here, so the
permission filter, the field allowlist and the ordering rules cannot diverge between
the two - and a client cannot pick the laxer endpoint.

PHASE_2_PERMISSIONS.md's last acceptance criterion ("permission bypass is impossible via
``fields``, ``order_by`` or ``group_by``") is enforced at this layer, in phase 0, rather
than left for phase 2: every one of those three parameters is validated against the
model's own concrete fields, so no relation can be traversed and no column outside the
doctype can be named.
"""

from __future__ import annotations

import json
import re
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError

from frappe_core import permissions, registry
from frappe_core.exceptions import ValidationError
from frappe_core.field_security import hidden_from, is_hidden
from frappe_core.filters import apply_filters
from frappe_core.session import get_current_user

DEFAULT_PAGE_LENGTH = 20
MAX_PAGE_LENGTH = 500


def by_name(model, name):
    """``frappe.get_doc(doctype, name)``'s lookup half: the rows called ``name``.

    A name the primary key cannot hold - letters for an autoincrement doctype such as
    CRM Task - finds nothing, as upstream, where such a name is simply absent from the
    table. Django instead raises ``ValueError`` from ``filter(pk=...)`` before any query
    runs, and that surfaced as a 500 on every lookup by name (FINDINGS.md 24).
    """
    try:
        key = model._meta.pk.to_python(name)
    except (DjangoValidationError, ValueError, TypeError):
        return model._default_manager.none()
    return model._default_manager.filter(pk=key)


def parse_json_param(value: Any, default: Any = None) -> Any:
    """Query params arrive JSON-encoded (PORT_PLAN.md section 3), not as native arrays."""
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            # A bare string like order_by=modified is legitimate.
            return value
    return value


def concrete_field_names(model) -> set[str]:
    """Every column the client may name. Relations appear under their Frappe fieldname."""
    names = set()
    for field in model._meta.get_fields():
        if getattr(field, "concrete", False):
            names.add(field.name)
            attname = getattr(field, "attname", None)
            if attname:
                names.add(attname)
    return names


def resolve_fields(model, fields: Any) -> list[str]:
    """Validate a requested field list. ``["*"]`` means every concrete field.

    Credential columns are never selectable, whether named explicitly or swept up by
    ``["*"]`` - see :mod:`frappe_core.field_security`. ``User`` and ``Email Account``
    are routable doctypes, so without this a list request would hand out password
    hashes.

    ``hidden_from`` rather than ``sensitive_fields``: it adds the model's restricted
    fields when the caller holds none of the privileged roles. The list path needs its
    own check because it does not build a serializer - ``EmailAccountList.vue`` asks for
    ``fields=['*']``, and without this the fields the serializer drops would come straight
    back through the list.
    """
    blocked = hidden_from(model)
    allowed = concrete_field_names(model) - blocked
    default = [
        f.name
        for f in model._meta.get_fields()
        if getattr(f, "concrete", False) and f.name not in blocked
    ]

    if not fields:
        return default
    if isinstance(fields, str):
        fields = [fields]
    if "*" in fields:
        return default

    resolved: list[str] = []
    for raw in fields:
        field = str(raw).strip()
        if field in blocked:
            raise ValidationError(f"Field {field!r} is not readable")
        if field not in allowed:
            # Deliberately strict: silently dropping an unknown field would let a
            # typo'd column quietly disappear from a list view instead of failing loudly.
            raise ValidationError(f"Unknown field {field!r} for this document type")
        if field not in resolved:
            resolved.append(field)
    return resolved


#: One ``order_by`` clause. The optional leading qualifier is backtick-quoted and may
#: contain spaces (``` `tabCRM Lead`.modified desc ```), so the whole clause cannot be
#: split on whitespace before the qualifier is stripped.
_ORDER_CLAUSE = re.compile(
    r"""^\s*
        (?: (?: `(?P<qtable>[^`]+)` | (?P<utable>\w+) ) \s*\.\s* )?   # optional table
        [`"]? (?P<field>\w+) [`"]?                                    # column
        (?: \s+ (?P<direction>asc|desc) )?                            # optional order
        \s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def resolve_order_by(model, order_by: Any) -> list[str]:
    """``"modified desc"`` -> ``["-modified"]``. Comma-separated clauses are supported.

    The shipped frontend only ever sends the unqualified form (``modified desc``, see
    ``ViewControls.vue:429``), but Frappe itself emits table-qualified ordering and a
    saved view can carry one, so both are accepted.
    """
    if not order_by:
        return []
    if isinstance(order_by, (list, tuple)):
        order_by = ",".join(str(o) for o in order_by)

    # Hidden fields are rejected per clause by `is_hidden` below, for the same reason
    # `resolve_group_by` rejects them and filters now do: ordering by a hidden column
    # leaks its ordering, and a caller who can sort by a secret can bisect it across
    # requests. `allowed` therefore only has to answer "is this a real column?".
    allowed = concrete_field_names(model)
    resolved: list[str] = []
    for clause in str(order_by).split(","):
        clause = clause.strip()
        if not clause:
            continue
        match = _ORDER_CLAUSE.match(clause)
        if match is None:
            raise ValidationError(f"Cannot parse sort clause {clause!r}")
        field = match.group("field")
        direction = (match.group("direction") or "asc").lower()
        if is_hidden(model, field):
            raise ValidationError(f"Cannot order by {field!r}")
        if field not in allowed:
            raise ValidationError(f"Cannot order by unknown field {field!r}")
        resolved.append(f"-{field}" if direction == "desc" else field)
    return resolved


def resolve_group_by(model, group_by: Any) -> str | None:
    if not group_by:
        return None
    field = str(group_by).strip()
    if "." in field:
        field = field.rsplit(".", 1)[-1].strip("`\"")
    if is_hidden(model, field):
        raise ValidationError(f"Cannot group by {field!r}")
    if field not in concrete_field_names(model):
        raise ValidationError(f"Cannot group by unknown field {field!r}")
    return field


def coerce_page_length(value: Any, default: int = DEFAULT_PAGE_LENGTH) -> int:
    if value in (None, ""):
        return default
    try:
        page_length = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"Invalid page length {value!r}") from None
    if page_length < 0:
        raise ValidationError("Page length cannot be negative")
    return min(page_length, MAX_PAGE_LENGTH)


def coerce_offset(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        offset = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"Invalid offset {value!r}") from None
    return max(offset, 0)


def base_queryset(doctype: str, user: str | None = None):
    """The permission-filtered starting point for every read of ``doctype``."""
    entry = registry.get_entry(doctype)
    user = user or get_current_user()
    queryset = entry.model._default_manager.all()
    return permissions.apply_permission_filter(queryset, doctype, user)


def build_list_queryset(
    doctype: str,
    *,
    filters: Any = None,
    or_filters: Any = None,
    order_by: Any = None,
    user: str | None = None,
):
    """Permission filter -> user filters -> ordering. Slicing is the caller's job."""
    user = user or get_current_user()
    queryset = base_queryset(doctype, user)
    queryset = apply_filters(
        queryset, filters=filters, or_filters=or_filters, doctype=doctype, user=user
    )
    ordering = resolve_order_by(queryset.model, order_by)
    if ordering:
        queryset = queryset.order_by(*ordering)
    return queryset


def fetch_rows(
    doctype: str,
    *,
    fields: Any = None,
    filters: Any = None,
    or_filters: Any = None,
    order_by: Any = None,
    limit_start: int = 0,
    limit_page_length: int | None = DEFAULT_PAGE_LENGTH,
    user: str | None = None,
) -> list[dict]:
    """The Django equivalent of ``frappe.get_list`` - returns dicts, not instances."""
    queryset = build_list_queryset(
        doctype, filters=filters, or_filters=or_filters, order_by=order_by, user=user
    )
    selected = resolve_fields(queryset.model, fields)

    start = coerce_offset(limit_start)
    if limit_page_length in (None, 0):
        queryset = queryset[start:]
    else:
        queryset = queryset[start : start + coerce_page_length(limit_page_length)]

    return [wire_json_text(row) for row in queryset.values(*selected)]


#: The three underscore caches that are **JSON text** on the wire. Upstream stores them
#: in Text columns holding a JSON string (``base_document.py:520-523`` lists them among
#: the text fields), so a list row carries ``_assign: '["ada@example.com"]'`` and the
#: frontend parses it: ``JSON.parse(lead._assign || '[]')`` (``Leads.vue:490``,
#: ``Deals.vue:456``) and ``JSON.parse(item)`` for ``_liked_by`` in every list view. The
#: port stores them as ``JSONField`` (``frappe_core/models.py:151-153``), which is the
#: better column but came out of ``values()`` and the serializer as a **decoded list** -
#: and ``JSON.parse`` of a list throws, which is why the leads and deals lists never
#: rendered (FINDINGS.md 40). ``_user_tags`` is a comma-separated string on both sides.
JSON_TEXT_FIELDS = ("_assign", "_liked_by", "_comments")


def wire_json_text(row: dict) -> dict:
    """Encode the JSON caches as strings, in place, the way upstream's rows carry them.

    Applied by :func:`fetch_rows` and by the serializer's ``to_representation``, which
    together cover every path that hands a document or a row to the client. An empty
    cache becomes ``"[]"`` rather than ``""``: both parse, and the frontend's
    ``JSON.parse(x || '[]')`` guards handle either, but ``isLiked`` parses whatever it
    is given without a guard.
    """
    for key in JSON_TEXT_FIELDS:
        if key in row and not isinstance(row[key], str):
            row[key] = json.dumps(row[key] if row[key] is not None else [])
    return row


def count_rows(
    doctype: str,
    *,
    filters: Any = None,
    or_filters: Any = None,
    user: str | None = None,
) -> int:
    """``frappe.get_list(..., fields=["count(name) as total_count"])``."""
    return build_list_queryset(
        doctype, filters=filters, or_filters=or_filters, user=user
    ).count()
