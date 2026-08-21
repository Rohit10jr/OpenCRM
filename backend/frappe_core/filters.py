"""Frappe filter grammar -> Django ``Q``.

PHASE_0_FOUNDATION.md section 5. Every list endpoint, ``get_data``, and the phase-2
permission layer route through here, so the edge cases below are deliberate rather than
incidental.

Three input shapes are accepted, matching upstream's ``frappe.utils.make_filter_tuple``
normalisation::

    {"status": "Open"}                        # equals
    {"status": ["in", ["Open", "Lost"]]}      # operator form
    [["CRM Lead", "status", "=", "Open"]]     # 4-tuple, doctype-qualified
    [["status", "=", "Open"]]                 # 3-tuple

Case sensitivity: upstream runs MariaDB, where ``LIKE`` is case-insensitive. Postgres'
``LIKE`` is not, so every ``like`` maps to an ``I``-prefixed lookup (PORT_PLAN.md
section 10). Getting this wrong silently diverges every text search in the product.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from django.db.models import Q
from django.db.models.fields.json import JSONField
from django.db.models.fields.related import ForeignKey, OneToOneField

from frappe_core.field_security import is_hidden
from frappe_core.session import get_current_user

ME_TOKEN = "@me"
ME_LIKE_TOKEN = "%@me%"

#: Text-ish Django internal types. ``is set`` has to exclude ''  as well as NULL for
#: these, because Frappe emits ``ifnull(field, '') != ''``.
_TEXT_INTERNAL_TYPES = {"CharField", "TextField", "EmailField", "SlugField", "URLField"}

#: doctype -> callable(fieldname, value, inclusive) -> Q. Filled in by phase 2 for the
#: nested-set trees (CRM Sales Hierarchy, CRM Territory).
_TREE_RESOLVERS: dict[str, Callable] = {}


class FilterError(ValueError):
    """A filter could not be translated. Surfaces to the client as a 400."""


def register_tree_resolver(doctype: str, resolver: Callable) -> None:
    """Phase-2 entry point for ``descendants of`` / ``ancestors of``."""
    _TREE_RESOLVERS[doctype] = resolver


# ---------------------------------------------------------------------------
# @me resolution
# ---------------------------------------------------------------------------


def resolve_me_tokens(value: Any, user: str | None = None) -> Any:
    """Rewrite ``@me`` / ``%@me%`` to the current user, recursively.

    Upstream (``crm/api/doc.py:283-293``) scans only the top level of a filter value,
    replaces the *first* ``@me`` via ``list.index()`` but *every* ``%@me%`` via a loop,
    and short-circuits the second check with ``elif``. We replace every occurrence of
    both, at any depth. That is identical to upstream for every filter the product
    actually sends (a token appears at most once per value) and resolves upstream's own
    inconsistency between the two branches in the direction it already takes for
    ``%@me%``. Logged as a decision in docs/internal/PROGRESS.md.
    """
    user = user or get_current_user()

    if isinstance(value, str):
        if value == ME_TOKEN:
            return user
        if value == ME_LIKE_TOKEN:
            return f"%{user}%"
        return value
    if isinstance(value, (list, tuple)):
        resolved = [resolve_me_tokens(v, user) for v in value]
        return type(value)(resolved) if isinstance(value, tuple) else resolved
    if isinstance(value, dict):
        return {k: resolve_me_tokens(v, user) for k, v in value.items()}
    return value


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def normalize_filters(filters: Any, doctype: str | None = None) -> list[tuple[str, str, Any]]:
    """Flatten any accepted input shape into ``[(fieldname, operator, value), ...]``."""
    if not filters:
        return []

    normalized: list[tuple[str, str, Any]] = []

    if isinstance(filters, dict):
        for fieldname, raw in filters.items():
            operator, value = _split_dict_value(raw)
            normalized.append((fieldname, operator, value))
        return normalized

    if isinstance(filters, (list, tuple)):
        for item in filters:
            normalized.append(_normalize_sequence_item(item, doctype))
        return normalized

    raise FilterError(f"Unsupported filter shape: {type(filters).__name__}")


def _split_dict_value(raw: Any) -> tuple[str, Any]:
    """``"Open"`` -> ``("=", "Open")``; ``["in", [...]]`` -> ``("in", [...])``."""
    if isinstance(raw, (list, tuple)) and len(raw) == 2 and isinstance(raw[0], str):
        candidate = raw[0].strip().lower()
        if candidate in _OPERATORS:
            return candidate, raw[1]
    return "=", raw


def _normalize_sequence_item(item: Any, doctype: str | None) -> tuple[str, str, Any]:
    if not isinstance(item, (list, tuple)):
        raise FilterError(f"Filter entry must be a list, got {type(item).__name__}")
    if len(item) == 4:
        # [doctype, fieldname, operator, value] - the doctype is dropped; cross-doctype
        # filters are not part of the CRM's surface.
        _, fieldname, operator, value = item
    elif len(item) == 3:
        fieldname, operator, value = item
    elif len(item) == 2:
        fieldname, value = item
        operator = "="
    else:
        raise FilterError(f"Filter entry must have 2-4 elements, got {len(item)}")
    return str(fieldname), str(operator).strip().lower(), value


# ---------------------------------------------------------------------------
# LIKE handling
# ---------------------------------------------------------------------------

_LIKE_SPECIALS = re.compile(r"[%_]")


def _like_to_lookup(value: Any) -> tuple[str, Any]:
    """Map a SQL ``LIKE`` pattern onto the narrowest case-insensitive Django lookup.

    ``%foo%`` -> ``icontains``, ``foo%`` -> ``istartswith``, ``%foo`` -> ``iendswith``,
    ``foo`` -> ``iexact``. Patterns with interior wildcards fall back to ``iregex``.

    Naively using ``icontains`` on the raw value would search for a literal ``%`` and
    match nothing, because the frontend sends its patterns pre-wrapped.
    """
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
        # value was exactly "%"
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


def _like_pattern_to_regex(pattern: str) -> str:
    """Translate a SQL LIKE pattern to a regex anchored at both ends."""
    out = ["^"]
    for char in pattern:
        if char == "%":
            out.append(".*")
        elif char == "_":
            out.append(".")
        else:
            out.append(re.escape(char))
    out.append("$")
    return "".join(out)


# ---------------------------------------------------------------------------
# Field resolution
# ---------------------------------------------------------------------------


def _get_field(model, fieldname: str):
    try:
        return model._meta.get_field(fieldname)
    except Exception:
        return None


def resolve_field_path(model, fieldname: str) -> str:
    """Django ORM path for a Frappe fieldname.

    Relations become ``<name>_id`` so that text lookups such as ``icontains`` apply to
    the stored key rather than raising against a model instance.
    """
    field = _get_field(model, fieldname)
    if field is not None and isinstance(field, (ForeignKey, OneToOneField)):
        return field.attname  # e.g. "lead_owner_id"
    return fieldname


def _is_text_field(model, fieldname: str) -> bool:
    field = _get_field(model, fieldname)
    if field is None:
        return True  # unknown -> assume text, matching Frappe's ifnull(x,'') default
    if isinstance(field, (ForeignKey, OneToOneField)):
        return True
    return field.get_internal_type() in _TEXT_INTERNAL_TYPES


def _is_json_field(model, fieldname: str) -> bool:
    field = _get_field(model, fieldname)
    return field is not None and isinstance(field, JSONField)


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------


def _op_equals(model, path, fieldname, value):
    return Q(**{path: value})


def _op_not_equals(model, path, fieldname, value):
    return ~Q(**{path: value})


def _simple(lookup):
    def build(model, path, fieldname, value):
        return Q(**{f"{path}__{lookup}": value})

    return build


def _op_like(model, path, fieldname, value):
    # A JSON list column (_assign, _liked_by) stores user emails. Upstream keeps the
    # same data in a JSON *string* column and filters it with a plain
    # LIKE '%user%' - case-insensitive, because MariaDB's LIKE is.
    #
    # Django renders `icontains` on a JSONField as
    #     UPPER("_assign"::text) LIKE UPPER('%user%')
    # which is that behaviour exactly. JSON containment (`__contains=[x]`) would be
    # tidier but diverges twice over: it is case-sensitive, and it matches whole
    # elements where upstream matches substrings.
    if _is_json_field(model, fieldname):
        lookup, operand = _like_to_lookup(value)
        # The anchored lookups are meaningless against a JSON blob (the text starts
        # with '['), so a JSON column always uses the containment form.
        if lookup in ("iexact", "istartswith", "iendswith"):
            return Q(**{f"{path}__icontains": operand})
        return Q(**{f"{path}__{lookup}": operand})
    lookup, operand = _like_to_lookup(value)
    return Q(**{f"{path}__{lookup}": operand})


def _op_not_like(model, path, fieldname, value):
    return ~_op_like(model, path, fieldname, value)


def _coerce_sequence(value, operator):
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if isinstance(value, str):
        # Frappe tolerates a comma-joined string here.
        return [part.strip() for part in value.split(",")]
    raise FilterError(f"Operator '{operator}' expects a list, got {type(value).__name__}")


def _op_in(model, path, fieldname, value):
    return Q(**{f"{path}__in": _coerce_sequence(value, "in")})


def _op_not_in(model, path, fieldname, value):
    return ~Q(**{f"{path}__in": _coerce_sequence(value, "not in")})


def _op_between(model, path, fieldname, value):
    bounds = _coerce_sequence(value, "between")
    if len(bounds) != 2:
        raise FilterError("Operator 'between' expects exactly two values")
    return Q(**{f"{path}__range": (bounds[0], bounds[1])})


def _op_is(model, path, fieldname, value):
    """``is set`` / ``is not set``.

    Frappe emits ``ifnull(field, '') != ''`` for "set", so an empty string counts as
    unset for text columns. Non-text columns test NULL only.
    """
    token = str(value).strip().lower()
    is_text = _is_text_field(model, fieldname)
    if token == "set":
        q = Q(**{f"{path}__isnull": False})
        if is_text:
            q &= ~Q(**{path: ""})
        return q
    if token == "not set":
        q = Q(**{f"{path}__isnull": True})
        if is_text:
            q |= Q(**{path: ""})
        return q
    raise FilterError(f"Operator 'is' expects 'set' or 'not set', got {value!r}")


def _tree_op(inclusive: bool, negate: bool = False, ancestors: bool = False):
    def build(model, path, fieldname, value):
        field = _get_field(model, fieldname)
        target_doctype = None
        if field is not None and isinstance(field, (ForeignKey, OneToOneField)):
            related = field.related_model
            target_doctype = getattr(related, "get_doctype", lambda: None)()
        resolver = _TREE_RESOLVERS.get(target_doctype) if target_doctype else None
        if resolver is None:
            raise FilterError(
                f"No tree resolver registered for {target_doctype or fieldname!r}; "
                "phase 2 registers these via filters.register_tree_resolver()"
            )
        q = resolver(
            fieldname=fieldname,
            path=path,
            value=value,
            inclusive=inclusive,
            ancestors=ancestors,
        )
        return ~q if negate else q

    return build


_OPERATORS: dict[str, Callable] = {
    "=": _op_equals,
    "!=": _op_not_equals,
    ">": _simple("gt"),
    "<": _simple("lt"),
    ">=": _simple("gte"),
    "<=": _simple("lte"),
    "like": _op_like,
    "not like": _op_not_like,
    "in": _op_in,
    "not in": _op_not_in,
    "between": _op_between,
    "is": _op_is,
    "descendants of": _tree_op(inclusive=False),
    "descendants of (inclusive)": _tree_op(inclusive=True),
    "not descendants of (inclusive)": _tree_op(inclusive=True, negate=True),
    "ancestors of": _tree_op(inclusive=False, ancestors=True),
    "not ancestors of (inclusive)": _tree_op(inclusive=True, negate=True, ancestors=True),
}

SUPPORTED_OPERATORS = tuple(_OPERATORS)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def build_q(
    model,
    filters: Any,
    *,
    doctype: str | None = None,
    user: str | None = None,
    combine: str = "AND",
) -> Q:
    """Translate ``filters`` into a single ``Q``.

    ``combine="OR"`` implements ``or_filters``.
    """
    entries = normalize_filters(filters, doctype)
    if not entries:
        return Q()

    result: Q | None = None
    for fieldname, operator, raw_value in entries:
        handler = _OPERATORS.get(operator)
        if handler is None:
            raise FilterError(
                f"Unsupported filter operator {operator!r}. "
                f"Supported: {', '.join(SUPPORTED_OPERATORS)}"
            )
        value = resolve_me_tokens(raw_value, user)
        # A field hidden from output must be hidden from *questions about it* too.
        # Hiding it from the response only stops the value being handed over; a filter
        # turns the row count into an oracle, and `like` narrows one character at a time.
        # Recovered a real SMTP password this way before this guard existed - see
        # `tests/test_field_security.py::test_a_secret_cannot_be_recovered_by_probing`.
        if is_hidden(model, fieldname, user):
            raise FilterError(f"Cannot filter on {fieldname!r}")
        path = resolve_field_path(model, fieldname)
        q = handler(model, path, fieldname, value)
        if result is None:
            result = q
        elif combine == "OR":
            result |= q
        else:
            result &= q

    return result if result is not None else Q()


def apply_filters(
    queryset,
    filters: Any = None,
    or_filters: Any = None,
    *,
    doctype: str | None = None,
    user: str | None = None,
):
    """Apply ``filters`` (AND) and ``or_filters`` (OR) to ``queryset``."""
    model = queryset.model
    if filters:
        queryset = queryset.filter(build_q(model, filters, doctype=doctype, user=user))
    if or_filters:
        queryset = queryset.filter(
            build_q(model, or_filters, doctype=doctype, user=user, combine="OR")
        )
    return queryset
