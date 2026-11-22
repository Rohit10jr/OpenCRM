"""Checks which must run before a document is deleted."""

from django.apps import apps

from core.doctypes import doctype_of, is_child_table, model_for_doctype
from core.exceptions import LinkExistsError, link_exists_message
from core.translate import _


IGNORE_LINKS_ON_DELETE = frozenset(
    {
        "Activity Log",
        "Comment",
        "Communication",
        "DocShare",
        "Document Follow",
        "Email Unsubscribe",
        "Failed Lead Sync Log",
        "File",
        "Notification Log",
        "Tag Link",
        "ToDo",
        "Version",
        "View Log",
    }
)


def _dynamic_link_declarations(model):
    """Yield ``(doctype field, name field)`` pairs explicitly declared by a model."""

    for declaration in getattr(model, "DYNAMIC_LINK_FIELDS", ()) or ():
        if isinstance(declaration, str):
            yield "reference_doctype", declaration
        else:
            yield tuple(declaration)


def check_dynamic_links(instance) -> None:
    """Refuse deletion while a declared dynamic link names ``instance``."""

    target_doctype = doctype_of(type(instance))
    # Resolve through declarations, rather than assuming the target model was imported.
    if model_for_doctype(target_doctype) is None:
        return

    for model in apps.get_models():
        reference_doctype = doctype_of(model)
        if reference_doctype in IGNORE_LINKS_ON_DELETE:
            continue
        for doctype_field, name_field in _dynamic_link_declarations(model):
            rows = model._default_manager.filter(
                **{
                    doctype_field: target_doctype,
                    name_field: str(instance.pk),
                }
            )
            if any(field.name == "docstatus" for field in model._meta.concrete_fields):
                rows = rows.exclude(docstatus=2)
            row = rows.order_by("pk").first()
            if row is None:
                continue
            fields = {field.name for field in type(instance)._meta.get_fields()}
            if "enabled" in fields or "disabled" in fields:
                raise LinkExistsError(
                    _("You can disable this {0} instead of deleting it.").format(
                        target_doctype
                    )
                )
            if is_child_table(model):
                parent = getattr(row, "parent", "")
                if hasattr(parent, "pk"):
                    parent = parent.pk
                reference_doctype = str(
                    getattr(row, "parenttype", "") or reference_doctype
                )
                reference_name = str(parent or row.pk)
            else:
                reference_name = str(row.pk)
            raise LinkExistsError(
                link_exists_message(
                    target_doctype,
                    str(instance.pk),
                    reference_doctype,
                    reference_name,
                    _row_position(model, row),
                )
            )


def _row_position(model, row) -> str:
    """The old `at_position` (`backend/frappe_core/delete_doc.py:137`): a child-table
    row names its place in its parent's table."""
    return f"at Row: {row.idx}" if is_child_table(model) else ""


def check_dynamic_links_batch(instances) -> None:
    """Refuse a batch using one query per declared dynamic-link field."""
    instances = list(instances)
    if not instances:
        return
    target_model = type(instances[0])
    target_doctype = doctype_of(target_model)
    targets = {str(instance.pk): instance for instance in instances}
    if model_for_doctype(target_doctype) is None:
        return

    for model in apps.get_models():
        reference_doctype = doctype_of(model)
        if reference_doctype in IGNORE_LINKS_ON_DELETE:
            continue
        for doctype_field, name_field in _dynamic_link_declarations(model):
            rows = model._default_manager.filter(
                **{
                    doctype_field: target_doctype,
                    f"{name_field}__in": targets,
                }
            )
            if any(field.name == "docstatus" for field in model._meta.concrete_fields):
                rows = rows.exclude(docstatus=2)
            row = rows.order_by("pk").first()
            if row is None:
                continue
            target_name = str(getattr(row, name_field))
            fields = {field.name for field in target_model._meta.get_fields()}
            if "enabled" in fields or "disabled" in fields:
                raise LinkExistsError(
                    _("You can disable this {0} instead of deleting it.").format(
                        target_doctype
                    )
                )
            if is_child_table(model):
                parent = getattr(row, "parent", "")
                if hasattr(parent, "pk"):
                    parent = parent.pk
                reference_doctype = str(
                    getattr(row, "parenttype", "") or reference_doctype
                )
                reference_name = str(parent or row.pk)
            else:
                reference_name = str(row.pk)
            raise LinkExistsError(
                link_exists_message(
                    target_doctype,
                    target_name,
                    reference_doctype,
                    reference_name,
                    _row_position(model, row),
                )
            )


