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
                )
            )


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
                )
            )


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
    """The delete itself, after the rules: refused by a dynamic link still naming it."""
    check_dynamic_links(document)
    document.delete()
