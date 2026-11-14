"""Tracked-field change history."""

from __future__ import annotations

import json

from core.doctypes import doctype_of
from core.models import Version


def _display_value(instance, fieldname):
    field = instance._meta.get_field(fieldname)
    if field.is_relation:
        return getattr(instance, field.attname, None)
    return getattr(instance, fieldname, None)


def capture_tracked_values(instance) -> dict:
    """Snapshot declared tracked fields without an extra database query."""
    tracked = getattr(type(instance), "TRACKED_FIELDS", ()) or ()
    return {name: _display_value(instance, name) for name in tracked}


def _stringify(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def record_version(instance, before: dict | None, user) -> Version | None:
    """Record one row when this save changed at least one tracked field."""
    tracked = getattr(type(instance), "TRACKED_FIELDS", ()) or ()
    if not tracked or before is None:
        return None

    changed = []
    for name in tracked:
        old = before.get(name)
        new = _display_value(instance, name)
        if old == new or (not old and not new):
            continue
        changed.append([name, _stringify(old), _stringify(new)])

    if not changed:
        return None

    version = Version(
        ref_doctype=doctype_of(type(instance)),
        docname=str(instance.pk),
        data=json.dumps({"changed": changed}),
    )
    version.save(user=user)
    return version


def versions_for(doctype: str, name) -> list[Version]:
    return list(
        Version.objects.filter(ref_doctype=doctype, docname=str(name)).order_by(
            "creation"
        )
    )
