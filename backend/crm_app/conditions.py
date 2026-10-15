"""Evaluate conditions produced by the CRM condition editor without running code."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.db.models import ForeignKey, Model


class ConditionError(ValueError):
    """A saved condition cannot be evaluated."""


_OPERATOR_ALIASES = {
    "equals": "==",
    "=": "==",
    "==": "==",
    "!=": "!=",
    "not equals": "!=",
    "<": "<",
    "<=": "<=",
    ">": ">",
    ">=": ">=",
    "in": "in",
    "not in": "not in",
    "like": "like",
    "not like": "not like",
    "is": "is",
    "is not": "is not",
    "between": "between",
}


def _load(conditions: Any) -> Any:
    if not isinstance(conditions, str):
        return conditions
    if not conditions.strip():
        return []
    try:
        return json.loads(conditions)
    except json.JSONDecodeError as exc:
        raise ConditionError(f"Condition is not valid JSON: {exc.msg}") from exc


def is_empty(conditions: Any) -> bool:
    """Return whether *conditions* represents the editor's no-condition value."""

    if conditions is None:
        return True
    parsed = _load(conditions)
    return parsed == []


def document_values(instance: Model | dict[str, Any]) -> dict[str, Any]:
    """Return the concrete values Frappe's ``doc.as_dict()`` would expose."""

    if isinstance(instance, dict):
        return instance
    if not isinstance(instance, Model):
        raise TypeError("document_values() requires a Django model instance or dict")

    values: dict[str, Any] = {}
    for field in instance._meta.concrete_fields:
        value = getattr(instance, field.attname if isinstance(field, ForeignKey) else field.name)
        if isinstance(value, Decimal):
            value = float(value)
        values[field.name] = value
    return values


def evaluate(conditions: Any, doc: Model | dict[str, Any]) -> bool:
    """Return whether *doc* meets *conditions* or raise :class:`ConditionError`.

    An empty condition deliberately has no truth value here.  Assignment and SLA callers
    make different policy decisions for that case, so they must check :func:`is_empty`.
    """

    parsed = _load(conditions)
    if parsed is None or parsed == []:
        raise ConditionError("Condition is empty")
    if not isinstance(parsed, list):
        raise ConditionError("Condition must be a JSON list")

    tree = _parse_group(parsed)
    return _evaluate_group(tree, document_values(doc))


def evaluate_safely(
    conditions: Any, doc: Model | dict[str, Any]
) -> tuple[bool, str | None]:
    """Evaluate a condition, returning ``(False, reason)`` for condition failures."""

    try:
        return evaluate(conditions, doc), None
    except ConditionError as exc:
        return False, str(exc)


def _parse_group(items: list[Any]) -> list[list[Any]]:
    """Validate a group and split it into OR-separated chains of AND terms."""

    if _looks_like_condition(items):
        return [[_parse_operand(items)]]
    if not items:
        raise ConditionError("A nested condition group cannot be empty")
    if len(items) % 2 == 0:
        raise ConditionError("Conditions must alternate values with 'and' or 'or'")

    chains: list[list[Any]] = [[]]
    for index, item in enumerate(items):
        if index % 2 == 0:
            chains[-1].append(_parse_operand(item))
            continue
        if not isinstance(item, str) or item.lower() not in {"and", "or"}:
            raise ConditionError(f"Invalid conjunction at item {index}: {item!r}")
        if item.lower() == "or":
            chains.append([])
    return chains


def _looks_like_condition(item: list[Any]) -> bool:
    return len(item) == 3 and isinstance(item[0], str) and isinstance(item[1], str)


def _parse_operand(item: Any) -> Any:
    if not isinstance(item, list):
        raise ConditionError(f"Malformed condition item: {item!r}")
    if item and isinstance(item[0], list):
        return ("group", _parse_group(item))
    if not _looks_like_condition(item):
        raise ConditionError(f"Malformed condition item: {item!r}")

    field, operator, value = item
    if not field:
        raise ConditionError("A condition field name cannot be empty")
    normalized = operator.lower()
    if normalized not in _OPERATOR_ALIASES:
        raise ConditionError(f"Unknown condition operator: {operator!r}")
    operation = _OPERATOR_ALIASES[normalized]
    if operation == "between" and value is not None:
        _between_bounds(value)
    elif operation == "is" and value is not None and str(value).lower() not in {"set", "not set"}:
        raise ConditionError(f"Unsupported value for 'is': {value!r}")
    elif operation == "is not" and value is not None and str(value).lower() != "set":
        raise ConditionError(f"Unsupported value for 'is not': {value!r}")
    return ("condition", field, operation, value)


