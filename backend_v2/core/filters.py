"""Translate Frappe's list-filter grammar into Django ``Q`` objects."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from django.db.models import Q
from django.db.models.fields.json import JSONField
from django.db.models.fields.related import ForeignKey, OneToOneField
from core.exceptions import FilterError
from core.field_access import is_hidden
from core.models import TreeDocument
from core.translate import _

ME_TOKEN = "@me"
ME_LIKE_TOKEN = "%@me%"
_TEXT_INTERNAL_TYPES = {"CharField", "TextField", "EmailField", "SlugField", "URLField"}


def resolve_me_tokens(value: Any, user) -> Any:
    user_name = user.pk if hasattr(user, "pk") else str(user)
    if isinstance(value, str):
        if value == ME_TOKEN:
            return user_name
        if value == ME_LIKE_TOKEN:
            return f"%{user_name}%"
        return value
    if isinstance(value, (list, tuple)):
        resolved = [resolve_me_tokens(item, user) for item in value]
        return tuple(resolved) if isinstance(value, tuple) else resolved
    if isinstance(value, dict):
        return {key: resolve_me_tokens(item, user) for key, item in value.items()}
    return value


def normalize_filters(filters: Any) -> list[tuple[str, str, Any]]:
    if not filters:
        return []
    if isinstance(filters, dict):
        normalized = []
        for fieldname, raw in filters.items():
            operator, value = _split_dict_value(raw)
            normalized.append((fieldname, operator, value))
        return normalized
    if isinstance(filters, (list, tuple)):
        return [_normalize_sequence_item(item) for item in filters]
    raise FilterError(_("Unsupported filter shape: {0}").format(type(filters).__name__))


def _split_dict_value(raw):
    if isinstance(raw, (list, tuple)) and len(raw) == 2 and isinstance(raw[0], str):
        candidate = raw[0].strip().lower()
        if candidate in _OPERATORS:
            return candidate, raw[1]
    return "=", raw


def _normalize_sequence_item(item):
    if not isinstance(item, (list, tuple)):
        raise FilterError(_("Filter entry must be a list, got {0}").format(type(item).__name__))
    if len(item) == 4:
        fieldname, operator, value = item[1:]
    elif len(item) == 3:
        fieldname, operator, value = item
    elif len(item) == 2:
        fieldname, value = item
        operator = "="
    else:
        raise FilterError(_("Filter entry must have 2-4 elements, got {0}").format(len(item)))
    return str(fieldname), str(operator).strip().lower(), value


_LIKE_SPECIALS = re.compile(r"[%_]")


def _like_pattern_to_regex(pattern: str) -> str:
    parts = ["^"]
    for character in pattern:
        parts.append(".*" if character == "%" else "." if character == "_" else re.escape(character))
    parts.append("$")
    return "".join(parts)


def _like_to_lookup(value):
    if not isinstance(value, str):
        return "iexact", value
    core = value
    starts_wild = core.startswith("%")
    ends_wild = core.endswith("%")
    if starts_wild:
        core = core[1:]
    if ends_wild and core.endswith("%"):
        core = core[:-1]
    elif ends_wild and not core:
        core = ""
    if _LIKE_SPECIALS.search(core):
        return "iregex", _like_pattern_to_regex(value)
    if starts_wild and ends_wild:
        return "icontains", core
    if ends_wild:
        return "istartswith", core
    if starts_wild:
        return "iendswith", core
    return "iexact", core


def _get_field(model, fieldname):
    try:
        return model._meta.get_field(fieldname)
    except Exception:
        return None


def resolve_field_path(model, fieldname):
    field = _get_field(model, fieldname)
    if isinstance(field, (ForeignKey, OneToOneField)):
        return field.attname
    return fieldname


def _simple(lookup):
    return lambda model, path, fieldname, value: Q(**{f"{path}__{lookup}": value})


def _op_like(model, path, fieldname, value):
    lookup, operand = _like_to_lookup(value)
    field = _get_field(model, fieldname)
    if isinstance(field, JSONField) and lookup in ("iexact", "istartswith", "iendswith"):
        lookup = "icontains"
    return Q(**{f"{path}__{lookup}": operand})


def _coerce_sequence(value, operator):
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if isinstance(value, str):
        return [part.strip() for part in value.split(",")]
    raise FilterError(
        _("Operator '{0}' expects a list, got {1}").format(
            operator, type(value).__name__
        )
    )


def _op_between(model, path, fieldname, value):
    bounds = _coerce_sequence(value, "between")
    if len(bounds) != 2:
        raise FilterError(_("Operator 'between' expects exactly two values"))
    return Q(**{f"{path}__range": bounds})


def _op_is(model, path, fieldname, value):
    token = str(value).strip().lower()
    field = _get_field(model, fieldname)
    is_text = isinstance(field, (ForeignKey, OneToOneField)) or (
        field is None or field.get_internal_type() in _TEXT_INTERNAL_TYPES
    )
    if token == "set":
        condition = Q(**{f"{path}__isnull": False})
        return condition & ~Q(**{path: ""}) if is_text else condition
    if token == "not set":
        condition = Q(**{f"{path}__isnull": True})
        return condition | Q(**{path: ""}) if is_text else condition
    raise FilterError(
        _("Operator 'is' expects 'set' or 'not set', got {0!r}").format(value)
    )


def _tree_op(inclusive, negate=False, ancestors=False):
    def build(model, path, fieldname, value):
        field = _get_field(model, fieldname)
        related = getattr(field, "related_model", None)
        if not isinstance(related, type) or not issubclass(related, TreeDocument):
            raise FilterError(_("'{0}' is not a tree field").format(fieldname))
        condition = related.tree_q(path, value, inclusive, ancestors)
        return ~condition if negate else condition

    return build


_NUMERIC_INTERNAL_TYPES = {
    "DecimalField", "FloatField", "IntegerField", "BigIntegerField", "SmallIntegerField",
    "PositiveIntegerField", "PositiveSmallIntegerField", "PositiveBigIntegerField",
}
_INTEGER_INTERNAL_TYPES = {name for name in _NUMERIC_INTERNAL_TYPES if "Integer" in name}
_NUMERIC_COERCED_OPERATORS = {"=", "!=", ">", "<", ">=", "<=", "in", "not in", "between"}
_NOT_NUMBER_CHARS = re.compile(r"[^0-9.\-]")


def _number_from(value, integer):
    if not isinstance(value, str):
        return value
    try:
        number = Decimal(value.strip())
    except InvalidOperation:
        digits = _NOT_NUMBER_CHARS.sub("", value.strip())
        digits = ("-" if digits.startswith("-") else "") + digits.replace("-", "")
        try:
            number = Decimal(digits)
        except InvalidOperation:
            number = Decimal(0)
    if not number.is_finite():
        number = Decimal(0)
    return int(number) if integer else number


def coerce_numeric_filter_value(field, operator, value):
    internal = field.get_internal_type()
    if internal not in _NUMERIC_INTERNAL_TYPES or operator not in _NUMERIC_COERCED_OPERATORS:
        return value
    integer = internal in _INTEGER_INTERNAL_TYPES
    if operator in ("in", "not in", "between"):
        return [_number_from(item, integer) for item in _coerce_sequence(value, operator)]
    return _number_from(value, integer)


_OPERATORS: dict[str, Callable] = {
    "=": lambda m, p, f, v: Q(**{p: v}),
    "!=": lambda m, p, f, v: ~Q(**{p: v}),
    ">": _simple("gt"), "<": _simple("lt"), ">=": _simple("gte"), "<=": _simple("lte"),
    "like": _op_like,
    "not like": lambda m, p, f, v: ~_op_like(m, p, f, v),
    "in": lambda m, p, f, v: Q(**{f"{p}__in": _coerce_sequence(v, "in")}),
    "not in": lambda m, p, f, v: ~Q(**{f"{p}__in": _coerce_sequence(v, "not in")}),
    "between": _op_between,
    "is": _op_is,
    "descendants of": _tree_op(False),
    "descendants of (inclusive)": _tree_op(True),
    "not descendants of (inclusive)": _tree_op(True, negate=True),
    "ancestors of": _tree_op(False, ancestors=True),
    "not ancestors of (inclusive)": _tree_op(True, negate=True, ancestors=True),
}
SUPPORTED_OPERATORS = tuple(_OPERATORS)


def build_q(model, filters, *, user, combine="AND", filterable=None):
    entries = normalize_filters(filters)
    result = None
    allowed = set(filterable) if filterable is not None else None
    for fieldname, operator, raw_value in entries:
        handler = _OPERATORS.get(operator)
        if handler is None:
            raise FilterError(
                _("Unsupported filter operator {0!r}. Supported: {1}").format(
                    operator, ", ".join(SUPPORTED_OPERATORS)
                )
            )
        if is_hidden(model, fieldname, user) or (allowed is not None and fieldname not in allowed):
            raise FilterError(_("Cannot filter on {0!r}").format(fieldname))
        field = _get_field(model, fieldname)
        if field is None or not getattr(field, "concrete", False):
            raise FilterError(
                _("Unknown field {0!r} for this document type").format(fieldname)
            )
        value = resolve_me_tokens(raw_value, user)
        value = coerce_numeric_filter_value(field, operator, value)
        condition = handler(model, resolve_field_path(model, fieldname), fieldname, value)
        result = condition if result is None else (result | condition if combine == "OR" else result & condition)
    return result if result is not None else Q()


def apply_filters(queryset, filters=None, or_filters=None, *, user, filterable=None):
    if filters:
        queryset = queryset.filter(build_q(queryset.model, filters, user=user, filterable=filterable))
    if or_filters:
        queryset = queryset.filter(
            build_q(queryset.model, or_filters, user=user, combine="OR", filterable=filterable)
        )
    return queryset
