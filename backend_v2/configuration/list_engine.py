"""The list engine: `crm.api.doc.get_data` (specs/CONFIGURATION.md section 4.8).

Ported from `backend/frappe_core/api/doc.py:38-372`. It runs on one resource: the
ViewSet that opts in (`configuration/mixins.py`) passes its row-ruled queryset and its
field lists, so the caller's rules apply to every row and every field it names (root
rule 11). Its list definition is the ViewSet's `list_view_class`.
"""

from __future__ import annotations

from django.db.models import ForeignKey, OneToOneField

from configuration import view_settings
from configuration.form_scripts import get_form_script
from configuration.kanban_counts import add_counts
from configuration.list_views import ListView
from core.doctypes import doctype_of
from core.exceptions import ValidationError
from core.field_access import hidden_from
from core.filters import normalize_filters, resolve_me_tokens
from core.inputs import parse_json_param
from core.exceptions import FilterError
from core.query import (
    MAX_PAGE_LENGTH,
    coerce_page_length,
    concrete_field_names,
    count_rows,
    fetch_rows,
)
from core.resources import routed_rule_map

#: Appended to every answer's `rows` and, when missing, `fields` (old `:47-55`).
STANDARD_FIELDS = (
    {"label": "Name", "fieldtype": "Data", "fieldname": "name"},
    {"label": "Created On", "fieldtype": "Datetime", "fieldname": "creation"},
    {"label": "Last Modified", "fieldtype": "Datetime", "fieldname": "modified"},
    {"label": "Modified By", "fieldtype": "Link", "fieldname": "modified_by", "options": "User"},
    {"label": "Assigned To", "fieldtype": "Text", "fieldname": "_assign"},
    {"label": "Owner", "fieldtype": "Link", "fieldname": "owner", "options": "User"},
    {"label": "Like", "fieldtype": "Data", "fieldname": "_liked_by"},
)
FALLBACK_ROWS = ("name",)

#: The old `frappe_core/metadata.py:175-194`: never `Select`, unlike
#: `configuration/field_meta.py`, so a field with choices is not grouped by its options.
_FIELDTYPES = {
    "BooleanField": "Check",
    "CharField": "Data",
    "TextField": "Small Text",
    "EmailField": "Data",
    "IntegerField": "Int",
    "BigIntegerField": "Int",
    "SmallIntegerField": "Int",
    "PositiveIntegerField": "Int",
    "FloatField": "Float",
    "DecimalField": "Currency",
    "DateField": "Date",
    "DateTimeField": "Datetime",
    "ForeignKey": "Link",
    "OneToOneField": "Link",
    "JSONField": "JSON",
}


# --- inputs (old `:58-111`) --------------------------------------------------------------


def as_list(value) -> list:
    parsed = parse_json_param(value, [])
    if parsed in (None, ""):
        return []
    return list(parsed) if isinstance(parsed, (list, tuple)) else [parsed]


def as_dict(value) -> dict:
    parsed = parse_json_param(value, {})
    return dict(parsed) if isinstance(parsed, dict) else {}


def as_filters(value):
    """A dict or a list of conditions, both passed through; anything else is 417 rather
    than an unfiltered list."""
    parsed = parse_json_param(value, None)
    if parsed in (None, ""):
        return {}
    if isinstance(parsed, dict):
        return dict(parsed)
    if isinstance(parsed, (list, tuple)):
        return [list(item) if isinstance(item, (list, tuple)) else item for item in parsed]
    raise ValidationError(f"Unsupported filters value of type {type(parsed).__name__}")


def merge_filters(filters, extra):
    """`default_filters` over `filters`: a dict overrides key by key (`dict.update`);
    otherwise the conditions are appended and AND-ed."""
    if not extra:
        return filters
    extra = parse_json_param(extra, None)
    if extra in (None, ""):
        return filters
    if isinstance(filters, dict) and isinstance(extra, dict):
        return {**filters, **extra}
    merged = normalize_filters(filters) if filters else []
    merged += normalize_filters(extra)
    return [list(entry) for entry in merged]


# --- fields (old `:114-134`, `:375-402`) -------------------------------------------------


def _link_target(field):
    if isinstance(field, (ForeignKey, OneToOneField)):
        related = field.related_model
        return getattr(related, "DOCTYPE", None) or related.__name__
    return None


