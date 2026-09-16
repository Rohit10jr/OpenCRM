"""Response envelope.

PORT_PLAN.md section 3, a hard external contract:

* ``/api/resource/*`` -> ``{"data": ...}``
* ``/api/method/*``   -> ``{"message": ...}``

Views return their bare payload wrapped in :class:`Envelope`; the renderer applies the
key. Error bodies (see ``exceptions.py``) are already in Frappe's shape and pass
through untouched, because the frontend reads ``exc_type`` / ``_server_messages`` off
the top level rather than out of an envelope.
"""

from __future__ import annotations

from rest_framework.renderers import JSONRenderer

#: Marker keys that identify an already-shaped error body.
_ERROR_KEYS = {"exc_type", "_server_messages"}


class Envelope:
    """A payload plus the key it should be wrapped in, and any sibling keys that sit
    beside it at the top level."""

    __slots__ = ("payload", "key", "extra")

    def __init__(self, payload, key: str = "data", extra: dict | None = None):
        self.payload = payload
        self.key = key
        self.extra = extra or {}


class WithResponseKeys:
    """What a whitelisted method returns when upstream also writes to ``frappe.response``:
    its ``message`` plus sibling keys at the top level. ``getdoctype`` is the case that
    needs it - it puts ``docs`` and ``user_settings`` beside ``message``, and frappe-ui
    hands the whole body to the caller whenever ``docs`` is present
    (``frappe-ui/src/utils/frappeRequest.ts:92``)."""

    __slots__ = ("message", "keys")

    def __init__(self, message=None, **keys):
        self.message = message
        self.keys = keys


class FrappeEnvelopeRenderer(JSONRenderer):
    """Wrap successful payloads; leave error bodies alone."""

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, Envelope):
            data = {data.key: data.payload, **data.extra}
        elif isinstance(data, dict) and _ERROR_KEYS & set(data):
            pass  # already a Frappe error body
        return super().render(data, accepted_media_type, renderer_context)
