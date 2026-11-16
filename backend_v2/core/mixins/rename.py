"""Rename through an opted-in resource's object-write policy."""

from rest_framework.decorators import action
from rest_framework.response import Response

from core.exceptions import throw
from core.inputs import build_payload
from core.naming import validate_name
from core.rename import rename_document
from core.renderers import Envelope
from core.translate import _


class RenameMixin:
    """Add the detail ``rename`` action to a document resource."""

    @action(detail=True, methods=("post",), url_path="rename")
    def rename(self, request, pk=None):
        inputs = build_payload(request)
        old_name = str(pk)
        new_name = str(inputs.get("new_name"))

        if inputs.get("merge", False):
            throw(_("Merging documents is not supported"))

        instance = self.document_model._default_manager.filter(pk=old_name).first()
        if instance is None:
            throw(
                _("Can't rename {0} to {1} because {0} doesn't exist.").format(
                    old_name, new_name
                )
            )
        if old_name == new_name:
            throw(_("No changes made because old and new name are the same."))
        if self.document_model._default_manager.filter(pk=new_name).exists():
            throw(
                _("Another {0} with name {1} exists, select another name").format(
                    self.document_type, new_name
                )
            )
        if self.has_object_rule(request.user, instance, "write") is False:
            throw(
                _("You need write permission on {0} {1} to rename").format(
                    self.document_type, old_name
                )
            )

        new_name = validate_name(self.document_type, new_name)
        return Response(
            Envelope(
                rename_document(self.document_model, old_name, new_name),
                "message",
            )
        )
