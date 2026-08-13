"""Generated serializers.

One ``ModelSerializer`` per doctype, built on demand and cached on the registry entry.
Phase-1 agents override by passing ``serializer_class=`` to ``register_doctype`` when a
doctype needs nested child tables or a computed field.

Link fields serialise to their raw key (an email for User, the string PK elsewhere),
which is what Frappe puts on the wire and what the frontend's Link controls expect.
DRF's default ``PrimaryKeyRelatedField`` already does exactly that.
"""

from __future__ import annotations

from rest_framework import serializers

#: Standard fields the client may never set directly; the model stamps them.
READ_ONLY_FIELDS = ("owner", "modified_by", "creation", "modified")


class DocumentSerializer(serializers.ModelSerializer):
    """Base for every generated serializer."""

    def get_fields(self):
        fields = super().get_fields()
        for name in READ_ONLY_FIELDS:
            if name in fields:
                fields[name].read_only = True
        return fields


def build_serializer_class(model) -> type[DocumentSerializer]:
    """Generate a serializer exposing every concrete field on ``model``."""
    name_strategy = getattr(model, "get_name_strategy", lambda: None)()
    # `prompt` doctypes take `name` from the client on create, so it must be writable.
    name_writable = bool(name_strategy is not None and name_strategy.requires_client_name)

    attrs: dict = {"Meta": type("Meta", (), {"model": model, "fields": "__all__"})}

    if name_writable:
        # `name` is `editable=False` on the model, which makes DRF derive it as
        # read-only - so `extra_kwargs={"name": {"required": True}}` is silently
        # ignored and a `prompt` doctype can never receive its client-supplied name.
        # An explicitly declared field overrides the model-derived one.
        attrs["name"] = serializers.CharField(max_length=140, required=True, allow_blank=False)

    return type(f"{model.__name__}Serializer", (DocumentSerializer,), attrs)
