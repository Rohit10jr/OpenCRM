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

from frappe_core import children, registry
from frappe_core.field_security import sensitive_fields

#: Standard fields the client may never set directly; the model stamps them.
#: Audit columns the server stamps, plus the four underscore caches.
#:
#: The underscore fields are **projections of other tables**, not user input
#: (PHASE_0_FOUNDATION.md section 3): ``_assign`` mirrors ``ToDo`` rows, ``_comments``
#: mirrors ``Comment``, ``_user_tags`` mirrors tag links, and ``_liked_by`` is toggled
#: through its own endpoint upstream. Leaving them writable let any client with write
#: access set them directly - not an access-control hole, because the permission layer
#: reads ``ToDo`` rather than ``_assign``, but a client could still make a document
#: advertise assignees it does not have, and the next rebuild would silently overwrite
#: the value. The maintainers write them with bare UPDATEs, which bypass the serializer.
READ_ONLY_FIELDS = (
    "owner",
    "modified_by",
    "creation",
    "modified",
    "_assign",
    "_liked_by",
    "_comments",
    "_user_tags",
)


class DocumentSerializer(serializers.ModelSerializer):
    """Base for every generated serializer.

    Child tables are serialised **inline** and **replaced wholesale on write**
    (PHASE_1_MODELS.md section 3). See :mod:`frappe_core.children`.
    """

    #: Filled in by build_serializer_class.
    child_table_spec: dict = {}

    def get_fields(self):
        fields = super().get_fields()
        for name in READ_ONLY_FIELDS:
            if name in fields:
                fields[name].read_only = True
        for fieldname, spec in (self.child_table_spec or {}).items():
            fields[fieldname] = _build_child_field(spec)
        return fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for fieldname, spec in (self.child_table_spec or {}).items():
            child_serializer = registry.get_entry(spec["doctype"]).get_serializer_class()
            data[fieldname] = child_serializer(
                children.read_children(instance, spec), many=True
            ).data
        return data

    def _pop_child_payloads(self, validated_data: dict) -> dict:
        """Remove child rows from ``validated_data`` before the model layer sees them.

        They are not model fields. Left in place, ``ModelSerializer.update`` treats the
        reverse accessor as a relation and calls ``field.set(rows)``, which raises
        because the rows are dicts, not instances.
        """
        payloads = {}
        for fieldname in self.child_table_spec or {}:
            if fieldname in validated_data:
                payloads[fieldname] = validated_data.pop(fieldname)
        return payloads

    def create(self, validated_data):
        payloads = self._pop_child_payloads(validated_data)
        instance = super().create(validated_data)
        self._write_children(instance, payloads)
        return instance

    def update(self, instance, validated_data):
        payloads = self._pop_child_payloads(validated_data)
        instance = super().update(instance, validated_data)
        self._write_children(instance, payloads)
        return instance

    def _write_children(self, instance, payloads):
        for fieldname, rows in payloads.items():
            children.replace_children(
                instance, fieldname, self.child_table_spec[fieldname], rows or []
            )


def _build_child_field(spec):
    """The *write* half of a child table.

    ``write_only`` matters: left readable, DRF would resolve the field to the reverse
    ``RelatedManager`` and fail to iterate it. Reads are served by
    :meth:`DocumentSerializer.to_representation`, which queries through
    ``children.read_children`` so the polymorphic and FK shapes look identical on the
    wire.

    Declared loosely on purpose: rows are filtered to the child model's concrete fields
    by ``children.replace_children``. A strict nested serializer here would duplicate
    that and force every phase-3 caller to send complete child rows.
    """
    return serializers.ListField(
        child=serializers.DictField(), required=False, write_only=True
    )


def build_serializer_class(model) -> type[DocumentSerializer]:
    """Generate a serializer exposing every concrete field on ``model``."""
    name_strategy = getattr(model, "get_name_strategy", lambda: None)()
    # `prompt` doctypes take `name` from the client on create, so it must be writable.
    name_writable = bool(name_strategy is not None and name_strategy.requires_client_name)

    # `exclude` rather than `fields="__all__"`: credential columns must never be
    # serialised. See frappe_core.field_security - `User` and `Email Account` are both
    # routable doctypes from phase 1 onwards.
    concrete = {f.name for f in model._meta.get_fields() if getattr(f, "concrete", False)}
    blocked = sorted(sensitive_fields(model) & concrete)
    meta_attrs: dict = {"model": model}
    if blocked:
        meta_attrs["exclude"] = tuple(blocked)
    else:
        meta_attrs["fields"] = "__all__"

    attrs: dict = {
        "Meta": type("Meta", (), meta_attrs),
        "child_table_spec": children.discover_child_tables(model),
    }

    if name_writable:
        # `name` is `editable=False` on the model, which makes DRF derive it as
        # read-only - so `extra_kwargs={"name": {"required": True}}` is silently
        # ignored and a `prompt` doctype can never receive its client-supplied name.
        # An explicitly declared field overrides the model-derived one.
        attrs["name"] = serializers.CharField(max_length=140, required=True, allow_blank=False)

    return type(f"{model.__name__}Serializer", (DocumentSerializer,), attrs)
