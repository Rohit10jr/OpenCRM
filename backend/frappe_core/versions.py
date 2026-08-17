"""Field-change history - a deliberately narrowed port of Frappe's ``Version``.

Upstream records **every** changed field on every save of a doctype with
``track_changes=1`` (``frappe/model/document.py:1310-1331``), and
``crm/api/activities.py:68-95`` turns those rows into the "Sarah changed Deal Value
£50,000 → £80,000" entries in a record's timeline.

``track_changes=1`` is set on **CRM Lead, CRM Deal and FCRM Note**, so upstream really
does show these. Our timeline showed creation, status changes, comments, emails, calls,
notes, tasks and attachments - but not field edits, so a deal's value could change with
no record of who did it.

### What this port does differently, and why

**Upstream tracks every field. This tracks a declared list per model**
(:attr:`TRACKED_FIELDS`).

Full parity would mean one extra INSERT on *every* save, forever, with no cleanup - and
a timeline entry each time somebody fixes a typo in a description. The narrowed list
keeps the entries a manager would actually ask about ("who raised this to £80k?", "who
took this deal off Sarah?") without logging every correction.

**Recorded so the difference is not mistaken for an oversight: upstream also logs
description edits, and every other field.** The list below is a product decision, not a
gap in the port. Widening it is a one-line change per model; the mechanism is the same.

Status changes are **not** in the list: they already reach the timeline through the
ported ``CRM Status Change Log``, which carries a duration per transition that a version
row cannot. Tracking them here would double every status entry.

Also faithful: upstream skips a change where both old and new are empty, and excludes
its own SLA plumbing (``crm/api/activities.py:33-40``). Those exclusions are inherited
by only ever looking at :attr:`TRACKED_FIELDS` in the first place.
"""

from __future__ import annotations

import json

from django.db import models

from frappe_core.models import BaseDocument
from frappe_core.naming import Hash
from frappe_core.registry import register_doctype
from frappe_core.session import get_current_user


@register_doctype("Version")
class Version(BaseDocument):
    """``frappe/core/doctype/version/version.json``.

    ``data`` holds Frappe's JSON shape - ``{"changed": [[field, old, new], ...]}`` - so
    a later widening to full parity is a change of *what* is written, not of the schema
    or of anything reading it.
    """

    ref_doctype = models.CharField(max_length=140, db_index=True)
    docname = models.CharField(max_length=140, db_index=True)
    data = models.TextField(blank=True, default="{}")

    class Meta:
        ordering = ["creation"]
        # ``autoname: hash`` in version.json - a version row has no natural key.
        name_strategy = Hash()
        indexes = [
            models.Index(fields=["ref_doctype", "docname"], name="version_ref_idx"),
        ]

    def changes(self) -> list[list]:
        try:
            return json.loads(self.data or "{}").get("changed", [])
        except (ValueError, TypeError):  # pragma: no cover - defensive
            return []


def _display_value(instance, fieldname):
    """The stored value, as the wire carries it.

    Foreign keys read through ``<name>_id`` so the entry records the key the frontend
    routes on, not a repr of a model instance.
    """
    field = instance._meta.get_field(fieldname)
    if field.is_relation:
        return getattr(instance, f"{fieldname}_id", None)
    return getattr(instance, fieldname, None)


def capture_tracked_values(instance) -> dict:
    """Snapshot the tracked fields. Called from ``from_db`` so it costs no extra query."""
    tracked = getattr(type(instance), "TRACKED_FIELDS", ()) or ()
    return {name: _display_value(instance, name) for name in tracked}


def record_version(instance, previous: dict | None) -> "Version | None":
    """Write one row for this save, or ``None`` when nothing tracked changed.

    ``previous`` is the snapshot taken when the instance was loaded. On create it is
    ``None`` and nothing is written: the timeline already has a "created" entry, and
    upstream's diff against a non-existent prior document produces no ``changed`` list
    either.
    """
    tracked = getattr(type(instance), "TRACKED_FIELDS", ()) or ()
    if not tracked or previous is None:
        return None

    changed = []
    for name in tracked:
        old = previous.get(name)
        new = _display_value(instance, name)
        if old == new:
            continue
        # Upstream skips a change where both sides are empty - "" to None is not an
        # edit anyone wants to read (crm/api/activities.py:76).
        if not old and not new:
            continue
        changed.append([name, _stringify(old), _stringify(new)])

    if not changed:
        return None

    return Version.objects.create(
        ref_doctype=type(instance).get_doctype(),
        docname=str(instance.pk),
        data=json.dumps({"changed": changed}),
        owner_id=get_current_user(),
    )


def _stringify(value):
    """Versions store display values, so a Decimal or date survives the JSON round trip."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def versions_for(doctype: str, name) -> list["Version"]:
    return list(
        Version.objects.filter(ref_doctype=doctype, docname=str(name)).order_by("creation")
    )
