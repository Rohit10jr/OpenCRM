"""DRF adapter for the shared Frappe list query functions."""

from rest_framework.filters import BaseFilterBackend

from core.query import build_list_queryset, parse_json_param, resolve_fields


class FilterBackend(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        params = request.query_params
        selectable = getattr(view, "selectable_fields", None)
        filterable = getattr(view, "filterable_fields", None)
        sortable = getattr(view, "sortable_fields", None)
        # Brief 08 consumes this projection after DRF has filtered the queryset.
        view.resolved_list_fields = resolve_fields(
            queryset.model,
            parse_json_param(params.get("fields")),
            user=request.user,
            selectable=selectable,
        )
        return build_list_queryset(
            queryset,
            user=request.user,
            filters=params.get("filters"),
            or_filters=params.get("or_filters"),
            order_by=params.get("order_by"),
            group_by=params.get("group_by"),
            filterable=filterable,
            sortable=sortable,
        )