def doctype_fields(model) -> list[dict]:
    """Every concrete field as `{label, fieldtype, fieldname, options}`."""
    return [
        {
            "label": str(getattr(field, "verbose_name", field.name)),
            "fieldtype": _FIELDTYPES.get(field.get_internal_type(), "Data"),
            "fieldname": field.name,
            "options": _link_target(field),
        }
        for field in model._meta.get_fields()
        if getattr(field, "concrete", False)
    ]


def check_shapes(columns, rows, kanban_columns=(), kanban_fields=()) -> None:
    """PE-12e: what the old code would crash on is 417."""
    if any(not isinstance(column, dict) for column in columns):
        raise ValidationError("Columns must be objects")
    if any(not isinstance(row, str) for row in rows):
        raise ValidationError("Rows must be fieldnames")
    if any(not isinstance(column, dict) for column in kanban_columns):
        raise ValidationError("Kanban columns must be objects")
    if any(not isinstance(field, str) for field in kanban_fields):
        raise ValidationError("Kanban fields must be fieldnames")


def group_by_options(fields: list, group_by_field: str, data: list, order_by):
    """Old `:601-630`: the group-by field as `{label, fieldname, fieldtype, options}`,
    the options a Select's or else the page's own distinct values."""
    descriptor = next((f for f in fields if f.get("fieldname") == group_by_field), None)
    if descriptor is None:
        return group_by_field
    if descriptor.get("fieldtype") == "Select" and descriptor.get("options"):
        options = list(str(descriptor["options"]).split("\n"))
    else:
        has_empty = any(not row.get(group_by_field) for row in data)
        options = [value for value in {row.get(group_by_field) for row in data} if value]
        if has_empty:
            options.append("")
        order_by_text = str(order_by or "")
        if group_by_field in order_by_text:
            clauses = [clause.strip().split(" ") for clause in order_by_text.split(",")]
            pairs = {(clause[0], clause[1]) for clause in clauses if len(clause) > 1}
            options.sort(reverse=(group_by_field, "desc") in pairs)
        else:
            options.sort()
    return {
        "label": descriptor.get("label"),
        "fieldname": descriptor.get("fieldname"),
        "fieldtype": descriptor.get("fieldtype"),
        "options": options,
    }


def kanban_link_columns(model, column_field, user) -> list[dict] | None:
    """A kanban's columns from the model (old `:426-450`): a forward foreign key gives the
    target's rows the caller may list, oldest modified first, and none when no resource
    serves the target (PE-22); a field with choices gives its choices. `None` when the
    field is neither."""
    try:
        field = model._meta.get_field(column_field)
    except Exception:
        return None
    if field.is_relation and field.related_model is not None and not field.auto_created:
        target = field.related_model
        rules = routed_rule_map().get(target)
        if rules is None:
            return []
        queryset = target._default_manager.all()
        rule = rules.list_rule(user)
        if rule is not None:
            queryset = queryset.filter(rule)
        order = "modified" if any(f.name == "modified" for f in target._meta.get_fields()) else "pk"
        return [{"name": pk} for pk in queryset.order_by(order).values_list("pk", flat=True)]
    if getattr(field, "choices", None):
        return [{"name": choice[0]} for choice in field.choices]
    return None


def selectable(model, rows: list) -> list:
    """The row keys to query: every unknown key named in one refusal, as the old
    `_selectable`; a known key the caller may not read is refused by the query."""
    if not rows:
        return list(FALLBACK_ROWS)
    available = concrete_field_names(model)
    unknown = [row for row in rows if row not in available]
    if unknown:
        raise ValidationError(
            f"Unknown field{'s' if len(unknown) > 1 else ''} "
            f"{', '.join(repr(name) for name in unknown)} for {doctype_of(model)}"
        )
    return list(rows)


# --- kanban (old `:405-561`) -------------------------------------------------------------


