"""Explicit document serializers and their shared wire behavior."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _
from rest_framework import serializers

from core import children
from core.doctypes import doctype_of, is_single
from core.exceptions import DuplicateEntryError
from core.field_access import (
    hidden_from,
    readonly_fields,
    sensitive_fields,
    unwritable_by,
)
from core.naming import FieldValue, Prompt
from core.query import wire_json_text


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
    """Base for serializers whose ``Meta.fields`` is always explicit."""

    CHILD_TABLES = {}

    @property
    def user(self):
        if "user" not in self.context or self.context["user"] is None:
            raise TypeError(_("`user` is required in serializer context"))
        return self.context["user"]

    def _child_specs(self):
        return children.child_table_specs(self.Meta.model, self.CHILD_TABLES)

    def build_unknown_field(self, field_name, model_class):
        if field_name in self._child_specs():
            return serializers.ListField, {
                "child": serializers.DictField(),
                "required": False,
                "write_only": True,
            }
        return super().build_unknown_field(field_name, model_class)

    def get_fields(self):
        fields = super().get_fields()
        model = self.Meta.model

        for fieldname in self._child_specs():
            if fieldname in self.Meta.fields:
                fields[fieldname] = serializers.ListField(
                    child=serializers.DictField(), required=False, write_only=True
                )

        # An explicit list cannot make a credential readable. Silently excluding one
        # matches the old generated serializer and keeps one policy source on the model.
        for name in sensitive_fields(model):
            fields.pop(name, None)
        for name in set(READ_ONLY_FIELDS) | readonly_fields(model):
            if name in fields:
                fields[name].read_only = True
        for name in getattr(model, "AUTO_DEFAULTED_FIELDS", ()) or ():
            if name in fields:
                fields[name].required = False
                fields[name].allow_null = True

        strategy = getattr(model, "NAME_STRATEGY", None)
        if isinstance(strategy, Prompt) and "name" in fields:
            fields["name"] = serializers.CharField(
                max_length=140, required=True, allow_blank=False
            )
        return fields

    def to_internal_value(self, data):
        user = self.user
        if isinstance(data, dict):
            blank_for_none = {
                name
                for name, field in self.fields.items()
                if isinstance(field, (serializers.CharField, serializers.ChoiceField))
                and not field.allow_null
                and not field.read_only
            }
            dropped = unwritable_by(self.Meta.model, user)
            data = {
                key: "" if value is None and key in blank_for_none else value
                for key, value in data.items()
                if key not in dropped
            }
        return super().to_internal_value(data)

    def to_representation(self, instance):
        user = self.user
        data = super().to_representation(instance)
        data["doctype"] = doctype_of(type(instance))
        for fieldname in hidden_from(self.Meta.model, user):
            data.pop(fieldname, None)
        wire_json_text(data)

        for fieldname, spec in self._child_specs().items():
            if fieldname not in self.Meta.fields:
                continue
            rows = children.read_children(instance, spec)
            data[fieldname] = [self._represent_child(row) for row in rows]
        return data

    def _represent_child(self, instance):
        model = type(instance)
        field_names = tuple(
            field.name
            for field in model._meta.get_fields()
            if getattr(field, "concrete", False)
        )
        meta = type("Meta", (), {"model": model, "fields": field_names})
        serializer_class = type(
            f"{model.__name__}InlineSerializer",
            (DocumentSerializer,),
            {"Meta": meta},
        )
        return serializer_class(instance, context={"user": self.user}).data

    def _pop_child_payloads(self, validated_data):
        payloads = {}
        for fieldname in self._child_specs():
            if fieldname in validated_data:
                payloads[fieldname] = validated_data.pop(fieldname)
        return payloads

    def save(self, **kwargs):
        # ViewSets pass the actor both ways: context governs visibility during
        # validation, while save(user=...) makes the write call site explicit.
        supplied_user = kwargs.pop("user", self.user)
        if supplied_user != self.user:
            raise TypeError(_("Serializer user does not match context user"))
        return super().save(**kwargs)

    def create(self, validated_data):
        payloads = self._pop_child_payloads(validated_data)
        try:
            with transaction.atomic():
                instance = self.Meta.model(**validated_data)
                instance.save(user=self.user)
                if payloads:
                    self._write_children(instance, payloads)
                    instance.refresh_from_db()
                    instance.save(user=self.user)
        except IntegrityError as exc:
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
            for fieldname, value in validated_data.items():
                setattr(instance, fieldname, value)
            instance.save(user=self.user)
        return instance

    def _write_children(self, instance, payloads):
        specs = self._child_specs()
        for fieldname, rows in payloads.items():
            children.replace_children(
                instance,
                fieldname,
                specs[fieldname],
                rows or [],
                user=self.user,
            )


def _duplicate_name_error(model, validated_data):
    if is_single(model):
        value = doctype_of(model)
    else:
        strategy = getattr(model, "NAME_STRATEGY", None)
        if isinstance(strategy, FieldValue):
            value = validated_data.get(strategy.fieldname)
        elif isinstance(strategy, Prompt):
            value = validated_data.get("name")
        else:
            return None
    if hasattr(value, "pk"):
        value = value.pk
    name = ("" if value is None else str(value)).strip()
    if not name or not model._default_manager.filter(pk=name).exists():
        return None
    return DuplicateEntryError(
        _("{0} <strong>{1}</strong> already exists").format(
            doctype_of(model), name
        ),
        title=_("Duplicate Name"),
    )
