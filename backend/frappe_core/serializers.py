"""Generated serializers.

One ``ModelSerializer`` per doctype, built on demand and cached on the registry entry.
Phase-1 agents override by passing ``serializer_class=`` to ``register_doctype`` when a
doctype needs nested child tables or a computed field.

Link fields serialise to their raw key (an email for User, the string PK elsewhere),
which is what Frappe puts on the wire and what the frontend's Link controls expect.
DRF's default ``PrimaryKeyRelatedField`` already does exactly that.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from rest_framework import serializers

from frappe_core import children, registry
from frappe_core import naming as naming_strategies
from frappe_core.exceptions import DuplicateEntryError
from frappe_core.field_security import hidden_from, readonly_fields, restricted_fields, sensitive_fields

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
        # A field the model fills in on save must not be *required* on the way in.
        # `CRMLead.status` is the case that surfaced this: phase 1 ported upstream's
        # `validate_status`, which defaults it on create, but DRF validates before the
        # model runs - so every API-created lead was rejected with "status is required"
        # while direct ORM creates worked. Declaring it here keeps the two paths in step.
        for name in getattr(self.Meta.model, "AUTO_DEFAULTED_FIELDS", ()) or ():
            if name in fields:
                fields[name].required = False
                fields[name].allow_null = True
        for fieldname, spec in (self.child_table_spec or {}).items():
            fields[fieldname] = _build_child_field(spec)
        return fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Restricted fields are dropped here rather than excluded when the class is
        # built, because the class is built once per model and cached on the registry
        # entry - it cannot know who is asking. `hidden_from` re-checks the sensitive set
        # too, which is redundant (those are already excluded from Meta) and costs a set
        # union; keeping it means one function answers "may this user see this field?"
        # instead of two that can drift.
        if restricted_fields(self.Meta.model):
            for fieldname in hidden_from(self.Meta.model):
                data.pop(fieldname, None)
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

    # Upstream validates a document together with its child rows in one pass, so a
    # save that adds product lines answers with the new expected value, and a save that
    # adds a contact row answers with that contact primary and its email copied onto
    # the deal (crm_deal.py:120-149, 240-248). Here the rows are written **before** the
    # parent's save on update, and on create - where the parent must exist first so the
    # rows have something to point at - the parent is saved again once they do, so the
    # derivations that read them run in the same request (FINDINGS.md 8). Atomic, so
    # a parent-level refusal takes the rows written before it back with it.

    # After the rows are written the parent is re-read: a child row's own save may have
    # updated columns on the parent directly (the product rows keep the lead's and
    # deal's totals with a bare ``update()``), and saving the stale in-memory parent
    # afterwards would write the old values back over them.

    def create(self, validated_data):
        payloads = self._pop_child_payloads(validated_data)
        try:
            with transaction.atomic():
                instance = super().create(validated_data)
                if payloads:
                    self._write_children(instance, payloads)
                    instance.refresh_from_db()
                    instance.save()
        except IntegrityError as exc:
            # Outside the savepoint, which has been rolled back, so the lookup below can
            # run. `base_document.py:598-606`: the unique-key error on insert becomes
            # "<DocType> <strong>name</strong> already exists" (FINDINGS.md 25). Any other
            # integrity error is not a duplicate name and keeps its own text.
            duplicate = _duplicate_name_error(self.Meta.model, validated_data)
            if duplicate is not None:
                raise duplicate from exc
            raise
        return instance

    def update(self, instance, validated_data):
        payloads = self._pop_child_payloads(validated_data)
        with transaction.atomic():
            if payloads:
                self._write_children(instance, payloads)
                instance.refresh_from_db()
            instance = super().update(instance, validated_data)
        return instance

    def _write_children(self, instance, payloads):
        for fieldname, rows in payloads.items():
            children.replace_children(
                instance, fieldname, self.child_table_spec[fieldname], rows or []
            )


def _duplicate_name_error(model, validated_data) -> DuplicateEntryError | None:
    """The name a failed insert attempted, and upstream's refusal when it is taken.

    The insert raised before returning an instance, so the name is worked out the way
    the strategy would have: the naming field's value for a ``field:`` doctype, the
    client's ``name`` for a ``prompt`` one, ``Settings`` for a singleton. Hash and
    series names cannot realistically collide, so for those - and whenever no row of
    the attempted name exists - this returns ``None`` and the caller re-raises the
    original error with its own text.
    """
    if model.is_single():
        value = "Settings"
    else:
        strategy = model.get_name_strategy()
        if isinstance(strategy, naming_strategies.FieldValue):
            value = validated_data.get(strategy.fieldname)
        elif isinstance(strategy, naming_strategies.Prompt):
            value = validated_data.get("name")
        else:
            return None
    if hasattr(value, "pk"):
        value = value.pk
    name = ("" if value is None else str(value)).strip()
    if not name or not model._default_manager.filter(pk=name).exists():
        return None
    return DuplicateEntryError(
        f"{model.get_doctype()} <strong>{name}</strong> already exists", title="Duplicate Name"
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

    # Readable, never writable - see `field_security.readonly_fields`. Subtracting
    # `blocked` matters: DRF raises if `extra_kwargs` names a field the serializer does
    # not have, and a field can legitimately be listed in both attributes on a model
    # whose author wanted "hidden, and definitely not writable".
    read_only = sorted((readonly_fields(model) & concrete) - set(blocked))
    if read_only:
        meta_attrs["extra_kwargs"] = {name: {"read_only": True} for name in read_only}

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
