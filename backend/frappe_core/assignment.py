"""``_assign`` <-> ``ToDo`` synchronisation.

PHASE_0_FOUNDATION.md section 3, the paragraph that starts "``_assign`` is the one that
catches people out".

**Assignment in Frappe is a ``ToDo`` record.** ``_assign`` is a denormalised cache of it
that the frontend reads directly. Phase 0 owns the mechanism; phase 1 cluster 1 owns the
``ToDo`` model and switches it on with one call::

    from frappe_core.assignment import register_todo_model

    @register_doctype("ToDo")
    class ToDo(BaseDocument):
        ...

    register_todo_model(ToDo)

After that, every ToDo write refreshes the parent's ``_assign``.

**Phase 2 must not read ``_assign``.** It is a cache, it can lag, and it is writable
through the generic resource endpoint. The permission layer queries ``ToDo`` directly -
PHASE_2_PERMISSIONS.md section 2.

### Two different "active" definitions, deliberately

The CRM source uses two different status filters, and they do not agree:

* ``crm/api/doc.py:608-625`` (``get_assigned_users``, what the UI shows as assignees)
  excludes **both** ``Closed`` and ``Cancelled``.
* ``PHASE_2_PERMISSIONS.md`` section 2 (the access-control clause) excludes
  **only** ``Cancelled`` - a closed assignment still grants access.

``_assign`` mirrors the first, because that is what it is a cache *of*. The permission
layer implements the second. A document can therefore grant access to someone who is
not listed in ``_assign``, which is precisely why the two must not share a source.
"""

from __future__ import annotations

import json

from django.db.models.signals import post_delete, post_save, pre_save

from frappe_core import registry

#: Statuses that keep a ToDo out of the ``_assign`` cache (``api/doc.py:615``).
INACTIVE_FOR_DISPLAY = ("Closed", "Cancelled")

#: Statuses that revoke access (PHASE_2_PERMISSIONS.md section 2). Phase 2 imports this
#: rather than re-deriving it.
INACTIVE_FOR_PERMISSION = ("Cancelled",)

_TODO_MODEL = None
_FIELDS = {
    "reference_type": "reference_type",
    "reference_name": "reference_name",
    "allocated_to": "allocated_to",
    "status": "status",
}


def get_todo_model():
    return _TODO_MODEL


def register_todo_model(model, **field_overrides) -> None:
    """Wire ToDo writes to the ``_assign`` cache. Called once, by phase 1 cluster 1."""
    global _TODO_MODEL
    _TODO_MODEL = model
    _FIELDS.update(field_overrides)

    pre_save.connect(_remember_previous_reference, sender=model, dispatch_uid="frappe_core.assign.pre")
    post_save.connect(_on_todo_write, sender=model, dispatch_uid="frappe_core.assign.save")
    post_delete.connect(_on_todo_write, sender=model, dispatch_uid="frappe_core.assign.delete")


def _reference_of(instance) -> tuple:
    return (
        getattr(instance, _FIELDS["reference_type"], None),
        getattr(instance, _FIELDS["reference_name"], None),
    )


def _remember_previous_reference(sender, instance, **kwargs):
    """Stash the reference this ToDo pointed at before the write.

    A ToDo can be *repointed* at a different document. Rebuilding only the new target
    would leave the old document advertising an assignee it no longer has - a stale
    cache that looks authoritative.
    """
    instance._previous_reference = None
    if instance._state.adding or instance.pk is None:
        return
    previous = (
        sender._default_manager.filter(pk=instance.pk)
        .values_list(_FIELDS["reference_type"], _FIELDS["reference_name"])
        .first()
    )
    if previous and previous != _reference_of(instance):
        instance._previous_reference = previous


def _on_todo_write(sender, instance, **kwargs):
    targets = {_reference_of(instance)}
    previous = getattr(instance, "_previous_reference", None)
    if previous:
        targets.add(previous)
    for reference_type, reference_name in targets:
        if reference_type and reference_name:
            rebuild_assign_cache(reference_type, reference_name)
    instance._previous_reference = None


def get_assigned_users(doctype: str, name, *, for_permission: bool = False) -> list[str]:
    """Users assigned to a document, read from ``ToDo`` - never from ``_assign``.

    ``for_permission=True`` applies the access-control status filter (Cancelled only)
    instead of the display one (Closed and Cancelled).
    """
    if _TODO_MODEL is None:
        return []
    excluded = INACTIVE_FOR_PERMISSION if for_permission else INACTIVE_FOR_DISPLAY
    rows = (
        _TODO_MODEL._default_manager.filter(
            **{
                _FIELDS["reference_type"]: doctype,
                _FIELDS["reference_name"]: name,
            }
        )
        .exclude(**{f"{_FIELDS['status']}__in": excluded})
        .values_list(_FIELDS["allocated_to"], flat=True)
    )
    # dict.fromkeys rather than set(): assignment order is stable in the UI.
    return [u for u in dict.fromkeys(rows) if u]


def rebuild_assign_cache(doctype: str, name) -> list[str] | None:
    """Recompute one document's ``_assign`` from its ToDo rows."""
    if not registry.has_doctype(doctype):
        return None
    model = registry.get_model(doctype)
    if not hasattr(model, "_assign"):
        return None

    users = get_assigned_users(doctype, name)
    # update() rather than save(): this is a cache refresh, not a document edit, so it
    # must not bump `modified` or re-stamp `modified_by`.
    model._default_manager.filter(pk=name).update(_assign=users)
    return users


def parse_assign(value) -> list[str]:
    """Read an ``_assign`` value that may be a JSON string (Frappe) or a list (here)."""
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []
