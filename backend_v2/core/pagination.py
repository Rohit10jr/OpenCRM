"""Frappe limit/offset pagination without DRF's metadata wrapper."""

from rest_framework.pagination import BasePagination
from rest_framework.response import Response

from core.query import coerce_offset, coerce_page_length


class LimitStartPagination(BasePagination):
    def paginate_queryset(self, queryset, request, view=None):
        start = coerce_offset(request.query_params.get("limit_start"))
        length = coerce_page_length(request.query_params.get("limit_page_length"))
        if length == 0:
            return list(queryset[start:])
        return list(queryset[start : start + length])

    def get_paginated_response(self, data):
        return Response(data)