def _evaluate_group(chains: list[list[Any]], doc: dict[str, Any]) -> bool:
    # ``any(all(...))`` is also the short-circuit order of Python's ``or``/``and``.
    return any(all(_evaluate_operand(operand, doc) for operand in chain) for chain in chains)


def _evaluate_operand(operand: Any, doc: dict[str, Any]) -> bool:
    if operand[0] == "group":
        return _evaluate_group(operand[1], doc)
    _, field, operator, expected = operand
    if field not in doc:
        raise ConditionError(f"Document has no field {field!r}")
    actual = doc[field]

    if expected is None:
        return not bool(actual) if operator in {"==", "is"} else bool(actual)

    expected_text = str(expected).lower()
    if operator in {"==", "!="} and expected_text in {"yes", "no"}:
        answer = bool(actual) if expected_text == "yes" else not bool(actual)
        return not answer if operator == "!=" else answer
    if operator == "is":
        return bool(actual) if expected_text == "set" else not bool(actual)
    if operator == "is not":
        return not bool(actual)

    try:
        if operator in {"in", "not in"}:
            if not actual:
                return False
            items = _membership_items(expected)
            present = actual in items
            return present if operator == "in" else not present
        if operator in {"like", "not like"}:
            if not actual:
                return False
            contains = str(expected) in actual
            return contains if operator == "like" else not contains
        if operator == "between":
            lower, upper = _between_bounds(expected)
            actual, lower = _coerce_date_pair(actual, lower)
            actual, upper = _coerce_date_pair(actual, upper)
            return actual >= lower and actual <= upper

        actual, expected = _coerce_date_pair(actual, expected)
        if operator == "==":
            return actual == expected
        if operator == "!=":
            return actual != expected
        if operator == "<":
            return actual < expected
        if operator == "<=":
            return actual <= expected
        if operator == ">":
            return actual > expected
        if operator == ">=":
            return actual >= expected
    except (TypeError, ValueError) as exc:
        raise ConditionError(
            f"Cannot evaluate {field!r} {operator} {expected!r}: {exc}"
        ) from exc
    raise AssertionError(f"unhandled validated operator {operator!r}")


def _membership_items(value: Any) -> list[str]:
    source = value if isinstance(value, list) else str(value).split(",")
    return [str(item).strip() for item in source]


def _between_bounds(value: Any) -> tuple[Any, Any]:
    if isinstance(value, list):
        if len(value) != 2:
            raise ConditionError("'between' requires exactly two bounds")
        return value[0], value[1]
    if isinstance(value, str) and "," in value:
        lower, upper = value.split(",", 1)
        return lower.strip(), upper.strip()
    raise ConditionError("'between' requires a two-item list or comma-separated string")


def _local(value: datetime) -> datetime:
    """An aware datetime in the site's time zone; a naive one unchanged."""

    if value.tzinfo is None:
        return value
    from django.utils import timezone

    return timezone.localtime(value)


def _align(value: datetime, like: datetime) -> datetime:
    """``value`` made comparable with ``like``: a naive value is local time, and an aware
    one is turned into local time, kept aware or made naive to match ``like``."""

    if like.tzinfo is not None:
        return value.replace(tzinfo=like.tzinfo) if value.tzinfo is None else _local(value)
    return value if value.tzinfo is None else _local(value).replace(tzinfo=None)


def _coerce_date_pair(actual: Any, expected: Any) -> tuple[Any, Any]:
    """Repair the editor/date mismatch recorded in ``UPSTREAM_BUGS.md`` 54.

    A stored datetime is aware (UTC, ``USE_TZ``), and the editor's text is the site's
    local time, as upstream's naive datetimes are in the system time zone. So the stored
    value is read in the site's zone (``TIME_ZONE``), and a text value with no offset is
    taken as local time, before they are compared.
    """

    if isinstance(actual, datetime):
        actual = _local(actual)
        if isinstance(expected, str):
            try:
                if "T" in expected or " " in expected:
                    return actual, _align(datetime.fromisoformat(expected), actual)
                return actual.date(), date.fromisoformat(expected)
            except ValueError as exc:
                raise ConditionError(f"Invalid date value {expected!r}") from exc
        if isinstance(expected, date) and not isinstance(expected, datetime):
            return actual.date(), expected
        if isinstance(expected, datetime):
            return actual, _align(expected, actual)
        return actual, expected
    elif isinstance(actual, date) and isinstance(expected, str):
        try:
            return actual, date.fromisoformat(expected)
        except ValueError as exc:
            raise ConditionError(f"Invalid date value {expected!r}") from exc
    return actual, expected