def _records_in_order(viewset, queryset, fields, filters, page_length, order, user):
    """Old `:531-561`: the cards named in `order` first, newest created first, then the
    rest to fill the page; both through the caller's rules. The engine's own clauses
    (`name in` / `not in`, `creation desc`) are not checked against the caller's lists."""
    common = {
        "user": user,
        "fields": fields,
        "filters": filters,
        "order_by": "creation desc",
        "selectable": viewset.readable_fields,
        "filterable": viewset.filterable_fields,
        "sortable": None,
    }
    # As the old code: a page length of 0 takes no named card and stops (`:540-550`).
    records = fetch_rows(
        queryset.filter(pk__in=list(order)[:page_length]), limit_page_length=page_length, **common
    )
    if len(records) < page_length:
        records += fetch_rows(
            queryset.exclude(pk__in=list(order)),
            limit_page_length=page_length - len(records),
            **common,
        )
    return records


def kanban(viewset, model, definition, queryset, *, filters, order_by, rows, column_field,
           title_field, kanban_columns, kanban_fields, user):
    """The kanban branch: one entry per column, each with its cards and counts."""
    if len(kanban_columns) > MAX_PAGE_LENGTH:
        raise ValidationError(f"At most {MAX_PAGE_LENGTH} kanban columns")  # PE-23
    if column_field and column_field not in viewset.filterable_fields:
        raise FilterError(f"Cannot filter on {column_field!r}")
    settings = definition.default_kanban_settings()

    if not kanban_columns and column_field:
        kanban_columns = kanban_link_columns(model, column_field, user) or []

    if not title_field:
        title_field = settings.get("title_field", "name")
    if title_field not in rows:
        rows.append(title_field)
    if not kanban_fields:
        raw = settings.get("kanban_fields")
        kanban_fields = parse_json_param(raw, None) if isinstance(raw, str) else (raw or ["name"])
    for fieldname in kanban_fields:
        if fieldname not in rows:
            rows.append(fieldname)
    fields = selectable(model, rows)

    # Only an equality filter on the column field pre-selects a column; any other
    # operator on it stays and is AND-ed (old `:464-482`).
    base = [list(condition) for condition in normalize_filters(filters)]
    equality = next(
        (value for fieldname, operator, value in base if column_field and fieldname == column_field and operator == "="),
        None,
    )

    data = []
    for column in kanban_columns:
        if (equality is not None and equality != column.get("name")) or column.get("delete"):
            cards = []
        else:
            column_filters = list(base)
            if column_field:
                column_filters = [c for c in column_filters if not (c[0] == column_field and c[1] == "=")]
                column_filters.append([column_field, "=", column.get("name")])
            page_length = coerce_page_length(column.get("page_length"), 20)
            order = column.get("order")
            if order is not None and not isinstance(order, list):
                raise ValidationError("A column's order must be a list")  # PE-12e
            if order:
                cards = _records_in_order(viewset, queryset, fields, column_filters, page_length, order, user)
                cards.sort(key=lambda row: order.index(row["name"]) if row.get("name") in order else len(order))
            else:
                cards = fetch_rows(
                    queryset,
                    user=user,
                    fields=fields,
                    filters=column_filters,
                    order_by=order_by,
                    limit_page_length=page_length,
                    selectable=viewset.readable_fields,
                    filterable=viewset.filterable_fields,
                    sortable=viewset.sortable_fields,
                )
            column["all_count"] = count_rows(
                queryset, user=user, filters=column_filters, filterable=viewset.filterable_fields
            )
            column["count"] = len(cards)
            add_counts(doctype_of(model), cards)
        data.append({"column": column, "fields": kanban_fields, "data": cards})
    return data, kanban_columns, kanban_fields, rows, title_field


# --- the call (old `:211-372`) -----------------------------------------------------------


