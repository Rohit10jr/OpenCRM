"""Permission-filtered autocomplete search for document resources."""

from rest_framework.decorators import action
from rest_framework.response import Response

from core.field_access import is_hidden
from core.inputs import build_payload
from core.query import fetch_rows, parse_json_param
from core.renderers import Envelope


def truthy(value) -> bool:
    return str(value).strip().lower() not in ("", "0", "false", "none", "null")


def without_disabled(model, filters):
    """Add the standard enabled/disabled condition when the model has one."""

    names = {field.name for field in model._meta.get_fields()}
    if "enabled" not in names and "disabled" not in names:
        return filters
    result = dict(filters or {})
    if "enabled" in names:
        result.setdefault("enabled", 1)
    if "disabled" in names:
        result.setdefault("disabled", ["!=", 1])
    return result


class LinkSearchMixin:
    """Add the Link control's autocomplete action to a document resource."""

    def search_filters(self, filters, flags, user):
        """Return resource-specific filters before the shared list query runs."""

        if not flags["include_disabled"] and isinstance(filters, (dict, type(None))):
            return without_disabled(self.document_model, filters)
        return filters

    def _search_title_field(self, user):
        title_field = getattr(self.document_model, "SEARCH_FIELD", None)
        if not title_field:
            return None
        if (
            title_field not in self.readable_fields
            or title_field not in self.filterable_fields
        ):
            return None
        if is_hidden(self.document_model, title_field, user):
            return None
        return title_field

    @action(detail=False, methods=("get", "post"), url_path="search")
    def search(self, request):
        inputs = build_payload(request)
        filters = parse_json_param(inputs.get("filters"), None)
        flag_names = ("include_disabled", "ignore_user_type")
        flags = dict.fromkeys(flag_names, False)
        if isinstance(filters, dict):
            flags = {name: truthy(filters.pop(name, False)) for name in flag_names}
        filters = self.search_filters(filters, flags, request.user)

        txt = inputs.get("txt", "") or ""
        title_field = self._search_title_field(request.user)
        or_filters = None
        if txt:
            or_filters = {"name": ["like", "%{0}%".format(txt)]}
            if title_field:
                or_filters[title_field] = ["like", "%{0}%".format(txt)]

        fields = ["name"]
        if title_field:
            fields.append(title_field)
        rows = fetch_rows(
            self.get_queryset(),
            user=request.user,
            fields=fields,
            filters=filters,
            or_filters=or_filters,
            order_by="modified desc",
            limit_page_length=int(inputs.get("page_length") or 10),
            selectable=self.readable_fields,
            filterable=self.filterable_fields,
            sortable=self.sortable_fields,
        )
        if title_field and getattr(
            self.document_model, "SHOW_TITLE_FIELD_IN_LINK", False
        ):
            result = [
                {
                    "value": row["name"],
                    "label": str(row.get(title_field) or row["name"]),
                    "description": str(row["name"]),
                }
                for row in rows
            ]
        else:
            result = [
                {
                    "value": row["name"],
                    "description": (
                        str(row.get(title_field) or "") if title_field else ""
                    ),
                }
                for row in rows
            ]
        return Response(Envelope(result, "message"))
