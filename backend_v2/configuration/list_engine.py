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
from configuration.list_views import ListView
from core.doctypes import doctype_of
from core.exceptions import ValidationError
from core.field_access import hidden_from
from core.filters import normalize_filters, resolve_me_tokens
from core.inputs import parse_json_param
from core.query import concrete_field_names, count_rows, fetch_rows

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
        if not custom_view or (is_default and has_list_data):
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

    return {
        "data": data,
        "columns": columns,
        "rows": rows,
        "fields": fields,
        "column_field": inputs.get("column_field"),
        "title_field": inputs.get("title_field"),
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