def get_data(viewset, inputs: dict, *, user) -> dict:
    model = viewset.serializer_class.Meta.model
    doctype = doctype_of(model)
    definition = getattr(viewset, "list_view_class", None) or ListView
    queryset = viewset.get_queryset()

    filters = as_filters(inputs.get("filters"))
    rows = as_list(inputs.get("rows"))
    columns = as_list(inputs.get("columns"))
    kanban_fields = as_list(inputs.get("kanban_fields"))
    kanban_columns = as_list(inputs.get("kanban_columns"))
    view = as_dict(inputs.get("view"))
    order_by = inputs.get("order_by")
    page_length = inputs.get("page_length", 20)
    view_type = view.get("view_type")
    group_by_field = view.get("group_by_field")
    custom_view_name = view.get("custom_view_name")
    check_shapes(columns, rows, kanban_columns, kanban_fields)

    # 1-2. @me, then default_filters over filters.
    filters = resolve_me_tokens(filters, user)
    filters = merge_filters(filters, inputs.get("default_filters"))

    is_default = True
    data: list = []
    has_list_data = definition.has_list_data()
    default_rows = definition.default_rows() if has_list_data else []

    if view_type != "kanban":
        # 3. Columns and rows, in the old order.
        custom_view = bool(columns or rows)
        if custom_view:
            is_default = False
        if not columns:
            columns = ListView.default_columns()
        if not rows:
            rows = list(FALLBACK_ROWS)
        saved = None
        if not custom_view:
            saved = view_settings.saved_standard_view(doctype, view_type, user=user)
        if saved is not None:
            # The caller's own standard view (old `:267-274`).
            columns = as_list(saved["columns"]) or ListView.default_columns()
            rows = as_list(saved["rows"]) or list(FALLBACK_ROWS)
            check_shapes(columns, rows)
            is_default = False
        elif not custom_view or (is_default and has_list_data):
            # The old clause, dead as written (`:275`), ported as it is.
            rows = list(default_rows) or list(FALLBACK_ROWS)
            columns = definition.default_columns() or ListView.default_columns()

        # 4. Every column key in rows; a hidden column is dropped (iterating a copy).
        hidden = set(definition.hidden_fields)
        for column in list(columns):
            key = column.get("key")
            if key is not None and key not in rows:
                rows.append(key)
            if key == "_liked_by" and column.get("width") == "10rem":
                column["width"] = "50px"
            if column.get("hidden") or key in hidden:
                columns.remove(column)
        if group_by_field and group_by_field not in rows:
            rows.append(group_by_field)

        # 5. The query, through the resource's rules and field lists.
        data = fetch_rows(
            queryset,
            user=user,
            fields=selectable(model, rows),
            filters=filters,
            order_by=order_by,
            limit_page_length=page_length,
            selectable=viewset.readable_fields,
            filterable=viewset.filterable_fields,
            sortable=viewset.sortable_fields,
        )
        data = definition.parse(data)

    title_field = inputs.get("title_field")
    if view_type == "kanban":
        data, kanban_columns, kanban_fields, rows, title_field = kanban(
            viewset,
            model,
            definition,
            queryset,
            filters=filters,
            order_by=order_by,
            rows=rows or list(default_rows),
            column_field=inputs.get("column_field"),
            title_field=title_field,
            kanban_columns=kanban_columns,
            kanban_fields=kanban_fields,
            user=user,
        )

    # 6. The fields block, the standard fields added, then PE-16.
    fields = doctype_fields(model)
    known = {field["fieldname"] for field in fields}
    for descriptor in STANDARD_FIELDS:
        if descriptor["fieldname"] not in rows:
            rows.append(descriptor["fieldname"])
        if descriptor["fieldname"] not in known:
            fields.append(dict(descriptor))
            known.add(descriptor["fieldname"])
    hidden_fields = hidden_from(model, user)
    fields = [field for field in fields if field["fieldname"] not in hidden_fields]

    # 7. A named view that loads the default columns reports itself as default.
    if not is_default and custom_view_name:
        is_default = view_settings.loads_default_columns(custom_view_name, user=user)

    # 8. Group-by options: the page's own values.
    if group_by_field and view_type == "group_by":
        group_by_field = group_by_options(fields, group_by_field, data, order_by)

    return {
        "data": data,
        "columns": columns,
        "rows": rows,
        "fields": fields,
        "column_field": inputs.get("column_field"),
        "title_field": title_field,
        "kanban_columns": kanban_columns,
        "kanban_fields": kanban_fields,
        "group_by_field": group_by_field,
        "page_length": page_length,
        "page_length_count": inputs.get("page_length_count", 20),
        "is_default": is_default,
        "views": view_settings.get_views(doctype, user=user),
        "total_count": count_rows(
            queryset, user=user, filters=filters, filterable=viewset.filterable_fields
        ),
        "row_count": len(data),
        "form_script": get_form_script(doctype),
        "list_script": get_form_script(doctype, "List"),
        "view_type": view_type,
    }
