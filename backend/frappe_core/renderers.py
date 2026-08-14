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
    """A payload plus the key it should be wrapped in."""

    __slots__ = ("payload", "key")

    def __init__(self, payload, key: str = "data"):
        self.payload = payload
        self.key = key


class FrappeEnvelopeRenderer(JSONRenderer):
    """Wrap successful payloads; leave error bodies alone."""

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, Envelope):
            data = {data.key: data.payload}
        elif isinstance(data, dict) and _ERROR_KEYS & set(data):
            pass  # already a Frappe error body
        return super().render(data, accepted_media_type, renderer_context)