#: Standard stamps, not links a delete is refused by (upstream's `check_if_doc_is_linked`
#: skips `owner` and `modified_by` the same way: they are not Link fields in a doctype).
_STAMP_FIELDS = frozenset({"owner", "modified_by"})


def _static_link_fields(target_model):
    """`(referencing model, column)` for each declared text Link and each PROTECT
    foreign key to `target_model`, singletons included; no query."""
    from django.db import models as django_models

    for model in apps.get_models():
        if doctype_of(model) in IGNORE_LINKS_ON_DELETE:
            continue
        # Fields that deliberately keep a deleted target's name (AS_BUILT §2) never
        # refuse its delete (A-79 finding 1).
        dangling = set(getattr(model, "ALLOW_DANGLING_LINK_FIELDS", ()) or ())
        for fieldname, (label, _label_text) in (getattr(model, "TEXT_LINK_FIELDS", None) or {}).items():
            if fieldname not in dangling and apps.get_model(label) is target_model:
                yield model, fieldname
        for field in model._meta.concrete_fields:
            remote = getattr(field, "remote_field", None)
            if (
                remote is not None
                and field.name not in _STAMP_FIELDS
                and remote.model is target_model
                and getattr(remote, "on_delete", None) is django_models.PROTECT
            ):
                yield model, field.attname


def check_static_links_batch(instances) -> None:
    """CONTACTS §11.3 (owner, temp A-48 6.3, A-74): refuse a delete while a text Link or
    a PROTECT foreign key still names one of `instances`, before the dynamic links, as
    upstream's `check_if_doc_is_linked` runs before `check_if_doc_is_dynamically_linked`
    (v15 `frappe/model/delete_doc.py:141-153`). One query per link column, whatever the
    batch size. A record with `enabled` or `disabled` answers "You can disable this {0}
    instead of deleting it.", as upstream does for either link kind."""
    instances = list(instances)
    if not instances:
        return
    target_model = type(instances[0])
    target_doctype = doctype_of(target_model)
    names = [str(instance.pk) for instance in instances]
    for model, column in _static_link_fields(target_model):
        rows = model._default_manager.filter(**{f"{column}__in": names})
        if model is target_model:
            # Upstream skips a document linking to itself (v15 delete_doc.py:329); in a
            # batch, links among the batch's own records do not refuse it (A-79 finding 4).
            rows = rows.exclude(pk__in=names)
        row = rows.order_by("pk").first()
        if row is None:
            continue
        fields = {field.name for field in target_model._meta.get_fields()}
        if "enabled" in fields or "disabled" in fields:
            raise LinkExistsError(
                _("You can disable this {0} instead of deleting it.").format(target_doctype)
            )
        if is_child_table(model):
            from core.exceptions import _child_parent_name

            reference_doctype = str(getattr(row, "parenttype", "") or doctype_of(model))
            reference_name = _child_parent_name(row) or str(row.pk)
        else:
            reference_doctype, reference_name = doctype_of(model), str(row.pk)
        if reference_doctype == reference_name:
            # Upstream names a Single once: its doctype is dropped when it equals the
            # name (v15 delete_doc.py:447-449).
            reference_doctype = ""
        # No row position: upstream's check_if_doc_is_linked passes none (v15
        # delete_doc.py:349-352); only the dynamic check does (A-79 finding 2).
        raise LinkExistsError(
            link_exists_message(
                target_doctype,
                str(getattr(row, column)),
                reference_doctype,
                reference_name,
            )
        )


def check_static_links(instance) -> None:
    check_static_links_batch([instance])


def may_delete(rules, user, document) -> bool:
    """Whether the record route would let `user` delete `document`: its resource is a
    routed document ViewSet that serves DELETE, and the object rule does not refuse. A
    doctype ruled only through `ROW_RULES` has no record route, so it is never deleted
    this way. The record route and the shared actions' linked delete both ask this
    (PE-26), so they cannot drift."""
    from core.views import DocumentViewSet

    if not (isinstance(rules, type) and issubclass(rules, DocumentViewSet)):
        return False
    if "delete" not in (getattr(rules, "http_method_names", ()) or ()):
        return False
    return rules.has_object_rule(user, document, "delete") is not False


def delete_document(document) -> None:
    """The delete itself, after the rules: refused by a static, then a dynamic, link
    still naming it."""
    check_static_links(document)
    check_dynamic_links(document)
    document.delete()
