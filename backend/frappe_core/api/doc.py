"""``crm.api.doc.get_data`` - the list/kanban engine.

Ported from ``crm/api/doc.py:256-541``. This is the keystone: six of the CRM's screens
render from its payload, and it is where the filter grammar, ``@me`` resolution, the
view-settings merge and column resolution all converge.

The **response shape is final now** (PHASE_0_FOUNDATION.md section 6b) even though two
of its inputs are not yet available:

* step 3, the saved ``CRM View Settings`` merge, stubs to the controller default until
  phase 4 lands the model. The branch structure is in place and commented, so phase 4
  fills in a body rather than restructuring.
* ``views`` and ``form_script`` / ``list_script`` return empty values for the same
  reason; the keys are always present.

Both stubs are marked ``PHASE 4`` below.
"""

from __future__ import annotations

import json
from typing import Any

from frappe_core import registry
from frappe_core.exceptions import ValidationError
from frappe_core.filters import normalize_filters, resolve_me_tokens
from frappe_core.query import (
    coerce_page_length,
    concrete_field_names,
    count_rows,
    fetch_rows,
    parse_json_param,
)
from frappe_core.metadata import _frappe_fieldtype, _link_target
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

#: Upstream's fallback columns when neither the client nor the controller supplies any
#: (``crm/api/doc.py:315-322``).
FALLBACK_COLUMNS = [
    {"label": "Name", "type": "Data", "key": "name", "width": "16rem"},
    {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
]
FALLBACK_ROWS = ["name"]

#: Appended to every payload's ``rows`` and ``fields`` (``crm/api/doc.py:463-483``).
STANDARD_FIELDS = [
    {"label": "Name", "fieldtype": "Data", "fieldname": "name"},
    {"label": "Created On", "fieldtype": "Datetime", "fieldname": "creation"},
    {"label": "Last Modified", "fieldtype": "Datetime", "fieldname": "modified"},
    {"label": "Modified By", "fieldtype": "Link", "fieldname": "modified_by", "options": "User"},
    {"label": "Assigned To", "fieldtype": "Text", "fieldname": "_assign"},
    {"label": "Owner", "fieldtype": "Link", "fieldname": "owner", "options": "User"},
    {"label": "Like", "fieldtype": "Data", "fieldname": "_liked_by"},
]


def _as_list(value: Any) -> list:
    parsed = parse_json_param(value, [])
    if parsed in (None, ""):
        return []
    return list(parsed) if isinstance(parsed, (list, tuple)) else [parsed]


def _as_dict(value: Any) -> dict:
    parsed = parse_json_param(value, {})
    return dict(parsed) if isinstance(parsed, dict) else {}


def _as_filters(value: Any):
    """Parse ``filters`` without narrowing the grammar.

    Upstream does ``filters = frappe._dict(filters)``, which assumes a dict and raises
    on the list-of-tuples form. Coercing a non-dict to ``{}`` instead - as an earlier
    revision of this function did - is far worse than raising: the filter silently
    disappears and the caller gets an unfiltered list back.

    So both accepted shapes from PHASE_0_FOUNDATION.md section 5 pass through intact and
    reach the shared translator, which already understands all of them.
    """
    parsed = parse_json_param(value, None)
    if parsed in (None, ""):
        return {}
    if isinstance(parsed, dict):
        return dict(parsed)
    if isinstance(parsed, (list, tuple)):
        return [list(item) if isinstance(item, (list, tuple)) else item for item in parsed]
    raise ValidationError(f"Unsupported filters value of type {type(parsed).__name__}")


def _merge_filters(filters, extra):
    """Apply ``default_filters`` over ``filters``, preserving each shape's semantics.

    For a dict this is upstream's ``filters.update(default_filters)`` - the default
    wins on a key clash. For the list form there is no key to clash on, so the
    conditions are appended and AND-ed, which is what the translator does with them.
    """
    if not extra:
        return filters
    extra_parsed = parse_json_param(extra, None)
    if extra_parsed in (None, ""):
        return filters

    if isinstance(filters, dict) and isinstance(extra_parsed, dict):
        merged = dict(filters)
        merged.update(extra_parsed)
        return merged

    as_list = normalize_filters(filters) if filters else []
    as_list += normalize_filters(extra_parsed)
    return [list(entry) for entry in as_list]


def get_doctype_fields(doctype: str) -> list[dict]:
    """The ``fields`` block: every value-carrying field on the doctype.

    Upstream filters out ``no_value_fields`` (Section/Column/Tab Break, HTML, ...). We
    never materialise those as columns in the first place (PHASE_1_MODELS.md section 2),
    so every concrete model field qualifies.
    """
    entry = registry.get_entry(doctype)
    fields = []
    for field in entry.model._meta.get_fields():
        if not getattr(field, "concrete", False):
            continue
        fields.append(
            {
                "label": str(getattr(field, "verbose_name", field.name)),
                "fieldtype": _frappe_fieldtype(field),
                "fieldname": field.name,
                "options": _link_target(field),
            }
        )
    return fields


def _has_field(model, fieldname: str) -> bool:
    try:
        model._meta.get_field(fieldname)
        return True
    except Exception:
        return False


def _hidden_fields(entry) -> set[str]:
    """Fieldnames the doctype declares hidden - upstream's ``DocField.hidden``.

    Django has no equivalent property, so a model declares them the same way it declares
    ``get_non_filterable_fields()``. Phase 1 populates this from the DocType JSON's
    ``"hidden": 1`` fields; phase 4 may extend it from Property Setters.
    """
    provider = getattr(entry.model, "get_hidden_fields", None)
    if callable(provider):
        return set(provider() or [])
    return set()


def _load_saved_view(doctype: str, view_type: str, user: str):
    """PHASE 4: the saved ``CRM View Settings`` lookup.

    Upstream (``crm/api/doc.py:324-335``) matches on
    ``{dt, type: view_type or "list", is_standard: 1, user}`` and, on a hit, replaces
    both ``columns`` and ``rows`` and clears ``is_default``.

    Phase 4 registers a provider via ``registry.register_metadata_hooks``; until then
    there is no CRM View Settings model, so this returns ``None`` and the caller falls
    through to the controller default - which is exactly upstream's ``elif`` branch.
    """
    entry = registry.get_entry(doctype)
    provider = entry.list_columns_provider
    if provider is None:
        return None
    return provider(doctype, user, view_type or "list")


def _get_views(doctype: str) -> list:
    """PHASE 4: ``crm/api/views.py:get_views`` - the user's saved views."""
    return []


def _get_form_script(doctype: str, script_type: str = "Form"):
    """PHASE 4: ``crm_form_script.get_form_script``."""
    return None


@whitelist("crm.api.doc.get_data")
def get_data(
    doctype: str,
    filters: Any = None,
    order_by: Any = None,
    page_length: int = 20,
    page_length_count: int = 20,
    column_field: str | None = None,
    title_field: str | None = None,
    columns: Any = None,
    rows: Any = None,
    kanban_columns: Any = None,
    kanban_fields: Any = None,
    view: Any = None,
    default_filters: Any = None,
) -> dict:
    """Parameter names and order match ``crm/api/doc.py:256-271`` exactly."""
    user = get_current_user()
    entry = registry.get_entry(doctype)

    filters = _as_filters(filters)
    rows = _as_list(rows)
    columns = _as_list(columns)
    kanban_fields = _as_list(kanban_fields)
    kanban_columns = _as_list(kanban_columns)
    view = _as_dict(view)

    custom_view_name = view.get("custom_view_name")
    view_type = view.get("view_type")
    group_by_field = view.get("group_by_field")

    # 1. @me tokens (upstream lines 283-293). resolve_me_tokens recurses, so it covers
    #    the dict and the list-of-tuples form alike.
    filters = resolve_me_tokens(filters, user)

    # 2. default_filters override user filters, matching dict.update() upstream.
    filters = _merge_filters(filters, default_filters)

    is_default = True
    custom_view = False
    data: list = []

    default_list_data = entry.default_list_data()
    default_rows = default_list_data.get("rows", []) if entry.has_default_list_data() else []

    if view_type != "kanban":
        # 3. Column/row resolution, in upstream's exact order.
        if columns or rows:
            custom_view = True
            is_default = False

        if not columns:
            columns = [dict(c) for c in FALLBACK_COLUMNS]
        if not rows:
            rows = list(FALLBACK_ROWS)

        saved = None
        if not custom_view:
            saved = _load_saved_view(doctype, view_type, user)

        if saved is not None:
            columns = _as_list(saved.get("columns")) or [dict(c) for c in FALLBACK_COLUMNS]
            rows = _as_list(saved.get("rows")) or list(FALLBACK_ROWS)
            is_default = False
        elif not custom_view or (is_default and entry.has_default_list_data()):
            # Fall back again rather than adopting an empty default. A controller may
            # define default_list_data() with columns but no rows (or vice versa), and
            # `default_rows` is deliberately [] when the controller defines nothing at
            # all - without these guards that empties what was just set above.
            rows = list(default_rows) or list(FALLBACK_ROWS)
            columns = [dict(c) for c in default_list_data.get("columns", [])] or [
                dict(c) for c in FALLBACK_COLUMNS
            ]

        # 4. Every column key must be present in rows; hidden columns are dropped.
        #
        # Upstream (lines 350-352) decides "hidden" from the *doctype field metadata*
        # (`meta.get_field(key).hidden`), not from a flag on the column dict. We honour
        # both: the field-level declaration is the faithful one, and a caller-supplied
        # flag is a strict superset that costs nothing.
        #
        # Upstream also mutates `columns` while iterating it, so a hidden column causes
        # the next one to be skipped. We iterate a copy; replicating that bug would
        # drop visible columns at random.
        hidden_fields = _hidden_fields(entry)
        for column in list(columns):
            key = column.get("key")
            if key is not None and key not in rows:
                rows.append(key)
            if key == "_liked_by" and column.get("width") == "10rem":
                column["width"] = "50px"
            if column.get("hidden") or key in hidden_fields:
                columns.remove(column)

        if group_by_field and group_by_field not in rows:
            rows.append(group_by_field)

        # 5. Query, permission-filtered (query.fetch_rows applies the phase-2 hook).
        data = fetch_rows(
            doctype,
            fields=_selectable(entry, rows),
            filters=filters,
            order_by=order_by,
            limit_page_length=coerce_page_length(page_length),
            user=user,
        )
        data = entry.parse_list_data(data)

    if view_type == "kanban":
        data, kanban_columns, kanban_fields, rows, title_field = _kanban(
            entry,
            doctype,
            filters=filters,
            order_by=order_by,
            rows=rows or list(default_rows),
            column_field=column_field,
            title_field=title_field,
            kanban_columns=kanban_columns,
            kanban_fields=kanban_fields,
            user=user,
        )

    # 6. fields + standard fields (upstream lines 450-483).
    fields = get_doctype_fields(doctype)
    known = {f["fieldname"] for f in fields}
    for descriptor in STANDARD_FIELDS:
        if descriptor["fieldname"] not in rows:
            rows.append(descriptor["fieldname"])
        if descriptor["fieldname"] not in known:
            fields.append(dict(descriptor))
            known.add(descriptor["fieldname"])

    if not is_default and custom_view_name:
        # PHASE 4: upstream reads load_default_columns off the saved view here.
        is_default = False

    if group_by_field and view_type == "group_by":
        group_by_field = _resolve_group_by_options(fields, group_by_field, data, order_by)

    return {
        "data": data,
        "columns": columns,
        "rows": rows,
        "fields": fields,
        "column_field": column_field,
        "title_field": title_field,
        "kanban_columns": kanban_columns,
        "kanban_fields": kanban_fields,
        "group_by_field": group_by_field,
        "page_length": page_length,
        "page_length_count": page_length_count,
        "is_default": is_default,
        "views": _get_views(doctype),
        "total_count": count_rows(doctype, filters=filters, user=user),
        "row_count": len(data),
        "form_script": _get_form_script(doctype),
        "list_script": _get_form_script(doctype, "List"),
        "view_type": view_type,
    }


def _selectable(entry, rows: list[str]) -> list[str]:
    """Validate the row keys and hand them to the query.

    **This used to silently drop unknown keys.** That was a deliberate port-time
    concession: ``default_list_data()`` is authored against the Frappe doctype, and while
    models were half-built a single missing column would have broken an entire list view.
    The concession carried a stated expiry - "revisit once phase 1 is complete, by then a
    missing field is a genuine bug and should raise".

    Phase 1 is complete and all 46 models were checked: **no ``default_list_data()``
    names a field its model lacks**. So the concession is retired, and this now behaves
    like every other field path - ``resolve_fields`` raises on an unknown name, for the
    reason recorded there: silently dropping one lets a typo'd column quietly vanish from
    a list view instead of failing loudly. Upstream raises here too.

    The empty-``rows`` fallback stays: it is not an error, just nothing selected yet.
    """
    if not rows:
        return ["name"]

    available = concrete_field_names(entry.model)
    unknown = [r for r in rows if r not in available]
    if unknown:
        raise ValidationError(
            f"Unknown field{'s' if len(unknown) > 1 else ''} "
            f"{', '.join(repr(u) for u in unknown)} for {entry.doctype}"
        )
    return list(rows)


def _kanban(
    entry,
    doctype: str,
    *,
    filters: dict | list,
    order_by: Any,
    rows: list,
    column_field: str | None,
    title_field: str | None,
    kanban_columns: list,
    kanban_fields: list,
    user: str,
):
    """The kanban branch (upstream lines 370-448), implemented structurally.

    Column resolution from a Link target or a Select's options is complete; the
    per-column ordering (``get_records_based_on_order``) and the ``getCounts`` badge
    counts need the CRM models and are phase 3/4 work.
    """
    kanban_settings = entry.default_kanban_settings() or {}

    if not kanban_columns and column_field:
        field = None
        try:
            field = entry.model._meta.get_field(column_field)
        except Exception:
            field = None
        if field is not None and field.is_relation and field.related_model is not None:
            related = field.related_model
            related_doctype = getattr(related, "get_doctype", lambda: None)()
            # Upstream resolves these with frappe.get_all, which applies permissions.
            # Going through base_queryset keeps that property: a kanban grouped by a
            # restricted doctype must not enumerate rows the user cannot see.
            if related_doctype and registry.has_doctype(related_doctype):
                from frappe_core.query import base_queryset

                queryset = base_queryset(related_doctype, user)
            else:
                queryset = related._default_manager.all()
            order_field = "modified" if _has_field(related, "modified") else "pk"
            kanban_columns = [
                {"name": pk}
                for pk in queryset.order_by(order_field).values_list("pk", flat=True)
            ]
        elif field is not None and getattr(field, "choices", None):
            kanban_columns = [{"name": choice[0]} for choice in field.choices]

    if not title_field:
        title_field = kanban_settings.get("title_field", "name")
    if title_field not in rows:
        rows.append(title_field)

    if not kanban_fields:
        raw = kanban_settings.get("kanban_fields")
        kanban_fields = json.loads(raw) if isinstance(raw, str) else (raw or ["name"])
    for field_name in kanban_fields:
        if field_name not in rows:
            rows.append(field_name)

    # Normalise once: filters may be a dict or a list of tuples here, and the per-column
    # logic below needs to both read and extend it.
    base_conditions = [list(condition) for condition in normalize_filters(filters)]

    # Only an *equality* filter on the column field can pre-select a column. Upstream
    # compares `filters.get(column_field) != kc.name`, which for the operator form
    # ("status", "!=", "Lost") compares a list against a string, is always unequal, and
    # so blanks every column. Dropping the operator instead - as an earlier revision did
    # - is worse: it treats "!= Lost" as "== Lost" and inverts the board.
    #
    # So: equality is honoured exactly as upstream, and any other operator on the column
    # field is kept and AND-ed with the column's own constraint rather than being
    # reinterpreted. That narrows correctly instead of blanking or inverting.
    equality_on_column = None
    if column_field:
        for fieldname, operator, value in base_conditions:
            if fieldname == column_field and operator == "=":
                equality_on_column = value
                break

    data = []
    for kc in kanban_columns:
        if (
            equality_on_column is not None and equality_on_column != kc.get("name")
        ) or kc.get("delete"):
            column_data = []
            column_filters = list(base_conditions)
        else:
            column_filters = list(base_conditions)
            if column_field:
                # Drop only the redundant equality; other operators stay and AND.
                column_filters = [
                    c for c in column_filters if not (c[0] == column_field and c[1] == "=")
                ]
                column_filters.append([column_field, "=", kc.get("name")])
            page_length = coerce_page_length(kc.get("page_length"), 20)
            column_data = fetch_rows(
                doctype,
                fields=_selectable(entry, rows),
                filters=column_filters,
                order_by=order_by,
                limit_page_length=page_length,
                user=user,
            )
            kc["all_count"] = count_rows(doctype, filters=column_filters, user=user)
            kc["count"] = len(column_data)
        data.append({"column": kc, "fields": kanban_fields, "data": column_data})

    return data, kanban_columns, kanban_fields, rows, title_field


def _resolve_group_by_options(fields: list, group_by_field: str, data: list, order_by: Any):
    """Upstream lines 488-520: turn the group-by fieldname into a descriptor + options."""
    descriptor = next((f for f in fields if f.get("fieldname") == group_by_field), None)
    if descriptor is None:
        return group_by_field

    if descriptor.get("fieldtype") == "Select" and descriptor.get("options"):
        options = list(str(descriptor["options"]).split("\n"))
    else:
        has_empty = any(not row.get(group_by_field) for row in data)
        options = [o for o in {row.get(group_by_field) for row in data} if o]
        if has_empty:
            options.append("")
        order_by_text = str(order_by or "")
        if group_by_field in order_by_text:
            clauses = [c.strip().split(" ") for c in order_by_text.split(",")]
            pairs = {(c[0], c[1]) for c in clauses if len(c) > 1}
            if (group_by_field, "desc") in pairs:
                options.sort(reverse=True)
            else:
                options.sort()
        else:
            options.sort()

    return {
        "label": descriptor.get("label"),
        "fieldname": descriptor.get("fieldname"),
        "fieldtype": descriptor.get("fieldtype"),
        "options": options,
    }
