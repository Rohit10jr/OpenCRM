"""Bulk updates through an opted-in document resource's own policy."""

from __future__ import annotations

import logging

from django.db import transaction
from rest_framework.decorators import action
from rest_framework.response import Response

from core.inputs import build_payload
from core.query import by_name, parse_json_param
from core.renderers import Envelope
from core.translate import _

logger = logging.getLogger(__name__)

BULK_UPDATE_INLINE_THRESHOLD = 20
BULK_UPDATE_MAX_DOCUMENTS = 500


def bulk_update_documents(
    viewset_class, docnames, action="submit", data=None, user=None
):
    """Apply one action per document and report every name that did not complete."""

    viewset = viewset_class()
    payload = parse_json_param(data, None) if data else data
    failed = []

    for docname in docnames:
        try:
            document = by_name(viewset.document_model, docname).first()
            if document is None:
                failed.append(docname)
                continue

            if action == "update":
                if viewset.has_object_rule(user, document, "write") is False:
                    failed.append(docname)
                    continue
                serializer = viewset.get_serializer_class()(
                    document,
                    data=payload or {},
                    partial=True,
                    context={"user": user},
                )
                serializer.is_valid(raise_exception=True)
                viewset._check_destination(user, document, serializer.validated_data)
                with transaction.atomic():
                    serializer.save(user=user)
            else:
                failed.append(docname)
        except Exception:
            logger.exception(
                "Bulk action failed: %s %s", viewset.document_type, docname
            )
            failed.append(docname)

    return failed


def viewset_path(viewset_class) -> str:
    return "{0}.{1}".format(viewset_class.__module__, viewset_class.__qualname__)


class BulkUpdateMixin:
    """Add the collection ``bulk-update`` action to a document resource."""

    @action(detail=False, methods=("post",), url_path="bulk-update")
    def bulk_update(self, request):
        inputs = build_payload(request)
        parsed = parse_json_param(inputs.get("docnames"), []) or []
        if not isinstance(parsed, list):
            parsed = [parsed]
        names = [str(name) for name in parsed]
        action_name = inputs.get("action", "submit")
        data = parse_json_param(inputs.get("data"), None)

        if len(names) < BULK_UPDATE_INLINE_THRESHOLD:
            failed = bulk_update_documents(
                type(self), names, action_name, data, request.user
            )
            return Response(Envelope(failed, "message"))

        if len(names) <= BULK_UPDATE_MAX_DOCUMENTS:
            from core.tasks import bulk_update_docs

            bulk_update_docs.delay(
                viewset_path(type(self)),
                names,
                action_name,
                data,
                request.user.name,
            )
            return Response(Envelope(None, "message"))

        from core.exceptions import throw

        throw(
            _("Bulk operations only support up to 500 documents."),
            title=_("Too Many Documents"),
        )
