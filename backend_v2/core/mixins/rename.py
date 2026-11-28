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
    """Add the detail ``rename`` action to a document resource.

    A resource that renames its own way overrides the hooks (ACCOUNTS §10.1-10.3):
    ``before_rename`` (normalises and refuses, right after the record is found),
    ``name_taken``, ``rename_rule`` and ``on_renamed`` (inside the rename's transaction).
    The defaults keep the old order and answers: merge, missing, unchanged, taken, the
    write rule, then ``validate_name``.
    """

    def before_rename(self, instance, old_name: str, new_name: str) -> str:
        """Answer the name every later check and the rename use; may refuse."""
        return new_name

    def name_taken(self, new_name: str, old_name: str) -> bool:
        return self.document_model._default_manager.filter(pk=new_name).exists()

    def rename_rule(self, user, instance) -> bool:
        return self.has_object_rule(user, instance, "write") is not False

    def on_renamed(self, old_name: str, new_name: str) -> None:
        """Called inside the rename's transaction, after the references are repointed
        and before the old row is deleted."""

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
        new_name = self.before_rename(instance, old_name, new_name)
        if old_name == new_name:
            throw(_("No changes made because old and new name are the same."))
        if self.name_taken(new_name, old_name):
            throw(
                _("Another {0} with name {1} exists, select another name").format(
                    self.document_type, new_name
                )
            )
        if not self.rename_rule(request.user, instance):
            throw(
                _("You need write permission on {0} {1} to rename").format(
                    self.document_type, old_name
                )
            )

        new_name = validate_name(self.document_type, new_name)
        return Response(
            Envelope(
                rename_document(
                    self.document_model, old_name, new_name, on_renamed=self.on_renamed
                ),
                "message",
            )
        )
